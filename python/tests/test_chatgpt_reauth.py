"""Tester for ChatGPT-spesifikk inline re-auth (2026-06-01).

ChatGPT (OpenAI MCP-connector) trigger IKKE sin inline re-auth-UI av et
bart HTTP 401 under et tools/call — den krever et JSON-RPC verktøy-resultat
(HTTP 200) med ``isError=true`` og ``_meta["mcp/www_authenticate"]`` som
inneholder både ``error`` og ``error_description``, pluss per-verktøy
``securitySchemes``. Claude bruker fortsatt HTTP-401-stien.

Disse testene dekker begge halvdeler:

* server.py: 401 fra backend → CallToolResult med _meta-challenge;
  ikke-401 → ingen _meta. Verktøy-annonser bærer securitySchemes.
* remote_server.py: ChatGPT-klient med dødt token slippes gjennom til
  verktøy-laget (HTTP 200 + _meta), mens Claude/andre får HTTP 401.
"""

from __future__ import annotations

import pytest


# ── server.py: _meta-challenge på 401-feilresultat ─────────────────────

class TestErrorResultMeta:

    def test_401_error_carries_reauth_meta(self):
        from firmaradar_mcp.server import _error_result, _REAUTH_META
        r = _error_result({"error": "x", "status_code": 401}, meta=_REAUTH_META)
        d = r.model_dump(by_alias=True, exclude_none=True)
        assert d["isError"] is True
        challenge = d["_meta"]["mcp/www_authenticate"]
        assert isinstance(challenge, list) and len(challenge) == 1
        # ChatGPT krever BÅDE error og error_description i challenge-strengen
        assert 'error="invalid_token"' in challenge[0]
        assert "error_description=" in challenge[0]
        assert "resource_metadata=" in challenge[0]

    def test_non_401_error_has_no_meta(self):
        from firmaradar_mcp.server import _error_result
        r = _error_result({"error": "x", "status_code": 500})
        d = r.model_dump(by_alias=True, exclude_none=True)
        assert d["isError"] is True
        assert "_meta" not in d

    def test_reauth_meta_constant_wellformed(self):
        from firmaradar_mcp.server import _REAUTH_META, _REAUTH_WWW_AUTHENTICATE
        assert _REAUTH_META["mcp/www_authenticate"] == [_REAUTH_WWW_AUTHENTICATE]
        assert _REAUTH_WWW_AUTHENTICATE.startswith("Bearer ")


# ── server.py: securitySchemes på verktøy-annonse ──────────────────────

class TestToolSecuritySchemes:
    """securitySchemes lever under ``_meta`` siden mcp 2.0-migreringen
    (2026-07-31) — IKKE top-level slik den lå til og med 0.5.11. Se
    kommentaren ved ``_TOOL_SECURITY_SCHEMES`` i ``server.py``: mcp_types
    2.0.0 sin per-metode wire-sieve dropper ethvert top-level Tool-felt
    utenfor spec-en uansett retur-form; ``_meta`` er det eneste feltet som
    overlever. Full-pipeline-overlevelse (gjennom den faktiske
    ``tools/list``-silen) dekkes separat av
    ``test_tool_list_wire_preserves_security_schemes_under_meta`` i
    test_smoke.py — testene her dekker kun at ``_handler_to_tool`` legger
    feltet på riktig sted i utgangspunktet."""

    def test_tool_advertises_oauth2_security_scheme(self):
        from firmaradar_mcp.server import _handler_to_tool
        from firmaradar_mcp.tools import ALL_TOOLS
        tool = _handler_to_tool(ALL_TOOLS[0])
        d = tool.model_dump(by_alias=True, exclude_none=True)
        assert "securitySchemes" not in d, "securitySchemes skal IKKE ligge top-level lenger"
        assert d.get("_meta", {}).get("securitySchemes") == [{"type": "oauth2", "scopes": ["mcp"]}]

    def test_all_tools_carry_security_schemes(self):
        from firmaradar_mcp.server import _handler_to_tool
        from firmaradar_mcp.tools import ALL_TOOLS
        for h in ALL_TOOLS:
            d = _handler_to_tool(h).model_dump(by_alias=True, exclude_none=True)
            assert d.get("_meta", {}).get("securitySchemes"), f"{h.name} mangler _meta.securitySchemes"


