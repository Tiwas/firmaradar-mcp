"""Tool: ``delete_subscription``.

Delete one NACE industry-monitoring subscription by its ``id``. After
deletion Firmaradar stops delivering webhooks for that industry.

Backed by ``DELETE /api/v1/nace/subscriptions/<id>``. The subscription
must belong to the Firmaradar user behind the Bearer token (404
otherwise — IDs are never enumerable across users). The deletion is
reversible only by re-creating the subscription with ``subscribe_nace``.

Use ``list_my_subscriptions`` first to find the correct ``id``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient, FirmaradarClientError
from . import ToolHandler


class DeleteSubscriptionInput(BaseModel):
    subscription_id: int = Field(
        description=(
            "The id of the subscription to delete (from list_my_subscriptions). "
            "Must belong to the authenticated user."
        ),
    )


class DeleteSubscriptionOutput(BaseModel):
    deleted: bool = Field(description="True if the subscription was removed.")
    id: int = Field(description="The id that was targeted.")
    already_absent: bool = Field(
        default=False,
        description="True if no subscription with that id existed for the user (nothing to delete).",
    )
    raw: dict[str, Any] | None = None


async def handle(
    client: FirmaradarClient, params: DeleteSubscriptionInput
) -> DeleteSubscriptionOutput:
    try:
        payload = await client.delete(
            f"/api/v1/nace/subscriptions/{params.subscription_id}"
        )
    except FirmaradarClientError as exc:
        # 404 → idempotent no-op: the subscription is already gone (or never
        # belonged to this user). Report it as "already absent" rather than
        # surfacing an error, so re-running the tool is safe.
        if exc.status_code == 404:
            return DeleteSubscriptionOutput(
                deleted=False,
                id=params.subscription_id,
                already_absent=True,
            )
        raise
    if not isinstance(payload, dict):
        payload = {}
    return DeleteSubscriptionOutput(
        deleted=bool(payload.get("deleted", False)),
        id=int(payload.get("id", params.subscription_id) or params.subscription_id),
        raw=payload,
    )


HANDLER = ToolHandler(
    name="firmaradar_delete_subscription",
    description=(
        "Delete one NACE industry-monitoring subscription by its id "
        "(from list_my_subscriptions); Firmaradar then stops delivering "
        "webhooks for that industry. The subscription must belong to the "
        "authenticated user. Idempotent — deleting an id that is already gone "
        "returns already_absent=true rather than an error. Reversible only by "
        "re-subscribing. Call only when the user has asked to stop monitoring "
        "an industry."
    ),
    input_schema=DeleteSubscriptionInput,
    output_schema=DeleteSubscriptionOutput,
    handler=handle,
)
