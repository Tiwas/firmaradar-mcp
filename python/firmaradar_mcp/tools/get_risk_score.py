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
    level: str = Field(description="One of: lav, moderat, høy, kritisk.")
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
        "and component breakdown for a Norwegian company. Combines distress "
        "classification, BRREG status, age, capital signals and other factors "
        "into a single comparable score. Use for credit decisions, supplier "
        "screening, KYC risk triage."
    ),
    input_schema=GetRiskScoreInput,
    output_schema=GetRiskScoreOutput,
    handler=handle,
)
