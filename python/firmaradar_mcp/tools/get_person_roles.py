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
    # Lars-runde-2-fix 2026-05-26: backend bruker "name" + "companies"
    # (med role_types-array per selskap), ikke "navn" + "roles" som
    # tool-stub antok. Schema-mismatch ga tomt skall for Mette Vonen
    # selv om backend hadde Daglig leder + Varamedlem hos ZERO FIVE.
    companies_raw = payload.get("companies") or payload.get("roles") or []
    # Hver "company" har en rolle-typer-liste — flatten til én rad per
    # (company, role_type) for å passe MCP-tool-skjemaet.
    roles: list[CompanyRole] = []
    for c in companies_raw:
        if not isinstance(c, dict):
            continue
        orgnr = str(c.get("orgnr", ""))
        nav = str(c.get("company_name") or c.get("navn") or "")
        role_types = c.get("role_types") or []
        if not role_types:
            # Backward-compat: hvis "rolle_type" finnes direkte
            single_role = c.get("rolle_type") or c.get("role_type")
            if single_role:
                role_types = [single_role]
        for rt in role_types or [None]:
            roles.append(CompanyRole(
                orgnr=orgnr,
                navn=nav,
                rolle_type=str(rt) if rt else "",
                fra_dato=c.get("fra_dato"),
                til_dato=c.get("til_dato"),
            ))
    return GetPersonRolesOutput(
        role_person_id=str(payload.get("role_person_id", params.role_person_id)),
        navn=str(payload.get("name") or payload.get("navn") or ""),
        roles=roles,
        total_roles=int(payload.get("total_roles", len(roles))),
    )


HANDLER = ToolHandler(
    name="firmaradar_get_person_roles",
    description=(
        "List all company roles (styreleder, daglig leder, etc.) held by a "
        "person, current and historic. Use when the user asks 'what roles "
        "does Person A hold?' Pass the role_person_id returned by `search_persons`."
    ),
    input_schema=GetPersonRolesInput,
    output_schema=GetPersonRolesOutput,
    handler=handle,
)
