"""handle()-mapping for get_company_financials — backend leverer flere år i
``items``; summary skal ALLTID prefikse med antall år + spenn slik at klienten
ikke feilleser arrayet som «kun 1 år» (QA-funn 2026-06-22)."""
from __future__ import annotations

import asyncio

from firmaradar_mcp.tools.get_company_financials import (
    GetCompanyFinancialsInput,
    handle,
)


class _Stub:
    def __init__(self, payload):
        self._p = payload

    async def get(self, path, params=None):
        return self._p


def _items(years):
    # Nyeste først, slik backend (years_back) leverer.
    return [
        {
            "regnskapsar": y,
            "driftsinntekter": 1_000_000 + (y - 2020) * 500_000,
            "driftsresultat": 100_000,
        }
        for y in years
    ]


def test_parses_all_years_and_prefixes_span():
    payload = {"orgnr": "823107242", "regnskapstype": "SELSKAP",
               "items": _items([2024, 2023, 2022, 2021, 2020])}
    out = asyncio.run(handle(_Stub(payload), GetCompanyFinancialsInput(orgnr="823107242")))
    # Hele arrayet returneres — ikke kun siste år.
    assert len(out.years) == 5
    assert {y.aar for y in out.years} == {2020, 2021, 2022, 2023, 2024}
    # Summary gjør antall år eksplisitt så klienten ikke narraterer «1 år».
    assert out.summary is not None
    assert out.summary.startswith("5 regnskapsår (2020–2024).")


def test_single_year_summary_states_one_year():
    payload = {"orgnr": "111111111", "regnskapstype": "SELSKAP",
               "items": _items([2024])}
    out = asyncio.run(handle(_Stub(payload), GetCompanyFinancialsInput(orgnr="111111111")))
    assert len(out.years) == 1
    assert out.summary is not None and out.summary.startswith("1 regnskapsår (2024).")


def test_empty_items_no_summary():
    out = asyncio.run(handle(_Stub({"orgnr": "111111111", "items": []}),
                             GetCompanyFinancialsInput(orgnr="111111111")))
    assert out.years == []
    assert out.summary is None
