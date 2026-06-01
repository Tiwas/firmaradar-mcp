"""Regresjonstest for factors-mappingen i get_aml_score-verktøyet.

Bug (2026-05-31): backend-indikatorene bruker nøklene ``name`` + ``trigger``,
men verktøyet leste ``id`` + ``triggered`` → ``triggered`` var ALLTID False og
``id`` alltid "". Et high-risk selskap så da ut som «ingenting trigget» i den
strukturerte MCP-outputen. Denne testen låser at mappingen leser riktige nøkler.
"""

from __future__ import annotations

import asyncio

from firmaradar_mcp.tools.get_aml_score import GetAmlScoreInput, handle


class _StubClient:
    def __init__(self, payload):
        self._payload = payload

    async def post(self, path, json_body=None, timeout_s=None):
        return self._payload


_PAYLOAD = {
    "orgnr": "989795848",
    "score": 50,
    "level": "medium",
    "rapport_id": "abc",
    "rapport": {
        "indicators": [
            {"name": "Sanksjoner/PEP-match", "weight": 40, "trigger": True,
             "details": "Treff."},
            {"name": "Geografisk risiko", "weight": 10, "trigger": False,
             "details": "NO."},
        ],
    },
}


def test_factors_map_trigger_and_name():
    out = asyncio.run(handle(_StubClient(_PAYLOAD), GetAmlScoreInput(orgnr="989795848")))
    by_name = {f.name: f for f in out.factors}
    # trigger=True skal gi triggered=True (tidligere alltid False):
    assert by_name["Sanksjoner/PEP-match"].triggered is True
    assert by_name["Geografisk risiko"].triggered is False
    # name + id skal være satt (tidligere id alltid ""):
    assert by_name["Sanksjoner/PEP-match"].id == "Sanksjoner/PEP-match"
    assert by_name["Sanksjoner/PEP-match"].weight == 40


def test_factors_backward_compat_triggered_key():
    # Hvis en eldre backend skulle sende `triggered`/`id`, skal det fortsatt virke.
    payload = {
        "orgnr": "1", "score": 0, "level": "low",
        "rapport": {"indicators": [
            {"id": "x", "weight": 5, "triggered": True, "details": "d"},
        ]},
    }
    out = asyncio.run(handle(_StubClient(payload), GetAmlScoreInput(orgnr="000000000")))
    assert out.factors[0].triggered is True
    assert out.factors[0].id == "x"
