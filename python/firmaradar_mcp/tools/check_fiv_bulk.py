"""Tool: ``check_fiv_bulk``.

Bulk-FIV-screening — vurder opptil 50 orgnr i ett kall. Hvert orgnr
evalueres parallelt på backend via threadpool og returneres med eget
status + result-objekt. Compliance-gates (ENK, ugyldig orgnr) feiler
ikke hele bulken — de returneres per orgnr i resultatlisten.

Backend: ``POST /api/v1/fiv/bulk`` (#134, 2026-05-27).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


# Backend håndhever samme grense; vi speiler den her for tidlig feilretur.
_BULK_MAX_ORGNRS: int = 50


class CheckFivBulkInput(BaseModel):
    orgnrs: list[str] = Field(
        description=(
            "List of 1-50 nine-digit Norwegian organization numbers. "
            "Each orgnr counts as one unit against your quota."
        ),
        min_length=1,
        max_length=_BULK_MAX_ORGNRS,
    )
    skip_freshness: bool = Field(
        default=False,
        description=(
            "If True, accept FIV-data even if the underlying regnskap- or "
            "BRREG-snapshot is older than the normal freshness window. "
            "Use sparingly — recommended only for retrospective screening."
        ),
    )


class BulkFivResult(BaseModel):
    """Per-orgnr resultat i bulk-FIV-respons."""

    orgnr: str
    status: str | None = Field(
        default=None,
        description=(
            "FIV (foretak i vanskeligheter / company-in-difficulty) status "
            "when available: not_distressed, distressed, insufficient_data, "
            "exempt_young_company, not_distressed_partial. Absent when error is set."
        ),
    )
    error: str | None = Field(
        default=None,
        description=(
            "Feiltype hvis evaluering ikke kunne fullføres: invalid_orgnr, "
            "blocked_enk, extension_disabled, etc. Body inneholder også "
            "detaljerte feilmeldinger."
        ),
    )
    score: float | None = None
    confidence: float | None = None
    raw: dict[str, Any] | None = None


class BulkMeta(BaseModel):
    total_requested: int
    successful: int
    failed: int


class CheckFivBulkOutput(BaseModel):
    results: list[BulkFivResult] = Field(default_factory=list)
    meta: BulkMeta = Field(
        ...,
        alias="_meta",
        description="Aggregate count status for the whole bulk call.",
    )


def _coerce_result(raw: dict[str, Any], fallback_orgnr: str) -> BulkFivResult:
    """Map et per-orgnr-respons-objekt til BulkFivResult."""
    if not isinstance(raw, dict):
        return BulkFivResult(orgnr=fallback_orgnr, error="invalid_response", raw=None)
    return BulkFivResult(
        orgnr=str(raw.get("orgnr") or fallback_orgnr),
        status=raw.get("status") if isinstance(raw.get("status"), str) else None,
        error=raw.get("error") if isinstance(raw.get("error"), str) else None,
        score=(
            float(raw["score"]) if isinstance(raw.get("score"), (int, float)) else None
        ),
        confidence=(
            float(raw["confidence"])
            if isinstance(raw.get("confidence"), (int, float))
            else None
        ),
        raw=raw,
    )


async def handle(
    client: FirmaradarClient, params: CheckFivBulkInput
) -> CheckFivBulkOutput:
    if len(params.orgnrs) < 1 or len(params.orgnrs) > _BULK_MAX_ORGNRS:
        # pydantic-validering har allerede fanget dette, men vi
        # double-checker for å gi tydelig feilmelding.
        raise ValueError(
            f"orgnrs må inneholde 1-{_BULK_MAX_ORGNRS} elementer, mottok {len(params.orgnrs)}"
        )
    body = {
        "orgnrs": list(params.orgnrs),
        "skip_freshness": bool(params.skip_freshness),
    }
    payload = await client.post("/api/v1/fiv/bulk", json_body=body)
    if not isinstance(payload, dict):
        payload = {}
    raw_results = payload.get("results") or []
    results: list[BulkFivResult] = []
    for idx, item in enumerate(raw_results):
        fallback = params.orgnrs[idx] if idx < len(params.orgnrs) else ""
        results.append(_coerce_result(item if isinstance(item, dict) else {}, fallback))
    meta_raw = payload.get("_meta") or {}
    meta = BulkMeta(
        total_requested=int(meta_raw.get("total_requested", len(params.orgnrs)) or 0),
        successful=int(meta_raw.get("successful", 0) or 0),
        failed=int(meta_raw.get("failed", 0) or 0),
    )
    return CheckFivBulkOutput(results=results, _meta=meta)


HANDLER = ToolHandler(
    name="firmaradar_check_fiv_bulk",
    description=(
        "Bulk-endpoint for portfolio-screening of 'foretak i vanskeligheter' "
        "(financially distressed companies per NUES rules a-e). Max 50 orgnr "
        "per call. Each orgnr counts as one unit against your quota. "
        "Compliance-gates (ENK blocking, invalid orgnr) are returned per "
        "orgnr in the result list instead of failing the whole call — check "
        "each result's `error` field. Use for screening supplier lists, "
        "credit-portfolios, or EU state-aid eligibility on multiple "
        "companies at once."
    ),
    input_schema=CheckFivBulkInput,
    output_schema=CheckFivBulkOutput,
    handler=handle,
)
