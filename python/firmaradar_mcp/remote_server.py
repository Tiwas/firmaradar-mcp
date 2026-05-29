"""Remote MCP-server (streamable-HTTP + SSE).

ASGI-app som hoster firmaradar-mcp over HTTPS slik at remote AI-klienter
— Claude Desktop med "Custom Connectors", Claude Web og **Claude mobile
(Android/iOS)** — kan koble seg til via en URL i stedet for å kjøre en
lokal stdio-prosess.

Lars-prioritering 2026-05-26: Android Claude er bare tilgjengelig via
remote MCP, så denne entry-pointen er forutsetningen for app-støtte.

Arkitektur:

* **Transport**: ``StreamableHTTPSessionManager`` fra MCP SDK (spec
  2025-03-26). Backward-compat SSE-endpoint vurderes til v0.2 hvis
  vi får eldre klienter som krever det.
* **Hosting**: Starlette + uvicorn. Lett ASGI-stack, samme som FastAPI
  bruker.
* **Auth**: Placeholder Bearer-token-sjekk. OAuth 2.0 + DCR (#117)
  bygges separat og kobles inn her via middleware.
* **Tool-handlere**: gjenbrukes 1:1 fra stdio-serveren (``server.py``).
  Begge entry-points serverer samme 26 verktøy mot samme backend.

Lokal kjøring (uten TLS, kun for utvikling):

    pip install -e tools/mcp_server/python
    FIRMARADAR_API_KEY=<key> FIRMARADAR_API_BASE_URL=https://firmaradar.no \\
        firmaradar-mcp-remote --port 8765

Production-deployment (mcp.firmaradar.no, etter #118 DNS+TLS):

    docker-compose-snippet i ``docker-compose.yml``-tillegget under,
    bak nginx-reverse-proxy med Let's Encrypt-cert.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import sys
from typing import Any

from . import __version__
from .client import ClientConfig, FirmaradarClient
from .server import build_server
from .tools import ALL_TOOLS

_LOG = logging.getLogger("firmaradar_mcp.remote_server")


def _configure_logging() -> None:
    level = os.environ.get("FIRMARADAR_MCP_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


# ── Auth-middleware (placeholder for OAuth, #117) ──────────────────────

def _extract_bearer_token(headers) -> str | None:
    """Parse ``Authorization: Bearer <token>``-header (case-insensitive)."""
    raw = headers.get("authorization") or headers.get("Authorization") or ""
    if raw.lower().startswith("bearer "):
        return raw[7:].strip() or None
    return None


# Session-token-cache for stateful MCP-streamable-HTTP-flyt.
# Anthropic-klienter (Claude Web, Claude mobile/Android/iOS) sender
# Bearer-token KUN på initialize-request (POST /mcp/). Follow-up-
# requests går til /mcp/<session-id> uten Bearer — Anthropic forventer
# at session-id-en i path representerer en allerede-autentisert sesjon.
#
# Vi cacher dermed token per session-id ved initialize, og slår opp
# token-en når follow-ups kommer med session-id i path eller
# Mcp-Session-Id-header.
#
# In-memory, per-process. Sesjons-tokens slettes når MCP-sesjonen
# termineres (StreamableHTTPSessionManager kaller close-hook).
_session_tokens: dict[str, str] = {}


def _extract_session_id(scope, headers) -> str | None:
    """Hent ut session-id fra Mcp-Session-Id-header eller path-suffix.

    Anthropic Claude Web/Mobile sender follow-up til ``/mcp/<session-id>``
    (path-basert). Andre klienter (Cursor, ChatGPT) bruker
    ``Mcp-Session-Id``-header per MCP-spec. Vi støtter begge.
    """
    sid = headers.get("mcp-session-id")
    if sid:
        return sid.strip() or None
    path = scope.get("path", "")
    if path.startswith("/mcp/"):
        # /mcp/abc123 → "abc123"; /mcp/ → ""
        suffix = path[len("/mcp/"):].strip("/")
        if suffix and "/" not in suffix:
            return suffix
    return None


# MCP-metoder som er trygge å eksponere UTEN auth: ren discovery/handshake
# som ikke rører kundedata. Verktøy-skjemaene er allerede offentlige
# (README, Official MCP Registry, Glama, public GitHub). ``tools/call`` er
# bevisst IKKE her — verktøy-KALL krever fortsatt OAuth siden de henter data.
# Dette lar directory-scannere (Cursor, PulseMCP, Glama connectors) og klienter
# introspektere verktøy-listen før innlogging.
_PUBLIC_MCP_METHODS = frozenset({
    "initialize",
    "notifications/initialized",
    "notifications/cancelled",
    "ping",
    "tools/list",
    "prompts/list",
    "resources/list",
    "resources/templates/list",
})


def _body_is_discovery_only(body: bytes) -> bool:
    """Returner True hvis JSON-RPC-bodyen KUN inneholder offentlige discovery-
    metoder (:data:`_PUBLIC_MCP_METHODS`).

    Fail-closed: tom body, ugyldig JSON, manglende ``method``, ikke-dict-item,
    eller ENHVER metode utenfor whitelisten → ``False`` (krever auth). Et
    JSON-RPC-batch tillates kun hvis ALLE metodene er offentlige.
    """
    if not body:
        return False
    try:
        import json as _json
        data = _json.loads(body)
    except Exception:  # noqa: BLE001 — ugyldig JSON → krev auth
        return False
    items = data if isinstance(data, list) else [data]
    if not items:
        return False
    for it in items:
        if not isinstance(it, dict):
            return False
        method = it.get("method")
        if not isinstance(method, str) or method not in _PUBLIC_MCP_METHODS:
            return False
    return True


async def _buffer_asgi_body(receive):
    """Les hele ASGI-request-bodyen og returner ``(body_bytes, replay_receive)``.

    ``replay_receive`` gjenspiller de bufrede meldingene slik at downstream-
    appen kan lese bodyen på nytt. Nødvendig fordi vi må inspisere JSON-RPC-
    metoden i middleware FØR vi avgjør om requesten slipper gjennom.
    """
    messages: list[dict] = []
    body = b""
    while True:
        message = await receive()
        messages.append(message)
        if message["type"] == "http.request":
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break
        else:
            # http.disconnect e.l. — stopp buffering
            break

    async def replay():
        if messages:
            return messages.pop(0)
        return await receive()

    return body, replay


def _build_auth_middleware():
    """Returner en Starlette ASGI-middleware som autentiserer Bearer +
    cacher session-tokens for follow-up-requests uten Bearer.

    v0.1: tokenet brukes direkte som Firmaradar API-key (kunden lager
    en API-key i portalen og limer den inn i Claude-connector-UI-en).

    v0.2 (#117): OAuth 2.0 + DCR. Tokenet er da et opaque access-token
    som vi slår opp mot ``oauth_token``-tabellen for å finne den
    tilknyttede API-key-en. Samme middleware fortsetter å fungere —
    bare lookup-strategien endres.

    Flyt:
      1. POST /mcp/ med Bearer → token settes på scope + cachet hvis
         response inkluderer ny session-id
      2. POST /mcp/<session-id> uten Bearer → resolve token fra cache
         via session-id i path/header
      3. Ingen Bearer + ingen kjent session → 401
    """
    from starlette.responses import JSONResponse
    from starlette.types import ASGIApp, Receive, Scope, Send

    class BearerAuthMiddleware:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return
            # Public paths — ingen auth-krav
            path = scope.get("path", "")
            if (
                path == "/health"
                or path.startswith("/.well-known/oauth-protected-resource")
                or path == "/.well-known/oauth-authorization-server"
                or path.startswith("/oauth/")
                or path == "/register"  # Claude probet denne direkte
            ):
                await self.app(scope, receive, send)
                return

            headers = {
                k.decode("latin-1").lower(): v.decode("latin-1")
                for k, v in scope.get("headers", [])
            }
            token = _extract_bearer_token(headers)
            session_id = _extract_session_id(scope, headers)

            # Bearer på request → resolve mot OAuth-store (eller pass-through
            # for direkte API-key-flow), cache for fremtidige session-follow-
            # ups, og videresend til MCP-handler.
            if token:
                from . import oauth_shim
                api_key = oauth_shim.resolve_bearer_to_api_key(token)
                if api_key is None:
                    # Tokenet er utløpt eller ukjent — krev re-auth.
                    # RFC 9728 § 5.1: WWW-Authenticate MÅ inkludere
                    # resource_metadata-parameter slik at klienten kan
                    # discovery'e auth-server via /.well-known/oauth-
                    # protected-resource.
                    response = JSONResponse(
                        {
                            "error": "invalid_token",
                            "error_description": (
                                "Access token expired or unknown. "
                                "Refresh via OAuth or re-paste API-key."
                            ),
                        },
                        status_code=401,
                        headers={
                            "WWW-Authenticate": (
                                'Bearer realm="firmaradar-mcp", '
                                'error="invalid_token", '
                                'resource_metadata="https://mcp.firmaradar.no/.well-known/oauth-protected-resource"'
                            ),
                        },
                    )
                    await response(scope, receive, send)
                    return
                scope.setdefault("state", {})["api_key"] = api_key
                if session_id:
                    _session_tokens[session_id] = api_key
                # Wrap send for å snappe session-id fra response-headers
                # (initialize-respons inneholder Mcp-Session-Id-header med
                # ny session-id som klient så bruker på follow-ups).
                wrapped_send = _make_session_capturing_send(send, api_key)
                await self.app(scope, receive, wrapped_send)
                return

            # Ingen Bearer — slå opp token fra session-cache
            if session_id and session_id in _session_tokens:
                scope.setdefault("state", {})["api_key"] = _session_tokens[session_id]
                await self.app(scope, receive, send)
                return

            # Ingen Bearer + ingen kjent session. Tillat uautentisert
            # DISCOVERY (initialize, tools/list, ping, notifications) slik at
            # directory-scannere (Cursor, PulseMCP, Glama) og klienter kan
            # introspektere verktøy-skjemaene FØR innlogging. tools/call
            # forblir gated (krever OAuth) — vi inspiserer JSON-RPC-metoden
            # i bodyen og slipper kun gjennom whitelistede discovery-metoder.
            buffered_body, replay = await _buffer_asgi_body(receive)
            if _body_is_discovery_only(buffered_body):
                # Ingen api_key settes — discovery-handlere (list_tools)
                # trenger den ikke; ev. tools/call på samme session blir
                # avvist her (ikke discovery-only) → 401.
                await self.app(scope, replay, send)
                return

            # Ikke-discovery uten auth → 401.
            # RFC 9728 § 5.1: resource_metadata-parameter peker klienten
            # til discovery-endepunktet slik at den vet hvilken auth-
            # server som beskytter ressursen.
            response = JSONResponse(
                {
                    "error": "missing_authorization",
                    "message": (
                        "Send 'Authorization: Bearer <token>' header. "
                        "v0.1: token = Firmaradar API-key. "
                        "v0.2: token = OAuth-issued access-token. "
                        "Follow-up requests gjenkjennes via Mcp-Session-Id-"
                        "header eller /mcp/<session-id>-path."
                    ),
                },
                status_code=401,
                headers={
                    "WWW-Authenticate": (
                        'Bearer realm="firmaradar-mcp", '
                        'resource_metadata="https://mcp.firmaradar.no/.well-known/oauth-protected-resource"'
                    ),
                },
            )
            await response(scope, replay, send)

    return BearerAuthMiddleware


def _make_session_capturing_send(original_send, token: str):
    """Wrap ASGI send-callable for å fange Mcp-Session-Id ved init.

    StreamableHTTPSessionManager returnerer en ny session-id i
    response-header på initialize-request. Vi sniffer den fra
    response.start-melding og cacher mappingen session_id → token
    så follow-up-requests uten Bearer kan resolves.
    """
    async def _send(message):
        if message.get("type") == "http.response.start":
            for k, v in message.get("headers", []):
                if k.lower() == b"mcp-session-id":
                    try:
                        sid = v.decode("latin-1").strip()
                        if sid:
                            _session_tokens[sid] = token
                    except Exception:
                        pass
                    break
        await original_send(message)
    return _send


# ── Per-request client-resolver ────────────────────────────────────────

def _client_for_token(token: str, base_url: str, timeout_s: float) -> FirmaradarClient:
    """Bygg en FirmaradarClient bundet til en spesifikk API-key.

    v0.1: tokenet ER API-keyen — lim inn rått fra portalen.
    v0.2 (#117): slå tokenet opp i oauth_token-tabellen og hent
    API-key derfra.
    """
    config = ClientConfig(
        api_key=token,
        base_url=base_url,
        timeout_s=timeout_s,
    )
    return FirmaradarClient(config=config)


# ── App-factory ────────────────────────────────────────────────────────

def create_app(
    *,
    base_url: str | None = None,
    timeout_s: float = 30.0,
    stateless: bool = True,
):
    """Bygg ASGI-appen som hosters av uvicorn.

    Args:
      base_url: Firmaradar API-base (default fra ``FIRMARADAR_API_BASE_URL``
        env, fallback ``https://firmaradar.no``).
      timeout_s: HTTP-timeout for backend-kall.
      stateless: Hvis True, ingen MCP-session-persistens mellom requests
        (anbefales for Android — mobil-tilkoblinger er ofte korte).

    Returns:
      Starlette-app klar for ``uvicorn.run(app, ...)``.
    """
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    api_base = base_url or os.environ.get(
        "FIRMARADAR_API_BASE_URL", "https://firmaradar.no"
    )

    # Bygg MCP-server-instans EN gang per process. Tool-handlerne lever
    # uavhengig av client-objektet siden vi injiserer per-request client
    # via context-var (se _wrapped_call_tool nedenfor).
    #
    # ContextVar settes per ASGI-request i StreamableHTTPSessionManager-
    # callbacken. Nytt design vs stdio-serveren: stdio har ett globalt
    # client, remote har ett per kunde.
    import contextvars

    _current_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
        "firmaradar_mcp_token", default=None,
    )

    class _DispatchingClient:
        """Proxy som ruter til riktig FirmaradarClient basert på contextvar."""

        def __init__(self) -> None:
            self._cache: dict[str, FirmaradarClient] = {}

        def _resolve(self) -> FirmaradarClient:
            token = _current_token.get()
            if not token:
                raise RuntimeError(
                    "No auth token in context — middleware må kjøre først"
                )
            client = self._cache.get(token)
            if client is None:
                client = _client_for_token(token, api_base, timeout_s)
                self._cache[token] = client
            return client

        async def get(self, path: str, params: dict | None = None) -> Any:
            return await self._resolve().get(path, params=params)

        async def post(
            self,
            path: str,
            json_body: dict | None = None,
            extra_headers: dict[str, str] | None = None,
        ) -> Any:
            return await self._resolve().post(
                path, json_body=json_body, extra_headers=extra_headers,
            )

        @property
        def base_url(self) -> str:
            return api_base

        async def aclose(self) -> None:
            for c in self._cache.values():
                with contextlib.suppress(Exception):
                    await c.aclose()
            self._cache.clear()

    dispatcher = _DispatchingClient()
    mcp_server = build_server(ALL_TOOLS, dispatcher)

    session_manager = StreamableHTTPSessionManager(
        app=mcp_server,
        stateless=stateless,
    )

    async def handle_mcp(scope, receive, send) -> None:
        # Sett contextvar fra middleware-resolvert token før vi gir kontroll
        # til MCP-session-manageren.
        token = (scope.get("state") or {}).get("api_key")
        token_ctx = _current_token.set(token) if token else None
        try:
            await session_manager.handle_request(scope, receive, send)
        finally:
            if token_ctx is not None:
                _current_token.reset(token_ctx)

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({
            "status": "ok",
            "service": "firmaradar-mcp-remote",
            "version": __version__,
            "transport": "streamable-http",
            "tools_count": len(ALL_TOOLS),
            "backend": api_base,
        })

    @contextlib.asynccontextmanager
    async def _lifespan(app):  # type: ignore[no-untyped-def]
        async with session_manager.run():
            try:
                yield
            finally:
                await dispatcher.aclose()

    # OAuth 2.0 + DCR-shim for Anthropic Claude Web/Mobile-klienter (#117)
    from . import oauth_shim

    return Starlette(
        debug=False,
        routes=[
            Route("/health", endpoint=health, methods=["GET"]),
            # OAuth discovery (RFC 9728 + RFC 8414)
            Route(
                "/.well-known/oauth-protected-resource",
                endpoint=oauth_shim.well_known_protected_resource,
                methods=["GET"],
            ),
            # Claude prøver også /.well-known/oauth-protected-resource/mcp/<session-id>
            Route(
                "/.well-known/oauth-protected-resource/{path:path}",
                endpoint=oauth_shim.well_known_protected_resource,
                methods=["GET"],
            ),
            Route(
                "/.well-known/oauth-authorization-server",
                endpoint=oauth_shim.well_known_authorization_server,
                methods=["GET"],
            ),
            # OAuth endpoints — registrer både /oauth/register (vår
            # canonical) og /register (Claude probet denne direkte i
            # 2026-05-26-loggene uten å lese discovery).
            Route(
                "/oauth/register",
                endpoint=oauth_shim.oauth_register,
                methods=["POST"],
                name="oauth_register",
            ),
            Route(
                "/register",
                endpoint=oauth_shim.oauth_register,
                methods=["POST"],
            ),
            Route(
                "/oauth/authorize",
                endpoint=oauth_shim.oauth_authorize,
                methods=["GET", "POST"],
                name="oauth_authorize",
            ),
            Route(
                "/oauth/token",
                endpoint=oauth_shim.oauth_token,
                methods=["POST"],
                name="oauth_token",
            ),
            # MCP streamable-HTTP-transport
            Mount("/mcp", app=handle_mcp),
        ],
        middleware=[Middleware(_build_auth_middleware())],
        lifespan=_lifespan,
    )


# ── Console-script entry ───────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="firmaradar-mcp-remote",
        description="Remote streamable-HTTP MCP-server for Firmaradar.",
    )
    parser.add_argument(
        "--host", default=os.environ.get("FIRMARADAR_MCP_HOST", "127.0.0.1"),
        help="Bind-host (default 127.0.0.1; sett til 0.0.0.0 for container).",
    )
    parser.add_argument(
        "--port", type=int,
        default=int(os.environ.get("FIRMARADAR_MCP_PORT", "8765")),
        help="Bind-port (default 8765).",
    )
    parser.add_argument(
        "--base-url", default=None,
        help="Firmaradar API base-URL (default https://firmaradar.no).",
    )
    args = parser.parse_args()

    _configure_logging()
    _LOG.info(
        "firmaradar-mcp-remote v%s starting on %s:%d (backend=%s)",
        __version__, args.host, args.port,
        args.base_url or os.environ.get("FIRMARADAR_API_BASE_URL",
                                        "https://firmaradar.no"),
    )

    app = create_app(base_url=args.base_url)

    try:
        import uvicorn
    except ImportError as exc:
        _LOG.error(
            "uvicorn ikke installert. Kjør: pip install 'firmaradar-mcp[remote]' "
            "eller pip install uvicorn"
        )
        raise SystemExit(1) from exc

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
