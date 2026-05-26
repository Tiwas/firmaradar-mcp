"""Tool: ``search_persons``.

Search for persons across shareholders and role-holders by name +
optional birth-year hint.

Backend status: **EXISTS** — wraps ``GET /api/v1/person/search?q=``
(see ``src/firmaradar/portal/routes_api.py:312``). PII-sensitive:
requires ``search_full_enabled`` and applies the V2.5 minor-filter
for non-super-admin callers.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class SearchPersonsInput(BaseModel):
    q: str = Field(min_length=2, description="Name to search (min 2 characters).")
    birth_year: int | None = Field(
        default=None,
        ge=1900,
        le=2100,
        description="Filter on birth year (helps disambiguate common names).",
    )
    kommune_hint: str | None = Field(
        default=None,
        description="Optional kommune name to help disambiguate matches.",
    )
    limit: int = Field(default=30, ge=1, le=100)


class ShareholderHit(BaseModel):
    owner_person_key: str = Field(description="Stable key — pass to `get_person_companies`.")
    owner_name: str
    birth_year: int | None = None
    poststed: str | None = None
    country_code: str | None = None
    shareholding_count: int | None = None


class RolePersonHit(BaseModel):
    role_person_id: str = Field(description="Stable key — pass to `get_person_roles`.")
    name: str
    birth_year: int | None = None
    company_count: int | None = None
    active_company_count: int | None = None


class SearchPersonsOutput(BaseModel):
    query: str
    shareholders: list[ShareholderHit]
    shareholders_count: int
    role_persons: list[RolePersonHit]
    role_persons_count: int


async def handle(
    client: FirmaradarClient, params: SearchPersonsInput
) -> SearchPersonsOutput:
    qp: dict[str, Any] = {"q": params.q, "limit": params.limit}
    if params.birth_year is not None:
        qp["birth_year"] = params.birth_year
    if params.kommune_hint:
        qp["kommune"] = params.kommune_hint
    payload = await client.get("/api/v1/person/search", params=qp)
    if not isinstance(payload, dict):
        payload = {}
    shareholders = [
        ShareholderHit(
            owner_person_key=str(s.get("owner_person_key", "")),
            owner_name=str(s.get("owner_name", "")),
            birth_year=s.get("birth_year"),
            poststed=s.get("poststed"),
            country_code=s.get("country_code"),
            shareholding_count=s.get("shareholding_count"),
        )
        for s in (payload.get("shareholders") or [])
    ]
    role_persons = [
        RolePersonHit(
            role_person_id=str(p.get("role_person_id", "")),
            name=str(p.get("name", "")),
            birth_year=p.get("birth_year"),
            company_count=p.get("company_count"),
            active_company_count=p.get("active_company_count"),
        )
        for p in (payload.get("role_persons") or [])
    ]
    return SearchPersonsOutput(
        query=str(payload.get("query", params.q)),
        shareholders=shareholders,
        shareholders_count=int(payload.get("shareholders_count", len(shareholders))),
        role_persons=role_persons,
        role_persons_count=int(payload.get("role_persons_count", len(role_persons))),
    )


HANDLER = ToolHandler(
    name="firmaradar.search_persons",
    description=(
        "Search for Norwegian persons in the shareholder/role-holder dataset "
        "by name. PII-sensitive — requires the search_full_enabled tier. "
        "Returns separate shareholder and role-holder hit lists with stable "
        "IDs that can be passed to `get_person_companies` and `get_person_roles`."
    ),
    input_schema=SearchPersonsInput,
    output_schema=SearchPersonsOutput,
    handler=handle,
)
