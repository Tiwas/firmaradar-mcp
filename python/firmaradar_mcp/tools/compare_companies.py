"""Tool: ``compare_companies``.

Side-by-side financial comparison of up to 5 companies.

Backend status: **GAP** — needs ``POST /api/v1/companies/compare`` to
orchestrate parallel calls to
``financial_metrics_history_payload()`` and return aligned year/metric
matrices. See ``plans/MCP_V01_INVENTORY.md`` tool #16.
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
        description="{<metric>: {<orgnr>: [<value_per_year>, ...]}}",
    )
    computed_at: str
    summary: str | None = None


async def handle(
    client: FirmaradarClient, params: CompareCompaniesInput
) -> CompareCompaniesOutput:
    """v0.1: ren klient-side orkestrering — parallelle kall til
    financials-endepunktet per orgnr, deretter aligner år/metric.
    v0.2 kan introdusere POST /api/v1/companies/compare for server-side
    optimalisering hvis bulk-volum krever det."""
    metrics = params.metrics or _STANDARD_METRICS

    async def _fetch(orgnr: str) -> tuple[str, dict[int, dict[str, Any]]]:
        try:
            payload = await client.get(
                f"/api/regnskap/{orgnr}/historikk",
                params={"years": params.years},
            )
            if not isinstance(payload, dict):
                return orgnr, {}
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
            return orgnr, year_map
        except FirmaradarClientError:
            return orgnr, {}

    results = await asyncio.gather(*[_fetch(o) for o in params.orgnrs])
    per_orgnr_data = dict(results)

    # Samle unike år på tvers av alle selskap, sortert.
    all_years_set: set[int] = set()
    for years_map in per_orgnr_data.values():
        all_years_set.update(years_map.keys())
    years_sorted = sorted(all_years_set)

    # Map MCP-tool-metric-navn til backend-feltnavn (BRREG-konvensjon).
    # Lars-runde-2-fix 2026-05-26: backend bruker "driftsinntekter" (ikke
    # "omsetning"), "egenkapital" (ikke "sum_egenkapital").
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

    summary = None
    if years_sorted and per_orgnr_data:
        latest_year = years_sorted[-1]
        omsetninger = [
            (o, per_orgnr_data.get(o, {}).get(latest_year, {}).get("driftsinntekter") or 0)
            for o in params.orgnrs
        ]
        omsetninger.sort(key=lambda t: t[1], reverse=True)
        if omsetninger and omsetninger[0][1]:
            summary = f"Største omsetning (driftsinntekter) {latest_year}: {omsetninger[0][0]} ({int(omsetninger[0][1]):,} NOK)"

    return CompareCompaniesOutput(
        orgnrs=params.orgnrs,
        years=years_sorted,
        comparison=comparison,
        computed_at=datetime.now(timezone.utc).isoformat(),
        summary=summary,
    )


HANDLER = ToolHandler(
    name="firmaradar_compare_companies",
    description=(
        "Compare key financial metrics of up to 5 Norwegian companies "
        "side-by-side across the last N years (default 5). Use for "
        "competitor analysis, benchmark research or 'which of these three "
        "companies is the strongest?'"
    ),
    input_schema=CompareCompaniesInput,
    output_schema=CompareCompaniesOutput,
    handler=handle,
)
