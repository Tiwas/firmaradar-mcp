"""Tool: ``get_risk_score_bulk``.

Bulk-risikoscoring — vurder opptil 50 orgnr i ett kall. Hvert orgnr
scores parallelt på backend via threadpool og returneres med eget
status + result-objekt. Compliance-gates (ENK-sperre,
kundebekreftelse-required, extension_disabled) feiler ikke hele bulken
— de returneres per orgnr i resultatlisten.

Backend: ``POST /api/v1/risikoscoring/score/bulk`` (#134, 2026-05-27).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


_BULK_MAX_ORGNRS: int = 50


class GetRiskScoreBulkInput(BaseModel):
    orgnrs: list[str] = Field(
        description=(
            "List of 1-50 nine-digit Norwegian organization numbers. "
            "Each orgnr counts as one unit against your quota."
        ),
        min_length=1,
        max_length=_BULK_MAX_ORGNRS,
    )


class RiskComponentBrief(BaseModel):
    id: str
    label: str | None = None
    points: float | None = None
    max: float | None = None
    status: str | None = None


class BulkRiskScoreResult(BaseModel):
    """Per-orgnr resultat i bulk-risikoscoring-respons."""

    orgnr: str
    score: float | None = None
    risk_level: str | None = Field(
        default=None,
        description=(
            "Norwegian risk level — one of: lav (low), moderat (moderate), "
            "høy (high), kritisk (critical). None on error."
        ),
    )
    error: str | None = Field(
        default=None,
        description=(
            "Feiltype hvis scoring ikke kunne fullføres: invalid_orgnr, "
            "blocked_enk, enk_not_supported, extension_disabled, "
            "confirmation_required, etc. Body inneholder også detaljer."
        ),
    )
    components: list[RiskComponentBrief] = Field(default_factory=list)
    # Full backend-respons per orgnr — KUN for intern bruk/debug. Ekskludert fra
    # serialisering (``exclude=True``): den blåste opp bulk-svaret 7× → ChatGPT
    # trunkerte og falt tilbake til individuelle kall. Strukturerte felt over
    # (score/risk_level/components) er det agenten trenger.
    raw: dict[str, Any] | None = Field(default=None, exclude=True)


class BulkMeta(BaseModel):
    total_requested: int
    successful: int
    failed: int


class GetRiskScoreBulkOutput(BaseModel):
    results: list[BulkRiskScoreResult] = Field(default_factory=list)
    meta: BulkMeta = Field(
        ...,
        alias="_meta",
        description="Aggregate count status for the whole bulk call.",
    )
    summary: str | None = Field(
        default=None,
        description="Human-readable markdown table of the per-company scores.",
    )


def _bulk_summary_table(results: list[BulkRiskScoreResult]) -> str:
    """Bygg en kompakt markdown-tabell over bulk-resultatene.

    Gjør at ChatGPT rendrer en ren score-tabell inline i stedet for å trunkere
    en stor JSON-blob (og falle tilbake til individuelle kall)."""
    lines = ["| Orgnr | Score | Nivå |", "|---|---|---|"]
    for r in results:
        if r.error:
            lines.append(f"| {r.orgnr} | — | {r.error} |")
        else:
            score = "—" if r.score is None else f"{r.score:g}"
            lines.append(f"| {r.orgnr} | {score} | {r.risk_level or '—'} |")
    return "\n".join(lines)


def _coerce_result(raw: dict[str, Any], fallback_orgnr: str) -> BulkRiskScoreResult:
    """Map et per-orgnr-respons-objekt til BulkRiskScoreResult."""
    if not isinstance(raw, dict):
        return BulkRiskScoreResult(
            orgnr=fallback_orgnr, error="invalid_response", raw=None,
        )
    components: list[RiskComponentBrief] = []
    for c in raw.get("components") or []:
        if not isinstance(c, dict):
            continue
        components.append(
            RiskComponentBrief(
                id=str(c.get("id", "")),
                label=c.get("label") if isinstance(c.get("label"), str) else None,
                points=(
                    float(c["points"]) if isinstance(c.get("points"), (int, float)) else None
                ),
                max=(
                    float(c["max"]) if isinstance(c.get("max"), (int, float)) else None
                ),
                status=c.get("status") if isinstance(c.get("status"), str) else None,
            )
        )
    return BulkRiskScoreResult(
        orgnr=str(raw.get("orgnr") or fallback_orgnr),
        score=(
            float(raw["score"]) if isinstance(raw.get("score"), (int, float)) else None
        ),
        risk_level=(
            raw.get("risk_level") if isinstance(raw.get("risk_level"), str)
            else raw.get("level") if isinstance(raw.get("level"), str)
            else None
        ),
        error=raw.get("error") if isinstance(raw.get("error"), str) else None,
        components=components,
        raw=raw,
    )


async def handle(
    client: FirmaradarClient, params: GetRiskScoreBulkInput
) -> GetRiskScoreBulkOutput:
    if len(params.orgnrs) < 1 or len(params.orgnrs) > _BULK_MAX_ORGNRS:
        raise ValueError(
            f"orgnrs må inneholde 1-{_BULK_MAX_ORGNRS} elementer, mottok {len(params.orgnrs)}"
        )
    body = {"orgnrs": list(params.orgnrs)}
    payload = await client.post(
        "/api/v1/risikoscoring/score/bulk", json_body=body,
    )
    if not isinstance(payload, dict):
        payload = {}
    raw_results = payload.get("results") or []
    results: list[BulkRiskScoreResult] = []
    for idx, item in enumerate(raw_results):
        fallback = params.orgnrs[idx] if idx < len(params.orgnrs) else ""
        results.append(_coerce_result(item if isinstance(item, dict) else {}, fallback))
    meta_raw = payload.get("_meta") or {}
    meta = BulkMeta(
        total_requested=int(meta_raw.get("total_requested", len(params.orgnrs)) or 0),
        successful=int(meta_raw.get("successful", 0) or 0),
        failed=int(meta_raw.get("failed", 0) or 0),
    )
    return GetRiskScoreBulkOutput(
        results=results, _meta=meta, summary=_bulk_summary_table(results),
    )


HANDLER = ToolHandler(
    name="firmaradar_get_risk_score_bulk",
    description=(
        "Bulk-endpoint for portfolio-screening of risikoscore (0-100 with "
        "named level lav/moderat/høy/kritisk + component breakdown) on up "
        "to 50 Norwegian companies in one call. Each orgnr counts as one "
        "unit against your quota. Compliance-gates (ENK/NUF blocking, "
        "customer-confirmation required, extension disabled) are returned "
        "per orgnr in the result list instead of failing the whole call — "
        "check each result's `error` field. Use for credit-decision "
        "screening, supplier-portfolio review, and KYC risk triage at scale."
    ),
    input_schema=GetRiskScoreBulkInput,
    output_schema=GetRiskScoreBulkOutput,
    handler=handle,
)
