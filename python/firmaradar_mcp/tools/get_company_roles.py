"""Tool: ``get_company_roles``.

Board, daglig leder, signatur, prokura and revisor for a company,
optionally with history.

Backend status: **GAP** — no public endpoint. Needs new
``GET /api/v1/company/<orgnr>/roles?include_historic=true`` route
backed by ``RollerCacheRepository.list_roles_for_company()`` (also new).
See ``plans/MCP_V01_INVENTORY.md`` tool #4.
"""

from __future__ import annotations

from typing import Literal

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


RoleType = Literal[
    "styreleder",
    "styremedlem",
    "varamedlem",
    "daglig_leder",
    "signatur",
    "prokura",
    "revisor",
]


class GetCompanyRolesInput(BaseModel):
    orgnr: str = Field(description="9-digit orgnr.")
    include_historic: bool = Field(
        default=False, description="Include roles that have ended."
    )
    role_type: RoleType | None = Field(
        default=None,
        description="Filter on a single role type. Omit to get all roles.",
    )


class CompanyRole(BaseModel):
    rolle_type: str
    navn: str
    fodselsaar: int | None = None
    fra_dato: str | None = None
    til_dato: str | None = None
    signatur_alene: bool | None = None
    role_person_id: str | None = Field(
        default=None,
        description="Stable ID — pass to `get_person_roles` for more.",
    )


class GetCompanyRolesOutput(BaseModel):
    orgnr: str
    roles: list[CompanyRole]
    total_count: int


async def handle(
    client: FirmaradarClient, params: GetCompanyRolesInput
) -> GetCompanyRolesOutput:
    qp: dict[str, Any] = {}
    if params.include_historic:
        qp["include_historic"] = 1
    if params.role_type:
        qp["role_type"] = params.role_type
    payload = await client.get(
        f"/api/v1/company/{params.orgnr}/roles", params=qp or None
    )
    if not isinstance(payload, dict):
        payload = {}
    roles_raw = payload.get("roles") or []
    roles = [
        CompanyRole(
            rolle_type=str(r.get("rolle_type", "")),
            navn=str(r.get("navn", "")) if r.get("navn") else "",
            fodselsaar=int(r["fodselsaar"]) if r.get("fodselsaar") and str(r["fodselsaar"]).isdigit() else None,
            fra_dato=r.get("fra_dato"),
            til_dato=r.get("til_dato"),
            signatur_alene=r.get("signatur_alene"),
            role_person_id=r.get("role_person_id"),
        )
        for r in roles_raw
    ]
    return GetCompanyRolesOutput(
        orgnr=str(payload.get("orgnr", params.orgnr)),
        roles=roles,
        total_count=int(payload.get("total_count", len(roles))),
    )


HANDLER = ToolHandler(
    name="firmaradar_get_company_roles",
    description=(
        "List board members, daglig leder, signature holders, prokura and "
        "revisor for a Norwegian company. Set include_historic=true for "
        "people who previously held roles. Use when the user asks 'who runs "
        "X AS?' or 'who is on the board?'"
    ),
    input_schema=GetCompanyRolesInput,
    output_schema=GetCompanyRolesOutput,
    handler=handle,
)
