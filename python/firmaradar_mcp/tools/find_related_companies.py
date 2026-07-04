"""Tool: ``find_related_companies``.

Find companies related to a given orgnr via shared person, shared
address, or shared owner-group.

Backend status: **READY** — via=person, via=address AND via=owner backed by
``GET /api/v1/company/<orgnr>/related?via=...``. via=owner traverses the
existing shareholder-book ownership graph (aksjeeierbok / ownership_pg) and
returns companies sharing significant owners (>=10%) with the input company —
same data source and threshold as find_shared_connections' shared-owner
analysis. Full RRH/UBO ultimate-owner traversal (piercing holding structures)
lands when the BRREG RRH scope ships; until then direct shareholder ownership
is used.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class FindRelatedCompaniesInput(BaseModel):
    orgnr: str = Field(description="9-digit orgnr — the company to find relations for.")
    via: Literal["person", "address", "owner"] = Field(
        description=(
            "'person' = shared board members/shareholders. "
            "'address' = same forretningsadresse. "
            "'owner' = shares significant owners (>=10%) via the shareholder-book "
            "ownership graph (heavier — owner-graph traversal)."
        )
    )
    limit: int = Field(default=25, ge=1, le=100)
    min_overlap: int = Field(
        default=1,
        ge=1,
        description="When via=person/owner: minimum number of shared entities to qualify.",
    )


class RelatedCompany(BaseModel):
    orgnr: str
    navn: str
    relation_strength: int = Field(description="Higher = stronger relation.")
    shared_entities: list[dict[str, Any]] = Field(default_factory=list)


class FindRelatedCompaniesOutput(BaseModel):
    orgnr: str
    via: str
    related: list[RelatedCompany]
    total_count: int


async def handle(
    client: FirmaradarClient, params: FindRelatedCompaniesInput
) -> FindRelatedCompaniesOutput:
    qp: dict[str, Any] = {
        "via": params.via,
        "limit": params.limit,
        "min_overlap": params.min_overlap,
    }
    payload = await client.get(
        f"/api/v1/company/{params.orgnr}/related", params=qp
    )
    if not isinstance(payload, dict):
        payload = {}
    related_raw = payload.get("related") or []
    related: list[RelatedCompany] = []
    for r in related_raw:
        if not isinstance(r, dict):
            continue
        related.append(
            RelatedCompany(
                orgnr=str(r.get("orgnr", "")),
                navn=str(r.get("navn", "")),
                relation_strength=int(r.get("relation_strength", 0) or 0),
                shared_entities=r.get("shared_entities", []) or [],
            )
        )
    return FindRelatedCompaniesOutput(
        orgnr=str(payload.get("orgnr", params.orgnr)),
        via=str(payload.get("via", params.via)),
        related=related,
        total_count=int(payload.get("total_count", len(related)) or 0),
    )


HANDLER = ToolHandler(
    name="firmaradar_find_related_companies",
    description=(
        "Find companies related to the given orgnr via shared persons (board "
        "members/shareholders), shared registered address, or shared ultimate "
        "owners. Use for cluster analysis, hidden-relation detection in DD, "
        "or fraud-pattern research."
    ),
    input_schema=FindRelatedCompaniesInput,
    output_schema=FindRelatedCompaniesOutput,
    handler=handle,
)
