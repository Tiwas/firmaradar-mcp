"""Tool: ``get_aml_score``.

Strukturert AML-risikoscore (0-100) + level. Skiller seg fra
``check_aml_pep`` ved å returnere selve scoren, ikke kun PEP/sanksjons-
match. Begge dekker komplementære use-cases:

* ``check_aml_pep`` — har personen/selskapet PEP/sanksjons-match? (boolean)
* ``get_aml_score`` — strukturert risiko-vurdering av et selskap

Backend (2026-07-07, kostnadsmatrise §4.6 + pen-test B1): verktøyet går nå
RETT på async rapport-flyten — ``POST /api/v1/aml/report`` (202 +
rapport-id) → poll ``GET /api/v1/aml/report/<id>``. Den synkrone
``POST /api/v1/aml/score`` er deprecert server-side (svarer selv 202 +
rapport-id i redirect-modus) og kalles ikke lenger herfra; det tidligere
sync-først-forsøket (A2, v0.5.10) er fjernet. Poll-budsjettet er bounded
slik at totalen holder seg under MCP-vert-tool-budsjettet; rekker ikke
rapporten å bli ferdig, returneres ``level="pending"`` + ``rapport_id``
som klienten poller videre med ``get_aml_report``.

Merk: async-poll-svaret inneholder ikke factor-breakdown — ``factors`` er
tom liste; detaljene ligger i den lagrede rapporten (``json_url``/
``pdf_url`` i ``raw`` når status er ``done``).
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, Field

from ..client import FirmaradarClient, FirmaradarClientError
from . import ToolHandler

# Bounded poll: totalbudsjett + intervall for status-polling av async-
# rapporten. Holder verktøyet godt under MCP-vertens tool-budsjett; store/
# komplekse eier-trær som ikke rekker ferdig returnerer «pending» +
# rapport_id (poll videre med get_aml_report).
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
    level: str = Field(
        description=(
            "One of: low, medium, high — or 'pending' when the report is "
            "still generating (poll `get_aml_report` with rapport_id)."
        ),
    )
    factors: list[AmlFactor] = Field(
        default_factory=list,
        description=(
            "Always empty for the async report flow — factor detail lives "
            "in the stored report (json_url/pdf_url in `raw` when done)."
        ),
    )
    rapport_id: str | None = Field(
        default=None,
        description="Persistent report-id for compliance audit (retrievable later).",
    )
    raw: dict[str, Any] | None = None


async def _run_async_report_flow(
    client: FirmaradarClient, params: GetAmlScoreInput
) -> GetAmlScoreOutput:
    """Start async-rapport + poll bounded. Returnerer score/level når ferdig;
    ellers ``level="pending"`` + report_id å polle videre med ``get_aml_report``."""
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
            raw={"note": "async-rapport-start returnerte ingen rapport_id",
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
                raw={"via": "async_report_flow", **last},
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
        raw={"via": "async_report_flow", "status": last.get("status") or "running",
             "note": ("Stort/komplekst selskap — rapporten genereres fortsatt. "
                      "Poll firmaradar_get_aml_report med report_id til status=done.")},
    )


async def handle(
    client: FirmaradarClient, params: GetAmlScoreInput
) -> GetAmlScoreOutput:
    return await _run_async_report_flow(client, params)


HANDLER = ToolHandler(
    name="firmaradar_get_aml_score",
    description=(
        "Structured COMPANY AML risk score (0-100) with named level "
        "(low/medium/high), by orgnr. This is the primary tool for 'what is "
        "the AML risk / AML score of company X'. "
        "Call it ONCE per company — it ALREADY screens the company's key "
        "persons and beneficial owners against PEP and sanctions lists "
        "internally and folds that into the score. You normally do NOT need "
        "to call `check_aml_pep` per owner/officer afterwards; do that only "
        "for ad-hoc screening of one specific named individual you need "
        "extra detail on. "
        "Complements `check_aml_pep` (binary match data for a single PERSON "
        "name). Generates an auditable AML report on the backend (rapport_id "
        "stored for 60 months per Hvitvaskingsloven §35); factor-level "
        "detail lives in the stored report links. The report is generated "
        "asynchronously — for very large/complex ownership structures the "
        "result can come back with level='pending' and a rapport_id; poll "
        "`get_aml_report` with that id until status is 'done'."
    ),
    input_schema=GetAmlScoreInput,
    output_schema=GetAmlScoreOutput,
    handler=handle,
)
