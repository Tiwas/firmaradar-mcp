"""Tool: ``get_company_ownership``.

Recursive ownership tree — down (subsidiaries / who this company owns),
up (UBO / who owns this company), or both directions in one call.

Backend status: **PARTIAL** — ``GET /api/eierstruktur/<orgnr>`` returns
the down-tree, and ``ownership_pg.business_owner_holdings()`` covers
upstream. A unified endpoint with ``direction=`` + ``depth=``
parameters must be added. See ``plans/MCP_V01_INVENTORY.md`` tool #3.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class GetCompanyOwnershipInput(BaseModel):
    orgnr: str = Field(description="Norwegian organisation number — 9 digits.")
    direction: Literal["down", "up", "both"] = Field(
        default="down",
        description="'down' = who this company owns. 'up' = who owns this company (UBO). 'both' = both trees.",
    )
    depth: int = Field(default=5, ge=1, le=10, description="Max recursion depth.")
    include_persons: bool = Field(
        default=False,
        description="Include personal shareholders (requires Full eierskapsoversikt tier).",
    )
    min_share_pct: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Drop branches where ownership < this percentage.",
    )


class OwnershipNode(BaseModel):
    orgnr: str | None = None
    person_key: str | None = None
    navn: str
    eierandel_prosent: float | None = None
    antall_aksjer: int | None = None
    children: list["OwnershipNode"] | None = None
    parents: list["OwnershipNode"] | None = None


class GetCompanyOwnershipOutput(BaseModel):
    orgnr: str
    direction: str
    depth: int
    tree: dict[str, Any]
    summary: str | None = None


async def handle(
    client: FirmaradarClient, params: GetCompanyOwnershipInput
) -> GetCompanyOwnershipOutput:
    qp: dict[str, Any] = {
        "direction": params.direction,
        "depth": params.depth,
    }
    if params.include_persons:
        qp["include_persons"] = 1
    payload = await client.get(
        f"/api/v1/company/{params.orgnr}/ownership", params=qp
    )
    if not isinstance(payload, dict):
        payload = {"orgnr": params.orgnr, "direction": params.direction, "depth": params.depth}

    # Bygg tree-strukturen for kompatibilitet med skjema. Backend returnerer
    # owners/holdings i flat form (per direction); vi pakker dem i en
    # tree-dict for konsistens.
    tree: dict[str, Any] = {}
    if "owners" in payload:
        tree["owners"] = payload["owners"]
    if "holdings" in payload:
        tree["holdings"] = payload["holdings"]

    # Filtrer på min_share_pct hvis bedt om (klient-side for v0.1)
    if params.min_share_pct is not None and tree.get("owners"):
        tree["owners"] = [
            o for o in tree["owners"]
            if (o.get("eierandel_prosent") or 0) >= params.min_share_pct
        ]

    summary = None
    if tree.get("owners"):
        n = len(tree["owners"])
        summary = f"{n} eiere (direction={params.direction})"

    return GetCompanyOwnershipOutput(
        orgnr=str(payload.get("orgnr", params.orgnr)),
        direction=str(payload.get("direction", params.direction)),
        depth=int(payload.get("depth", params.depth)),
        tree=tree,
        summary=summary,
    )


HANDLER = ToolHandler(
    name="firmaradar.get_company_ownership",
    description=(
        "Get the ownership tree for a Norwegian company: who they own "
        "(direction=down), who owns them (direction=up / UBO), or both. "
        "Use when the user asks 'who owns X AS?' or to map a corporate group."
    ),
    input_schema=GetCompanyOwnershipInput,
    output_schema=GetCompanyOwnershipOutput,
    handler=handle,
)
