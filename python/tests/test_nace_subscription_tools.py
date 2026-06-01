"""Tests for the NACE-overvåkning v0.5 agent-exposure tools.

Covers the four tools added 2026-05-31 — ``list_nace_codes``,
``subscribe_nace``, ``list_my_subscriptions`` and ``delete_subscription``
— at the handler level with a fake client (same pattern as the
``get_aml_score`` timeout regression test). We assert the request shape
(path + params/body) and the parsing of the backend response, plus the
idempotent 404-handling in ``delete_subscription``.
"""

from __future__ import annotations

import pytest

from firmaradar_mcp.client import FirmaradarClientError
from firmaradar_mcp.tools.delete_subscription import (
    DeleteSubscriptionInput,
    handle as delete_handle,
)
from firmaradar_mcp.tools.list_my_subscriptions import (
    ListMySubscriptionsInput,
    handle as list_subs_handle,
)
from firmaradar_mcp.tools.list_nace_codes import (
    ListNaceCodesInput,
    handle as list_codes_handle,
)
from firmaradar_mcp.tools.subscribe_nace import (
    SubscribeNaceInput,
    handle as subscribe_handle,
)


class _FakeClient:
    """Records the last call and returns a canned payload (or raises)."""

    def __init__(self, payload=None, *, raise_exc: Exception | None = None):
        self._payload = payload if payload is not None else {}
        self._raise = raise_exc
        self.calls: list[dict] = []

    async def get(self, path, params=None):
        self.calls.append({"method": "GET", "path": path, "params": params})
        if self._raise:
            raise self._raise
        return self._payload

    async def post(self, path, json_body=None, *, extra_headers=None, timeout_s=None):
        self.calls.append({"method": "POST", "path": path, "json_body": json_body})
        if self._raise:
            raise self._raise
        return self._payload

    async def delete(self, path, params=None):
        self.calls.append({"method": "DELETE", "path": path, "params": params})
        if self._raise:
            raise self._raise
        return self._payload


# ── list_nace_codes ──────────────────────────────────────────────────────────


async def test_list_nace_codes_builds_query_and_parses() -> None:
    client = _FakeClient({
        "items": [
            {
                "code": "47.110",
                "code_short": "47.11",
                "label_no": "Butikkhandel med bredt vareutvalg",
                "label_en": "Retail sale in non-specialised stores",
                "parent_code": "47.1",
                "level": 5,
                "company_count": 3421,
                "company_count_active": 3421,
                "company_count_total": 3800,
                "has_children": False,
            }
        ],
        "count": 1,
    })
    out = await list_codes_handle(client, ListNaceCodesInput(q="butikk", limit=10))
    call = client.calls[0]
    assert call["path"] == "/api/v1/nace/catalog"
    assert call["params"] == {"limit": 10, "q": "butikk"}
    assert out.count == 1
    assert out.items[0].code == "47.110"
    assert out.items[0].label_en == "Retail sale in non-specialised stores"
    assert out.items[0].has_children is False


async def test_list_nace_codes_eu_param_takes_precedence_in_query() -> None:
    client = _FakeClient({"items": [], "count": 0})
    await list_codes_handle(client, ListNaceCodesInput(eu="47.11", parent="G"))
    params = client.calls[0]["params"]
    assert params["eu"] == "47.11"
    assert params["parent"] == "G"  # both forwarded; backend applies priority


# ── subscribe_nace ───────────────────────────────────────────────────────────


async def test_subscribe_nace_minimal_body_omits_unset_fields() -> None:
    client = _FakeClient({
        "subscription": {
            "id": 7,
            "nace_code": "47.110",
            "url": "https://example.test/hook",
            "events": ["created", "updated", "deleted", "status_changed"],
            "aggregation_mode": "real_time",
            "aggregation_mode_en": "real time",
            "aktivert": True,
        }
    })
    out = await subscribe_handle(
        client,
        SubscribeNaceInput(nace_code="47.110", url="https://example.test/hook"),
    )
    body = client.calls[0]["json_body"]
    assert client.calls[0]["path"] == "/api/v1/nace/subscriptions"
    # Required/defaulted fields present
    assert body["nace_code"] == "47.110"
    assert body["aggregation_mode"] == "real_time"
    assert body["aktivert"] is True
    assert body["url"] == "https://example.test/hook"
    # Unset optional fields are NOT sent (so backend defaults apply)
    assert "events" not in body
    assert "kommune_filter" not in body
    assert "min_ansatte" not in body
    # Parsed output
    assert out.id == 7
    assert out.aktivert is True
    assert out.aggregation_mode == "real_time"


async def test_subscribe_nace_forwards_filters_and_events() -> None:
    client = _FakeClient({"subscription": {"id": 1, "nace_code": "G"}})
    await subscribe_handle(
        client,
        SubscribeNaceInput(
            nace_code="G",
            events=["status_changed"],
            aggregation_mode="daily_digest",
            kommune_filter=["0301"],
            min_ansatte=5,
        ),
    )
    body = client.calls[0]["json_body"]
    assert body["events"] == ["status_changed"]
    assert body["aggregation_mode"] == "daily_digest"
    assert body["kommune_filter"] == ["0301"]
    assert body["min_ansatte"] == 5


def test_subscribe_nace_rejects_invalid_event_type() -> None:
    """Pydantic Literal-validering skal avvise ugyldige event-typer før kallet."""
    with pytest.raises(Exception):
        SubscribeNaceInput(nace_code="47.110", events=["not_an_event"])


# ── list_my_subscriptions ────────────────────────────────────────────────────


async def test_list_my_subscriptions_parses_items() -> None:
    client = _FakeClient({
        "items": [
            {
                "id": 3,
                "nace_code": "62.010",
                "events": ["status_changed"],
                "aggregation_mode": "hourly_digest",
                "aktivert": True,
                "has_bearer_token": True,
            }
        ],
        "count": 1,
    })
    out = await list_subs_handle(client, ListMySubscriptionsInput())
    assert client.calls[0]["path"] == "/api/v1/nace/subscriptions"
    assert client.calls[0]["method"] == "GET"
    assert out.count == 1
    assert out.items[0].id == 3
    assert out.items[0].has_bearer_token is True


# ── delete_subscription ──────────────────────────────────────────────────────


async def test_delete_subscription_success() -> None:
    client = _FakeClient({"deleted": True, "id": 9})
    out = await delete_handle(client, DeleteSubscriptionInput(subscription_id=9))
    assert client.calls[0]["path"] == "/api/v1/nace/subscriptions/9"
    assert client.calls[0]["method"] == "DELETE"
    assert out.deleted is True
    assert out.id == 9
    assert out.already_absent is False


async def test_delete_subscription_404_is_idempotent_noop() -> None:
    client = _FakeClient(raise_exc=FirmaradarClientError("not found", status_code=404))
    out = await delete_handle(client, DeleteSubscriptionInput(subscription_id=404))
    assert out.deleted is False
    assert out.already_absent is True
    assert out.id == 404


async def test_delete_subscription_other_error_propagates() -> None:
    client = _FakeClient(raise_exc=FirmaradarClientError("boom", status_code=500))
    with pytest.raises(FirmaradarClientError):
        await delete_handle(client, DeleteSubscriptionInput(subscription_id=5))
