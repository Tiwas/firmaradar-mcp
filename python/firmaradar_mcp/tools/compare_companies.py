"""Tool: ``compare_companies``.

Side-by-side financial comparison of up to 5 companies.

Client-side orchestration: parallel calls to the financials-history
endpoint per orgnr, aligned into year/metric matrices. ``antall_ansatte``
is a current-value register attribute (no per-year history) and is served
as a scalar per orgnr — the same semantics as the server-side
``POST /api/v1/companies/compare`` endpoint.
"""

from __future__ import annotations

from typing import Any

import asyncio
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ..client import FirmaradarClient, FirmaradarClientError
from . import ToolHandler


_STANDARD_METRICS = [
    "omsetning",
    "driftsresultat",
    "aarsresultat",
    "sum_egenkapital",
    "sum_gjeld",
    "antall_ansatte",
]


class CompareCompaniesInput(BaseModel):
    orgnrs: list[str] = Field(
        min_length=1,
        max_length=5,
        description="1-5 orgnr to compare side-by-side.",
    )
    years: int = Field(default=5, ge=1, le=10)
    metrics: list[str] | None = Field(
        default=None,
        description=(
            "Optional subset of metrics: omsetning, driftsresultat, "
            "aarsresultat, sum_egenkapital, sum_gjeld, antall_ansatte. "
            "Omit for the standard set."
        ),
    )


class CompareCompaniesOutput(BaseModel):
    orgnrs: list[str]
    years: list[int]
    comparison: dict[str, dict[str, list[Any]]] = Field(
        description=(
            "{<metric>: {<orgnr>: [<value_per_year>, ...]}}. For "
            "`antall_ansatte` the per-year lists are always null — headcount "
            "does not exist per fiscal year; use the top-level "
            "`antall_ansatte` field instead."
        ),
    )
    antall_ansatte: dict[str, int | None] | None = Field(
        default=None,
        description=(
            "{<orgnr>: <current headcount|null>}. Present only when "
            "`antall_ansatte` is in the requested metric set. CURRENT value "
            "from Enhetsregisteret (the register attribute has no per-year "
            "history), mirroring `companies[].antall_ansatte` on the "
            "server-side compare endpoint. Null when unknown."
        ),
    )
    currencies: dict[str, list[str | None]] | None = Field(
        default=None,
        description=(
            "{<orgnr>: [<ISO 4217 currency per year, aligned with `years`>]}. "
            "None for years without data. Amounts in `comparison` are in the "
            "company's reporting currency for that year (NOK for most "
            "Norwegian companies) — do not compare amounts across different "
            "currencies without converting."
        ),
    )
    computed_at: str
    summary: str | None = None


def _naaverdi_antall_ansatte(payload: dict[str, Any]) -> int | None:
    """Nåværende antall ansatte fra historikk-payloaden vi allerede henter.

    ``antall_ansatte`` finnes ikke per regnskapsår (register-attributt, ikke
    et regnskaps-felt), men backend injiserer nåverdien i payloadens
    ``foretaksklassifisering.<lov>.kriterier.ansatte.verdi``. Å lese den
    derfra koster null ekstra API-kall — samme kilde som `companies[].
    antall_ansatte` på server-side compare-endepunktet. Selskap uten noen
    regnskapsår klassifiseres uten ansatte-tall → None (feltet er da uansett
    tomt over hele linja for det selskapet)."""
    fk = payload.get("foretaksklassifisering")
    if not isinstance(fk, dict):
        return None
    for lov in ("regnskapsloven", "aksjeloven"):
        node = fk.get(lov)
        if not isinstance(node, dict):
            continue
        kriterier = node.get("kriterier")
        if not isinstance(kriterier, dict):
            continue
        ansatte = kriterier.get("ansatte")
        if not isinstance(ansatte, dict):
            continue
        verdi = ansatte.get("verdi")
        if verdi is None or isinstance(verdi, bool):
            continue
        try:
            return int(verdi)
        except (TypeError, ValueError):
            continue
    return None


