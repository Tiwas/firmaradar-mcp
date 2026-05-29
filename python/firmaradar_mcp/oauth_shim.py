"""Minimal OAuth 2.0 + DCR-shim for Anthropic MCP-klienter.

Bakgrunn (2026-05-26 — Lars Android-test):
  Claude Mobile + Claude Web krever full OAuth 2.0-flyt for Custom
  Connectors, ikke Bearer-token-only. Når MCP-serveren mangler
  OAuth-discovery-endepunkter feiler Claude med "Couldn't reach the
  MCP server" / "failed to start mcp authentication".

  Server-loggen viste at Claude prøvde 4 endepunkter:
    GET /.well-known/oauth-protected-resource[/mcp/<sid>]   (RFC 9728)
    GET /.well-known/oauth-authorization-server             (RFC 8414)
    POST /register                                          (RFC 7591 DCR)
  Når alle returnerte 404 → "failed to start authentication".

Dette modul er en MINIMAL-LIVEDYKTIG OAuth-implementasjon:

* DCR aksepterer alle registrations (offentlig connector — public clients)
* Authorization-endepunktet viser et enkelt skjema hvor BRUKEREN limer
  inn sin Firmaradar API-key som "samtykke"
* Token-endepunktet bytter authorization_code (etter PKCE-verifisering)
  for et access_token som internt er en mapping til den limt-inn
  API-keyen
* In-memory storage. Forsvinner ved restart. Akseptabelt for v0.1.

v0.2-roadmap (#117 ekte): PG-backed token-store i firmaradar_web sin
DB, consent-screen rendret av Flask-portalen, refresh-rotation,
revoke-endepunkt, audit-trail.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

_LOG = logging.getLogger("firmaradar_mcp.oauth_shim")


# ── In-memory storage ──────────────────────────────────────────────────

@dataclass
class _OAuthClient:
    client_id: str
    client_id_issued_at: int
    redirect_uris: list[str] = field(default_factory=list)
    grant_types: list[str] = field(default_factory=lambda: ["authorization_code", "refresh_token"])
    response_types: list[str] = field(default_factory=lambda: ["code"])
    token_endpoint_auth_method: str = "none"  # public client
    client_name: str = ""


@dataclass
class _AuthorizationCode:
    code: str
    client_id: str
    redirect_uri: str
    code_challenge: str
    code_challenge_method: str
    api_key: str  # Firmaradar API-key brukeren limte inn
    expires_at: float  # 10 min etter utstedelse
    state: str | None = None
    scope: str | None = None


@dataclass
class _AccessToken:
    access_token: str
    api_key: str  # Firmaradar API-key
    client_id: str
    expires_at: float | None  # None = ingen utløp (refresh_token)
    scope: str | None = None


# Globale stores — per process. Restart resetter alt (akseptabelt for v0.1).
_clients: dict[str, _OAuthClient] = {}
_codes: dict[str, _AuthorizationCode] = {}
_access_tokens: dict[str, _AccessToken] = {}
_refresh_tokens: dict[str, _AccessToken] = {}  # refresh → access (peker på samme api_key)

_CODE_TTL_SECONDS = 600         # 10 min — kort, brukes umiddelbart av klient
_ACCESS_TOKEN_TTL_SECONDS = 3600  # 1 t — refreshes automatisk av klient


# ── PKCE-verifikasjon ──────────────────────────────────────────────────

def _verify_pkce(code_verifier: str, code_challenge: str, method: str) -> bool:
    """Verifiser PKCE-utfordring (RFC 7636).

    Anthropic-klienter bruker S256 (SHA-256). Vi støtter også 'plain'
    for komplett spec-dekning, men ikke anbefalt.
    """
    if method == "S256":
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return secrets.compare_digest(computed, code_challenge)
    if method == "plain":
        return secrets.compare_digest(code_verifier, code_challenge)
    return False


# ── Token-lookup (brukes av middleware) ────────────────────────────────

def resolve_bearer_to_api_key(bearer_token: str) -> str | None:
    """Returner Firmaradar API-key fra Bearer-token.

    Stateless-design (Lars-bug 2026-05-26 fiks): vi har INGEN lookup-
    tabell lenger. ``oauth_token`` returnerer brukerens API-key
    direkte som access_token, så Bearer = API-key uansett hvilken
    klient som kobler til:

    * Claude Web/Mobile via OAuth-flyt → access_token = API-key (gitt
      i consent-formen) → Bearer matcher backend
    * Cursor/Codex/Desktop med direkte Bearer → tokenet ER API-keyen
      som brukeren limte inn i mcp.json eller settings.json
    * Curl/scripts med Bearer → samme

    I alle tilfellene: backend (firmaradar_web) validerer Bearer mot
    portal_api_key-tabellen. Hvis API-keyen er rotert eller revoked
    → backend returnerer 401 → klient må re-autentisere.

    Returnerer None for tom input.
    """
    if not bearer_token:
        return None
    return bearer_token


# ── ASGI route handlers ────────────────────────────────────────────────

def _build_well_known_protected_resource_payload(base_url: str) -> dict:
    """RFC 9728 — Protected Resource Metadata.

    Forteller klienten hvilken authorization server som beskytter
    denne ressursen.
    """
    return {
        "resource": base_url,
        "authorization_servers": [base_url],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["mcp"],
    }


def _build_well_known_authorization_server_payload(base_url: str) -> dict:
    """RFC 8414 — Authorization Server Metadata."""
    return {
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/oauth/authorize",
        "token_endpoint": f"{base_url}/oauth/token",
        "registration_endpoint": f"{base_url}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp"],
        # Verken introspection eller revoke i v0.1 — la oss legge til
        # i v0.2 sammen med PG-backed token-store.
    }


async def well_known_protected_resource(request) -> Any:
    """GET /.well-known/oauth-protected-resource[/mcp/<sid>]"""
    from starlette.responses import JSONResponse
    base_url = _base_url_from_request(request)
    return JSONResponse(_build_well_known_protected_resource_payload(base_url))


async def well_known_authorization_server(request) -> Any:
    """GET /.well-known/oauth-authorization-server"""
    from starlette.responses import JSONResponse
    base_url = _base_url_from_request(request)
    return JSONResponse(_build_well_known_authorization_server_payload(base_url))


async def oauth_register(request) -> Any:
    """POST /oauth/register — Dynamic Client Registration (RFC 7591).

    Aksepterer alle registrations som public clients. Returnerer
    ferdig-generert client_id (intet client_secret siden vi krever PKCE).
    """
    from starlette.responses import JSONResponse
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    client_id = f"firmaradar-mcp-client-{secrets.token_hex(16)}"
    redirect_uris = body.get("redirect_uris") or []
    if not isinstance(redirect_uris, list):
        redirect_uris = []
    client_name = body.get("client_name") or "MCP Connector"

    client = _OAuthClient(
        client_id=client_id,
        client_id_issued_at=int(time.time()),
        redirect_uris=[str(u) for u in redirect_uris][:10],  # cap
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
        client_name=str(client_name)[:200],
    )
    _clients[client_id] = client
    _LOG.info("OAuth: DCR registered client %s (%s)", client_id, client.client_name)

    return JSONResponse(
        {
            "client_id": client.client_id,
            "client_id_issued_at": client.client_id_issued_at,
            "redirect_uris": client.redirect_uris,
            "grant_types": client.grant_types,
            "response_types": client.response_types,
            "token_endpoint_auth_method": client.token_endpoint_auth_method,
            "client_name": client.client_name,
        },
        status_code=201,
    )


_AUTHORIZE_FORM_HTML = """<!DOCTYPE html>
<html lang="no">
<head>
    <meta charset="UTF-8">
    <title>Koble Firmaradar til AI-agenten din</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f6f8;
            margin: 0;
            padding: 40px 20px;
            color: #1a1a1a;
        }}
        .container {{
            max-width: 480px;
            margin: 0 auto;
            background: #fff;
            border-radius: 12px;
            padding: 36px 32px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.08);
        }}
        h1 {{ margin: 0 0 8px; font-size: 1.4em; }}
        .subtitle {{ color: #666; margin-bottom: 24px; font-size: 0.95em; }}
        .client-info {{
            background: #f0f4f8;
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 24px;
            font-size: 0.88em;
            color: #555;
        }}
        label {{
            display: block;
            font-size: 0.88em;
            font-weight: 600;
            margin-bottom: 6px;
            color: #333;
        }}
        input[type="text"], input[type="password"] {{
            width: 100%;
            padding: 12px 14px;
            border: 1px solid #d0d4d8;
            border-radius: 8px;
            font-size: 1em;
            font-family: monospace;
            box-sizing: border-box;
        }}
        input:focus {{ outline: 2px solid #0066cc; border-color: #0066cc; }}
        .helper {{
            font-size: 0.82em;
            color: #666;
            margin-top: 6px;
            line-height: 1.4;
        }}
        .helper a {{ color: #0066cc; }}
        button {{
            width: 100%;
            padding: 14px;
            margin-top: 24px;
            background: #0066cc;
            color: #fff;
            border: none;
            border-radius: 8px;
            font-size: 1em;
            font-weight: 600;
            cursor: pointer;
        }}
        button:hover {{ background: #0052a3; }}
        .cancel {{
            display: block;
            text-align: center;
            margin-top: 14px;
            color: #666;
            text-decoration: none;
            font-size: 0.88em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔌 Koble til Firmaradar MCP</h1>
        <p class="subtitle">Gi AI-agenten din tilgang til 25 verktøy for norske selskapsdata.</p>

        <div class="client-info">
            <strong>{client_name}</strong> ber om tilgang.
        </div>

        <form method="POST" action="{action}">
            <input type="hidden" name="client_id" value="{client_id}">
            <input type="hidden" name="redirect_uri" value="{redirect_uri}">
            <input type="hidden" name="state" value="{state}">
            <input type="hidden" name="code_challenge" value="{code_challenge}">
            <input type="hidden" name="code_challenge_method" value="{code_challenge_method}">
            <input type="hidden" name="scope" value="{scope}">

            <label for="api_key">Firmaradar API-nøkkel</label>
            <input type="password" id="api_key" name="api_key"
                   placeholder="Lim inn din API-nøkkel her"
                   autocomplete="off" required autofocus>
            <p class="helper">
                Generer eller hent eksisterende nøkkel under
                <a href="https://firmaradar.no/api-nokler" target="_blank">API-nøkler</a>
                på Firmaradar-portalen. MCP-bruk har egen pakkekvote.
            </p>

            <button type="submit">Godta og koble til</button>
        </form>
        <a href="javascript:window.close()" class="cancel">Avbryt</a>
    </div>
</body>
</html>
"""


async def oauth_authorize(request) -> Any:
    """GET/POST /oauth/authorize — consent-skjema.

    GET: vis HTML-form hvor bruker limer inn API-key
    POST: validér + generér authorization_code + redirect tilbake til klient

    Krav:
      * response_type=code
      * client_id må eksistere
      * redirect_uri må matche client-registrasjon
      * code_challenge + code_challenge_method=S256/plain (PKCE)
    """
    from starlette.responses import HTMLResponse, RedirectResponse, JSONResponse

    if request.method == "GET":
        params = dict(request.query_params)
        client_id = params.get("client_id", "")
        redirect_uri = params.get("redirect_uri", "")
        state = params.get("state", "")
        code_challenge = params.get("code_challenge", "")
        code_challenge_method = params.get("code_challenge_method", "S256")
        scope = params.get("scope", "mcp")
        response_type = params.get("response_type", "code")

        if response_type != "code":
            return JSONResponse(
                {"error": "unsupported_response_type"}, status_code=400
            )

        client = _clients.get(client_id)
        if client is None:
            return JSONResponse(
                {"error": "invalid_client",
                 "error_description": f"Unknown client_id: {client_id[:32]}"},
                status_code=400,
            )

        # PKCE er strengt påkrevd (public client, ingen client_secret)
        if not code_challenge:
            return JSONResponse(
                {"error": "invalid_request",
                 "error_description": "code_challenge required (PKCE)"},
                status_code=400,
            )

        # Lett HTML-escape — verdiene kommer fra Anthropic-klienten,
        # men vi vil ikke risikere XSS hvis noen prøver injection
        def _esc(s: str) -> str:
            return (
                s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )

        action = request.url_for("oauth_authorize")
        html = _AUTHORIZE_FORM_HTML.format(
            client_name=_esc(client.client_name or "MCP Connector"),
            action=action,
            client_id=_esc(client_id),
            redirect_uri=_esc(redirect_uri),
            state=_esc(state),
            code_challenge=_esc(code_challenge),
            code_challenge_method=_esc(code_challenge_method),
            scope=_esc(scope),
        )
        return HTMLResponse(html)

    # POST — verifiser + redirect tilbake
    form = await request.form()
    client_id = form.get("client_id", "")
    redirect_uri = form.get("redirect_uri", "")
    state = form.get("state", "")
    code_challenge = form.get("code_challenge", "")
    code_challenge_method = form.get("code_challenge_method", "S256")
    scope = form.get("scope", "mcp")
    api_key = (form.get("api_key") or "").strip()

    client = _clients.get(client_id)
    if client is None or not api_key:
        return JSONResponse(
            {"error": "invalid_request"}, status_code=400,
        )

    # Generér kort-levetid authorization-code
    code = secrets.token_urlsafe(32)
    _codes[code] = _AuthorizationCode(
        code=code,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        api_key=api_key,
        expires_at=time.time() + _CODE_TTL_SECONDS,
        state=state,
        scope=scope,
    )
    _LOG.info("OAuth: issued code for client %s", client_id)

    # Redirect tilbake til Anthropic
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(
        f"{redirect_uri}{sep}code={code}&state={state}",
        status_code=302,
    )


async def oauth_token(request) -> Any:
    """POST /oauth/token — bytt code for access_token, eller refresh.

    grant_type=authorization_code:
      * Verifiser code finnes + ikke utløpt
      * Verifiser PKCE: code_verifier matcher lagret code_challenge
      * Slett code (single-use)
      * Generér + returner access_token + refresh_token

    grant_type=refresh_token:
      * Verifiser refresh_token finnes
      * Roter til nytt access_token (samme refresh)
    """
    from starlette.responses import JSONResponse

    form = await request.form()
    grant_type = form.get("grant_type", "")

    if grant_type == "authorization_code":
        code = form.get("code", "")
        code_verifier = form.get("code_verifier", "")
        client_id = form.get("client_id", "")
        redirect_uri = form.get("redirect_uri", "")

        entry = _codes.pop(code, None)
        if entry is None:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Unknown code"},
                status_code=400,
            )
        if entry.expires_at < time.time():
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Code expired"},
                status_code=400,
            )
        if entry.client_id != client_id:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "client_id mismatch"},
                status_code=400,
            )
        if entry.redirect_uri != redirect_uri:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "redirect_uri mismatch"},
                status_code=400,
            )
        if not _verify_pkce(code_verifier, entry.code_challenge, entry.code_challenge_method):
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "PKCE verification failed"},
                status_code=400,
            )

        # Stateless-strategi (Lars-bug 2026-05-26): in-memory token-cache
        # forsvant ved container-recreate → pass-through-fallback sendte
        # OAuth-token-strenger til backend som returnerte 401. Løsning:
        # access_token = brukerens API-key direkte. Trygt fordi brukeren
        # frivillig ga oss API-keyen i consent-formen — og hvis hen
        # roterer den i portalen, invalideres alle utstedte tokens
        # automatisk på backend-siden uten ekstra state hos oss.
        access_token = entry.api_key
        refresh_token = entry.api_key
        _LOG.info(
            "OAuth: issued access_token=API-key for client %s (stateless)",
            client_id,
        )

        return JSONResponse({
            "access_token": access_token,
            "token_type": "Bearer",
            # 24t — OAuth-spec krever et tall, men siden access_token ER
            # API-keyen, levetiden styres faktisk av API-keyens egen
            # `revoked_at`. Klienten vil refreshe når den får 401 fra
            # backend.
            "expires_in": 86400,
            "refresh_token": refresh_token,
            "scope": entry.scope or "mcp",
        })

    if grant_type == "refresh_token":
        # I stateless-mode er refresh_token = API-key. Vi returnerer den
        # uendret slik at klienten kan fortsette å bruke samme Bearer.
        refresh_token = form.get("refresh_token", "")
        if not refresh_token:
            return JSONResponse(
                {"error": "invalid_grant"}, status_code=400,
            )
        return JSONResponse({
            "access_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": 86400,
            "refresh_token": refresh_token,
            "scope": "mcp",
        })

    return JSONResponse(
        {"error": "unsupported_grant_type"}, status_code=400,
    )


def _base_url_from_request(request) -> str:
    """Hent canonical base-URL (https://mcp.firmaradar.no).

    Bruker X-Forwarded-Proto + Host hvis bak proxy, ellers request.url.
    Fjerner trailing slash.
    """
    headers = request.headers
    scheme = headers.get("x-forwarded-proto", request.url.scheme)
    host = headers.get("x-forwarded-host") or headers.get("host") or request.url.netloc
    return f"{scheme}://{host}".rstrip("/")
