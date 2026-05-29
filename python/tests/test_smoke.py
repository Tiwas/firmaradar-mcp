"""Smoke tests for the firmaradar-mcp tools.

These tests verify that:

* The 25-tool registry imports and exposes all expected names.
* Every tool has a user-friendly title and accurate MCP
  ``ToolAnnotations`` (readOnlyHint etc.) — required by the connector
  directories.
* Handler-signaturen er ``(client, params)`` per Lars-beslutning 2026-05-25.
* 1 DEFER-tool (find_related_companies) raiser NotImplementedError ved
  kall — implementeres i en senere versjon.
* The remaining implemented tools er kallbare (kallet vil prøve å nå
  REST-API og kan kaste FirmaradarClientError mot mock, men ikke
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
    # v0.3 markedsplass-utvidelser (#130) (5)
    "firmaradar_get_risk_score",
    "firmaradar_check_foretak_i_vanskeligheter",
    "firmaradar_get_aml_score",
    "firmaradar_get_konsernstotte",
    "firmaradar_get_skattelister",
    # v0.3 compliance-helper (#134) (1)
    "firmaradar_confirm_risk_score_disclaimer",
    # v0.3 bulk-portfolio-screening (#134) (2)
    "firmaradar_check_fiv_bulk",
    "firmaradar_get_risk_score_bulk",
}


def test_registry_lists_all_tools() -> None:
    names = {tool.name for tool in ALL_TOOLS}
    assert names == EXPECTED_TOOL_NAMES, names.symmetric_difference(EXPECTED_TOOL_NAMES)
    assert len(ALL_TOOLS) == 25


def test_every_tool_has_description_and_schemas() -> None:
    for tool in ALL_TOOLS:
        assert tool.description.strip(), f"{tool.name} missing description"
        assert tool.input_schema is not None, f"{tool.name} missing input schema"
        assert tool.output_schema is not None, f"{tool.name} missing output schema"
        assert callable(tool.handler), f"{tool.name} handler not callable"


def test_every_tool_has_user_friendly_title() -> None:
    """MCP-connector-katalogene krever en menneskevennlig tittel per verktøy.
    Hver tool i registeret må ha en ``TOOL_TITLES``-oppføring (ikke bare navnet),
    og det skal ikke finnes orphan-titler for verktøy som ikke finnes."""
    from firmaradar_mcp.tools import TOOL_TITLES

    names = {tool.name for tool in ALL_TOOLS}
    assert set(TOOL_TITLES) == names, set(TOOL_TITLES).symmetric_difference(names)
    for name, title in TOOL_TITLES.items():
        assert title.strip(), f"{name} har tom tittel"
        assert title != name, f"{name} bør ha en lesbar tittel, ikke selve verktøynavnet"


def test_exactly_the_disclaimer_tool_is_a_write_tool() -> None:
    """Bare disclaimer-bekreftelsen skriver state; alt annet er rene oppslag."""
    from firmaradar_mcp.tools import WRITE_TOOLS

    names = {tool.name for tool in ALL_TOOLS}
    assert WRITE_TOOLS == {"firmaradar_confirm_risk_score_disclaimer"}
    assert WRITE_TOOLS <= names, WRITE_TOOLS - names


def test_list_tools_advertises_titles_and_annotations() -> None:
    """``server._handler_to_tool`` skal sette ``title`` + ``ToolAnnotations`` på
    hvert verktøy: ``readOnlyHint=True`` for oppslag, ``False`` for skrive-
    verktøy, aldri destruktivt."""
    from firmaradar_mcp import server
    from firmaradar_mcp.tools import WRITE_TOOLS

    for handler in ALL_TOOLS:
        tool = server._handler_to_tool(handler)
        assert tool.title, f"{tool.name} mangler title"
        assert tool.annotations is not None, f"{tool.name} mangler annotations"
        ann = tool.annotations
        assert ann.title == tool.title, f"{tool.name}: annotation-title != tool-title"
        expected_read_only = tool.name not in WRITE_TOOLS
        assert ann.readOnlyHint is expected_read_only, (
            f"{tool.name}: readOnlyHint skal være {expected_read_only}"
        )
        assert ann.destructiveHint is False, f"{tool.name} skal ikke være destruktivt"
        assert ann.idempotentHint is True, f"{tool.name} skal være idempotent"


def test_every_tool_advertises_output_schema() -> None:
    """``_handler_to_tool`` skal sette ``outputSchema`` på hvert verktøy.

    OpenAI Apps SDK + Claude flagger ``OUTPUT SCHEMA RECOMMENDED`` når et
    verktøy mangler det. Vi deklarerer det fra den pydantic output-modellen
    hvert tool allerede har, og forventer et gyldig objekt-skjema."""
    from firmaradar_mcp import server

    for handler in ALL_TOOLS:
        tool = server._handler_to_tool(handler)
        assert tool.outputSchema is not None, f"{tool.name} mangler outputSchema"
        # Pydantic-genererte skjemaer for BaseModel er alltid objekt-skjemaer.
        assert tool.outputSchema.get("type") == "object", (
            f"{tool.name}: outputSchema skal være et objekt-skjema"
        )
        # Skjemaet skal beskrive minst ett felt (properties) ELLER referere
        # nøstede modeller via $defs — tomt skjema er en feil.
        assert tool.outputSchema.get("properties") or tool.outputSchema.get("$defs"), (
            f"{tool.name}: outputSchema mangler properties/$defs"
        )


def test_error_result_is_flagged_and_unstructured() -> None:
    """Feilsvar skal være ``isError=True`` uten ``structuredContent`` — slik at
    SDK-en tar dem as-is og ikke kjører outputSchema-validering på dem."""
    from firmaradar_mcp import server

    res = server._error_result({"error": "boom", "tool": "x"})
    assert res.isError is True
    assert res.structuredContent is None
    assert res.content and res.content[0].type == "text"


def test_structured_content_serialises_models_and_dicts() -> None:
    """``_structured_content`` skal returnere en dict for BaseModel/dict og
    ``None`` for ikke-coerce-bare typer (trygt — vi returnerer alltid
    CallToolResult, så None gir ren tekst uten valideringsfeil)."""
    from pydantic import BaseModel

    from firmaradar_mcp import server
    from firmaradar_mcp.tools import ALL_TOOLS as _tools

    class _Sample(BaseModel):
        a: int
        b: str | None = None

    handler = _tools[0]  # vilkårlig handler — kun output_schema brukes i str-grenen

    # BaseModel → dict, exclude_none dropper b=None
    assert server._structured_content(handler, _Sample(a=1)) == {"a": 1}
    # dict → passthrough
    assert server._structured_content(handler, {"k": "v"}) == {"k": "v"}
    # ren streng coerce-er ikke gjennom en objekt-modell → None
    assert server._structured_content(handler, "not-an-object") is None


def test_no_tool_uses_json_kwarg_on_client_post() -> None:
    """Regresjon: ``FirmaradarClient.post()`` tar ``json_body=``, ikke ``json=``.
    ``get_aml_score`` ble deployet med ``json=`` og feilet i prod 2026-05-28
    (TypeError før HTTP-kallet ble sendt). Vakt mot at feil kwarg sniker seg
    inn igjen i et hvilket som helst tool."""
    import pathlib
    from firmaradar_mcp import tools as _tools_pkg

    tools_dir = pathlib.Path(_tools_pkg.__file__).parent
    offenders = [
        path.name
        for path in sorted(tools_dir.glob("*.py"))
        if "client.post(" in (src := path.read_text(encoding="utf-8")) and "json=" in src
    ]
    assert not offenders, f"tools som bruker json= i stedet for json_body=: {offenders}"


# Ingen verktøy er lenger *rent* deferred — alle gjør reelle API-kall. Det
# eneste gjenværende deferrede er én *modus*: ``find_related_companies`` med
# via=owner (krever UBO-graf-traversal, deferred til v0.3). Den dekkes av den
# fokuserte testen under; alle 25 verktøy har korrekt handler-signatur.
async def test_find_related_companies_owner_mode_is_deferred() -> None:
    """``find_related_companies`` er implementert for via=person/address, men
    via=owner er deferred (krever UBO-graf-traversal) og skal raise
    NotImplementedError med en hjelpende workaround-melding — uten å treffe
    REST-API-et, siden sjekken skjer før nettverkskallet."""
    import os
    os.environ.setdefault("FIRMARADAR_API_KEY", "test-key-for-test-only")
    from firmaradar_mcp.client import FirmaradarClient
    from firmaradar_mcp.tools.find_related_companies import (
        FindRelatedCompaniesInput,
        handle,
    )

    client = FirmaradarClient()
    try:
        params = FindRelatedCompaniesInput(orgnr="123456789", via="owner")
        with pytest.raises(NotImplementedError) as exc_info:
            await handle(client, params)
        msg = str(exc_info.value).lower()
        assert "v0.3" in msg or "owner" in msg, (
            "NotImplementedError-meldingen bør forklare at via=owner er deferred"
        )
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    "tool",
    list(ALL_TOOLS),
    ids=lambda t: t.name,
)
def test_implemented_tools_accept_client_and_params(tool) -> None:
    """Alle tools skal ha (client, params)-signatur.
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


