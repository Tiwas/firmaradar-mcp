"""Tool: ``get_company_signals``.

Aggregated risk signals: bankruptcy score, capital-loss flags,
recent role/signature changes, M&A interim-balance signals and KYC
announcement anomalies in one envelope.

Backend status: **READY (v0.2)** — orchestrates 3 sources via
``GET /api/v1/company/<orgnr>/signals`` (commit 2026-05-26).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class GetCompanySignalsInput(BaseModel):
    orgnr: str = Field(description="9-digit orgnr.")
    since: str | None = Field(
        default=None,
        description="ISO 8601 date — only signals on/after this date. Defaults to 90 days back.",
    )


class KycSignal(BaseModel):
    type: str
    kunngjoring_dato: str | None = None
    kategori: str | None = None
    payload: dict[str, Any] | None = None


class GetCompanySignalsOutput(BaseModel):
    orgnr: str
    distress_category: Literal["green", "yellow", "red", "unknown"] | None = None
    distress_score: float | None = None
    distress_reasons: list[str] = Field(default_factory=list)
    kyc_signals: list[KycSignal] = Field(default_factory=list)
    interim_balance_signal: dict[str, Any] | None = None
    hiring: dict[str, Any] | None = Field(
        default=None,
        description="NAV Arbeidsplassen hiring/growth signal: active_postings, "
        "positions_active, postings_30d/90d, burst_score, is_hiring_burst.",
    )
    fusjon: dict[str, Any] | None = Field(
        default=None,
        description="Merger/demerger relations: inbound (companies merged into "
        "this orgnr) + outbound (companies this orgnr was merged into), with dates.",
    )
    frivillighet: dict[str, Any] | None = Field(
        default=None,
        description="Authoritative Frivillighetsregister (voluntary-org) membership: "
        "registered, registreringsdato, kategorier. Omitted when the source is off.",
    )
    recent_role_changes_count: int = 0
    generated_at: str | None = None
    summary: str | None = None


async def handle(
    client: FirmaradarClient, params: GetCompanySignalsInput
) -> GetCompanySignalsOutput:
    qp: dict[str, Any] = {}
    if params.since:
        qp["since"] = params.since
    payload = await client.get(
        f"/api/v1/company/{params.orgnr}/signals", params=qp
    )
    if not isinstance(payload, dict):
        payload = {}

    # ── Distress-blokk → top-level felter på output ────────────────────
    distress = payload.get("distress") if isinstance(payload.get("distress"), dict) else None
    distress_score: float | None = None
    distress_reasons: list[str] = []
    distress_category: str | None = None
    if distress and not distress.get("error"):
        raw_score = distress.get("score")
        try:
            distress_score = float(raw_score) if raw_score is not None else None
        except (TypeError, ValueError):
            distress_score = None
        # Map server-side FIV/distress-status til output-kategori. Backend bruker
        # 'distressed' / 'not_distressed' / 'not_distressed_partial' /
        # 'requires_manual_review' / 'insufficient_data' / 'exempt_young_company'.
        # Den gamle mappingen sjekket 'no_distress' (feil literal) → traff aldri →
        # alltid 'unknown' (motsa get_risk_score sin not_distressed). Legacy-literals
        # beholdt som fallback.
        #
        # «not_distressed_partial» = verdikt «ikke i vanskeligheter», men basert på
        # DELVISE regnskapsdata. Verdiktet er grønt — det matcher get_risk_score som
        # gir 0 distress-poeng for samme selskap (QA-funn 2026-06-22: gul her motsa
        # grønn der). «partial» er et data-forbehold (surfaces i distress_reasons),
        # ikke en caution-flagg. Kun 'requires_manual_review' (genuint tvetydig →
        # klassifikatoren overlater til menneske) forblir gul.
        status = (distress.get("status") or "").lower()
        if status in ("distressed", "distress"):
            distress_category = "red"
        elif status in (
            "not_distressed", "no_distress", "not_distressed_partial", "exempt_young_company"
        ):
            distress_category = "green"
        elif status in ("requires_manual_review", "warning", "yellow"):
            distress_category = "yellow"
        else:  # insufficient_data / ukjent
            distress_category = "unknown"
        for rule in (distress.get("rules_fired") or []):
            if isinstance(rule, dict) and rule.get("description"):
                distress_reasons.append(str(rule["description"]))
        # Sørg for at en grønn «partial»-vurdering ikke står uten forklaring.
        if status == "not_distressed_partial" and not distress_reasons:
            distress_reasons.append(
                "Ikke i økonomiske vanskeligheter, men vurderingen bygger på "
                "delvise regnskapsdata (færre år/poster tilgjengelig)."
            )

    # ── KYC-signaler ───────────────────────────────────────────────────
    kyc_block = payload.get("kyc_signals") if isinstance(payload.get("kyc_signals"), dict) else {}
    kyc_signals_raw = kyc_block.get("signals") or []
    kyc_signals: list[KycSignal] = []
    for sig in kyc_signals_raw:
        if not isinstance(sig, dict):
            continue
        kyc_signals.append(
            KycSignal(
                type=str(sig.get("kunngjoring_type") or sig.get("type") or ""),
                kunngjoring_dato=str(sig.get("dato") or sig.get("kunngjoring_dato") or "") or None,
                kategori=sig.get("kategori"),
                payload=sig if isinstance(sig, dict) else None,
            )
        )

    interim = payload.get("interim_balance") if isinstance(payload.get("interim_balance"), dict) else None
    # interim kan være {"error": "..."} ved kilde-feil
    if interim and interim.get("error"):
        interim = None

    def _clean(key: str) -> dict[str, Any] | None:
        """Pass-through av en kilde-blokk; dropp {"error": ...}-konvolutter."""
        blk = payload.get(key)
        if not isinstance(blk, dict) or blk.get("error"):
            return None
        return blk

    return GetCompanySignalsOutput(
        orgnr=str(payload.get("orgnr", params.orgnr)),
        distress_category=distress_category,
        distress_score=distress_score,
        distress_reasons=distress_reasons,
        kyc_signals=kyc_signals,
        interim_balance_signal=interim,
        hiring=_clean("hiring"),
        fusjon=_clean("fusjon"),
        frivillighet=_clean("frivillighet"),
        recent_role_changes_count=0,  # ikke en del av v0.2-payload; v0.3
        generated_at=None,
        summary=None,
    )


HANDLER = ToolHandler(
    name="firmaradar_get_company_signals",
    description=(
        "Aggregated risk and growth signals for one company: bankruptcy/distress "
        "score, capital-loss flags, M&A interim-balance signals, KYC announcement "
        "anomalies, NAV hiring/growth signal, and merger/demerger (fusjon/fisjon) "
        "relations plus authoritative voluntary-org (Frivillighetsregister) status. "
        "Use as the second step after `get_company` to evaluate whether a company "
        "needs deeper due diligence."
    ),
    input_schema=GetCompanySignalsInput,
    output_schema=GetCompanySignalsOutput,
    handler=handle,
)
