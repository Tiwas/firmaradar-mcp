"""Tool: ``list_my_subscriptions``.

List the NACE industry-monitoring subscriptions belonging to the
Firmaradar user behind the Bearer token. Use it to review what is being
monitored, and to find the ``id`` needed by ``delete_subscription``.

Backed by ``GET /api/v1/nace/subscriptions``. Encrypted bearer tokens are
never returned; ``has_bearer_token`` indicates whether one is set.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class ListMySubscriptionsInput(BaseModel):
    """No parameters — scoped to the authenticated user via the Bearer token."""

    pass


class SubscriptionRecord(BaseModel):
    id: int | None = None
    nace_code: str | None = None
    url: str | None = None
    events: list[str] = Field(default_factory=list)
    aggregation_mode: str | None = None
    aggregation_mode_en: str | None = None
    landsdel_filter: list[str] = Field(default_factory=list)
    fylke_filter: list[str] = Field(default_factory=list)
    kommune_filter: list[str] = Field(default_factory=list)
    min_ansatte: int | None = None
    min_omsetning_nok: int | None = None
    aktivert: bool = False
    has_bearer_token: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class ListMySubscriptionsOutput(BaseModel):
    items: list[SubscriptionRecord]
    count: int


def _to_record(d: dict[str, Any]) -> SubscriptionRecord:
    return SubscriptionRecord(
        id=d.get("id"),
        nace_code=d.get("nace_code"),
        url=d.get("url"),
        events=list(d.get("events", []) or []),
        aggregation_mode=d.get("aggregation_mode"),
        aggregation_mode_en=d.get("aggregation_mode_en"),
        landsdel_filter=list(d.get("landsdel_filter", []) or []),
        fylke_filter=list(d.get("fylke_filter", []) or []),
        kommune_filter=list(d.get("kommune_filter", []) or []),
        min_ansatte=d.get("min_ansatte"),
        min_omsetning_nok=d.get("min_omsetning_nok"),
        aktivert=bool(d.get("aktivert", False)),
        has_bearer_token=bool(d.get("has_bearer_token", False)),
        created_at=d.get("created_at"),
        updated_at=d.get("updated_at"),
    )


async def handle(
    client: FirmaradarClient, params: ListMySubscriptionsInput
) -> ListMySubscriptionsOutput:
    payload = await client.get("/api/v1/nace/subscriptions")
    if not isinstance(payload, dict):
        payload = {}
    items_raw = payload.get("items") or []
    items = [_to_record(d) for d in items_raw if isinstance(d, dict)]
    return ListMySubscriptionsOutput(
        items=items, count=int(payload.get("count", len(items)))
    )


HANDLER = ToolHandler(
    name="firmaradar_list_my_subscriptions",
    description=(
        "List the NACE industry-monitoring subscriptions of the authenticated "
        "Firmaradar user (created via subscribe_nace or the portal). Returns "
        "each subscription's id, NACE code, webhook URL, event filters, "
        "aggregation mode, geographic/size filters and active state. Use the "
        "returned `id` with delete_subscription to remove one. Encrypted "
        "bearer tokens are never returned (only `has_bearer_token`)."
    ),
    input_schema=ListMySubscriptionsInput,
    output_schema=ListMySubscriptionsOutput,
    handler=handle,
)
