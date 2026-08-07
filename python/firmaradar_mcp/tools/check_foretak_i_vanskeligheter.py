"""Tool: ``check_foretak_i_vanskeligheter``.

Foretak-i-vanskeligheter (FIV) status etter GBER art. 2(18) kriterium a-e.
Returnerer hvilke kriterier som er utløst, samlet status og konfidens.

Vurderingen gjøres på to nivåer — selskapet og konsernet det inngår i —
og det er nok at ett av nivåene slår til. Konsern-leddet returneres i
``group_assessment``/``distress_basis``.

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


class GroupAssessment(BaseModel):
    """Konsern-leddet i to-nivå-testen (GBER art. 2(18))."""

    evaluated: bool = Field(
        default=False,
        description="False when the company is not part of any group.",
    )
    status: str | None = Field(
        default=None,
        description=(
            "Group-level outcome: clean, distressed, doubt or unknown. "
            "'unknown' means the group could not be assessed (typically a "
            "foreign parent, which does not exist as an entity in Norwegian "
            "registries)."
        ),
    )
    basis: str | None = Field(
        default=None,
        description=(
            "Data basis: konsernregnskap (filed consolidated accounts), "
            "aggregert_selskapsregnskap (individual accounts summed "
            "arithmetically — indicative, intra-group balances are not "
            "eliminated), utenlandsk_majoritet or ingen_data."
        ),
    )
    root_orgnr: str | None = None
    root_name: str | None = None
    members_total: int | None = None
    members_evaluated: int | None = None
    capital_loss_ratio: float | None = Field(
        default=None,
        description="Share of the group's subscribed capital lost to accumulated losses.",
    )
    truncated: bool = False


class RescueEstimate(BaseModel):
    """Hva konsernet må tilføre for å fjerne kapitalkriteriet (a)."""

    konsernbidrag_min_nok: float | None = Field(
        default=None,
        description="Minimum group contribution / grant, in NOK.",
    )
    kapitalforhoyelse_min_nok: float | None = Field(
        default=None,
        description="Minimum share-capital increase, in NOK.",
    )
    frist: str | None = Field(
        default=None,
        description="Deadline — no later than the point the aid is granted.",
    )


class CheckFivOutput(BaseModel):
    orgnr: str
    status: str = Field(
        description=(
            "One of: not_distressed, insufficient_data, "
            "not_distressed_partial, exempt_young_company, distressed. "
            "Reflects BOTH levels of the assessment — a company with clean "
            "accounts is 'distressed' when its group is."
        )
    )
    verdict: str | None = Field(
        default=None,
        description=(
            "Display verdict: 'Yes', 'Yes (group)', 'Yes (!)', 'Uncertain' or "
            "'No (*)'. 'Yes (group)' means only the group triggers; 'Yes (!)' "
            "means the company triggers only the capital criterion and its "
            "group is sound enough to remedy it."
        ),
    )
    score: float = Field(description="Confidence-weighted distress score in [0.0, 1.0].")
    confidence: float = Field(description="Data-completeness confidence in [0.0, 1.0].")
    rules_fired: list[FivRule] = Field(default_factory=list)
    company_status: str | None = Field(
        default=None,
        description="The company-level result alone, before the group level was applied.",
    )
    distress_basis: str | None = Field(
        default=None,
        description=(
            "Which level makes the company distressed: company, group or "
            "company_and_group. Null when not distressed."
        ),
    )
    group_assessment: GroupAssessment | None = None
    rescuable_by_group: bool = Field(
        default=False,
        description=(
            "True when the group can lift the company out of difficulty by "
            "injecting capital before the aid is granted."
        ),
    )
    rescue_estimate: RescueEstimate | None = None
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

    # Dommen (Ja / Ja (konsern) / Ja (!) / Tvil / Nei (*)) beregnes av backend
    # og følger med i payloaden — vi speiler den i stedet for å reimplementere
    # tabellen her (pakken er frittstående og kan ikke importere backend-koden).
    verdict_block = payload.get("verdict")
    verdict = None
    if isinstance(verdict_block, dict):
        verdict = verdict_block.get("label_en") or verdict_block.get("label")

    group_raw = payload.get("group_assessment")
    group = GroupAssessment(**{
        k: v for k, v in group_raw.items()
        if k in GroupAssessment.model_fields
    }) if isinstance(group_raw, dict) else None

    rescue_raw = payload.get("rescue_estimate")
    rescue = RescueEstimate(**{
        k: v for k, v in rescue_raw.items()
        if k in RescueEstimate.model_fields
    }) if isinstance(rescue_raw, dict) else None

    return CheckFivOutput(
        orgnr=str(payload.get("orgnr", params.orgnr)),
        status=status,
        verdict=verdict,
        score=score,
        confidence=confidence,
        rules_fired=rules,
        company_status=payload.get("company_status") or None,
        distress_basis=payload.get("distress_basis") or None,
        group_assessment=group,
        rescuable_by_group=bool(payload.get("rescuable_by_group")),
        rescue_estimate=rescue,
        as_of=payload.get("as_of") or payload.get("assessed_at"),
        raw=payload,
    )


HANDLER = ToolHandler(
    name="firmaradar_check_foretak_i_vanskeligheter",
    description=(
        "Assess whether a Norwegian company qualifies as *foretak i "
        "vanskeligheter* (a 'company in difficulty') under EU GBER "
        "art. 2(18) criteria a-e. Assessed at BOTH company and group level, "
        "as EU/EFTA state-aid practice requires — a company with clean "
        "accounts is in difficulty when its group is. Returns which criteria "
        "triggered, the overall status, the group assessment, and a "
        "data-completeness confidence score — a deterministic distress "
        "classification, not a raw registry flag. Use for EU state-aid "
        "eligibility, credit assessment, and supplier-risk screening."
    ),
    input_schema=CheckFivInput,
    output_schema=CheckFivOutput,
    handler=handle,
)
