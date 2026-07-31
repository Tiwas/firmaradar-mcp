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


def _payload(orgnr, items, ansatte=None):
    p = {"orgnr": orgnr, "regnskapstype": "SELSKAP", "items": items}
    if ansatte is not None:
        # Slik historikk-endepunktet faktisk bærer nåverdien: injisert i
        # klassifiserings-kriteriene, ikke som eget toppnivå-felt.
        p["foretaksklassifisering"] = {
            "regnskapsloven": {
                "kode": "R:MIK",
                "kriterier": {
                    "inntekter": {"verdi": 1.0, "grense": 5.0, "over": False},
                    "balansesum": {"verdi": 1.0, "grense": 5.0, "over": False},
                    "ansatte": {"verdi": ansatte, "grense": 10, "over": False},
                },
            },
        }
    return p


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


def test_antall_ansatte_naaverdi_per_orgnr_year_matrix_stays_none():
    """`antall_ansatte` finnes ikke per regnskapsår — nåverdien serveres i
    toppnivå-feltet `antall_ansatte` per orgnr (fra klassifiserings-
    kriteriene i payloaden vi allerede henter), og år-matrisen forblir
    None-lister (samme lås som server-side compare — aldri fabrikkert
    som flat år-serie)."""
    stub = _Stub({
        "111111111": _payload("111111111", [_item(2024, 500), _item(2023, 400)], ansatte=42),
        "222222222": _payload("222222222", [_item(2024, 300)], ansatte=7),
    })
    out = asyncio.run(handle(stub, CompareCompaniesInput(orgnrs=["111111111", "222222222"])))
    assert out.antall_ansatte == {"111111111": 42, "222222222": 7}
    # År-matrisen for antall_ansatte er BEVISST null-verdier.
    assert out.comparison["antall_ansatte"] == {
        "111111111": [None, None],
        "222222222": [None, None],
    }
    # De ekte per-år-metric-ene er uberørt av nåverdi-tillegget.
    assert out.comparison["omsetning"]["111111111"] == [400, 500]


def test_antall_ansatte_absent_when_not_requested():
    """Feltet er kun med når metric-en faktisk er bedt om — eksplisitt
    metrics-subset uten antall_ansatte gir None (utelatt), ikke tom dict."""
    stub = _Stub({
        "111111111": _payload("111111111", [_item(2024, 500)], ansatte=42),
    })
    out = asyncio.run(handle(stub, CompareCompaniesInput(
        orgnrs=["111111111"], metrics=["omsetning"],
    )))
    assert out.antall_ansatte is None
    assert "antall_ansatte" not in out.comparison


def test_antall_ansatte_none_when_klassifisering_missing_or_unknown():
    """Selskap uten klassifiserings-kriterier (f.eks. ingen regnskapsår)
    degraderer til None for det selskapet — aldri en exception."""
    stub = _Stub({
        "111111111": _payload("111111111", [_item(2024, 500)], ansatte=42),
        "222222222": _payload("222222222", []),  # ingen klassifisering
        "333333333": {
            "orgnr": "333333333", "items": [_item(2024, 100)],
            "foretaksklassifisering": {"regnskapsloven": {"kode": "R:UKJ", "kriterier": {}}},
        },
    })
    out = asyncio.run(handle(stub, CompareCompaniesInput(
        orgnrs=["111111111", "222222222", "333333333"],
    )))
    assert out.antall_ansatte == {
        "111111111": 42,
        "222222222": None,
        "333333333": None,
    }
