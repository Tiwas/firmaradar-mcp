"""Tool: ``get_person``.

Unified summary for one person — active roles + shareholdings +
AML/PEP risk flags in a single payload.

Backend status: **PARTIAL** — shareholdings and roles each have their
own endpoint, but no aggregate. v0.1 may fan out client-side; a
server-side ``GET /api/v1/person/<id>`` aggregate is recommended for
v0.2. See ``plans/MCP_V01_INVENTORY.md`` tool #8.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient, FirmaradarClientError
from . import ToolHandler


class GetPersonInput(BaseModel):
    person_id: str = Field(
        description=(
            "Person ID — either `person-YYYY-[24 hex]` (from `search_persons` "
            "shareholders) or `role-[24 hex]` (from `search_persons` role_persons)."
        )
    )
    purpose: str | None = Field(
        default=None,
        description=(
            "Purpose-of-processing string for the F10.11 audit trail. "
            "Required when calling against accounts with purpose-confirmation."
        ),
    )


class GetPersonOutput(BaseModel):
    person_id: str
    navn: str
    birth_year: int | None = None
    summary: str | None = None
    active_roles: list[dict[str, Any]] = Field(default_factory=list)
    shareholdings: list[dict[str, Any]] = Field(default_factory=list)
    aml_pep_hits: list[dict[str, Any]] = Field(default_factory=list)


async def handle(
    client: FirmaradarClient, params: GetPersonInput
) -> GetPersonOutput:
    # v0.1: to-call client-side fan-out (Lars-beslutning 2026-05-25).
    # Server-side aggregat utsatt til v0.2 — agenten kaller begge
    # endepunkter selv og vi sammenstiller her.
    pid = params.person_id
    headers_extra: dict[str, str] = {}
    if params.purpose:
        headers_extra["X-FR-Purpose"] = params.purpose

    navn = ""
    birth_year: int | None = None
    active_roles: list[dict[str, Any]] = []
    shareholdings: list[dict[str, Any]] = []

    # Hvilken type ID er det? Avgjør hvilke endepunkter vi kaller.
    is_role = pid.startswith("role-")
    is_shareholder = pid.startswith("person-")

    if is_role:
        try:
            roles_payload = await client.get(f"/api/v1/person/roles/{pid}")
            if isinstance(roles_payload, dict):
                navn = roles_payload.get("navn", "") or navn
                for r in roles_payload.get("roles") or []:
                    # Filtrer på aktive roller (til_dato tom eller framover)
                    if not r.get("til_dato"):
                        active_roles.append(r)
        except FirmaradarClientError:
            pass

    if is_shareholder:
        try:
            sh_payload = await client.get(f"/api/v1/person/shareholdings/{pid}")
            if isinstance(sh_payload, dict):
                navn = sh_payload.get("navn", "") or navn
                shareholdings = list(sh_payload.get("shareholdings") or [])
        except FirmaradarClientError:
            pass

    # Bygg kort summary
    summary_parts = []
    if navn:
        summary_parts.append(navn)
    if active_roles:
        summary_parts.append(f"{len(active_roles)} aktive verv")
    if shareholdings:
        summary_parts.append(f"{len(shareholdings)} aksjeposter")
    summary = ", ".join(summary_parts) if summary_parts else None

    return GetPersonOutput(
        person_id=pid,
        navn=navn,
        birth_year=birth_year,
        summary=summary,
        active_roles=active_roles,
        shareholdings=shareholdings,
        aml_pep_hits=[],  # eget tool, ikke fan-out her — sparer rate-limit
    )


HANDLER = ToolHandler(
    name="firmaradar.get_person",
    description=(
        "Aggregated person profile: name, birth year, active roles, "
        "shareholdings and any AML/PEP risk hits. Strict PII-sensitive — "
        "requires search_full_enabled tier and F10.11 purpose confirmation. "
        "Minors are blocked except for super-admin accounts."
    ),
    input_schema=GetPersonInput,
    output_schema=GetPersonOutput,
    handler=handle,
)
