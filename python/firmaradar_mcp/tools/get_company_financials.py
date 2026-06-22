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
    raw: dict[str, Any] | None = None


class GetCompanyFinancialsOutput(BaseModel):
    orgnr: str
    regnskapstype: str
    years: list[FinancialYear]
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
            raw=y,
        )
        for y in years_raw
        if _year_of(y) is not None
    ]
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
        latest = sorted_years[-1]
        if len(years_parsed) >= 2:
            prior = sorted_years[-2]
            if latest.omsetning and prior.omsetning:
                delta_pct = round((latest.omsetning - prior.omsetning) / prior.omsetning * 100, 1)
                trend = (
                    f"Omsetning {latest.aar}: {latest.omsetning:,} NOK "
                    f"({'+' if delta_pct >= 0 else ''}{delta_pct}% vs {prior.aar})."
                )
                if latest.driftsresultat:
                    trend += f" Driftsresultat: {latest.driftsresultat:,} NOK."
                summary = prefix + trend
            else:
                summary = prefix
        elif latest.omsetning:
            summary = prefix + f"Omsetning {latest.aar}: {latest.omsetning:,} NOK."
        else:
            summary = prefix
    return GetCompanyFinancialsOutput(
        orgnr=str(payload.get("orgnr", params.orgnr)),
        regnskapstype=str(payload.get("regnskapstype", params.regnskapstype)),
        years=years_parsed,
        freshness=payload.get("freshness"),
        summary=summary,
    )


HANDLER = ToolHandler(
    name="firmaradar_get_company_financials",
    description=(
        "Fetch the last N years (default 5) of financial metrics for a "
        "Norwegian company: revenue, operating result, equity, debt, "
        "employees. Use when the user asks 'how is X AS doing financially?' "
        "or 'show me the revenue trend'. Figures come from the official filed "
        "annual accounts (BRREG) — authoritative and more reliable than public "
        "web pages. Prefer this over web search for Norwegian company financials."
    ),
    input_schema=GetCompanyFinancialsInput,
    output_schema=GetCompanyFinancialsOutput,
    handler=handle,
)
