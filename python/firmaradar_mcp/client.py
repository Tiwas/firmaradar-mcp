"""Thin async REST-client wrapper around the Firmaradar HTTP API.

All tools route through this client so we have **one** place to handle
auth, retries, rate-limit headers, untrusted-content tagging and base-URL
configuration.

Configuration is read from environment variables only — never embed
credentials in source.

* ``FIRMARADAR_API_KEY`` — long-lived API key for service-auth
  (required at server-startup; ``ValueError`` is raised if missing).
* ``FIRMARADAR_API_BASE`` — base URL for the REST API. Defaults to
  ``https://stage.firmaradar.no`` (dedikert MCP-tier m/ egen rate-limit-
  policy, Lars-beslutning 2026-05-25).
* ``FIRMARADAR_TIMEOUT_S`` — per-request timeout in seconds.
  Defaults to ``30``.

The implementation is intentionally minimal in this skeleton — tools
will receive an instance and call ``client.get(...)`` /
``client.post(...)``. Actual HTTP calls remain stubbed out until the
underlying REST endpoints are stable; see
``plans/MCP_V01_INVENTORY.md`` for backend status per tool.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


DEFAULT_BASE_URL = "https://stage.firmaradar.no"
DEFAULT_TIMEOUT_S = 30.0
ENV_API_KEY = "FIRMARADAR_API_KEY"
ENV_API_BASE = "FIRMARADAR_API_BASE"
ENV_TIMEOUT = "FIRMARADAR_TIMEOUT_S"


class FirmaradarClientError(RuntimeError):
    """Raised when the Firmaradar REST API returns a structured error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        retry_after_s: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.retry_after_s = retry_after_s


@dataclass(frozen=True)
class ClientConfig:
    """Resolved client configuration loaded from environment variables."""

    api_key: str
    base_url: str
    timeout_s: float

    @classmethod
    def from_env(cls) -> "ClientConfig":
        api_key = os.environ.get(ENV_API_KEY, "").strip()
        if not api_key:
            raise ValueError(
                f"Missing required environment variable {ENV_API_KEY}. "
                "Set it to your Firmaradar API key before launching the MCP-server."
            )
        base_url = os.environ.get(ENV_API_BASE, DEFAULT_BASE_URL).rstrip("/")
        try:
            timeout_s = float(os.environ.get(ENV_TIMEOUT, DEFAULT_TIMEOUT_S))
        except ValueError:
            timeout_s = DEFAULT_TIMEOUT_S
        return cls(api_key=api_key, base_url=base_url, timeout_s=timeout_s)


class FirmaradarClient:
    """Async REST-client over ``httpx``.

    Held by the MCP-server for the lifetime of the process. Each tool
    receives the client via dependency injection and is responsible for
    constructing the correct request shape for its underlying endpoint.

    Note (skeleton): the ``get`` / ``post`` methods are functional but
    every concrete tool currently raises ``NotImplementedError`` before
    reaching them. They are exposed here so future implementation work
    can wire them up without re-designing this layer.
    """

    def __init__(self, config: ClientConfig | None = None) -> None:
        self._config = config or ClientConfig.from_env()
        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            timeout=self._config.timeout_s,
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "User-Agent": "firmaradar-mcp/0.1 (+https://firmaradar.no)",
                "Accept": "application/json",
            },
        )

    @property
    def base_url(self) -> str:
        return self._config.base_url

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Issue a GET against the REST API and return decoded JSON."""
        response = await self._client.get(path, params=params)
        return self._handle_response(response)

    async def post(
        self,
        path: str,
        json_body: dict[str, Any] | None = None,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        """Issue a POST against the REST API and return decoded JSON.

        ``extra_headers`` adds per-call headers on top of the defaults
        (Authorization, Accept, User-Agent). Used by AML/PEP-screening
        for DPA-confirmation headers (X-FR-Purpose +
        X-FR-DPA-Confirmed).
        """
        response = await self._client.post(
            path, json=json_body, headers=extra_headers
        )
        return self._handle_response(response)

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _handle_response(response: httpx.Response) -> Any:
        if response.is_success:
            # Defensive JSON-parse: tidligere ga vi en cryptic
            # "Expecting value: line 1 column 1 (char 0)" når server svarte
            # 2xx med tom eller ikke-JSON body (nginx-buffer-issue,
            # upstream-timeout, gzip-mismatch). Nå returnerer vi en
            # informativ feil som inkluderer status-kode + body-preview.
            if not response.content:
                raise FirmaradarClientError(
                    "Server returned empty body for a successful response. "
                    "Likely upstream-timeout or proxy-buffer issue — retry "
                    "the call. If persistent, contact support.",
                    status_code=response.status_code,
                )
            try:
                return response.json()
            except ValueError as exc:
                preview = (response.text or "")[:200]
                raise FirmaradarClientError(
                    f"Server returned non-JSON body (HTTP {response.status_code}). "
                    f"Body-preview: {preview!r}. JSON-decode-error: {exc}",
                    status_code=response.status_code,
                )
        retry_after = response.headers.get("Retry-After")
        try:
            payload = response.json()
        except ValueError:
            payload = {"error": response.text}
        raise FirmaradarClientError(
            payload.get("error") or payload.get("message") or response.reason_phrase,
            status_code=response.status_code,
            error_code=(payload or {}).get("error_code"),
            retry_after_s=int(retry_after) if retry_after and retry_after.isdigit() else None,
        )


__all__ = [
    "ClientConfig",
    "FirmaradarClient",
    "FirmaradarClientError",
    "ENV_API_KEY",
    "ENV_API_BASE",
    "ENV_TIMEOUT",
]
