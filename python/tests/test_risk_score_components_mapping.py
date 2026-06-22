"""handle()-mapping for get_risk_score + get_risk_score_bulk — backend emitterer
component_id/max_points (ikke id/max); regresjon for QA-funn 2026-06-22 der
toppnivå-components hadde tom id + max=0."""
from __future__ import annotations

import asyncio

from firmaradar_mcp.tools.get_risk_score import GetRiskScoreInput, handle


class _Stub:
    def __init__(self, payload):
        self._p = payload

    async def get(self, path, params=None):
        return self._p


_PAYLOAD = {
    "orgnr": "123456789",
    "score": 20,
    "risk_level": "lav",
    "components": [
        {"component_id": "fiv_status", "label": "FIV", "points": 18, "max_points": 30},
        {"component_id": "egenkapital", "label": "EK", "points": 2, "max_points": 10},
    ],
}


def test_components_map_canonical_backend_keys():
    out = asyncio.run(handle(_Stub(_PAYLOAD), GetRiskScoreInput(orgnr="123456789")))
    c0 = out.components[0]
    assert c0.id == "fiv_status"   # var "" før fiksen (leste c["id"])
    assert c0.max == 30.0          # var 0.0 før fiksen (leste c["max"])
    assert c0.points == 18.0
    assert out.components[1].id == "egenkapital" and out.components[1].max == 10.0
    assert out.level == "lav"


def test_components_fallback_to_legacy_keys():
    # Hvis en eldre backend-variant skulle sende id/max → fortsatt lest.
    payload = {"orgnr": "1", "components": [{"id": "x", "max": 5, "points": 1, "label": "L"}]}
    out = asyncio.run(handle(_Stub(payload), GetRiskScoreInput(orgnr="111111111")))
    assert out.components[0].id == "x" and out.components[0].max == 5.0
