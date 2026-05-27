"""Tool: ``check_foretak_i_vanskeligheter``.

Foretak-i-vanskeligheter (FIV) status iht NUES-reglene a-e. Returnerer
hvilke regler som er utløst + total-status + konfidens.

Backend: ``GET /api/v1/fiv/assess/<orgnr>`` (#130, 2026-05-27).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class CheckFivInput(BaseModel):
    orgnr: str = Field(description="9-digit norwegian organization number.")


class FivRule(BaseModel):
    rule_id: str
    severity: str
    description: str | None = None


class CheckFivOutput(BaseModel):
    orgnr: str
    status: str = Field(
        description=(
            "One of: not_distressed, insufficient_data, "
            "not_distressed_partial, exempt_young_company, distressed."
        )
    )
    score: float = Field(description="Confidence-weighted distress score in [0.0, 1.0].")
    confidence: float = Field(description="Data-completeness confidence in [0.0, 1.0].")
    rules_fired: list[FivRule] = Field(default_factory=list)
    as_of: str | None = None
    raw: dict[str, Any] | None = None


async def handle(
    client: FirmaradarClient, params: CheckFivInput
) -> CheckFivOutput:
    payload = await client.get(f"/api/v1/fiv/assess/{params.orgnr}")
    if not isinstance(payload, dict):
        payload = {}
    rules_raw = payload.get("rules_fired") or []
    rules: list[FivRule] = []
    for r in rules_raw:
        if not isinstance(r, dict):
            continue
        rules.append(
            FivRule(
                rule_id=str(r.get("rule_id", "")),
                severity=str(r.get("severity", "")),
                description=r.get("description"),
            )
        )
    return CheckFivOutput(
        orgnr=str(payload.get("orgnr", params.orgnr)),
        status=str(payload.get("status", "unknown")),
        score=float(payload.get("score", 0) or 0),
        confidence=float(payload.get("confidence", 0) or 0),
        rules_fired=rules,
        as_of=payload.get("as_of"),
        raw=payload,
    )


HANDLER = ToolHandler(
    name="firmaradar_check_foretak_i_vanskeligheter",
    description=(
        "Assess whether a Norwegian company is 'foretak i vanskeligheter' "
        "(financially distressed) per NUES rules a-e. Returns which rules "
        "triggered + overall status + confidence. Used in EU state-aid eligibility "
        "checks, kreditt-vurdering, and supplier risk screening."
    ),
    input_schema=CheckFivInput,
    output_schema=CheckFivOutput,
    handler=handle,
)
