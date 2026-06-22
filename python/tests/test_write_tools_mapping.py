"""MCP-lag-mapping for skrive-verktøyene (subscribe_nace, delete_subscription,
start_aml_report, confirm_risk_score_disclaimer).

Samme bug-klasse som lese-verktøy-funnene A–F (QA 2026-06-22): verifiser at
handlerne leser KANONISKE backend-nøkler (rapport_id, subscription.id, …), former
riktig request-body/path, og håndterer feil-/idempotens-konvolutter — uten å røre
ekte konto/fakturering (stub-klient)."""
from __future__ import annotations

import asyncio

from firmaradar_mcp.client import FirmaradarClientError
from firmaradar_mcp.tools.subscribe_nace import SubscribeNaceInput, handle as sub_handle
from firmaradar_mcp.tools.delete_subscription import (
    DeleteSubscriptionInput,
    handle as del_handle,
)
from firmaradar_mcp.tools.start_aml_report import StartAmlReportInput, handle as aml_handle
from firmaradar_mcp.tools.confirm_risk_score_disclaimer import (
    ConfirmRiskScoreDisclaimerInput,
    handle as conf_handle,
)


class _Stub:
    """Fanger siste request og returnerer et forhåndssatt svar (eller kaster)."""

    def __init__(self, response=None, raise_exc=None):
        self._response = response if response is not None else {}
        self._raise = raise_exc
        self.calls = []

    async def post(self, path, json_body=None, params=None):
        self.calls.append(("POST", path, json_body))
        if self._raise:
            raise self._raise
        return self._response

    async def delete(self, path, params=None):
        self.calls.append(("DELETE", path, None))
        if self._raise:
            raise self._raise
        return self._response


# ── subscribe_nace ──────────────────────────────────────────────────────────

def test_subscribe_nace_posts_and_reads_subscription_envelope():
    stub = _Stub({"subscription": {"id": 42, "nace_code": "62.010", "aktivert": True,
                                   "events": ["ny_virksomhet"], "aggregation_mode": "umiddelbar"}})
    out = asyncio.run(sub_handle(stub, SubscribeNaceInput(nace_code="62.010")))
    assert stub.calls[0][:2] == ("POST", "/api/v1/nace/subscriptions")
    assert out.id == 42 and out.nace_code == "62.010" and out.aktivert is True


# ── delete_subscription ─────────────────────────────────────────────────────

def test_delete_subscription_targets_id_path():
    stub = _Stub({"deleted": True, "id": 42})
    out = asyncio.run(del_handle(stub, DeleteSubscriptionInput(subscription_id=42)))
    assert stub.calls[0] == ("DELETE", "/api/v1/nace/subscriptions/42", None)
    assert out.deleted is True and out.id == 42


def test_delete_subscription_404_is_idempotent_no_op():
    stub = _Stub(raise_exc=FirmaradarClientError("not found", status_code=404))
    out = asyncio.run(del_handle(stub, DeleteSubscriptionInput(subscription_id=999)))
    assert out.deleted is False and out.already_absent is True and out.id == 999


def test_delete_subscription_non_404_propagates():
    stub = _Stub(raise_exc=FirmaradarClientError("boom", status_code=500))
    try:
        asyncio.run(del_handle(stub, DeleteSubscriptionInput(subscription_id=1)))
        assert False, "should have raised"
    except FirmaradarClientError as e:
        assert e.status_code == 500


# ── start_aml_report ────────────────────────────────────────────────────────

def test_start_aml_report_reads_rapport_id_key():
    # Backend (routes_mcp_v3) returnerer 'rapport_id' + status pending (HTTP 202).
    stub = _Stub({"rapport_id": "amlr_abc123", "orgnr": "923609016", "status": "pending"})
    out = asyncio.run(aml_handle(stub, StartAmlReportInput(orgnr="923609016", purpose="kyc_review")))
    assert stub.calls[0][:2] == ("POST", "/api/v1/aml/report")
    assert stub.calls[0][2] == {"orgnr": "923609016", "purpose": "kyc_review"}
    assert out.report_id == "amlr_abc123" and out.status == "pending"


# ── confirm_risk_score_disclaimer ───────────────────────────────────────────

def test_confirm_disclaimer_maps_audit_and_idempotent():
    stub = _Stub({"confirmed": True, "version": "v1", "confirmed_by_user_id": 7,
                  "audit_id": 100, "idempotent": False})
    out = asyncio.run(conf_handle(stub, ConfirmRiskScoreDisclaimerInput()))
    assert stub.calls[0][:2] == ("POST", "/api/v1/risikoscoring/confirm-disclaimer")
    assert out.confirmed is True and out.confirmed_by_user_id == 7
    assert out.audit_id == 100 and out.idempotent is False


def test_confirm_disclaimer_idempotent_replay():
    stub = _Stub({"confirmed": True, "version": "v1", "confirmed_by_user_id": 7,
                  "audit_id": None, "idempotent": True})
    out = asyncio.run(conf_handle(stub, ConfirmRiskScoreDisclaimerInput()))
    assert out.idempotent is True and out.audit_id is None
