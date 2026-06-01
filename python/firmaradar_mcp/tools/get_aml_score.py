"""Tool: ``get_aml_score``.

Strukturert AML-risikoscore (0-100) + level + faktor-breakdown. Skiller
seg fra ``check_aml_pep`` ved å returnere selve scoren med komponenter,
ikke kun PEP/sanksjons-match. Begge dekker komplementære use-cases:

* ``check_aml_pep`` — har personen/selskapet PEP/sanksjons-match? (boolean)
* ``get_aml_score`` — strukturert risiko-vurdering med faktor-breakdown

Backend: ``POST /api/v1/aml/score`` (#130, 2026-05-27) som internt
orchestrerer to-kall mot ``aml_rapport``-extensionen (generer + rapport).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler

# Stopgap-timeout (2026-05-30): aml/score er det eneste tunge verktøyet. Backend
# enkeltkall er ~17-21 s, men under batch-screening (agent kjører flere store
# selskaper raskt) kan et kall kø i gunicorn-backloggen bak andre CPU-tunge
# AML-kall og overstige 30 s-defaulten i vegg-klokke (kø + prosessering) — selv
# om backend-prosesseringen er under 30 s. Hever timeouten KUN for dette
# verktøyet til 60 s; alle andre verktøy beholder 30 s. Se
# plans/arkitektur/AML_SCORE_PERF_PLAN.md §7 (async-sti = varig fiks).
AML_SCORE_TIMEOUT_S: float = 60.0


class GetAmlScoreInput(BaseModel):
    orgnr: str = Field(description="9-digit norwegian organization number.")
    purpose: Literal[
        "kyc_onboarding", "kyc_review", "risk_monitoring", "manual"
    ] = Field(
        default="kyc_onboarding",
        description="Purpose of the screening — recorded for audit trail.",
    )


class AmlFactor(BaseModel):
    id: str
    name: str | None = None
    weight: int
    triggered: bool
    details: str | None = None


class GetAmlScoreOutput(BaseModel):
    orgnr: str
    score: int = Field(description="AML risk score 0-100 (higher = riskier).")
    level: str = Field(description="One of: low, medium, high.")
    factors: list[AmlFactor] = Field(default_factory=list)
    rapport_id: str | None = Field(
        default=None,
        description="Persistent report-id for compliance audit (retrievable later).",
    )
    raw: dict[str, Any] | None = None


async def handle(
    client: FirmaradarClient, params: GetAmlScoreInput
) -> GetAmlScoreOutput:
    payload = await client.post(
        "/api/v1/aml/score",
        json_body={"orgnr": params.orgnr, "purpose": params.purpose},
        timeout_s=AML_SCORE_TIMEOUT_S,
    )
    if not isinstance(payload, dict):
        payload = {}
    rapport_block = payload.get("rapport") if isinstance(payload.get("rapport"), dict) else {}
    factors_raw = rapport_block.get("indicators") or rapport_block.get("factors") or []
    factors: list[AmlFactor] = []
    for f in factors_raw:
        if not isinstance(f, dict):
            continue
        # Backend-indikatorene bruker nøkkelen `name` + `trigger` (ikke `id`/
        # `triggered`). Tidligere leste vi feil nøkler → `id` alltid "" og
        # `triggered` alltid False (enhver high-risk score så ut som «ingenting
        # trigget»). Les begge med fallback for bakoverkompatibilitet.
        name = f.get("name")
        factors.append(
            AmlFactor(
                id=str(f.get("id") or name or ""),
                name=name,
                weight=int(f.get("weight", 0) or 0),
                triggered=bool(f.get("trigger", f.get("triggered", False))),
                details=f.get("details"),
            )
        )
    return GetAmlScoreOutput(
        orgnr=str(payload.get("orgnr", params.orgnr)),
        score=int(payload.get("score", 0) or 0),
        level=str(payload.get("level", "unknown")),
        factors=factors,
        rapport_id=payload.get("rapport_id"),
        raw=payload,
    )


HANDLER = ToolHandler(
    name="firmaradar_get_aml_score",
    description=(
        "Structured AML risk score (0-100) with named level (low/medium/high) "
        "and factor breakdown. Use this when you need the calculated risk "
        "score with reasoning, not just PEP/sanctions match flags. "
        "Complements `check_aml_pep` which returns binary match data. "
        "Generates an auditable AML report on the backend (rapport_id stored "
        "for 60 months per Hvitvaskingsloven §35)."
    ),
    input_schema=GetAmlScoreInput,
    output_schema=GetAmlScoreOutput,
    handler=handle,
)