async def handle(
    client: FirmaradarClient, params: CompareCompaniesInput
) -> CompareCompaniesOutput:
    """v0.1: ren klient-side orkestrering — parallelle kall til
    financials-endepunktet per orgnr, deretter aligner år/metric.
    v0.2 kan introdusere POST /api/v1/companies/compare for server-side
    optimalisering hvis bulk-volum krever det."""
    metrics = params.metrics or _STANDARD_METRICS

    async def _fetch(
        orgnr: str,
    ) -> tuple[str, dict[int, dict[str, Any]], int | None]:
        try:
            payload = await client.get(
                f"/api/regnskap/{orgnr}/historikk",
                params={"years": params.years},
            )
            if not isinstance(payload, dict):
                return orgnr, {}, None
            # Lars-runde-2-fix 2026-05-26: backend bruker "items"/"regnskapsar",
            # ikke "years"/"aar".
            items = payload.get("items") or payload.get("years") or []
            year_map: dict[int, dict[str, Any]] = {}
            for y in items:
                year_val = y.get("regnskapsar") or y.get("aar")
                if year_val is None:
                    continue
                try:
                    year_map[int(year_val)] = y
                except (TypeError, ValueError):
                    continue
            return orgnr, year_map, _naaverdi_antall_ansatte(payload)
        except FirmaradarClientError:
            return orgnr, {}, None

    results = await asyncio.gather(*[_fetch(o) for o in params.orgnrs])
    per_orgnr_data = {orgnr: year_map for orgnr, year_map, _ in results}
    ansatte_naaverdi = {orgnr: ansatte for orgnr, _, ansatte in results}

    # Samle unike år på tvers av alle selskap, sortert.
    all_years_set: set[int] = set()
    for years_map in per_orgnr_data.values():
        all_years_set.update(years_map.keys())
    years_sorted = sorted(all_years_set)

    # Map MCP-tool-metric-navn til backend-feltnavn (BRREG-konvensjon).
    # Lars-runde-2-fix 2026-05-26: backend bruker "driftsinntekter" (ikke
    # "omsetning"), "egenkapital" (ikke "sum_egenkapital").
    # MERK: `antall_ansatte` finnes IKKE i regnskapsår-items — år-matrisen for
    # den metric-en forblir BEVISST None-lister (aldri fabrikkert som flat
    # år-serie av nåverdien). Den brukbare verdien serveres i stedet som
    # NÅVERDI per orgnr i toppnivå-feltet `antall_ansatte` — samme semantikk
    # som server-side compare-endepunktet.
    _METRIC_FIELD_MAP = {
        "omsetning": "driftsinntekter",
        "driftsresultat": "driftsresultat",
        "aarsresultat": "aarsresultat",
        "sum_egenkapital": "egenkapital",
        "sum_gjeld": "sum_gjeld",
        "antall_ansatte": "antall_ansatte",
    }

    # Bygg comparison-matrise: {metric: {orgnr: [verdi per år]}}
    comparison: dict[str, dict[str, list[Any]]] = {}
    for metric in metrics:
        backend_field = _METRIC_FIELD_MAP.get(metric, metric)
        comparison[metric] = {}
        for orgnr in params.orgnrs:
            year_data = per_orgnr_data.get(orgnr, {})
            comparison[metric][orgnr] = [
                year_data.get(y, {}).get(backend_field) for y in years_sorted
            ]

    def _valuta_of(y_item: dict) -> str:
        # Backend leverer beløp i ORIGINALVALUTA per regnskapsår
        # (valuta-fiks 2026-07-14); None/tom betyr NOK (radkonvensjon).
        return str(y_item.get("valuta") or "NOK").strip().upper() or "NOK"

    # Additivt felt: rapporteringsvaluta per orgnr per år (alignet med
    # `years`) — None for år uten data.
    currencies: dict[str, list[str | None]] = {}
    for orgnr in params.orgnrs:
        year_data = per_orgnr_data.get(orgnr, {})
        currencies[orgnr] = [
            _valuta_of(year_data[y]) if y in year_data else None
            for y in years_sorted
        ]

    summary = None
    if years_sorted and per_orgnr_data:
        latest_year = years_sorted[-1]
        omsetninger = [
            (
                o,
                per_orgnr_data.get(o, {}).get(latest_year, {}).get("driftsinntekter") or 0,
                _valuta_of(per_orgnr_data.get(o, {}).get(latest_year, {})),
            )
            for o in params.orgnrs
        ]
        omsetninger.sort(key=lambda t: t[1], reverse=True)
        if omsetninger and omsetninger[0][1]:
            winner_orgnr, winner_amount, winner_ccy = omsetninger[0]
            summary = (
                f"Highest revenue (driftsinntekter / operating income) {latest_year}: "
                f"{winner_orgnr} ({int(winner_amount):,} {winner_ccy})"
            )
            latest_ccys = {
                ccy for o, amount, ccy in omsetninger
                if per_orgnr_data.get(o, {}).get(latest_year) is not None
            }
            if len(latest_ccys) > 1:
                summary += (
                    " — NB: the companies report in different currencies ("
                    + ", ".join(sorted(latest_ccys))
                    + "); amounts are not directly comparable without conversion."
                )

    return CompareCompaniesOutput(
        orgnrs=params.orgnrs,
        years=years_sorted,
        comparison=comparison,
        antall_ansatte=(
            {o: ansatte_naaverdi.get(o) for o in params.orgnrs}
            if "antall_ansatte" in metrics
            else None
        ),
        currencies=currencies or None,
        computed_at=datetime.now(timezone.utc).isoformat(),
        summary=summary,
    )


HANDLER = ToolHandler(
    name="firmaradar_compare_companies",
    description=(
        "Compare key financial metrics of up to 5 Norwegian companies "
        "side-by-side across the last N years (default 5). Use for "
        "competitor analysis, benchmark research or 'which of these three "
        "companies is the strongest?' Amounts are in each company's "
        "reporting currency (see the `currencies` field; NOK for most "
        "Norwegian companies) — check it before comparing absolute amounts. "
        "`antall_ansatte` is a CURRENT-value register attribute with no "
        "per-year history: read it from the top-level `antall_ansatte` field "
        "({orgnr: headcount}); its rows in `comparison` are always null."
    ),
    input_schema=CompareCompaniesInput,
    output_schema=CompareCompaniesOutput,
    handler=handle,
)
