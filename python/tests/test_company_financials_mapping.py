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


# ── Valuta-awareness (2026-07-14) ──────────────────────────────────────
# Backend leverer beløp i ORIGINALVALUTA per regnskapsår (Equinor 2024 =
# USD). Summary hardkodet tidligere «NOK»; nå brukes faktisk valuta,
# `valuta` finnes per år og på toppnivå, og YoY-prosent utelates over
# valutaskifte.


def _items_with_valuta(spec):
    """spec: liste av (år, omsetning, valuta|None) — nyeste først."""
    return [
        {
            "regnskapsar": ar,
            "driftsinntekter": omsetning,
            "driftsresultat": 100_000,
            **({"valuta": valuta} if valuta is not None else {}),
        }
        for ar, omsetning, valuta in spec
    ]


def test_mixed_series_marks_valuta_and_skips_yoy_pct():
    # Equinor-lignende: 2024 avlagt i USD, 2022–2023 i NOK.
    payload = {"orgnr": "923609016", "regnskapstype": "SELSKAP",
               "items": _items_with_valuta([
                   (2024, 72_543_000_000, "USD"),
                   (2023, 650_000_000_000, "NOK"),
                   (2022, 600_000_000_000, "NOK"),
               ])}
    out = asyncio.run(handle(_Stub(payload), GetCompanyFinancialsInput(orgnr="923609016")))
    # Toppnivå-felt: blandet serie merkes eksplisitt.
    assert out.valuta == "MIXED"
    # Per-år-felt.
    by_year = {y.aar: y.valuta for y in out.years}
    assert by_year[2024] == "USD"
    assert by_year[2023] == "NOK"
    # Summary: USD for 2024, valutaskifte nevnt, ingen misvisende YoY-%.
    assert out.summary is not None
    assert "72,543,000,000 USD" in out.summary
    assert "blandet regnskapsvaluta" in out.summary
    assert "skiftet fra NOK" in out.summary
    assert "% vs" not in out.summary
    # 2024-beløpet skal aldri merkes NOK.
    assert "72,543,000,000 NOK" not in out.summary


def test_uniform_nok_series_unchanged_contract():
    payload = {"orgnr": "823107242", "regnskapstype": "SELSKAP",
               "items": _items_with_valuta([
                   (2024, 1_050_000, "NOK"),
                   (2023, 1_000_000, None),  # None = NOK (radkonvensjon)
               ])}
    out = asyncio.run(handle(_Stub(payload), GetCompanyFinancialsInput(orgnr="823107242")))
    assert out.valuta == "NOK"
    assert out.summary is not None
    assert "1,050,000 NOK" in out.summary
    assert "+5.0% vs 2023" in out.summary
    assert "blandet" not in out.summary


def test_uniform_foreign_series_uses_actual_currency_with_yoy():
    # Samme valuta i begge år → YoY-prosent er gyldig (valutanøytral).
    payload = {"orgnr": "111111111", "regnskapstype": "SELSKAP",
               "items": _items_with_valuta([
                   (2024, 1_200_000, "USD"),
                   (2023, 1_000_000, "USD"),
               ])}
    out = asyncio.run(handle(_Stub(payload), GetCompanyFinancialsInput(orgnr="111111111")))
    assert out.valuta == "USD"
    assert out.summary is not None
    assert "1,200,000 USD" in out.summary
    assert "+20.0% vs 2023" in out.summary
    assert " NOK" not in out.summary
