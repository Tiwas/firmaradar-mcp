"""handle()-mapping for compare_companies — valuta-awareness (2026-07-14).

Backend leverer beløp i ORIGINALVALUTA per regnskapsår. Summary hardkodet
tidligere «NOK» (feil for f.eks. Equinor 2024 = USD). Nå: faktisk valuta i
summary, additivt ``currencies``-toppnivåfelt per orgnr/år, og eksplisitt
caveat når selskapene rapporterer i ulik valuta.
"""
from __future__ import annotations

import asyncio

from firmaradar_mcp.tools.compare_companies import (
    CompareCompaniesInput,
    handle,
)


class _Stub:
    """Klient-stub: payload per orgnr (path = /api/regnskap/<orgnr>/historikk)."""

    def __init__(self, per_orgnr: dict):
        self._per_orgnr = per_orgnr

    async def get(self, path, params=None):
        orgnr = path.split("/")[3]
        return self._per_orgnr.get(orgnr, {})


def _payload(orgnr, items):
    return {"orgnr": orgnr, "regnskapstype": "SELSKAP", "items": items}


def _item(ar, innt, valuta=None):
    d = {"regnskapsar": ar, "driftsinntekter": innt}
    if valuta is not None:
        d["valuta"] = valuta
    return d


def test_summary_uses_actual_currency_and_flags_mixed():
    # B (USD) har høyest råbeløp — summary skal si USD, ikke NOK, og
    # advare om at beløpene ikke er direkte sammenlignbare.
    stub = _Stub({
        "111111111": _payload("111111111", [_item(2024, 500_000_000, "NOK")]),
        "222222222": _payload("222222222", [_item(2024, 72_543_000_000, "USD")]),
    })
    out = asyncio.run(handle(stub, CompareCompaniesInput(orgnrs=["111111111", "222222222"])))
    assert out.summary is not None
    assert "72,543,000,000 USD" in out.summary
    assert "different currencies" in out.summary
    assert out.currencies == {
        "111111111": ["NOK"],
        "222222222": ["USD"],
    }


def test_summary_nok_only_without_caveat():
    stub = _Stub({
        "111111111": _payload("111111111", [_item(2024, 500_000, "NOK")]),
        "222222222": _payload("222222222", [_item(2024, 300_000)]),  # None = NOK
    })
    out = asyncio.run(handle(stub, CompareCompaniesInput(orgnrs=["111111111", "222222222"])))
    assert out.summary is not None
    assert "500,000 NOK" in out.summary
    assert "different currencies" not in out.summary
    assert out.currencies == {
        "111111111": ["NOK"],
        "222222222": ["NOK"],
    }


def test_currencies_aligned_with_years_none_for_missing():
    # A har 2023+2024; B kun 2024 → B får None for 2023-slotten.
    stub = _Stub({
        "111111111": _payload("111111111", [
            _item(2024, 150, "NOK"), _item(2023, 100, "NOK"),
        ]),
        "222222222": _payload("222222222", [_item(2024, 120, "USD")]),
    })
    out = asyncio.run(handle(stub, CompareCompaniesInput(orgnrs=["111111111", "222222222"])))
    assert out.years == [2023, 2024]
    assert out.currencies == {
        "111111111": ["NOK", "NOK"],
        "222222222": [None, "USD"],
    }
