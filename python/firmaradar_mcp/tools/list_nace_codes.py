"""Tool: ``list_nace_codes``.

Search / browse the Norwegian NACE industry-code catalogue so an agent
can resolve the exact code needed before subscribing to industry
monitoring (``subscribe_nace``) or listing companies
(``list_companies_in_nace``).

Backed by ``GET /api/v1/nace/catalog`` (API-key accessible mirror of the
session-only autocomplete used by the portal NACE-picker). Search modes
(priority ``eu`` > ``parent`` > ``q`` > top-level):

* ``q``      — free-text search on the Norwegian label (full-text).
* ``parent`` — direct children of a code (hierarchy walk).
* ``eu``     — EU NACE Rev. 2 code → the Norwegian level-5 sub-codes the
  register actually stores (e.g. ``47.11`` → ``47.110``).
* neither    — top-level sections (A–U).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class ListNaceCodesInput(BaseModel):
    q: str | None = Field(
        default=None,
        description=(
            "Free-text search on the Norwegian industry label (e.g. "
            "'restaurant', 'programvare', 'bygg'). Returns the best-matching "
            "NACE codes ranked by relevance."
        ),
    )
    parent: str | None = Field(
        default=None,
        description=(
            "Return the direct children of this code to drill down the "
            "hierarchy: a section letter ('G'), a 2-digit group ('47'), a "
            "3-digit ('47.1') or 4-digit ('47.11') code. Omit to list the "
            "top-level sections (A–U)."
        ),
    )
    eu: str | None = Field(
        default=None,
        description=(
            "An EU NACE Rev. 2 code (e.g. '47.11', '62.01') — returns the "
            "Norwegian 5-digit sub-codes the register actually uses. Use this "
            "when you have an EU/international code and need the Norwegian "
            "equivalent before subscribing or listing companies."
        ),
    )
    limit: int = Field(default=50, ge=1, le=200)


class NaceCodeHit(BaseModel):
    code: str = Field(description="Norwegian NACE code, e.g. '47.110' or section letter 'G'.")
    code_short: str | None = Field(
        default=None,
        description="4-digit BRREG-format variant of the code (e.g. '47.11').",
    )
    label_no: str | None = Field(default=None, description="Norwegian industry label.")
    label_en: str | None = Field(
        default=None,
        description="English industry label (from SSB Klass), when available.",
    )
    parent_code: str | None = None
    level: int | None = Field(
        default=None,
        description="Hierarchy level: 1=section, 2=group, 3, 4, 5=most specific.",
    )
    company_count: int = Field(
        default=0,
        description="Active companies with this code (legacy alias for company_count_active).",
    )
    company_count_active: int = 0
    company_count_total: int = 0
    has_children: bool = Field(
        default=False,
        description="True if the code can be drilled into with `parent`=this code.",
    )


class ListNaceCodesOutput(BaseModel):
    items: list[NaceCodeHit]
    count: int


async def handle(
    client: FirmaradarClient, params: ListNaceCodesInput
) -> ListNaceCodesOutput:
    qp: dict[str, Any] = {"limit": params.limit}
    if params.q:
        qp["q"] = params.q
    if params.parent:
        qp["parent"] = params.parent
    if params.eu:
        qp["eu"] = params.eu
    payload = await client.get("/api/v1/nace/catalog", params=qp)
    if not isinstance(payload, dict):
        payload = {}
    items_raw = payload.get("items") or []
    items = [
        NaceCodeHit(
            code=str(i.get("code", "")),
            code_short=i.get("code_short"),
            label_no=i.get("label_no"),
            label_en=i.get("label_en"),
            parent_code=i.get("parent_code"),
            level=i.get("level"),
            company_count=int(i.get("company_count", 0) or 0),
            company_count_active=int(i.get("company_count_active", 0) or 0),
            company_count_total=int(i.get("company_count_total", 0) or 0),
            has_children=bool(i.get("has_children", False)),
        )
        for i in items_raw
        if isinstance(i, dict)
    ]
    return ListNaceCodesOutput(items=items, count=int(payload.get("count", len(items))))


HANDLER = ToolHandler(
    name="firmaradar_list_nace_codes",
    description=(
        "Search and browse the Norwegian NACE industry-code catalogue. Use "
        "this to resolve the exact code before calling subscribe_nace "
        "(industry monitoring) or list_companies_in_nace. Free-text search "
        "with `q` ('restaurant', 'programvare'), drill the hierarchy with "
        "`parent` (omit for the top-level sections A–U), or convert an EU "
        "NACE Rev. 2 code to the Norwegian 5-digit sub-codes with `eu`. Each "
        "hit includes the Norwegian and (when available) English label plus "
        "company counts. Backed by the official catalogue (SSB/BRREG), "
        "refreshed daily."
    ),
    input_schema=ListNaceCodesInput,
    output_schema=ListNaceCodesOutput,
    handler=handle,
)
