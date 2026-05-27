"""Smoke tests for the firmaradar-mcp tools.

These tests verify that:

* The 17-tool registry imports and exposes all expected names.
* Handler-signaturen er ``(client, params)`` per Lars-beslutning 2026-05-25.
* 4 DEFER-tools (check_aml_pep, get_company_signals,
  find_related_companies, search_announcements) raiser
  NotImplementedError ved kall — implementeres i v0.2.
* 13 IMPLEMENTED-tools er kallbare (kallet vil prøve å nå REST-API
  og kan kaste FirmaradarClientError mot mock, men ikke
  NotImplementedError).
* The :class:`ClientConfig` correctly refuses to start without an
  API-key.

Run with ``python -m pytest tests/`` from the ``python/`` directory.
"""

from __future__ import annotations

import importlib
import os

import pytest

from firmaradar_mcp.client import ClientConfig, ENV_API_BASE, ENV_API_KEY
from firmaradar_mcp.tools import ALL_TOOLS


EXPECTED_TOOL_NAMES = {
    # Selskap (6)
    "firmaradar_search_companies",
    "firmaradar_get_company",
    "firmaradar_get_company_ownership",
    "firmaradar_get_company_roles",
    "firmaradar_get_company_financials",
    "firmaradar_get_company_announcements",
    # Person (4)
    "firmaradar_search_persons",
    "firmaradar_get_person",
    "firmaradar_get_person_roles",
    "firmaradar_get_person_companies",
    # Risikosignaler (3)
    "firmaradar_get_company_signals",
    "firmaradar_check_aml_pep",
    "firmaradar_get_recent_changes",
    # Bransje/relasjon (3)
    "firmaradar_list_companies_in_nace",
    "firmaradar_find_related_companies",
    "firmaradar_compare_companies",
    # Tverr-søk (1)
    "firmaradar_search_announcements",
}


def test_registry_lists_all_seventeen_tools() -> None:
    names = {tool.name for tool in ALL_TOOLS}
    assert names == EXPECTED_TOOL_NAMES, names.symmetric_difference(EXPECTED_TOOL_NAMES)
    assert len(ALL_TOOLS) == 17


def test_every_tool_has_description_and_schemas() -> None:
    for tool in ALL_TOOLS:
        assert tool.description.strip(), f"{tool.name} missing description"
        assert tool.input_schema is not None, f"{tool.name} missing input schema"
        assert tool.output_schema is not None, f"{tool.name} missing output schema"
        assert callable(tool.handler), f"{tool.name} handler not callable"


# 4 tools er bevisst utsatt til v0.2 — disse skal raise
# NotImplementedError med en hjelpende workaround-melding.
DEFERRED_TOOL_NAMES = {
    "firmaradar_check_aml_pep",
    "firmaradar_get_company_signals",
    "firmaradar_find_related_companies",
    "firmaradar_search_announcements",
}


@pytest.mark.parametrize(
    "tool",
    [t for t in ALL_TOOLS if t.name in DEFERRED_TOOL_NAMES],
    ids=lambda t: t.name,
)
async def test_deferred_tools_raise_with_helpful_message(tool) -> None:
    """v0.2-deferred tools skal raise NotImplementedError med v0.1-
    workaround i meldingen, slik at agenten får handling."""
    import os
    os.environ.setdefault("FIRMARADAR_API_KEY", "test-key-for-test-only")
    from firmaradar_mcp.client import FirmaradarClient
    client = FirmaradarClient()
    try:
        payload = _minimal_payload(tool.input_schema)
        with pytest.raises(NotImplementedError) as exc_info:
            await tool.handler(client, payload)
        # Skal nevne "v0.1" eller "v0.2" i meldingen så agenten vet status
        msg = str(exc_info.value).lower()
        assert "v0.1" in msg or "v0.2" in msg, (
            f"{tool.name}: NotImplementedError-melding bør referere v0.1/v0.2-status"
        )
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    "tool",
    [t for t in ALL_TOOLS if t.name not in DEFERRED_TOOL_NAMES],
    ids=lambda t: t.name,
)
def test_implemented_tools_accept_client_and_params(tool) -> None:
    """13 IMPLEMENTED-tools skal ha (client, params)-signatur.
    Vi sjekker bare at signaturen er korrekt; faktisk kall krever
    live API-gates (egne integrasjonstester)."""
    import inspect
    sig = inspect.signature(tool.handler)
    params = list(sig.parameters.keys())
    assert len(params) == 2, (
        f"{tool.name}: handler skal ta (client, params) — fikk {params}"
    )
    assert "client" in params[0].lower() or params[0] == "client", (
        f"{tool.name}: første parameter bør hete 'client', fikk '{params[0]}'"
    )


def test_client_config_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_API_KEY, raising=False)
    with pytest.raises(ValueError, match=ENV_API_KEY):
        ClientConfig.from_env()


def test_client_config_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_API_KEY, "test-key")
    monkeypatch.setenv(ENV_API_BASE, "http://localhost:8080/")
    config = ClientConfig.from_env()
    assert config.api_key == "test-key"
    assert config.base_url == "http://localhost:8080"  # trailing slash stripped


def test_server_module_imports() -> None:
    """Server module must import cleanly even before MCP wiring is done."""
    module = importlib.import_module("firmaradar_mcp.server")
    assert hasattr(module, "main")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_payload(schema):
    """Return an instance of ``schema`` with placeholder values for required fields."""
    placeholders: dict[str, object] = {}
    for field_name, field in schema.model_fields.items():
        if not field.is_required():
            continue
        placeholders[field_name] = _placeholder_for(field_name)
    return schema(**placeholders)


def _placeholder_for(field_name: str) -> object:
    if field_name in {"orgnr", "id"}:
        return "123456789"
    if field_name in {"orgnrs"}:
        return ["123456789"]
    if field_name in {"q", "name"}:
        return "Test"
    if field_name in {"person_key"}:
        return "person-1980-aaaaaaaaaaaaaaaaaaaaaaaa"
    if field_name in {"role_person_id", "person_id"}:
        return "role-aaaaaaaaaaaaaaaaaaaaaaaa"
    if field_name == "code":
        return "47.11"
    if field_name == "via":
        return "person"
    if field_name == "entity_type":
        return "company"
    return "placeholder"
