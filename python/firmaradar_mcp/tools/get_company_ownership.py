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


# Hardt tak per gren (owners/holdings) for å unngå multi-MB-svar på svært
# bredt eide/forgrente konsern (f.eks. Equinor `both` ga ~987k tegn og sprengte
# ett MCP-svar). Når en gren overstiger taket beholder vi de N største etter
# eierandel + setter en `truncated`-markør i summary.
_MAX_ENTRIES_PER_BRANCH = 200


def _ownership_pct(node: Any) -> float:
    """Hent eierandel-prosent robust (backend bruker `ownership_pct`; eldre
    klienter/data kan ha `eierandel_prosent`)."""
    if not isinstance(node, dict):
        return 0.0
    value = node.get("ownership_pct")
    if value is None:
        value = node.get("eierandel_prosent")
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _bound_branch(
    entries: list, min_pct: float | None
) -> tuple[list, bool]:
    """Filtrer på min_pct (hvis satt) og kapp til de største N. Returnerer
    ``(liste, truncated)``."""
    out = [o for o in entries if isinstance(o, dict)]
    if min_pct is not None:
        out = [o for o in out if _ownership_pct(o) >= min_pct]
    truncated = len(out) > _MAX_ENTRIES_PER_BRANCH
    if truncated:
        out = sorted(out, key=_ownership_pct, reverse=True)[:_MAX_ENTRIES_PER_BRANCH]
    return out, truncated


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

    # Filtrer på min_share_pct (hvis bedt om) + kapp store grener. owners er en
    # flat liste; holdings kan være en flat liste ELLER en dict med nestet
    # `holdings`-liste — håndter begge.
    notes: list[str] = []
    if isinstance(tree.get("owners"), list):
        tree["owners"], trunc = _bound_branch(tree["owners"], params.min_share_pct)
        if trunc:
            notes.append(f"owners avkortet til de {_MAX_ENTRIES_PER_BRANCH} største (etter eierandel)")
    holdings = tree.get("holdings")
    if isinstance(holdings, list):
        tree["holdings"], trunc = _bound_branch(holdings, params.min_share_pct)
        if trunc:
            notes.append(f"holdings avkortet til de {_MAX_ENTRIES_PER_BRANCH} største")
    elif isinstance(holdings, dict) and isinstance(holdings.get("holdings"), list):
        holdings["holdings"], trunc = _bound_branch(holdings["holdings"], params.min_share_pct)
        if trunc:
            notes.append(f"holdings avkortet til de {_MAX_ENTRIES_PER_BRANCH} største")

    summary = None
    if isinstance(tree.get("owners"), list) and tree["owners"]:
        summary = f"{len(tree['owners'])} eiere (direction={params.direction})"
    if notes:
        summary = ((summary + ". ") if summary else "") + "; ".join(notes)

    return GetCompanyOwnershipOutput(
        orgnr=str(payload.get("orgnr", params.orgnr)),
        direction=str(payload.get("direction", params.direction)),
        depth=int(payload.get("depth", params.depth)),
        tree=tree,
        summary=summary,
    )


HANDLER = ToolHandler(
    name="firmaradar_get_company_ownership",
    description=(
        "Get the ownership tree for a Norwegian company: who they own "
        "(direction=down), who owns them (direction=up / UBO), or both. "
        "Use when the user asks 'who owns X AS?' or to map a corporate group. "
        "Ownership comes from Skatteetaten's Aksjeeierbok (the official "
        "shareholder register) and reflects the latest filed holdings — "
        "authoritative and more current than public web pages. Prefer this "
        "over web search for who-owns-X, corporate-group and subsidiary "
        "questions; do not rely on websites, which are often outdated."
    ),
    input_schema=GetCompanyOwnershipInput,
    output_schema=GetCompanyOwnershipOutput,
    handler=handle,
)
