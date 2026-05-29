"""Tests for the remote_server ASGI-app (#116).

Verifiserer at:

* ``create_app()`` returnerer Starlette-app med /health + /mcp routes.
* /health er auth-fri og rapporterer tools_count + transport.
* /mcp uten Bearer-token returnerer 401 med WWW-Authenticate.
* /mcp med Bearer-token aksepteres (auth-middleware passerer).

Bruker httpx.AsyncClient + Starlette test-stack — ingen ekte HTTP-server.
"""

from __future__ import annotations

import os

import pytest


def _skip_if_no_remote_deps():
    try:
        import starlette  # noqa: F401
        import mcp.server.streamable_http_manager  # noqa: F401
    except ImportError:
        pytest.skip("starlette/mcp[remote] not installed — install '.[remote]'")


@pytest.fixture
def app():
    _skip_if_no_remote_deps()
    os.environ.setdefault("FIRMARADAR_API_KEY", "placeholder")
    from firmaradar_mcp.remote_server import create_app
    return create_app(base_url="https://firmaradar.no")


@pytest.fixture
async def client(app):
    import httpx
    from httpx import ASGITransport
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as ac:
        yield ac


class TestCreateApp:

    def test_app_has_health_and_mcp_routes(self, app):
        paths = [r.path for r in app.routes]
        assert "/health" in paths
        assert "/mcp" in paths

    def test_app_is_starlette_instance(self, app):
        from starlette.applications import Starlette
        assert isinstance(app, Starlette)


class TestHealth:

    async def test_health_returns_200_without_auth(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["status"] == "ok"
        assert payload["service"] == "firmaradar-mcp-remote"
        assert payload["transport"] == "streamable-http"
        # 25 tools per v0.3-katalogen (17 v0.1/v0.2 + 8 markedsplass-utvidelser)
        assert payload["tools_count"] == 25
        assert payload["backend"] == "https://firmaradar.no"

    async def test_health_exposes_version(self, client):
        resp = await client.get("/health")
        from firmaradar_mcp import __version__
        assert resp.json()["version"] == __version__


class TestBearerAuth:

    async def test_mcp_without_bearer_returns_401(self, client):
        resp = await client.post("/mcp/")
        assert resp.status_code == 401
        payload = resp.json()
        assert payload["error"] == "missing_authorization"
        # WWW-Authenticate per RFC 6750
        assert "Bearer" in resp.headers.get("www-authenticate", "")

    async def test_mcp_with_malformed_bearer_passes_auth_layer(self):
        """Bekreft at auth-middleware passerer ved gyldig Bearer-header.

        Vi bygger en minimal isolert middleware-test her i stedet for å
        kjøre full MCP-protokoll mot ASGITransport — streamable-HTTP
        + anyio TaskGroup spiller dårlig sammen med httpx ASGI-stack
        i unit-tester. Live smoke-test (curl) bekrefter end-to-end.
        """
        _skip_if_no_remote_deps()
        from firmaradar_mcp.remote_server import _build_auth_middleware
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.routing import Route
        from starlette.responses import JSONResponse
        import httpx
        from httpx import ASGITransport

        async def _ok(request):
            # Middleware skal ha satt api_key i scope["state"]
            return JSONResponse(
                {"api_key": request.scope.get("state", {}).get("api_key")}
            )

        app = Starlette(
            routes=[Route("/mcp/", endpoint=_ok, methods=["POST"])],
            middleware=[Middleware(_build_auth_middleware())],
        )
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
            resp = await ac.post(
                "/mcp/",
                headers={"Authorization": "Bearer my-firmaradar-key"},
            )
        assert resp.status_code == 200
        assert resp.json() == {"api_key": "my-firmaradar-key"}

    async def test_alternative_mcp_client_string_accepted(self):
        """Andre token-strenger må også aksepteres av middleware."""
        _skip_if_no_remote_deps()
        from firmaradar_mcp.remote_server import _build_auth_middleware
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.routing import Route
        from starlette.responses import JSONResponse
        import httpx
        from httpx import ASGITransport

        async def _ok(request):
            return JSONResponse({"ok": True})

        app = Starlette(
            routes=[Route("/mcp/", endpoint=_ok, methods=["POST"])],
            middleware=[Middleware(_build_auth_middleware())],
        )
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
            resp = await ac.post(
                "/mcp/",
                headers={"Authorization": "Bearer codex-mcp-token-123"},
            )
        assert resp.status_code == 200

    async def test_health_check_bypasses_auth(self, client):
        # Selv om vi sender en ugyldig Authorization-header skal /health
        # alltid svare 200 (load-balancere må kunne hit'e den uten cred).
        resp = await client.get(
            "/health", headers={"Authorization": "Bearer total-garbage"}
        )
        assert resp.status_code == 200
