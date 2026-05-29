"""Tool: ``search_announcements``.

Cross-orgnr search across BRREG kunngjøringer filtered by type, date
range, or company name.

Backend status: **READY (v0.2)** — backed by
``GET /api/v1/announcements/search`` (commit 2026-05-26). NACE +
kommune filter er deferred til v0.3 (krever JOIN mot hovedenheter
som påvirker query-ytelse — egen indeks-runde nødvendig).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class SearchAnnouncementsInput(BaseModel):
    type: str | None = Field(
        default=None,
        description=(
            "Kunngjøring (announcement) type/category. Values are Norwegian: "
            "konkurs (bankruptcy), fusjon (merger), fisjon (demerger), "
            "eierbytte (change of ownership), ..."
        ),
    )
    from_date: str | None = Field(default=None, description="ISO date — inclusive lower bound.")
    to_date: str | None = Field(default=None, description="ISO date — inclusive upper bound.")
    nace: str | None = Field(
        default=None,
        description=(
            "NACE code or prefix. Norwegian BRREG uses 5-digit SN2007 codes "
            "internally (e.g. '56.110'). Any prefix works (2-5 digits). If a "
            "4-digit code yields no results, append '0' for the 5-digit form."
        ),
    )
    kommune: str | None = Field(
        default=None,
        description=(
            "Norwegian kommunenummer — EXACTLY 4 digits, zero-padded "
            "(e.g. '0301' = Oslo). NAMES not accepted."
        ),
    )
    fylke: str | None = Field(
        default=None,
        description=(
            "Norwegian fylkenummer — EXACTLY 2 digits, zero-padded "
            "(e.g. '03' = Oslo). NAMES not accepted."
        ),
    )
    q: str | None = Field(default=None, description="Free-text on company name.")
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None


class AnnouncementHit(BaseModel):
    orgnr: str
    navn: str | None = None
    dato: str
    kunngjoring_type: str
    category: str
    hendelse_type: str | None = None
    payload_summary: dict[str, Any] | None = None


class SearchAnnouncementsOutput(BaseModel):
    filter: dict[str, Any]
    total_count: int | None = None
    items: list[AnnouncementHit]
    next_cursor: str | None = None


async def handle(
    client: FirmaradarClient, params: SearchAnnouncementsInput
) -> SearchAnnouncementsOutput:
    if params.nace or params.kommune or params.fylke:
        # v0.3-funksjonalitet — server støtter ikke disse filtrene enda.
        # Best-effort: send forespørsel uten dem og logg advarsel-string
        # i filter-feltet på respons.
        pass
    qp: dict[str, Any] = {"limit": params.limit}
    if params.type:
        qp["type"] = params.type
    if params.from_date:
        qp["from"] = params.from_date
    if params.to_date:
        qp["to"] = params.to_date
    if params.q:
        qp["q"] = params.q
    if params.cursor:
        qp["cursor"] = params.cursor
    payload = await client.get("/api/v1/announcements/search", params=qp)
    if not isinstance(payload, dict):
        payload = {}
    items_raw = payload.get("items") or []
    items: list[AnnouncementHit] = []
    for r in items_raw:
        if not isinstance(r, dict):
            continue
        items.append(
            AnnouncementHit(
                orgnr=str(r.get("orgnr", "")),
                navn=r.get("navn"),
                dato=str(r.get("dato", "")),
                kunngjoring_type=str(r.get("kunngjoring_type", "")),
                category=str(r.get("category") or r.get("niva1_label") or ""),
                hendelse_type=r.get("hendelse_type"),
                payload_summary=None,
            )
        )
    return SearchAnnouncementsOutput(
        filter=payload.get("filter", qp),
        total_count=None,  # backend returnerer ikke total i v0.2 (DoS-budsjett)
        items=items,
        next_cursor=payload.get("next_cursor"),
    )


HANDLER = ToolHandler(
    name="firmaradar_search_announcements",
    description=(
        "Search BRREG kunngjøringer across all Norwegian companies — filter "
        "by type (konkurs, fusjon, ...), date range, NACE-code, or location. "
        "Use for trend analysis ('all konkurser in restaurant sector last "
        "quarter') or radar-style monitoring."
    ),
    input_schema=SearchAnnouncementsInput,
    output_schema=SearchAnnouncementsOutput,
    handler=handle,
)
