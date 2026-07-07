"""Tester for async rapport-flyten i get_aml_score-verktøyet.

Historikk: denne filen het ``test_aml_factors_mapping.py`` og låste
factor-mappingen i den SYNKRONE ``POST /api/v1/aml/score``-parsingen
(name/trigger-nøkler, bug 2026-05-31). Den synkrone stien ble deprecert
2026-07-07 (kostnadsmatrise §4.6 + pen-test B1) og verktøyet går nå RETT
på async rapport-flyten (``POST /api/v1/aml/report`` → poll) — sync-parse-
koden (og dermed factor-mapping-regresjonen) er fjernet med vilje.

Kontrakten som låses nå:

1. handle() starter async-rapporten på ``/api/v1/aml/report`` med
   DPA-headere (X-FR-Purpose url-enkodet + X-FR-DPA-Confirmed) — ALDRI
   den deprecerte ``/api/v1/aml/score``-ruta.
2. 202-svaret (rapport_id) polles til ``done`` → score/level/rapport_id
   mappes ut; ``factors`` er alltid tom (detalj = rapport-lenkene).
3. ``failed`` → FirmaradarClientError.
4. Budsjett brukt opp uten terminal status → ``level="pending"`` +
   rapport_id (klienten poller videre med get_aml_report).
5. Manglende rapport_id i start-svaret → ærlig «unknown», ingen crash.
"""

from __future__ import annotations

import asyncio

import pytest

from firmaradar_mcp.client import FirmaradarClientError
from firmaradar_mcp.tools import get_aml_score
from firmaradar_mcp.tools.get_aml_score import GetAmlScoreInput, handle

ORGNR = "989795848"
JOB_ID = "f" * 32


class _StubClient:
    """Fanger post/get-kall; returnerer konfigurerbare payloads."""

    def __init__(self, start_payload, poll_payloads):
        self.start_payload = start_payload
        self.poll_payloads = list(poll_payloads)
        self.post_calls: list[dict] = []
        self.get_calls: list[str] = []

    async def post(self, path, json_body=None, *, extra_headers=None, timeout_s=None):
        self.post_calls.append({
            "path": path, "json_body": json_body,
            "extra_headers": extra_headers, "timeout_s": timeout_s,
        })
        return self.start_payload

    async def get(self, path, params=None):
        self.get_calls.append(path)
        if len(self.poll_payloads) > 1:
            return self.poll_payloads.pop(0)
        return self.poll_payloads[0]


@pytest.fixture(autouse=True)
def _fast_poll(monkeypatch):
    """Ingen ekte 3s-sleeps i test."""
    monkeypatch.setattr(get_aml_score, "_ASYNC_POLL_BUDGET_S", 0.05)
    monkeypatch.setattr(get_aml_score, "_ASYNC_POLL_INTERVAL_S", 0.01)


def test_starts_async_report_with_dpa_headers_never_score_route():
    client = _StubClient(
        {"rapport_id": JOB_ID, "status": "pending"},
        [{"status": "done", "orgnr": ORGNR, "score": 72, "level": "high",
          "rapport_id": JOB_ID}],
    )
    out = asyncio.run(handle(client, GetAmlScoreInput(orgnr=ORGNR)))
    assert len(client.post_calls) == 1
    call = client.post_calls[0]
    # RETT på async-flyten — den deprecerte score-ruta skal aldri kalles:
    assert call["path"] == "/api/v1/aml/report"
    assert call["json_body"] == {"orgnr": ORGNR, "purpose": "kyc_onboarding"}
    assert call["extra_headers"]["X-FR-DPA-Confirmed"] == "true"
    assert call["extra_headers"]["X-FR-Purpose"] == "kyc_onboarding"
    assert call["extra_headers"]["X-FR-Purpose-Encoding"] == "url"
    assert out.score == 72
    assert out.level == "high"
    assert out.rapport_id == JOB_ID
    assert out.factors == []  # detalj ligger i rapport-lenkene, ikke i poll-svaret


def test_polls_until_done():
    client = _StubClient(
        {"rapport_id": JOB_ID, "status": "pending"},
        [{"status": "running"},
         {"status": "done", "orgnr": ORGNR, "score": 12, "level": "low",
          "rapport_id": JOB_ID}],
    )
    out = asyncio.run(handle(client, GetAmlScoreInput(orgnr=ORGNR)))
    assert out.level == "low"
    assert client.get_calls == [f"/api/v1/aml/report/{JOB_ID}"] * 2


def test_failed_report_raises_client_error():
    client = _StubClient(
        {"rapport_id": JOB_ID, "status": "pending"},
        [{"status": "failed", "error": "orgnr finnes ikke"}],
    )
    with pytest.raises(FirmaradarClientError) as exc_info:
        asyncio.run(handle(client, GetAmlScoreInput(orgnr=ORGNR)))
    assert "orgnr finnes ikke" in str(exc_info.value)


def test_budget_exhausted_returns_pending_with_rapport_id():
    client = _StubClient(
        {"rapport_id": JOB_ID, "status": "pending"},
        [{"status": "running"}],
    )
    out = asyncio.run(handle(client, GetAmlScoreInput(orgnr=ORGNR)))
    assert out.level == "pending"
    assert out.rapport_id == JOB_ID
    assert out.raw and "get_aml_report" in str(out.raw.get("note"))


def test_missing_rapport_id_returns_unknown_without_crash():
    client = _StubClient({"error": "noe gikk galt"}, [{}])
    out = asyncio.run(handle(client, GetAmlScoreInput(orgnr=ORGNR)))
    assert out.level == "unknown"
    assert out.rapport_id is None
    assert client.get_calls == []
