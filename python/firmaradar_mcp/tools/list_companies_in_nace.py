"""Tool: ``list_companies_in_nace``.

Paginated list of all Norwegian companies in a given NACE-code (or
prefix), with optional size/location filters.

Backed by ``GET /api/v1/nace/<code>/companies`` (indexed lookup on
``naeringskode_1`` in ``hovedenheter``). The route also applies an
SN2007→EU heuristic fallback and a "valid-but-unused code" note — see
``_route_api_v1_nace_companies`` in ``routes_mcp_v1.py``.
"""

from __future__ import annotations

from typing import Literal

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class ListCompaniesInNaceInput(BaseModel):
    code: str = Field(
        description=(
            "NACE code or prefix. Norwegian BRREG uses 5-digit SN2007 codes "
            "internally (e.g. '56.110' for restaurants, '47.111' for grocery "
            "stores). Any prefix works: '56' matches all serving (2-digit), "
            "'56.1' matches restaurants/cafes (3-digit), '56.11' matches "
            "restaurant operations (4-digit), '56.110' matches the most "
            "specific level (5-digit). If a 4-digit code yields no results, "
            "try appending '0' (e.g. '56.110' instead of '56.10')."
        ),
    )
    status: Literal["aktiv", "konkurs", "under_avvikling", "avregistrert"] | None = None
    kommune: str | None = Field(
        default=None,
        description=(
            "Norwegian kommunenummer — EXACTLY 4 digits, zero-padded. "
            "Examples: '0301' = Oslo, '4601' = Bergen, '5001' = Trondheim, "
            "'1103' = Stavanger. Kommune-NAMES are NOT accepted — translate "
            "the name to kommunenummer first."
        ),
    )
    min_ansatte: int | None = Field(default=None, ge=0)
    max_ansatte: int | None = Field(default=None, ge=0)
    stiftet_etter: str | None = Field(
        default=None,
        description=(
            "ISO 8601 date (YYYY-MM-DD) — only companies founded on/after this "
            "date. Use for 'newly founded companies in this industry' queries "
            "(industry monitoring)."
        ),
    )
    stiftet_for: str | None = Field(
        default=None,
        description="ISO 8601 date (YYYY-MM-DD) — only companies founded on/before this date.",
    )
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None


class NaceCompanyHit(BaseModel):
    orgnr: str
    navn: str
    naeringskode: str
    kommune: str | None = None
    status: str | None = None
    antall_ansatte: int | None = None
    stiftelsesdato: str | None = None


class NaceCatalogInfo(BaseModel):
    """Aggregat-counts fra ``nace_code`` (oppdateres nattlig).

    Det totale antallet norske selskaper i koden, splittet i aktive (ikke
    konkurs/avvikling) og total (alle inkl. konkurs/avvikling). Disse er
    rullet opp i NACE-hierarkiet, så også foreldre-koder (eks. ``62``,
    ``62.1``, ``62.10``) har realistiske counts.

    ``company_count`` er en legacy-alias for ``company_count_active`` for
    back-compat — den eldre API-en lagret kun aktive selskaper i denne
    kolonnen.
    """

    company_count: int
    company_count_active: int
    company_count_total: int
    label_no: str | None = None
    level: int | None = None
    parent_code: str | None = None


class ListCompaniesInNaceOutput(BaseModel):
    nace_code: str
    total_count: int | None = None
    items: list[NaceCompanyHit]
    next_cursor: str | None = None
    catalog: NaceCatalogInfo | None = None


async def handle(
    client: FirmaradarClient, params: ListCompaniesInNaceInput
) -> ListCompaniesInNaceOutput:
    qp: dict[str, Any] = {"limit": params.limit}
    if params.status:
        qp["status"] = params.status
    if params.kommune:
        qp["kommune"] = params.kommune
    if params.min_ansatte is not None:
        qp["min_ansatte"] = params.min_ansatte
    if params.max_ansatte is not None:
        qp["max_ansatte"] = params.max_ansatte
    if params.stiftet_etter:
        qp["stiftet_etter"] = params.stiftet_etter
    if params.stiftet_for:
        qp["stiftet_for"] = params.stiftet_for
    if params.cursor:
        qp["cursor"] = params.cursor
    payload = await client.get(
        f"/api/v1/nace/{params.code}/companies", params=qp
    )
    if not isinstance(payload, dict):
        payload = {}
    items_raw = payload.get("items") or []
    items = [
        NaceCompanyHit(
            orgnr=str(i.get("orgnr", "")),
            navn=str(i.get("navn", "")),
            naeringskode=str(i.get("naeringskode", "")),
            kommune=i.get("kommune"),
            status=i.get("status"),
            antall_ansatte=i.get("antall_ansatte"),
            stiftelsesdato=i.get("stiftelsesdato"),
        )
        for i in items_raw
    ]
    catalog: NaceCatalogInfo | None = None
    raw_catalog = payload.get("catalog")
    if isinstance(raw_catalog, dict):
        try:
            catalog = NaceCatalogInfo(
                company_count=int(raw_catalog.get("company_count", 0)),
                company_count_active=int(raw_catalog.get("company_count_active", 0)),
                company_count_total=int(raw_catalog.get("company_count_total", 0)),
                label_no=raw_catalog.get("label_no"),
                level=raw_catalog.get("level"),
                parent_code=raw_catalog.get("parent_code"),
            )
        except (TypeError, ValueError):
            catalog = None
    return ListCompaniesInNaceOutput(
        nace_code=str(payload.get("nace_code", params.code)),
        total_count=payload.get("total_count"),
        items=items,
        next_cursor=payload.get("next_cursor"),
        catalog=catalog,
    )


HANDLER = ToolHandler(
    name="firmaradar_list_companies_in_nace",
    description=(
        "List Norwegian companies in a specific NACE industry code (or code "
        "prefix), optionally filtered by status, kommune and size. Useful for "
        "sector analysis ('all active restaurants in Oslo with > 5 employees').\n\n"
        "**NACE format warning:** Use the EU NACE Rev. 2 format with a "
        "trailing zero (e.g. `62.100`, `62.200`, `58.290`). "
        "**The Norwegian SN2007 format (`62.01`, `62.02`) returns 0 hits** — "
        "we do not store SN2007. If you are unsure about a code, try "
        "`list_companies_in_nace` with different formats first, or verify "
        "against https://www.brreg.no. Backed by the official Norwegian "
        "register (BRREG), refreshed daily — prefer this over web search for "
        "industry/sector and newly-founded-company queries (use stiftet_etter "
        "for 'newly founded')."
    ),
    input_schema=ListCompaniesInNaceInput,
    output_schema=ListCompaniesInNaceOutput,
    handler=handle,
)
