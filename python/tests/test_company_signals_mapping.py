"""handle()-mapping for get_company_signals — nye hiring/fusjon/frivillighet-felt
passerer gjennom som dict, og {"error": ...}-konvolutter droppes til None."""
from __future__ import annotations

import asyncio

from firmaradar_mcp.tools.get_company_signals import (
    GetCompanySignalsInput,
    handle,
)


class _StubClient:
    def __init__(self, payload):
        self._payload = payload

    async def get(self, path, params=None):
        return self._payload


_PAYLOAD = {
    "orgnr": "928429210",
    "distress": {"status": "no_distress", "score": 0.1},
    "kyc_signals": {"signals": []},
    "hiring": {"active_postings": 3, "is_hiring_burst": True, "source": "nav_arbeidsplassen"},
    "fusjon": {"inbound": [{"orgnr": "111111111"}], "outbound": [], "has_any": True},
    "frivillighet": {"registered": True, "registreringsdato": "2013-08-24"},
}


def test_maps_hiring_fusjon_frivillighet():
    out = asyncio.run(handle(_StubClient(_PAYLOAD), GetCompanySignalsInput(orgnr="928429210")))
    assert out.hiring is not None and out.hiring["is_hiring_burst"] is True
    assert out.fusjon is not None and out.fusjon["has_any"] is True
    assert out.frivillighet is not None and out.frivillighet["registered"] is True


def test_drops_error_envelopes_to_none():
    payload = {
        "orgnr": "000000000",
        "hiring": {"error": "x"},
        "fusjon": {"error": "x"},
        "frivillighet": {"error": "x"},
    }
    out = asyncio.run(handle(_StubClient(payload), GetCompanySignalsInput(orgnr="000000000")))
    assert out.hiring is None
    assert out.fusjon is None
    assert out.frivillighet is None


def test_omitted_sources_are_none():
    out = asyncio.run(handle(_StubClient({"orgnr": "000000000"}), GetCompanySignalsInput(orgnr="000000000")))
    assert out.hiring is None
    assert out.fusjon is None
    assert out.frivillighet is None
