"""Tester for :mod:`firmaradar_mcp._token_validation` (2026-05-31).

Verifiserer at ``TokenValidator``:

* mapper HTTP-status fra /oauth/introspect til riktig :class:`TokenStatus`
  (200 → VALID, 401/403 → INVALID, 5xx/uventet → UNKNOWN),
* failer-open (UNKNOWN) ved nettverksfeil,
* cacher positive/negative svar (ingen ny HTTP-rundtur innen TTL),
* IKKE cacher UNKNOWN (transient skal forsøkes på nytt),
* sender Bearer + X-FR-Client på introspeksjons-kallet,
* ``invalidate`` tømmer cachen for et token.

Bruker respx for å mocke httpx uten ekte HTTP-server.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from firmaradar_mcp._token_validation import TokenStatus, TokenValidator

_BASE = "http://web.test"
_URL = f"{_BASE}/oauth/introspect"


def _validator(**kwargs) -> TokenValidator:
    return TokenValidator(web_base_url=_BASE, **kwargs)


@respx.mock
async def test_200_maps_to_valid():
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"active": True}))
    v = _validator()
    assert await v.validate("tok") is TokenStatus.VALID
    await v.aclose()


@respx.mock
async def test_401_maps_to_invalid():
    respx.get(_URL).mock(return_value=httpx.Response(401, json={"active": False}))
    v = _validator()
    assert await v.validate("tok") is TokenStatus.INVALID
    await v.aclose()


@respx.mock
async def test_403_maps_to_invalid():
    respx.get(_URL).mock(return_value=httpx.Response(403))
    v = _validator()
    assert await v.validate("tok") is TokenStatus.INVALID
    await v.aclose()


@respx.mock
async def test_500_maps_to_unknown_failopen():
    respx.get(_URL).mock(return_value=httpx.Response(500))
    v = _validator()
    assert await v.validate("tok") is TokenStatus.UNKNOWN
    await v.aclose()


@respx.mock
async def test_network_error_maps_to_unknown_failopen():
    respx.get(_URL).mock(side_effect=httpx.ConnectError("boom"))
    v = _validator()
    assert await v.validate("tok") is TokenStatus.UNKNOWN
    await v.aclose()


async def test_empty_token_is_invalid_without_call():
    # Tom token skal ikke engang trigge en HTTP-rundtur.
    v = _validator()
    assert await v.validate("") is TokenStatus.INVALID
    assert await v.validate(None) is TokenStatus.INVALID
    await v.aclose()


@respx.mock
async def test_positive_result_is_cached():
    route = respx.get(_URL).mock(return_value=httpx.Response(200))
    v = _validator()
    assert await v.validate("tok") is TokenStatus.VALID
    assert await v.validate("tok") is TokenStatus.VALID
    # Andre kall skal komme fra cachen — kun ÉN HTTP-rundtur.
    assert route.call_count == 1
    await v.aclose()


@respx.mock
async def test_invalid_result_is_cached():
    route = respx.get(_URL).mock(return_value=httpx.Response(401))
    v = _validator()
    assert await v.validate("tok") is TokenStatus.INVALID
    assert await v.validate("tok") is TokenStatus.INVALID
    assert route.call_count == 1
    await v.aclose()


@respx.mock
async def test_unknown_result_is_not_cached():
    route = respx.get(_URL).mock(return_value=httpx.Response(503))
    v = _validator()
    assert await v.validate("tok") is TokenStatus.UNKNOWN
    assert await v.validate("tok") is TokenStatus.UNKNOWN
    # UNKNOWN caches ikke → to rundturer.
    assert route.call_count == 2
    await v.aclose()


@respx.mock
async def test_invalidate_clears_cache():
    route = respx.get(_URL).mock(return_value=httpx.Response(200))
    v = _validator()
    assert await v.validate("tok") is TokenStatus.VALID
    v.invalidate("tok")
    assert await v.validate("tok") is TokenStatus.VALID
    # Etter invalidate skal andre kall treffe nettet igjen.
    assert route.call_count == 2
    await v.aclose()


@respx.mock
async def test_sends_bearer_and_client_marker():
    captured = {}

    def _handler(request):
        captured["auth"] = request.headers.get("authorization")
        captured["client"] = request.headers.get("x-fr-client")
        return httpx.Response(200)

    respx.get(_URL).mock(side_effect=_handler)
    v = _validator()
    await v.validate("my-token")
    assert captured["auth"] == "Bearer my-token"
    assert captured["client"].startswith("firmaradar-mcp/")
    await v.aclose()
