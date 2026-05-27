"""Tool: ``list_companies_in_nace``.

Paginated list of all Norwegian companies in a given NACE-code (or
prefix), with optional size/location filters.

Backend status: **GAP** — needs
``GET /api/v1/nace/<code>/companies?status=…&kommune=…&limit=…&cursor=…``
backed by indexed lookup on ``naeringskode_1`` in ``enheter``/
``hovedenheter``. See ``plans/MCP_V01_INVENTORY.md`` tool #14.
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
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None


class NaceCompanyHit(BaseModel):
    orgnr: str
    navn: str
    naeringskode: str
    kommune: str | None = None
    status: str | None = None
    antall_ansatte: int | None = None


class ListCompaniesInNaceOutput(BaseModel):
    nace_code: str
    total_count: int | None = None
    items: list[NaceCompanyHit]
    next_cursor: str | None = None


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
        )
        for i in items_raw
    ]
    return ListCompaniesInNaceOutput(
        nace_code=str(payload.get("nace_code", params.code)),
        total_count=payload.get("total_count"),
        items=items,
        next_cursor=payload.get("next_cursor"),
    )


HANDLER = ToolHandler(
    name="firmaradar_list_companies_in_nace",
    description=(
        "List Norwegian companies in a specific NACE industry code (or code "
        "prefix), optionally filtered by status, kommune and size. Useful for "
        "sector analysis ('all active restaurants in Oslo with > 5 employees')."
    ),
    input_schema=ListCompaniesInNaceInput,
    output_schema=ListCompaniesInNaceOutput,
    handler=handle,
)
