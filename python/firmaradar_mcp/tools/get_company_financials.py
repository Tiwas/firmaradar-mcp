"""Tool: ``get_company_financials``.

Historic financial metrics (omsetning, driftsresultat, ek, gjeld,
antall ansatte) for a company. Defaults to the last 5 years.

Backend status: **EXISTS** — wraps
``GET /api/regnskap/<orgnr>/historikk?years=5`` (see
``src/firmaradar/portal/routes_search.py:763``).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class GetCompanyFinancialsInput(BaseModel):
    orgnr: str = Field(description="9-digit orgnr.")
    years: int = Field(default=5, ge=1, le=20)
    regnskapstype: Literal["SELSKAP", "KONSERN"] = Field(default="SELSKAP")
    skip_freshness: bool = Field(
        default=False,
        description="Skip the inline freshness fetch (faster, but may return stale data).",
    )


class FinancialYear(BaseModel):
    aar: int
    omsetning: int | None = None
    driftsresultat: int | None = None
    aarsresultat: int | None = None
    sum_egenkapital: int | None = None
    sum_gjeld: int | None = None
    antall_ansatte: int | None = None
    valuta: str | None = Field(
        default=None,
        description="Reporting currency for this year (ISO 4217). None means NOK.",
    )
    raw: dict[str, Any] | None = None


class GetCompanyFinancialsOutput(BaseModel):
    orgnr: str
    regnskapstype: str
    years: list[FinancialYear]
    valuta: str | None = Field(
        default=None,
        description=(
            "Reporting currency across the series (ISO 4217, e.g. 'NOK' or "
            "'USD'). 'MIXED' when the years are filed in different "
            "currencies — then check valuta per year before comparing "
            "amounts across years."
        ),
    )
    freshness: dict[str, Any] | None = None
    summary: str | None = None


async def handle(
    client: FirmaradarClient, params: GetCompanyFinancialsInput
) -> GetCompanyFinancialsOutput:
    qp: dict[str, Any] = {
        "years": params.years,
        "regnskapstype": params.regnskapstype,
    }
    if params.skip_freshness:
        qp["skip_freshness"] = 1
    payload = await client.get(
        f"/api/regnskap/{params.orgnr}/historikk", params=qp
    )
    if not isinstance(payload, dict):
        payload = {}
    # Lars-runde-2-fix 2026-05-26: backend bruker "items" + "regnskapsar"
    # + "driftsinntekter" — ikke "years"/"aar"/"omsetning" som tool-stub
    # antok. Schema-mismatch ga `years: []` selv om data fantes (525 MNOK
    # omsetning verifisert for Peppes Pizza 984388659).
    years_raw = (
        payload.get("items")
        or payload.get("years")  # backward-compat hvis backend endrer
        or []
    )
    def _year_of(y: dict) -> int | None:
        for key in ("regnskapsar", "aar", "year"):
            val = y.get(key)
            if val is not None:
                try:
                    return int(val)
                except (TypeError, ValueError):
                    pass
        return None
    def _valuta_of(y: dict) -> str | None:
        # Backend leverer `valuta` per regnskapsår (originalvaluta —
        # Equinor 2024 er f.eks. USD). None/tom betyr NOK (radkonvensjon).
        val = str(y.get("valuta") or "").strip().upper()
        return val or None
    years_parsed = [
        FinancialYear(
            aar=_year_of(y) or 0,
            omsetning=int(y["driftsinntekter"]) if y.get("driftsinntekter") is not None else (y.get("omsetning") or None),
            driftsresultat=int(y["driftsresultat"]) if y.get("driftsresultat") is not None else None,
            aarsresultat=int(y["aarsresultat"]) if y.get("aarsresultat") is not None else None,
            sum_egenkapital=(
                int(y["egenkapital"]) if y.get("egenkapital") is not None
                else (int(y["sum_egenkapital"]) if y.get("sum_egenkapital") is not None else None)
            ),
            sum_gjeld=int(y["sum_gjeld"]) if y.get("sum_gjeld") is not None else None,
            antall_ansatte=y.get("antall_ansatte"),
            valuta=_valuta_of(y),
            raw=y,
        )
        for y in years_raw
        if _year_of(y) is not None
    ]
    # Effektiv valuta per år (None = NOK) + serie-nivå: én kode når hele
    # serien er i samme valuta, «MIXED» ved blandet serie (valuta-fiks
    # 2026-07-14 — summary hardkodet tidligere NOK, feil for f.eks.
    # Equinor 2024 = USD).
    series_currencies = {(y.valuta or "NOK") for y in years_parsed}
    series_valuta: str | None = None
    if series_currencies:
        series_valuta = next(iter(series_currencies)) if len(series_currencies) == 1 else "MIXED"
    # Bygg kort utviklings-summary. Prefiks ALLTID med antall år + spennet, slik at
    # klienten ikke feilleser `years`-arrayet som «kun 1 år» (QA-funn 2026-06-22:
    # flere klienter narraterte bare siste-år-linja og rapporterte 1 år selv om
    # 5 år lå i structuredContent.years).
    summary = None
    if years_parsed:
        sorted_years = sorted(years_parsed, key=lambda y: y.aar)
        lo, hi = sorted_years[0].aar, sorted_years[-1].aar
        span = f"{lo}–{hi}" if lo != hi else f"{hi}"
        prefix = f"{len(years_parsed)} regnskapsår ({span}). "
        if series_valuta == "MIXED":
            prefix += (
                "NB: blandet regnskapsvaluta i serien ("
                + ", ".join(sorted(series_currencies))
                + ") — sjekk valuta per år før beløp sammenlignes. "
            )
        latest = sorted_years[-1]
        latest_ccy = latest.valuta or "NOK"
        if len(years_parsed) >= 2:
            prior = sorted_years[-2]
            prior_ccy = prior.valuta or "NOK"
            if latest.omsetning and prior.omsetning and latest_ccy == prior_ccy:
                delta_pct = round((latest.omsetning - prior.omsetning) / prior.omsetning * 100, 1)
                trend = (
                    f"Omsetning {latest.aar}: {latest.omsetning:,} {latest_ccy} "
                    f"({'+' if delta_pct >= 0 else ''}{delta_pct}% vs {prior.aar})."
                )
                if latest.driftsresultat:
                    trend += f" Driftsresultat: {latest.driftsresultat:,} {latest_ccy}."
                summary = prefix + trend
            elif latest.omsetning and prior.omsetning:
                # Valutaskifte mellom de to siste årene — YoY-prosent på
                # rå originalvaluta-tall ville vært misvisende. Utelates.
                trend = (
                    f"Omsetning {latest.aar}: {latest.omsetning:,} {latest_ccy} "
                    f"(regnskapsvaluta skiftet fra {prior_ccy} i {prior.aar} — "
                    f"YoY-prosent utelatt)."
                )
                if latest.driftsresultat:
                    trend += f" Driftsresultat: {latest.driftsresultat:,} {latest_ccy}."
                summary = prefix + trend
            else:
                summary = prefix
        elif latest.omsetning:
            summary = prefix + f"Omsetning {latest.aar}: {latest.omsetning:,} {latest_ccy}."
        else:
            summary = prefix
    return GetCompanyFinancialsOutput(
        orgnr=str(payload.get("orgnr", params.orgnr)),
        regnskapstype=str(payload.get("regnskapstype", params.regnskapstype)),
        years=years_parsed,
        valuta=series_valuta,
        freshness=payload.get("freshness"),
        summary=summary,
    )


HANDLER = ToolHandler(
    name="firmaradar_get_company_financials",
    description=(
        "Fetch the last N years (default 5) of financial metrics for a "
        "Norwegian company: revenue, operating result, equity, debt, "
        "employees. Use when the user asks 'how is X AS doing financially?' "
        "or 'show me the revenue trend'. Figures come from the official annual "
        "accounts filed with BRREG. "
        "Amounts are in the company's reporting currency — check the `valuta` "
        "field (NOK for most companies, but e.g. USD for some international "
        "groups; 'MIXED' means the currency changed within the series)."
    ),
    input_schema=GetCompanyFinancialsInput,
    output_schema=GetCompanyFinancialsOutput,
    handler=handle,
)
