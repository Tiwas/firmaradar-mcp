"""Tool: ``get_risk_score``.

Strukturert risikoscore (0-100) + nivå (lav/moderat/høy/kritisk) +
komponent-breakdown for et selskap.

Backend: ``GET /api/v1/risikoscoring/score/<orgnr>`` (#130, 2026-05-27)
som internt invocerer ``risikoscoring``-extensionen.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class GetRiskScoreInput(BaseModel):
    orgnr: str = Field(description="9-digit norwegian organization number.")


class RiskComponent(BaseModel):
    id: str
    label: str
    points: float
    max: float
    status: str | None = None


class GetRiskScoreOutput(BaseModel):
    orgnr: str
    score: float = Field(description="Risk score on the 0-100 scale (higher = riskier).")
    level: str = Field(
        description=(
            "Norwegian risk level — one of: lav (low), moderat (moderate), "
            "høy (high), kritisk (critical)."
        )
    )
    components: list[RiskComponent] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


async def handle(
    client: FirmaradarClient, params: GetRiskScoreInput
) -> GetRiskScoreOutput:
    payload = await client.get(f"/api/v1/risikoscoring/score/{params.orgnr}")
    if not isinstance(payload, dict):
        payload = {}
    components_raw = payload.get("components") or []
    components: list[RiskComponent] = []
    for c in components_raw:
        if not isinstance(c, dict):
            continue
        components.append(
            RiskComponent(
                id=str(c.get("id", "")),
                label=str(c.get("label", "")),
                points=float(c.get("points", 0) or 0),
                max=float(c.get("max", 0) or 0),
                status=c.get("status"),
            )
        )
    return GetRiskScoreOutput(
        orgnr=str(payload.get("orgnr", params.orgnr)),
        score=float(payload.get("score", 0) or 0),
        level=str(payload.get("level", "unknown")),
        components=components,
        sources=list(payload.get("sources") or []),
        data_gaps=list(payload.get("data_gaps") or []),
        raw=payload,
    )


HANDLER = ToolHandler(
    name="firmaradar_get_risk_score",
    description=(
        "Structured risk score (0-100) with named level (lav/moderat/høy/kritisk) "
        "and component breakdown for a Norwegian COMPANY's financial health. "
        "Combines distress classification, BRREG status, age, capital signals "
        "and other factors into one comparable score. Returns blocked_enk error "
        "for sole-proprietorships (ENK).\n\n"
        "SCOPE: Company financial health only. NOT a personal credit check on "
        "owners or officers. For full KYC pre-screening, combine with "
        "firmaradar_get_aml_score (PEP/sanctions on key persons). "
        "Personal tax-record integration (firmaradar_get_skattelister for "
        "persons) is gated pending Skatteetaten data-access approval.\n\n"
        "**Requires a one-time pre-screening-disclaimer confirmation.** "
        "If this returns HTTP 403 with error_code `kundebekreftelse_required` "
        "or `disclaimer_required`, the agent may call "
        "`firmaradar_confirm_risk_score_disclaimer` to confirm on the "
        "user's behalf (per OAuth user, audit-logged). The confirmation is "
        "per account, not per call, and is permanent. Alternatively the "
        "user can confirm manually at "
        "https://firmaradar.no/minbedrift/utvidelser/risikoscoring — both "
        "paths write to the same audit table."
    ),
    input_schema=GetRiskScoreInput,
    output_schema=GetRiskScoreOutput,
    handler=handle,
)
