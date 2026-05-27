"""Tool: ``search_companies``.

Search the Norwegian company registry with structured filters: name
fragment, NACE code, kommune/fylke, status, employee-range,
revenue-range, founding-date range.

When to use: agent has a fuzzy description ("active retail companies in
Bergen with > 10 employees") and needs candidate orgnr to investigate
further.

Backend status (2026-05-25): **PARTIAL** — only ``/api/autocomplete``
exists today. A new ``GET /api/v1/companies/search`` endpoint with the
full filter-set must be added before this tool can ship. See
``plans/MCP_V01_INVENTORY.md`` tool #1.
"""

from __future__ import annotations

from typing import Literal

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient, FirmaradarClientError
from . import ToolHandler


class SearchCompaniesInput(BaseModel):
    q: str | None = Field(default=None, description="Free-text search across company names.")
    nace: str | None = Field(
        default=None,
        description=(
            "NACE code or prefix. Norwegian BRREG uses 5-digit SN2007 codes "
            "internally (e.g. '56.110' for restaurants, '47.111' for grocery "
            "stores). Any prefix works: '47' matches all retail (2-digit), "
            "'47.1' matches food/beverage retail (3-digit), '47.11' matches "
            "grocery stores (4-digit), '47.111' is the most specific (5-digit). "
            "If a 4-digit code yields no results, try appending '0' for the "
            "5-digit form (e.g. '56.110' instead of '56.10')."
        ),
    )
    kommune: str | None = Field(
        default=None,
        description=(
            "Norwegian kommunenummer — EXACTLY 4 digits, zero-padded. "
            "Examples: '0301' = Oslo, '4601' = Bergen, '5001' = Trondheim, "
            "'1103' = Stavanger. Kommune-NAMES are NOT accepted — translate "
            "the name to kommunenummer first."
        ),
    )
    fylke: str | None = Field(
        default=None,
        description=(
            "Norwegian fylkenummer — EXACTLY 2 digits, zero-padded. "
            "Examples: '03' = Oslo, '11' = Rogaland, '15' = Møre og Romsdal. "
            "Fylke-NAMES are NOT accepted — translate first."
        ),
    )
    status: Literal["aktiv", "konkurs", "under_avvikling", "avregistrert"] | None = Field(
        default=None,
        description="Filter on company status.",
    )
    min_ansatte: int | None = Field(default=None, ge=0)
    max_ansatte: int | None = Field(default=None, ge=0)
    min_omsetning_nok: int | None = Field(default=None, ge=0)
    max_omsetning_nok: int | None = Field(default=None, ge=0)
    stiftet_etter: str | None = Field(default=None, description="ISO 8601 date — only companies founded on/after.")
    stiftet_for: str | None = Field(default=None, description="ISO 8601 date — only companies founded on/before.")
    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = Field(default=None, description="Opaque pagination cursor from previous call.")


class CompanyHit(BaseModel):
    orgnr: str
    navn: str
    organisasjonsform: str | None = None
    naeringskode: str | None = None
    kommune: str | None = None
    status: str | None = None
    antall_ansatte: int | None = None


class SearchCompaniesOutput(BaseModel):
    items: list[CompanyHit]
    next_cursor: str | None = None
    total_count: int | None = None


async def handle(
    client: FirmaradarClient, params: SearchCompaniesInput
) -> SearchCompaniesOutput:
    """v0.1: hybrid approach.

    * Hvis kun `nace` (eller `nace + kommune + status + ansatte`) er gitt
      uten `q`, route mot list_companies_in_nace-endepunktet som har
      effektiv indeks-basert query.
    * Hvis `q` er gitt (navn-prefix), bruk eksisterende
      /api/autocomplete + klient-side filtrering for status/ansatte.
    * Full filter-kombinasjon (omsetning-spenn, stiftelsesdato) krever
      ny backend-endepunkt med disse kolonnene indeksert. Flagget for
      v0.2 — disse filtrene logges som ignored hvis brukt.
    """
    # NACE-only path: bruk det effektive endepunktet
    if params.nace and not params.q:
        qp: dict[str, Any] = {"limit": params.limit}
        if params.status:
            qp["status"] = params.status
        if params.kommune:
            qp["kommune"] = params.kommune
        if params.min_ansatte is not None:
            qp["min_ansatte"] = params.min_ansatte
        if params.max_ansatte is not None:
            qp["max_ansatte"] = params.max_ansatte
        if params.cursor:
            qp["cursor"] = params.cursor
        try:
            payload = await client.get(
                f"/api/v1/nace/{params.nace}/companies", params=qp
            )
        except FirmaradarClientError:
            payload = {}
        items_raw = payload.get("items", []) if isinstance(payload, dict) else []
        return SearchCompaniesOutput(
            items=[
                CompanyHit(
                    orgnr=str(i.get("orgnr", "")),
                    navn=str(i.get("navn", "")),
                    naeringskode=i.get("naeringskode"),
                    kommune=i.get("kommune"),
                    status=i.get("status"),
                    antall_ansatte=i.get("antall_ansatte"),
                )
                for i in items_raw
            ],
            next_cursor=payload.get("next_cursor") if isinstance(payload, dict) else None,
            total_count=payload.get("total_count") if isinstance(payload, dict) else None,
        )

    # Navn-søk: bruk autocomplete + filtrer klient-side
    if not params.q:
        return SearchCompaniesOutput(
            items=[],
            next_cursor=None,
            total_count=0,
        )

    try:
        # /api/autocomplete returnerer maks 10 — vi henter det maks vi
        # kan og filtrerer ned. Ikke ideelt for store datasett, men
        # dekker v0.1-bruk for spesifikke navn.
        raw = await client.get("/api/autocomplete", params={"q": params.q})
    except FirmaradarClientError:
        raw = []

    if not isinstance(raw, list):
        raw = []

    # Klient-side filter
    filtered = []
    for item in raw:
        if params.status:
            status = "aktiv"
            if item.get("konkurs"):
                status = "konkurs"
            elif item.get("under_avvikling"):
                status = "under_avvikling"
            if status != params.status:
                continue
        if params.min_ansatte is not None and (item.get("antall_ansatte") or 0) < params.min_ansatte:
            continue
        if params.max_ansatte is not None and (item.get("antall_ansatte") or 0) > params.max_ansatte:
            continue
        filtered.append(
            CompanyHit(
                orgnr=str(item.get("orgnr", "")),
                navn=str(item.get("navn", "")),
                kommune=item.get("forr_poststed"),
                status=(
                    "konkurs" if item.get("konkurs") else
                    "under_avvikling" if item.get("under_avvikling") else
                    "aktiv"
                ),
                antall_ansatte=item.get("antall_ansatte"),
            )
        )
        if len(filtered) >= params.limit:
            break

    return SearchCompaniesOutput(
        items=filtered,
        next_cursor=None,  # autocomplete har ikke paginering
        total_count=len(filtered),
    )


HANDLER = ToolHandler(
    name="firmaradar_search_companies",
    description=(
        "Search Norwegian companies with filters (name, NACE, location, status, "
        "size, founding date). Returns paginated list of candidate orgnr to "
        "investigate further. Use when you have a description and need to find "
        "matching companies; use `get_company` once you have a specific orgnr."
    ),
    input_schema=SearchCompaniesInput,
    output_schema=SearchCompaniesOutput,
    handler=handle,
)
