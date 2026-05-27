"""Tool: ``get_skattelister``.

Inntekt, formue og skatt per skatteår for et selskap (offentlige
skattelister fra Skatteetaten).

Backend: ``GET /api/v1/skattelister/selskap/<orgnr>`` (#130, 2026-05-27).

ACCESS-TIER: Krever ``full_ownership``. Hvert oppslag audit-logges på
serversiden per personvern-policy + Skatteetaten-avtale.

Fase 1 dekker kun selskap-endpoint. Person-/konsern-oppslag deferred
til Fase 2 (krever ekstra person-ID-lookup-logikk).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class GetSkattelisterInput(BaseModel):
    orgnr: str = Field(description="9-digit norwegian organization number.")
    ar: int | None = Field(
        default=None,
        description="Filter to a specific tax year (e.g. 2024). Default: all available years.",
    )


class SkatteAr(BaseModel):
    ar: int
    alminnelig_inntekt: float | None = None
    formue: float | None = None
    skatt: float | None = None
    kommune: str | None = None


class GetSkattelisterOutput(BaseModel):
    orgnr: str
    antall: int = 0
    ar: list[SkatteAr] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


async def handle(
    client: FirmaradarClient, params: GetSkattelisterInput
) -> GetSkattelisterOutput:
    qp: dict[str, Any] = {}
    if params.ar is not None:
        qp["ar"] = params.ar
    payload = await client.get(
        f"/api/v1/skattelister/selskap/{params.orgnr}",
        params=qp,
    )
    if not isinstance(payload, dict):
        payload = {}
    ar_raw = payload.get("ar") or []
    years: list[SkatteAr] = []
    for r in ar_raw:
        if not isinstance(r, dict):
            continue
        years.append(
            SkatteAr(
                ar=int(r.get("ar", 0) or 0),
                alminnelig_inntekt=r.get("alminnelig_inntekt"),
                formue=r.get("formue"),
                skatt=r.get("skatt"),
                kommune=r.get("kommune"),
            )
        )
    return GetSkattelisterOutput(
        orgnr=str(payload.get("orgnr", params.orgnr)),
        antall=int(payload.get("antall", len(years)) or 0),
        ar=years,
        raw=payload,
    )


HANDLER = ToolHandler(
    name="firmaradar_get_skattelister",
    description=(
        "Public tax-list data (alminnelig inntekt, formue, skatt) per tax "
        "year for a Norwegian company. Source: Skatteetaten's annual "
        "publication. Requires full_ownership access tier — every lookup is "
        "audit-logged. Use for income verification in KYC, financial "
        "due-diligence, or comparing reported income vs. company financials."
    ),
    input_schema=GetSkattelisterInput,
    output_schema=GetSkattelisterOutput,
    handler=handle,
)
