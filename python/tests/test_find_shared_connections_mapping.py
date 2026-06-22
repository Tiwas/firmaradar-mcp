"""handle()-mapping for find_shared_connections — motorens output passerer gjennom
+ sammendrag bygges, og en 403 (utvidelse ikke aktiv) surfaces pent i meta.error."""
from __future__ import annotations

import asyncio

from firmaradar_mcp.client import FirmaradarClientError
from firmaradar_mcp.tools.find_shared_connections import (
    FindSharedConnectionsInput,
    handle,
)


class _StubClient:
    def __init__(self, payload=None, raise_exc=None):
        self._payload = payload
        self._raise = raise_exc
        self.last_params = None

    async def get(self, path, params=None):
        self.last_params = params
        if self._raise is not None:
            raise self._raise
        return self._payload


_PAYLOAD = {
    "selskaper": [{"orgnr": "111111111", "navn": "A AS"}, {"orgnr": "222222222", "navn": "B AS"}],
    "risiko_score": 7.5,
    "risiko_niva": "middels",
    "risiko_indikatorer": [
        {"kode": "delt_person", "tittel": "Delt person: Ola"},
        {"kode": "delt_adresse", "tittel": "Delt forretningsadresse: Gata 1"},
    ],
    "felles_personer": [{"navn": "Ola"}],
    "graf": {"noder": [], "kanter": []},
    "meta": {"antall_selskaper": 2, "tier_cap": 5},
}


def test_maps_engine_output_and_summary():
    client = _StubClient(_PAYLOAD)
    out = asyncio.run(handle(client, FindSharedConnectionsInput(orgnrs=["111111111", "222222222"])))
    assert out.risiko_niva == "middels"
    assert out.risiko_score == 7.5
    assert len(out.risiko_indikatorer) == 2
    assert out.felles_personer == [{"navn": "Ola"}]
    assert out.meta["tier_cap"] == 5
    # orgnrs sendes komma-separert til backend
    assert client.last_params == {"orgnrs": "111111111,222222222"}
    # sammendrag nevner antall selskaper + risikonivå + en indikator
    assert "2 selskaper" in out.summary
    assert "middels" in out.summary
    assert "Delt person: Ola" in out.summary


def test_entitlement_error_surfaces_in_meta_not_raised():
    client = _StubClient(raise_exc=FirmaradarClientError("HTTP 403: EXTENSION_NOT_ACTIVE"))
    out = asyncio.run(handle(client, FindSharedConnectionsInput(orgnrs=["111111111", "222222222"])))
    assert out.risiko_niva == "ukjent"
    assert "error" in out.meta
    assert "utilgjengelig" in (out.summary or "").lower()


def test_empty_indicators_summary():
    out = asyncio.run(handle(_StubClient({"selskaper": [{"orgnr": "1"}], "risiko_niva": "lav"}),
                             FindSharedConnectionsInput(orgnrs=["111111111", "222222222"])))
    assert "ingen koblinger" in out.summary
