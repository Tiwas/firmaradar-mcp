"""Tool: ``subscribe_nace``.

Create (or update) an industry-monitoring subscription on a NACE code.
When any Norwegian company in the chosen industry triggers a monitored
event (new announcement / status change / ownership update), Firmaradar
delivers a webhook to the URL you provide.

Backed by ``POST /api/v1/nace/subscriptions``. The subscription is
**upserted** on ``(user, nace_code)`` — calling again with the same code
updates the existing subscription rather than creating a duplicate, so
the tool is idempotent.

Compliance / auth:

* The subscription is registered against the Firmaradar user behind the
  Bearer token (Bearer → portal_api_key → user_id is 1:1).
* Requires a user whose plan has Firmaovervakning enabled (403 ``Tilgang
  krever Firmaovervakning`` otherwise).
* A per-user cap applies (currently 50 subscriptions; 409 when reached).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


# Mirrors backend constants:
#   events            — repos._overvakning_webhook_repo.VALID_EVENTS
#   aggregation_mode  — repos._nace_overvakning_repo.VALID_AGGREGATION_MODES
EventType = Literal["created", "updated", "deleted", "status_changed"]
AggregationMode = Literal["real_time", "hourly_digest", "daily_digest"]


class SubscribeNaceInput(BaseModel):
    nace_code: str = Field(
        description=(
            "The NACE code to monitor. Accepts a section letter ('G'), a "
            "group ('47'), or a more specific code ('47.110'). Resolve the "
            "exact code first with list_nace_codes if unsure. A subscription "
            "on a parent code also matches events in all child codes."
        ),
    )
    url: str | None = Field(
        default=None,
        description=(
            "HTTPS webhook URL that receives a POST for each matched event. "
            "Omit only if you intend to add it later via the portal."
        ),
    )
    bearer_token: str | None = Field(
        default=None,
        description=(
            "Optional bearer token Firmaradar sends as `Authorization: Bearer "
            "<token>` when calling your webhook URL, so your endpoint can "
            "authenticate the delivery. Stored encrypted."
        ),
    )
    events: list[EventType] | None = Field(
        default=None,
        description=(
            "Which event types to deliver. Omit for all of them. Restrict to "
            "e.g. ['status_changed'] to receive only bankruptcy/dissolution "
            "signals and cut volume dramatically in large industries."
        ),
    )
    aggregation_mode: AggregationMode = Field(
        default="real_time",
        description=(
            "Delivery cadence. 'real_time' (default) posts each event "
            "immediately. 'hourly_digest' / 'daily_digest' batch events to "
            "reduce noise in high-volume industries."
        ),
    )
    landsdel_filter: list[str] | None = Field(
        default=None,
        description="Optional geographic filter: only companies in these landsdeler.",
    )
    fylke_filter: list[str] | None = Field(
        default=None,
        description="Optional geographic filter: only companies in these fylker (county numbers).",
    )
    kommune_filter: list[str] | None = Field(
        default=None,
        description="Optional geographic filter: only companies in these kommuner (4-digit kommunenummer).",
    )
    min_ansatte: int | None = Field(
        default=None, ge=1,
        description="Optional size filter: only companies with at least this many employees.",
    )
    min_omsetning_nok: int | None = Field(
        default=None, ge=1,
        description="Optional size filter: only companies with at least this much revenue (NOK).",
    )
    aktivert: bool = Field(
        default=True,
        description="Whether the subscription is active immediately (default true).",
    )


class SubscribeNaceOutput(BaseModel):
    id: int | None = Field(default=None, description="ID of the created/updated subscription.")
    nace_code: str | None = None
    url: str | None = None
    events: list[str] = Field(default_factory=list)
    aggregation_mode: str | None = None
    aggregation_mode_en: str | None = None
    aktivert: bool = False
    created_at: str | None = None
    updated_at: str | None = None
    raw: dict[str, Any] | None = None


def _build_body(params: SubscribeNaceInput) -> dict[str, Any]:
    body: dict[str, Any] = {
        "nace_code": params.nace_code,
        "aggregation_mode": params.aggregation_mode,
        "aktivert": params.aktivert,
    }
    if params.url is not None:
        body["url"] = params.url
    if params.bearer_token is not None:
        body["bearer_token"] = params.bearer_token
    if params.events is not None:
        body["events"] = list(params.events)
    if params.landsdel_filter is not None:
        body["landsdel_filter"] = params.landsdel_filter
    if params.fylke_filter is not None:
        body["fylke_filter"] = params.fylke_filter
    if params.kommune_filter is not None:
        body["kommune_filter"] = params.kommune_filter
    if params.min_ansatte is not None:
        body["min_ansatte"] = params.min_ansatte
    if params.min_omsetning_nok is not None:
        body["min_omsetning_nok"] = params.min_omsetning_nok
    return body


async def handle(
    client: FirmaradarClient, params: SubscribeNaceInput
) -> SubscribeNaceOutput:
    payload = await client.post(
        "/api/v1/nace/subscriptions",
        json_body=_build_body(params),
    )
    if not isinstance(payload, dict):
        payload = {}
    sub = payload.get("subscription") if isinstance(payload.get("subscription"), dict) else payload
    return SubscribeNaceOutput(
        id=sub.get("id"),
        nace_code=sub.get("nace_code"),
        url=sub.get("url"),
        events=list(sub.get("events", []) or []),
        aggregation_mode=sub.get("aggregation_mode"),
        aggregation_mode_en=sub.get("aggregation_mode_en"),
        aktivert=bool(sub.get("aktivert", False)),
        created_at=sub.get("created_at"),
        updated_at=sub.get("updated_at"),
        raw=payload,
    )


HANDLER = ToolHandler(
    name="firmaradar_subscribe_nace",
    description=(
        "Subscribe to industry (NACE) monitoring: when any Norwegian company "
        "in the chosen industry triggers a monitored event (new announcement, "
        "status change such as bankruptcy/dissolution, or ownership update), "
        "Firmaradar delivers a webhook to your URL. Use list_nace_codes first "
        "to resolve the exact code. A subscription on a parent code matches "
        "all child codes. Restrict `events` (e.g. ['status_changed']) and use "
        "geographic/size filters to cut volume in large industries, or pick a "
        "digest `aggregation_mode`. Idempotent — upserted on (user, "
        "nace_code), so re-subscribing the same code updates it. Requires a "
        "user whose plan has Firmaovervakning enabled. Call only when the user "
        "has asked to set up industry monitoring."
    ),
    input_schema=SubscribeNaceInput,
    output_schema=SubscribeNaceOutput,
    handler=handle,
)
