"""Tool: ``get_company``.

Full company profile — group structure, owners, grants, recent
announcements and financial-metrics summary in one call.

Backend status: **EXISTS** — wraps ``GET /api/v1/company/<orgnr>``
(see ``src/firmaradar/portal/routes_api.py:251``).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class GetCompanyInput(BaseModel):
    orgnr: str = Field(description="Norwegian organisation number — exactly 9 digits.")
    fields: list[
        Literal[
            "group",
            "owners",
            "business_owners",
            "full_owners",
            "grants",
            "brreg_grants",
            "changes",
            "financial_metrics",
        ]
    ] | None = Field(
        default=None,
        description="Subset of sections to include. Omit to get the default profile.",
    )
    owners: Literal["business", "full"] | None = Field(
        default=None,
        description="Owner-tier requested. 'full' requires Full eierskapsoversikt tier.",
    )
    include_financial_metrics: bool = Field(default=False)


class GetCompanyOutput(BaseModel):
    orgnr: str
    navn: str | None = None
    konsernstruktur: dict[str, Any] | None = None
    eiere: dict[str, Any] | None = None
    tildelinger: dict[str, Any] | None = None
    endringer: list[dict[str, Any]] | None = None
    financial_metrics: dict[str, Any] | None = None
    foretaksklassifisering: dict[str, Any] | None = None
    summary: str | None = Field(
        default=None, description="Human-readable summary (LLM-friendly)."
    )


async def handle(client: FirmaradarClient, params: GetCompanyInput) -> GetCompanyOutput:
    qp: dict[str, Any] = {}
    if params.fields:
        qp["fields"] = ",".join(params.fields)
    if params.owners:
        qp["owners"] = params.owners
    if params.include_financial_metrics:
        qp["financial_metrics"] = 1
    payload = await client.get(f"/api/v1/company/{params.orgnr}", params=qp or None)
    if not isinstance(payload, dict):
        payload = {"orgnr": params.orgnr}
    # Bygg human-readable summary for LLM-vennlig output. Hvis backend
    # returnerer en summary direkte (fremtidig ?include=summary-flag),
    # bruk den. Ellers bygg en minimal lokalt.
    summary = payload.get("summary")
    if not summary and payload.get("navn"):
        parts = [f"{payload['navn']} (orgnr {payload.get('orgnr', params.orgnr)})"]
        klass = (payload.get("foretaksklassifisering") or {}).get("klasse")
        if klass:
            parts.append(f"klassifisert som {klass}")
        summary = " — ".join(parts) + "."
    return GetCompanyOutput(
        orgnr=str(payload.get("orgnr", params.orgnr)),
        navn=payload.get("navn"),
        konsernstruktur=payload.get("konsernstruktur"),
        eiere=payload.get("eiere"),
        tildelinger=payload.get("tildelinger"),
        endringer=payload.get("endringer"),
        financial_metrics=payload.get("financial_metrics"),
        foretaksklassifisering=payload.get("foretaksklassifisering"),
        summary=summary,
    )


HANDLER = ToolHandler(
    name="firmaradar.get_company",
    description=(
        "Fetch the full profile for one Norwegian company by orgnr: name, group "
        "structure, ownership data, grants, recent BRREG announcements and "
        "financial metrics. The primary 'show me this company' tool — use after "
        "`search_companies` returns an orgnr."
    ),
    input_schema=GetCompanyInput,
    output_schema=GetCompanyOutput,
    handler=handle,
)
