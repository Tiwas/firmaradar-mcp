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
    status = str(payload.get("status", "unknown"))
    coverage = str(payload.get("coverage", "")).lower()

    # Backend (DistressAssessment) emitter IKKE numerisk `score`/`confidence` eller
    # en `rules_fired`-liste — de feltene var fantom (alltid 0/tomt). De ekte
    # signalene er `status`, `coverage`, `triggers` (liste rule-IDer som traff) og
    # `rule_results` (per-regel-detalj). Vi avleder de strukturerte feltene herfra.

    # confidence = data-dekning: complete → 1.0, incomplete → 0.5.
    if coverage == "complete":
        confidence = 1.0
    elif coverage == "incomplete":
        confidence = 0.5
    else:
        confidence = float(payload.get("confidence") or 0.0)

    # score = enkel distress-indikator i [0,1] avledet av status.
    _score_by_status = {
        "distressed": 1.0,
        "not_distressed_partial": 0.5,
        "insufficient_data": 0.5,
        "not_distressed": 0.0,
        "exempt_young_company": 0.0,
    }
    score = _score_by_status.get(status, float(payload.get("score") or 0.0))

    # rules_fired = reglene som traff, fra `triggers` (+ detalj fra rule_results).
    rule_results = payload.get("rule_results")
    rule_results = rule_results if isinstance(rule_results, dict) else {}
    rules: list[FivRule] = []
    for trig in payload.get("triggers") or []:
        rid = str(trig)
        detail = rule_results.get(rid)
        detail = detail if isinstance(detail, dict) else {}
        rules.append(
            FivRule(
                rule_id=rid,
                severity=str(detail.get("status") or "triggered"),
                description=detail.get("reason"),
            )
        )

    return CheckFivOutput(
        orgnr=str(payload.get("orgnr", params.orgnr)),
        status=status,
        score=score,
        confidence=confidence,
        rules_fired=rules,
        as_of=payload.get("as_of") or payload.get("assessed_at"),
        raw=payload,
    )


HANDLER = ToolHandler(
    name="firmaradar_check_foretak_i_vanskeligheter",
    description=(
        "Assess whether a Norwegian company qualifies as *foretak i "
        "vanskeligheter* (a 'company in difficulty') under NUES criteria "
        "a-e. Returns which criteria triggered, the overall distress "
        "status, and a data-completeness confidence score — a "
        "deterministic distress classification, not a raw registry flag. "
        "Use for EU state-aid eligibility, credit assessment, and "
        "supplier-risk screening."
    ),
    input_schema=CheckFivInput,
    output_schema=CheckFivOutput,
    handler=handle,
)