# ── remote_server.py: ChatGPT-deteksjon + routing ──────────────────────

class TestChatGptDetection:

    def test_detects_openai_mcp_user_agent(self):
        from firmaradar_mcp.remote_server import _is_chatgpt_client
        assert _is_chatgpt_client({"user-agent": "openai-mcp/1.0.0"})
        assert _is_chatgpt_client({"user-agent": "Mozilla openai-mcp/2 (x)"})

    def test_non_openai_user_agents_are_not_chatgpt(self):
        from firmaradar_mcp.remote_server import _is_chatgpt_client
        assert not _is_chatgpt_client({"user-agent": "claude-mcp/1"})
        assert not _is_chatgpt_client({"user-agent": "cursor/0.4"})
        assert not _is_chatgpt_client({})


def _skip_if_no_remote_deps():
    try:
        import starlette  # noqa: F401
        import mcp.server.streamable_http_manager  # noqa: F401
    except ImportError:
        pytest.skip("starlette/mcp[remote] not installed")


class _StubValidator:
    def __init__(self, status):
        self.status = status
        self.invalidated = []
    async def validate(self, token):
        return self.status
    def invalidate(self, token):
        self.invalidated.append(token)
    async def aclose(self):
        pass


class TestMiddlewareChatGptRouting:
    """Dødt token: ChatGPT slippes til verktøy-laget (200+_meta), Claude → 401."""

    def _app(self, validator):
        from firmaradar_mcp.remote_server import _build_auth_middleware
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.routing import Route
        from starlette.responses import JSONResponse

        async def _ok(request):
            # Simulerer verktøy-laget: returnerer 200; her ville den ekte
            # MCP-handleren bygget _meta-challengen.
            return JSONResponse(
                {"reached_tool_layer": True,
                 "api_key": request.scope.get("state", {}).get("api_key")}
            )

        return Starlette(
            routes=[Route("/mcp/", endpoint=_ok, methods=["POST"])],
            middleware=[Middleware(_build_auth_middleware(validator))],
        )

    async def test_chatgpt_dead_token_passes_to_tool_layer(self):
        _skip_if_no_remote_deps()
        from firmaradar_mcp._token_validation import TokenStatus
        import httpx
        from httpx import ASGITransport

        app = self._app(_StubValidator(TokenStatus.INVALID))
        async with httpx.AsyncClient(transport=ASGITransport(app=app),
                                     base_url="http://t") as ac:
            resp = await ac.post("/mcp/", headers={
                "Authorization": "Bearer dead",
                "User-Agent": "openai-mcp/1.0.0",
            })
        # ChatGPT: ikke 401 — slippes til verktøy-laget (som gir 200 + _meta)
        assert resp.status_code == 200
        assert resp.json()["reached_tool_layer"] is True
        assert resp.json()["api_key"] == "dead"

    async def test_claude_dead_token_gets_http_401(self):
        _skip_if_no_remote_deps()
        from firmaradar_mcp._token_validation import TokenStatus
        import httpx
        from httpx import ASGITransport

        app = self._app(_StubValidator(TokenStatus.INVALID))
        async with httpx.AsyncClient(transport=ASGITransport(app=app),
                                     base_url="http://t") as ac:
            resp = await ac.post("/mcp/", headers={
                "Authorization": "Bearer dead",
                "User-Agent": "claude-mcp/1.0",
            })
        assert resp.status_code == 401
        assert resp.json()["error"] == "invalid_token"

    async def test_chatgpt_valid_token_normal_passthrough(self):
        _skip_if_no_remote_deps()
        from firmaradar_mcp._token_validation import TokenStatus
        import httpx
        from httpx import ASGITransport

        app = self._app(_StubValidator(TokenStatus.VALID))
        async with httpx.AsyncClient(transport=ASGITransport(app=app),
                                     base_url="http://t") as ac:
            resp = await ac.post("/mcp/", headers={
                "Authorization": "Bearer good",
                "User-Agent": "openai-mcp/1.0.0",
            })
        assert resp.status_code == 200
        assert resp.json()["api_key"] == "good"
