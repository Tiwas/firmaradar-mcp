"""Tool: ``get_company_announcements``.

BRREG kunngjøringer (announcements) for a single company: konkurs,
fusjon, fisjon, eierbytte, address changes, name changes, etc.

Backend status: **EXISTS** — wraps
``GET /api/v1/company/<orgnr>/changes`` (see
``src/firmaradar/portal/routes_api.py:236``).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class GetCompanyAnnouncementsInput(BaseModel):
    orgnr: str = Field(description="9-digit orgnr.")


class Announcement(BaseModel):
    dato: str = Field(description="ISO 8601 date (YYYY-MM-DD).")
    kunngjoring_type: str = Field(description="Raw BRREG label, e.g. 'Konkursåpning'.")
    category: str = Field(
        description="Normalised category: 'konkurs', 'fusjon', 'fisjon', 'eierbytte', 'aarsregnskap', ..."
    )
    hendelse_type: str | None = None
    navn: str | None = None


class GetCompanyAnnouncementsOutput(BaseModel):
    orgnr: str
    count: int
    items: list[Announcement]


def _wrap_untrusted(text: str | None) -> str | None:
    """Wrap free-text BRREG fields i untrusted-content-marker for å
    minimere prompt-injection-risiko fra eksterne kilder.
    AGENTIC_PLATFORM_PLAN § 0.8 punkt 9.
    """
    if not text:
        return text
    return f"<untrusted_content>{text}</untrusted_content>"


async def handle(
    client: FirmaradarClient, params: GetCompanyAnnouncementsInput
) -> GetCompanyAnnouncementsOutput:
    payload = await client.get(f"/api/v1/company/{params.orgnr}/changes")
    if not isinstance(payload, dict):
        payload = {}
    items_raw = payload.get("items") or []
    items = [
        Announcement(
            dato=str(item.get("dato", "")),
            kunngjoring_type=str(item.get("kunngjoring_type", "")),
            category=str(item.get("category", "")),
            hendelse_type=item.get("hendelse_type"),
            navn=_wrap_untrusted(item.get("navn")),
        )
        for item in items_raw
    ]
    return GetCompanyAnnouncementsOutput(
        orgnr=str(payload.get("orgnr", params.orgnr)),
        count=int(payload.get("count", len(items))),
        items=items,
    )


HANDLER = ToolHandler(
    name="firmaradar_get_company_announcements",
    description=(
        "List BRREG kunngjøringer (official announcements) for a Norwegian "
        "company: bankruptcy, mergers, demergers, ownership changes, address "
        "changes, etc. Free-text fields are wrapped in <untrusted_content> "
        "tags to prevent prompt injection from BRREG-sourced text."
    ),
    input_schema=GetCompanyAnnouncementsInput,
    output_schema=GetCompanyAnnouncementsOutput,
    handler=handle,
)
