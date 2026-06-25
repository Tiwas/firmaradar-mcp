"""Tool: ``add_company_monitoring``.

Add a single Norwegian company (organisation number) to the caller's
company-monitoring list. The user is then alerted when announcements,
status changes (bankruptcy/dissolution), ownership changes or new public
grants are registered for that company.

Backed by ``POST /monitoring/targets/add`` (accepts a JSON body). New
targets monitor **all** announcement categories by default (empty category
filter = no filtering). ``ip_alerts`` (default ``True``) additionally turns
on IP-change alerts when the caller's account has the ``ip_overvakning``
add-on active; without it the company is still monitored for everything
else, but the IP flag is left off (delivery is entitlement-gated anyway).

Compliance / auth:

* The target is registered against the Firmaradar user behind the Bearer
  token (Bearer → portal_api_key → user_id is 1:1).
* Requires a user whose plan has Firmaovervakning enabled (403 otherwise).
* 409 if the company is already in the list — idempotent, no duplicate row.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class AddCompanyMonitoringInput(BaseModel):
    orgnr: str = Field(
        description="Norwegian organisation number (9 digits) to add to monitoring.",
    )
    ip_alerts: bool = Field(
        default=True,
        description=(
            "Also enable IP-change alerts for this company. Default true = "
            "monitor everything. Requires the IP-monitoring add-on "
            "(ip_overvakning) on the account; without it the company is still "
            "monitored for all announcement/status/ownership changes, but IP "
            "alerts stay off. Set false to skip IP alerts."
        ),
    )


class AddCompanyMonitoringOutput(BaseModel):
    ok: bool = Field(default=False, description="True when the company was added.")
    orgnr: str | None = None
    ip_alerts_enabled: bool = Field(
        default=False,
        description="Whether IP-change alerts were turned on (false without the add-on).",
    )
    raw: dict[str, Any] | None = None


async def handle(
    client: FirmaradarClient, params: AddCompanyMonitoringInput
) -> AddCompanyMonitoringOutput:
    body: dict[str, Any] = {"orgnr": params.orgnr}
    if params.ip_alerts:
        body["ip_alerts"] = "on"
    payload = await client.post("/monitoring/targets/add", json_body=body)
    if not isinstance(payload, dict):
        payload = {}
    return AddCompanyMonitoringOutput(
        ok=bool(payload.get("ok", False)),
        orgnr=payload.get("orgnr"),
        ip_alerts_enabled=bool(payload.get("ip_alerts_enabled", False)),
        raw=payload,
    )


HANDLER = ToolHandler(
    name="firmaradar_add_company_monitoring",
    description=(
        "Add a Norwegian company (by 9-digit orgnr) to the user's company-"
        "monitoring list. The user is then alerted when announcements, status "
        "changes (bankruptcy/dissolution), ownership changes or new public "
        "grants are registered for that company. New targets monitor ALL "
        "announcement categories by default; keep ip_alerts=true (default) to "
        "also turn on IP-change alerts when the account has the IP-monitoring "
        "add-on, or set ip_alerts=false to skip them. 409 if already monitored "
        "(idempotent — no duplicate). Requires a user whose plan has "
        "Firmaovervakning enabled. Call only when the user has asked to monitor "
        "a specific company."
    ),
    input_schema=AddCompanyMonitoringInput,
    output_schema=AddCompanyMonitoringOutput,
    handler=handle,
)