def test_client_sends_x_fr_client_header_not_legacy_x_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MCP-serveren skal sende den NYE ``X-FR-Client``-headeren med
    ``firmaradar-mcp/<v>``-prefiks, ikke den legacy ``X-MCP-Client``-
    headeren. Backend støtter begge i 6+ mnd, men ny kode skal kun sende
    foretrukket header (Lars-beslutning 2026-05-27, #L_telemetri.A).

    Snapshot-test: hvis noen ved en feil reverterer ``client.py`` til
    legacy-headeren skal denne testen fange det.
    """
    from firmaradar_mcp import __version__ as _mcp_version
    from firmaradar_mcp.client import FirmaradarClient

    monkeypatch.setenv(ENV_API_KEY, "test-key")
    client = FirmaradarClient()
    default_headers = client._client.headers
    assert "X-FR-Client" in default_headers, (
        "MCP-klienten skal sende X-FR-Client (foretrukket). "
        f"Fant headers: {dict(default_headers)}"
    )
    # Forventet verdi inkluderer pakke-versjonen — billing-relevant
    # at MCP-pool identifiseres via ``mcp``-substring i verdien.
    assert default_headers["X-FR-Client"] == f"firmaradar-mcp/{_mcp_version}"
    # Legacy-headeren skal IKKE lenger sendes — backend håndterer
    # bakoverkompatibilitet, ikke klienten.
    assert "X-MCP-Client" not in default_headers, (
        "Legacy X-MCP-Client skal IKKE sendes av ny MCP-klient. "
        f"Fant headers: {dict(default_headers)}"
    )


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
