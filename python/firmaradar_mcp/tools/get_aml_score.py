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

import asyncio
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, Field

from ..client import FirmaradarClient, FirmaradarClientError
from . import ToolHandler

# A2 (2026-06-21): sync-først + async-fallback for robusthet mot TUNGE selskap.
# Den synkrone `POST /api/v1/aml/score` (generer + rapport) timer ut internt i
# backend (~17 s → HTTP 503 upstream_timeout) for selskap med store/komplekse
# eier-trær. Da falt verktøyet før (Internal error/503). Nå: prøv sync med kort
# timeout (rask + fulle factors for normale selskap); ved upstream-timeout fall
# tilbake til async-stien (`POST /api/v1/aml/report` → poll) som genererer i
# bakgrunnen — bounded slik at totalen holder seg under MCP-vert-tool-budsjettet.
AML_SCORE_TIMEOUT_S: float = 25.0
_ASYNC_POLL_BUDGET_S: float = 25.0
_ASYNC_POLL_INTERVAL_S: float = 3.0


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


def _parse_sync_payload(
    payload: dict, params: GetAmlScoreInput
) -> GetAmlScoreOutput:
    """Parse den synkrone `/aml/score`-responsen (med full factor-breakdown)."""
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


def _is_upstream_timeout(exc: FirmaradarClientError) -> bool:
    """True hvis feilen er en oppstrøms-timeout (backend 502/503/504 eller
    klient-getconn-timeout) — kandidat for async-fallback. Andre feil
    (401/403/400 osv.) er ekte og skal propagere."""
    if exc.status_code in (502, 503, 504):
        return True
    detail = f"{exc} {getattr(exc, 'details', '') or ''}".lower()
    return "timeout" in detail or "timed out" in detail


async def _async_fallback(
    client: FirmaradarClient, params: GetAmlScoreInput
) -> GetAmlScoreOutput:
    """Tunge selskap: start async-rapport + poll bounded. Returnerer score/level
    når ferdig; ellers report_id å polle videre med `get_aml_report`."""
    start = await client.post(
        "/api/v1/aml/report",
        json_body={"orgnr": params.orgnr, "purpose": params.purpose},
        extra_headers={
            "X-FR-Purpose": quote(params.purpose, safe=""),
            "X-FR-Purpose-Encoding": "url",
            "X-FR-DPA-Confirmed": "true",
        },
    )
    start = start if isinstance(start, dict) else {}
    report_id = start.get("rapport_id") or start.get("report_id")
    if not report_id:
        # Kunne ikke starte async — gi et ærlig, ikke-krasjende svar.
        return GetAmlScoreOutput(
            orgnr=params.orgnr, score=0, level="unknown", factors=[],
            rapport_id=None,
            raw={"note": "aml-score timet ut synkront og async-start feilet",
                 "async_start": start},
        )
    waited = 0.0
    last: dict = {}
    while waited < _ASYNC_POLL_BUDGET_S:
        await asyncio.sleep(_ASYNC_POLL_INTERVAL_S)
        waited += _ASYNC_POLL_INTERVAL_S
        last = await client.get(f"/api/v1/aml/report/{report_id}")
        last = last if isinstance(last, dict) else {}
        status = str(last.get("status") or "")
        if status == "done":
            return GetAmlScoreOutput(
                orgnr=str(last.get("orgnr") or params.orgnr),
                score=int(last.get("score") or 0),
                level=str(last.get("level") or "unknown"),
                factors=[],  # async-poll gir ikke factor-breakdown; bruk get_aml_report/json_url for detalj
                rapport_id=str(last.get("rapport_id") or report_id),
                raw={"via": "async_fallback", **last},
            )
        if status == "failed":
            raise FirmaradarClientError(
                f"AML-rapport feilet: {last.get('error') or 'ukjent feil'}",
                status_code=502,
            )
    # Fortsatt ikke ferdig innen budsjettet — gi report_id å polle videre.
    return GetAmlScoreOutput(
        orgnr=params.orgnr, score=0, level="pending", factors=[],
        rapport_id=str(report_id),
        raw={"via": "async_fallback", "status": last.get("status") or "running",
             "note": ("Stort/komplekst selskap — rapporten genereres fortsatt. "
                      "Poll firmaradar_get_aml_report med report_id til status=done.")},
    )


async def handle(
    client: FirmaradarClient, params: GetAmlScoreInput
) -> GetAmlScoreOutput:
    try:
        payload = await client.post(
            "/api/v1/aml/score",
            json_body={"orgnr": params.orgnr, "purpose": params.purpose},
            timeout_s=AML_SCORE_TIMEOUT_S,
            extra_headers={
                "X-FR-Purpose": quote(params.purpose, safe=""),
                "X-FR-Purpose-Encoding": "url",
                "X-FR-DPA-Confirmed": "true",
            },
        )
    except FirmaradarClientError as exc:
        if not _is_upstream_timeout(exc):
            raise
        # Tungt selskap → async-fallback (genererer i bakgrunnen, ingen 503).
        return await _async_fallback(client, params)
    if not isinstance(payload, dict):
        payload = {}
    return _parse_sync_payload(payload, params)


HANDLER = ToolHandler(
    name="firmaradar_get_aml_score",
    description=(
        "Structured COMPANY AML risk score (0-100) with named level "
        "(low/medium/high) and factor breakdown, by orgnr. This is the primary "
        "tool for 'what is the AML risk / AML score of company X'. "
        "Call it ONCE per company — it ALREADY screens the company's key "
        "persons and beneficial owners against PEP and sanctions lists "
        "internally and folds that into the score and factors. You normally do "
        "NOT need to call `check_aml_pep` per owner/officer afterwards; do that "
        "only for ad-hoc screening of one specific named individual you need "
        "extra detail on. "
        "Complements `check_aml_pep` (binary match data for a single PERSON "
        "name). Generates an auditable AML report on the backend (rapport_id "
        "stored for 60 months per Hvitvaskingsloven §35). For very large/complex "
        "ownership structures this can be slow; if it times out, use "
        "`start_aml_report` + `get_aml_report` (async) instead."
    ),
    input_schema=GetAmlScoreInput,
    output_schema=GetAmlScoreOutput,
    handler=handle,
)
