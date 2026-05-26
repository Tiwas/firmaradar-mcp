"""Tool: ``get_person_roles``.

All company roles (current + historic) held by one person.

Backend status: **EXISTS** — wraps
``GET /api/v1/person/roles/<role_person_id>`` (see
``src/firmaradar/portal/routes_api.py:381``).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class GetPersonRolesInput(BaseModel):
    role_person_id: str = Field(
        description=(
            "Stable role-person ID, format `role-[24 hex chars]`. "
            "Obtain from `search_persons` role_persons[] results."
        )
    )
    include_historic: bool = Field(default=True)


class CompanyRole(BaseModel):
    orgnr: str
    navn: str
    rolle_type: str
    fra_dato: str | None = None
    til_dato: str | None = None


class GetPersonRolesOutput(BaseModel):
    role_person_id: str
    navn: str
    roles: list[CompanyRole]
    total_roles: int


async def handle(
    client: FirmaradarClient, params: GetPersonRolesInput
) -> GetPersonRolesOutput:
    qp = {"include_historic": 1 if params.include_historic else 0}
    payload = await client.get(
        f"/api/v1/person/roles/{params.role_person_id}", params=qp
    )
    if not isinstance(payload, dict):
        payload = {}
    roles_raw = payload.get("roles") or []
    roles = [
        CompanyRole(
            orgnr=str(r.get("orgnr", "")),
            navn=str(r.get("navn", "")),
            rolle_type=str(r.get("rolle_type", "")),
            fra_dato=r.get("fra_dato"),
            til_dato=r.get("til_dato"),
        )
        for r in roles_raw
    ]
    return GetPersonRolesOutput(
        role_person_id=str(payload.get("role_person_id", params.role_person_id)),
        navn=str(payload.get("navn", "")),
        roles=roles,
        total_roles=int(payload.get("total_roles", len(roles))),
    )


HANDLER = ToolHandler(
    name="firmaradar.get_person_roles",
    description=(
        "List all company roles (styreleder, daglig leder, etc.) held by a "
        "person, current and historic. Use when the user asks 'what roles "
        "does Person A hold?' Pass the role_person_id returned by `search_persons`."
    ),
    input_schema=GetPersonRolesInput,
    output_schema=GetPersonRolesOutput,
    handler=handle,
)
