"""Tool: ``get_aml_report``.

Poller status/resultat for en asynkron AML-rapport startet med
``start_aml_report``. Returnerer status (``pending`` / ``running`` /
``done`` / ``failed``). Når ``done`` inkluderes score, level og lenker
til den ferdige rapporten; når ``failed`` inkluderes en feilmelding.

Backend: ``GET /api/v1/aml/report/<report_id>`` (async-plan §8, arkivert i backups/deleted/2026-06-18-plans-todo-opprydding/plans/arkitektur/AML_SCORE_PERF_PLAN.md).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class GetAmlReportInput(BaseModel):
    report_id: str = Field(
        description="The report_id returned by `start_aml_report`.",
    )


class GetAmlReportOutput(BaseModel):
    report_id: str
    orgnr: str | None = None
    status: str = Field(
        description="One of: pending, running, done, failed.",
    )
    score: int | None = Field(
        default=None,
        description="AML risk score 0-100 (only when status='done').",
    )
    level: str | None = Field(
        default=None, description="low/medium/high (only when status='done')."
    )
    error: str | None = Field(
        default=None, description="Failure reason (only when status='failed')."
    )
    raw: dict[str, Any] | None = None


async def handle(
    client: FirmaradarClient, params: GetAmlReportInput
) -> GetAmlReportOutput:
    payload = await client.get(f"/api/v1/aml/report/{params.report_id}")
    if not isinstance(payload, dict):
        payload = {}
    score = payload.get("score")
    return GetAmlReportOutput(
        report_id=str(payload.get("rapport_id") or params.report_id),
        orgnr=payload.get("orgnr"),
        status=str(payload.get("status", "unknown")),
        score=int(score) if isinstance(score, (int, float)) else None,
        level=payload.get("level"),
        error=payload.get("error"),
        raw=payload,
    )


HANDLER = ToolHandler(
    name="firmaradar_get_aml_report",
    description=(
        "Poll the status and result of an asynchronous AML report started "
        "with `start_aml_report`. Pass the report_id; returns status "
        "(pending/running/done/failed). When status is 'done' it includes the "
        "AML risk score (0-100), level (low/medium/high) and links to the "
        "stored report; when 'failed' it includes the error reason. Poll "
        "periodically until the status is terminal (done/failed)."
    ),
    input_schema=GetAmlReportInput,
    output_schema=GetAmlReportOutput,
    handler=handle,
)
