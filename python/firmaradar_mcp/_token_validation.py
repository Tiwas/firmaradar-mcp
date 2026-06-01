"""Proaktiv token-liveness-validering for den remote MCP-serveren.

Bakgrunn (2026-05-31 — "tilby ny innlogging når MCP gir 401"):

  Streamable-HTTP-transporten eier HTTP-svaret så snart den begynner å
  streame en JSON-RPC-respons. Når et ``tools/call`` treffer backend og
  får 401 (delegate-token utløpt, eller underliggende API-key rotert/
  revoked), fanges feilen av ``server._call_tool`` og returneres som en
  ``CallToolResult(isError=True)`` — altså over **HTTP 200** med 401-koden
  begravet i feil-payloaden. Claude ser dermed aldri en ekte HTTP 401 +
  ``WWW-Authenticate`` på verktøykall, og tilbyr derfor aldri OAuth-re-auth.
  Brukeren sitter fast med "Firmaradar API error 401" til hen manuelt
  kobler til på nytt — og siden delegate-tokens har 24t TTL skjer dette
  daglig.

  Løsning: ``BearerAuthMiddleware`` validerer tokenet PROAKTIVT (før
  kontrollen gis til transporten) mot et lett introspeksjons-endepunkt på
  firmaradar_web. Er tokenet dødt, svarer middlewaren selv HTTP 401 +
  ``WWW-Authenticate`` (RFC 9728 § 5.1 med ``resource_metadata``), som er
  nøyaktig signalet Claude trenger for å starte ny innlogging.

Designvalg:

* **Single source of truth.** Introspeksjon kaller firmaradar_web sitt
  ``/oauth/introspect``, som internt bruker samme
  ``_resolve_user_and_key_from_request`` som de ekte API-rutene. Vi
  dupliserer ingen auth-logikk i mcp_remote og kan ikke drifte ut av sync.
* **Fail-open ved transient feil.** Tidsavbrudd, nettverksfeil eller 5xx
  fra web gir :data:`TokenStatus.UNKNOWN` → middlewaren slipper requesten
  videre (backend forblir siste skanse). En web-hikke skal aldri logge ut
  alle MCP-brukere. Kun et **definitivt** 401/403 gir re-auth.
* **Kort TTL-cache.** Positive svar caches ~60s, negative ~10s, så vi
  unngår en backend-rundtur per JSON-RPC-kall uten å la et revoked token
  overleve lenge.
"""

from __future__ import annotations

import enum
import hashlib
import logging
import time

import httpx

from . import __version__

_LOG = logging.getLogger("firmaradar_mcp.token_validation")

_POSITIVE_TTL_S = 60.0
_NEGATIVE_TTL_S = 10.0
_DEFAULT_TIMEOUT_S = 5.0


class TokenStatus(enum.Enum):
    """Resultat av en token-liveness-sjekk."""

    VALID = "valid"      # backend bekreftet gyldig → slipp gjennom
    INVALID = "invalid"  # definitivt 401/403 → krev re-auth (HTTP 401)
    UNKNOWN = "unknown"  # transient feil → fail-open (slipp gjennom)


class TokenValidator:
    """Validerer Bearer-/delegate-tokens mot firmaradar_web /oauth/introspect.

    Instansieres én gang per prosess i :func:`remote_server.create_app` og
    deles av alle requests. Holder en intern httpx-klient + TTL-cache.
    """

    def __init__(
        self,
        *,
        web_base_url: str,
        introspect_path: str = "/oauth/introspect",
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        positive_ttl_s: float = _POSITIVE_TTL_S,
        negative_ttl_s: float = _NEGATIVE_TTL_S,
    ) -> None:
        self._url = web_base_url.rstrip("/") + introspect_path
        self._timeout_s = timeout_s
        self._positive_ttl_s = positive_ttl_s
        self._negative_ttl_s = negative_ttl_s
        # token-hash → (expires_monotonic, status)
        self._cache: dict[str, tuple[float, TokenStatus]] = {}
        self._client: httpx.AsyncClient | None = None

    @staticmethod
    def _hash(token: str) -> str:
        """SHA-256 av tokenet — vi cacher aldri råtokenet i minne som key."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _client_or_create(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_s)
        return self._client

    async def validate(self, token: str | None) -> TokenStatus:
        """Returner :class:`TokenStatus` for ``token`` (cache-først)."""
        if not token:
            return TokenStatus.INVALID
        key = self._hash(token)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

        status = await self._introspect(token)
        if status is TokenStatus.VALID:
            self._cache[key] = (now + self._positive_ttl_s, status)
        elif status is TokenStatus.INVALID:
            self._cache[key] = (now + self._negative_ttl_s, status)
        # UNKNOWN caches IKKE — transient, skal forsøkes på nytt.
        return status

    async def _introspect(self, token: str) -> TokenStatus:
        try:
            resp = await self._client_or_create().get(
                self._url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-FR-Client": f"firmaradar-mcp/{__version__}",
                    "Accept": "application/json",
                },
            )
        except Exception as exc:  # noqa: BLE001 — nettverk/timeout → fail-open
            _LOG.warning(
                "token-introspeksjon nådde ikke %s (%s) — fail-open (UNKNOWN)",
                self._url, exc,
            )
            return TokenStatus.UNKNOWN
        if resp.status_code == 200:
            return TokenStatus.VALID
        if resp.status_code in (401, 403):
            return TokenStatus.INVALID
        _LOG.warning(
            "token-introspeksjon ga uventet status %s fra %s — fail-open (UNKNOWN)",
            resp.status_code, self._url,
        )
        return TokenStatus.UNKNOWN

    def invalidate(self, token: str | None) -> None:
        """Fjern ev. cachet status for ``token`` (kalles ved 401-evicting)."""
        if token:
            self._cache.pop(self._hash(token), None)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


__all__ = ["TokenStatus", "TokenValidator"]
