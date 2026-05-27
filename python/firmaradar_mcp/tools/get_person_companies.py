"""Tool: ``get_person_companies``.

All companies where a person holds shares (current).

Backend status: **EXISTS** — wraps
``GET /api/v1/person/shareholdings/<owner_person_key>`` (see
``src/firmaradar/portal/routes_api.py:363``).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class GetPersonCompaniesInput(BaseModel):
    person_key: str = Field(
        description=(
            "Shareholder key, format `person-YYYY-[24 hex]`. "
            "Obtain from `search_persons` shareholders[] results."
        )
    )
    include_historic: bool = Field(
        default=False,
        description="Reserved for future support; currently only current holdings are returned.",
    )


class Shareholding(BaseModel):
    orgnr: str
    navn: str
    antall_aksjer: int | None = None
    eierandel_prosent: float | None = None


class GetPersonCompaniesOutput(BaseModel):
    person_key: str
    navn: str
    shareholdings: list[Shareholding]
    total_companies: int


async def handle(
    client: FirmaradarClient, params: GetPersonCompaniesInput
) -> GetPersonCompaniesOutput:
    payload = await client.get(
        f"/api/v1/person/shareholdings/{params.person_key}"
    )
    if not isinstance(payload, dict):
        payload = {}
    shareholdings_raw = payload.get("shareholdings") or []
    shareholdings = [
        Shareholding(
            orgnr=str(s.get("orgnr", "")),
            navn=str(s.get("navn", "")),
            antall_aksjer=s.get("antall_aksjer"),
            eierandel_prosent=s.get("eierandel_prosent"),
        )
        for s in shareholdings_raw
    ]
    return GetPersonCompaniesOutput(
        person_key=str(payload.get("person_key", params.person_key)),
        navn=str(payload.get("navn", "")),
        shareholdings=shareholdings,
        total_companies=int(payload.get("total_companies", len(shareholdings))),
    )


HANDLER = ToolHandler(
    name="firmaradar_get_person_companies",
    description=(
        "List all Norwegian companies where the given person holds shares. "
        "Use when the user asks 'what does Person A own?' Pass the "
        "owner_person_key returned by `search_persons`."
    ),
    input_schema=GetPersonCompaniesInput,
    output_schema=GetPersonCompaniesOutput,
    handler=handle,
)
