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


def test_distress_category_maps_backend_status_literals():
    """Backend bruker 'not_distressed' (ikke 'no_distress') — QA-funn 2026-06-22 der
    not_distressed feilaktig ble 'unknown' og motsa get_risk_score."""
    cases = {
        "not_distressed": "green",
        "distressed": "red",
        # «partial»-verdiktet er fortsatt «ikke i vanskeligheter» → grønt, så det
        # matcher get_risk_score (0 distress-poeng) for samme selskap. QA-funn
        # 2026-06-22 re-verifisering: gul motsa grønn i risk_score.
        "not_distressed_partial": "green",
        "requires_manual_review": "yellow",
        "insufficient_data": "unknown",
        "exempt_young_company": "green",
    }
    for status, expected in cases.items():
        out = asyncio.run(handle(
            _StubClient({"orgnr": "923609016", "distress": {"status": status, "score": 0.1}}),
            GetCompanySignalsInput(orgnr="923609016"),
        ))
        assert out.distress_category == expected, f"{status} → {out.distress_category} (forventet {expected})"


def test_partial_not_distressed_gets_clarifying_reason():
    """Grønn «partial»-vurdering uten fyrte regler skal få en forklaring i
    distress_reasons (QA-funn 2026-06-22: «yellow uten distress_reasons» var rart)."""
    out = asyncio.run(handle(
        _StubClient({"orgnr": "823107242", "distress": {"status": "not_distressed_partial"}}),
        GetCompanySignalsInput(orgnr="823107242"),
    ))
    assert out.distress_category == "green"
    assert out.distress_reasons and "delvise regnskapsdata" in out.distress_reasons[0]
