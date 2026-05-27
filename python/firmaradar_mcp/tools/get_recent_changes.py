"""Tool: ``get_recent_changes``.

Recent changes for either a company (uses ``/changes`` endpoint) or a
person (role + ownership changes — needs new join logic server-side).

Backend status: **PARTIAL** — company-side covered by
``GET /api/v1/company/<orgnr>/changes``; person-side needs new
``GET /api/v1/changes?entity_type=person&id=…&days=N``. See
``plans/MCP_V01_INVENTORY.md`` tool #13.
"""

from __future__ import annotations

from typing import Any, Literal

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class GetRecentChangesInput(BaseModel):
    entity_type: Literal["company", "person"] = Field(
        description="'company' = orgnr; 'person' = person_id."
    )
    id: str = Field(description="Orgnr (9 digits) or person_id depending on entity_type.")
    days: int = Field(default=90, ge=1, le=365)
    category: str | None = Field(
        default=None,
        description="Optional kunngjøring-category filter (konkurs, fusjon, eierbytte, ...).",
    )


class ChangeItem(BaseModel):
    dato: str
    category: str
    summary: str | None = None
    payload: dict[str, Any] | None = None


class GetRecentChangesOutput(BaseModel):
    entity_type: str
    id: str
    since: str
    until: str
    count: int
    items: list[ChangeItem]


async def handle(
    client: FirmaradarClient, params: GetRecentChangesInput
) -> GetRecentChangesOutput:
    now = datetime.now(timezone.utc)
    until = now.date().isoformat()
    since = (now - timedelta(days=params.days)).date().isoformat()

    if params.entity_type == "person":
        # v0.1 begrensning: person-scope krever ny join-endpoint som
        # ikke er bygget enda. Returner tom + hint via summary.
        return GetRecentChangesOutput(
            entity_type="person",
            id=params.id,
            since=since,
            until=until,
            count=0,
            items=[
                ChangeItem(
                    dato=until,
                    category="info",
                    summary=(
                        "Person-scope er ikke støttet i v0.1. Bruk "
                        "get_person_roles / get_person_companies for nåværende "
                        "verv/eierskap. Person-historikk-endpoint er planlagt "
                        "for v0.2 (se plans/MCP_V01_INVENTORY.md tool #13)."
                    ),
                )
            ],
        )

    # Company-scope: bruk eksisterende /changes-endpoint og filtrer
    # klient-side på dato + kategori.
    payload = await client.get(f"/api/v1/company/{params.id}/changes")
    if not isinstance(payload, dict):
        payload = {}
    all_items = payload.get("items") or []
    cutoff = since

    items = []
    for it in all_items:
        item_date = str(it.get("dato", ""))
        if item_date and item_date < cutoff:
            continue
        if params.category and it.get("category") != params.category:
            continue
        items.append(
            ChangeItem(
                dato=item_date,
                category=str(it.get("category", "")),
                summary=it.get("navn") or it.get("kunngjoring_type"),
                payload=it,
            )
        )

    return GetRecentChangesOutput(
        entity_type="company",
        id=params.id,
        since=since,
        until=until,
        count=len(items),
        items=items,
    )


HANDLER = ToolHandler(
    name="firmaradar_get_recent_changes",
    description=(
        "List changes (kunngjøringer for companies; role + ownership "
        "movements for persons) in the last N days. Use when monitoring a "
        "target entity for triggers ('has anything changed for X AS in the "
        "last month?'). Pair with `subscribe_company` for push notifications."
    ),
    input_schema=GetRecentChangesInput,
    output_schema=GetRecentChangesOutput,
    handler=handle,
)
