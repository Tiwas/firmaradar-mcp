"""Tool: ``start_aml_report``.

Starter en AML-rapport-generering ASYNKRONT og returnerer umiddelbart en
``report_id`` + status ``pending``. I motsetning til ``get_aml_score``
(som blokker til rapporten er ferdig, og kan time ut for de aller største
eier-trærne) garanterer denne stien ingen klient-timeout uansett selskaps-
størrelse, kø eller batch.

Bruk når et selskap er stort/komplekst nok til at den synkrone
``get_aml_score`` time-er ut, eller når du vil starte mange rapporter
parallelt og hente dem senere. Poll status med ``get_aml_report``.

Backend: ``POST /api/v1/aml/report`` (async-plan §8, arkivert i backups/deleted/2026-06-18-plans-todo-opprydding/plans/arkitektur/AML_SCORE_PERF_PLAN.md).
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class StartAmlReportInput(BaseModel):
    orgnr: str = Field(description="9-digit norwegian organization number.")
    purpose: Literal[
        "kyc_onboarding", "kyc_review", "risk_monitoring", "manual"
    ] = Field(
        default="kyc_onboarding",
        description="Purpose of the screening — recorded for audit trail.",
    )


class StartAmlReportOutput(BaseModel):
    report_id: str = Field(
        description=(
            "Job/report id — poll with `get_aml_report` until status is "
            "'done' or 'failed'."
        ),
    )
    orgnr: str
    status: str = Field(
        description="One of: pending, running, done, failed (starts at 'pending').",
    )
    raw: dict[str, Any] | None = None


async def handle(
    client: FirmaradarClient, params: StartAmlReportInput
) -> StartAmlReportOutput:
    payload = await client.post(
        "/api/v1/aml/report",
        json_body={"orgnr": params.orgnr, "purpose": params.purpose},
        extra_headers={
            "X-FR-Purpose": quote(params.purpose, safe=""),
            "X-FR-Purpose-Encoding": "url",
            "X-FR-DPA-Confirmed": "true",
        },
    )
    if not isinstance(payload, dict):
        payload = {}
    return StartAmlReportOutput(
        report_id=str(payload.get("rapport_id") or ""),
        orgnr=str(payload.get("orgnr", params.orgnr)),
        status=str(payload.get("status", "pending")),
        raw=payload,
    )


HANDLER = ToolHandler(
    name="firmaradar_start_aml_report",
    description=(
        "Start generating an AML risk report ASYNCHRONOUSLY for a Norwegian "
        "company. Returns immediately with a report_id and status 'pending' "
        "— the report is built in the background. Poll `get_aml_report` with "
        "the report_id until status is 'done' (then read score/level/factors) "
        "or 'failed'. Use this instead of `get_aml_score` for large/complex "
        "ownership structures that may otherwise time out, or to start many "
        "screenings in parallel. Generates an auditable report stored for 60 "
        "months per Hvitvaskingsloven §35."
    ),
    input_schema=StartAmlReportInput,
    output_schema=StartAmlReportOutput,
    handler=handle,
)
