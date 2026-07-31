"""Smoke tests for the firmaradar-mcp tools.

These tests verify that:

* The 32-tool registry imports and exposes all expected names.
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

import pytest

from firmaradar_mcp.client import ClientConfig, ENV_API_BASE, ENV_API_KEY
from firmaradar_mcp.tools import ALL_TOOLS


EXPECTED_TOOL_NAMES = {
    # Selskap (7)
    "firmaradar_search_companies",
    "firmaradar_get_company",
    "firmaradar_get_company_ownership",
    "firmaradar_get_company_roles",
    "firmaradar_get_company_financials",
    "firmaradar_get_company_announcements",
    "firmaradar_get_company_ip",
    # Person (4)
    "firmaradar_search_persons",
    "firmaradar_get_person",
    "firmaradar_get_person_roles",
    "firmaradar_get_person_companies",
    # Risikosignaler (4)
    "firmaradar_get_company_signals",
    "firmaradar_check_aml_pep",
    "firmaradar_check_konkurs_eksponering",
    "firmaradar_get_recent_changes",
    # Bransje/relasjon (4)
    "firmaradar_list_companies_in_nace",
    "firmaradar_find_related_companies",
    "firmaradar_find_shared_connections",
    "firmaradar_compare_companies",
    # Tverr-søk (1)
    "firmaradar_search_announcements",
    # v0.3 markedsplass-utvidelser (#130) (4)
    "firmaradar_get_risk_score",
    "firmaradar_check_foretak_i_vanskeligheter",
    "firmaradar_get_aml_score",
    "firmaradar_get_konsernstotte",
    # AML-rapport async-sti (§8) (2)
    "firmaradar_start_aml_report",
    "firmaradar_get_aml_report",
    # v0.3 compliance-helper (#134) (1)
    "firmaradar_confirm_risk_score_disclaimer",
    # v0.3 bulk-portfolio-screening (#134) (2)
    "firmaradar_check_fiv_bulk",
    "firmaradar_get_risk_score_bulk",
    # i18n: valuta-konvertering (1)
    "firmaradar_convert_nok",
    # NACE-overvåkning v0.5 — agent-eksponering (4)
    "firmaradar_list_nace_codes",
    "firmaradar_subscribe_nace",
    "firmaradar_list_my_subscriptions",
    "firmaradar_delete_subscription",
    "firmaradar_add_company_monitoring",
}


def test_registry_lists_all_tools() -> None:
    names = {tool.name for tool in ALL_TOOLS}
    assert names == EXPECTED_TOOL_NAMES, names.symmetric_difference(EXPECTED_TOOL_NAMES)
    assert len(ALL_TOOLS) == 35


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


def test_write_and_destructive_tool_sets() -> None:
    """Skrive-verktøyene muterer privat Firmaradar-state eller audit/report-state.

    ``openWorldHint`` betyr skriveeffekt mot offentlig internett-state eller
    eksterne tredjepartssystemer, ikke at verktøyet leser eksterne kilder.
    """
    from firmaradar_mcp.tools import DESTRUCTIVE_TOOLS, OPEN_WORLD_TOOLS, WRITE_TOOLS

    names = {tool.name for tool in ALL_TOOLS}
    assert WRITE_TOOLS == {
        "firmaradar_check_aml_pep",
        "firmaradar_get_aml_score",
        "firmaradar_start_aml_report",
        "firmaradar_confirm_risk_score_disclaimer",
        "firmaradar_subscribe_nace",
        "firmaradar_delete_subscription",
        "firmaradar_add_company_monitoring",
    }
    assert WRITE_TOOLS <= names, WRITE_TOOLS - names
    assert OPEN_WORLD_TOOLS == frozenset()
    # Destruktive verktøy er en delmengde av skrive-verktøyene.
    assert DESTRUCTIVE_TOOLS == {"firmaradar_delete_subscription"}
    assert DESTRUCTIVE_TOOLS <= WRITE_TOOLS, DESTRUCTIVE_TOOLS - WRITE_TOOLS


def test_list_tools_advertises_titles_and_annotations() -> None:
    """``server._handler_to_tool`` skal sette ``title`` + ``ToolAnnotations`` på
    hvert verktøy med eksplisitte Apps SDK review-hints."""
    from firmaradar_mcp import server
    from firmaradar_mcp.tools import (
        DESTRUCTIVE_TOOLS,
        NON_IDEMPOTENT_TOOLS,
        OPEN_WORLD_TOOLS,
        WRITE_TOOLS,
    )

    for handler in ALL_TOOLS:
        tool = server._handler_to_tool(handler)
        assert tool.title, f"{tool.name} mangler title"
        assert tool.annotations is not None, f"{tool.name} mangler annotations"
        ann = tool.annotations
        assert ann.title == tool.title, f"{tool.name}: annotation-title != tool-title"
        expected_read_only = tool.name not in WRITE_TOOLS
        assert ann.read_only_hint is expected_read_only, (
            f"{tool.name}: readOnlyHint skal være {expected_read_only}"
        )
        expected_destructive = tool.name in DESTRUCTIVE_TOOLS
        assert ann.destructive_hint is expected_destructive, (
            f"{tool.name}: destructiveHint skal være {expected_destructive}"
        )
        expected_open_world = tool.name in OPEN_WORLD_TOOLS
        assert ann.open_world_hint is expected_open_world, (
            f"{tool.name}: openWorldHint skal være {expected_open_world}"
        )
        expected_idempotent = tool.name not in NON_IDEMPOTENT_TOOLS
        assert ann.idempotent_hint is expected_idempotent, (
            f"{tool.name}: idempotentHint skal være {expected_idempotent}"
        )


def test_every_tool_advertises_output_schema() -> None:
    """``_handler_to_tool`` skal sette ``outputSchema`` på hvert verktøy.

    OpenAI Apps SDK + Claude flagger ``OUTPUT SCHEMA RECOMMENDED`` når et
    verktøy mangler det. Vi deklarerer det fra den pydantic output-modellen
    hvert tool allerede har, og forventer et gyldig objekt-skjema."""
    from firmaradar_mcp import server

    for handler in ALL_TOOLS:
        tool = server._handler_to_tool(handler)
        assert tool.output_schema is not None, f"{tool.name} mangler outputSchema"
        # Pydantic-genererte skjemaer for BaseModel er alltid objekt-skjemaer.
        assert tool.output_schema.get("type") == "object", (
            f"{tool.name}: outputSchema skal være et objekt-skjema"
        )
        # Skjemaet skal beskrive minst ett felt (properties) ELLER referere
        # nøstede modeller via $defs — tomt skjema er en feil.
        assert tool.output_schema.get("properties") or tool.output_schema.get("$defs"), (
            f"{tool.name}: outputSchema mangler properties/$defs"
        )


async def test_tool_list_wire_preserves_security_schemes_under_meta() -> None:
    """Regresjon (mcp 2.0-migrering): ``tools/list``-svaret MÅ beholde
    ``securitySchemes`` under ``_meta`` på hvert verktøy — ChatGPT sin
    inline re-auth-UI trigges av dette feltet (se kommentaren ved
    ``_TOOL_SECURITY_SCHEMES`` i ``server.py`` for hele historikken).

    mcp_types 2.0.0 kjører EN EKSTRA revalidering for spec-metoder
    (``mcp_types.methods.serialize_server_result``, kalt fra
    ``ServerRunner._serialize``) OVENPÅ handler-returen, med
    ``extra="ignore"`` mot protokollens eget skjema — ETHVERT top-level felt
    utenfor spec-en droppes UANSETT retur-form (dict, ListToolsResult, eller
    en ``extra="allow"``-subclass). Et unit-nivå-kall på den registrerte
    handleren alene (uten denne silen) IKKE ville fanget dette — testen
    kjører derfor de to SAMME ekte SDK-funksjonene som
    ``ServerRunner._serialize`` bruker, i samme rekkefølge."""
    from mcp.server.runner import _dump_result
    from mcp_types.methods import serialize_server_result

    from firmaradar_mcp import server
    from firmaradar_mcp.tools import ALL_TOOLS as _tools

    srv = server.build_server(_tools, client=object())
    entry = srv.get_request_handler("tools/list")
    assert entry is not None, "on_list_tools ble ikke registrert på tools/list"

    result = await entry.handler(None, None)
    dumped = _dump_result(result)
    wire = serialize_server_result("tools/list", "2025-06-18", dumped)

    assert len(wire["tools"]) == len(_tools)
    for tool_wire in wire["tools"]:
        meta = tool_wire.get("_meta") or {}
        assert meta.get("securitySchemes") == [{"type": "oauth2", "scopes": ["mcp"]}], (
            f"{tool_wire.get('name')}: _meta.securitySchemes mangler i tools/list-wire-responsen"
        )
        # Regresjonsvakt: dette feltet skal IKKE ligge top-level (det ble
        # flyttet nettopp fordi top-level ikke overlever silen over).
        assert "securitySchemes" not in tool_wire, (
            f"{tool_wire.get('name')}: securitySchemes ligger top-level — "
            "skal ligge under _meta (se _TOOL_SECURITY_SCHEMES-kommentaren)"
        )
        assert "outputSchema" in tool_wire, f"{tool_wire.get('name')}: outputSchema mangler på wire"
        assert "annotations" in tool_wire, f"{tool_wire.get('name')}: annotations mangler på wire"


def test_error_result_is_flagged_and_unstructured() -> None:
    """Feilsvar skal være ``isError=True`` uten ``structuredContent`` — slik at
    SDK-en tar dem as-is og ikke kjører outputSchema-validering på dem."""
    from firmaradar_mcp import server

    res = server._error_result({"error": "boom", "tool": "x"})
    assert res.is_error is True
    assert res.structured_content is None
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


# Ingen verktøy er lenger deferred — alle gjør reelle API-kall, inkludert
# ``find_related_companies`` med via=owner (traversal på den eksisterende
# aksjeeierbok-eierskapsgrafen; RRH/UBO-gjennomskjæring lander med BRREG-scopet).
# Den fokuserte testen under låser at via=owner nå treffer REST-API-et og
# mapper responsen — ingen NotImplementedError lenger.
async def test_find_related_companies_owner_mode_hits_api() -> None:
    """``find_related_companies`` med via=owner skal nå routes til
    ``GET /api/v1/company/<orgnr>/related?via=owner`` og mappe delt-eier-
    treffene til RelatedCompany, IKKE raise NotImplementedError."""
    from firmaradar_mcp.tools.find_related_companies import (
        FindRelatedCompaniesInput,
        handle,
    )

    class _StubClient:
        def __init__(self):
            self.last_path = None
            self.last_params = None

        async def get(self, path, params=None):
            self.last_path = path
            self.last_params = params
            return {
                "orgnr": "123456789",
                "via": "owner",
                "related": [
                    {
                        "orgnr": "999888777",
                        "navn": "Delt Eier AS",
                        "relation_strength": 2,
                        "shared_entities": [
                            {"type": "owner", "owner_type": "business",
                             "name": "Holding AS", "ownership_pct": 55.0},
                        ],
                    },
                ],
                "total_count": 1,
            }

    client = _StubClient()
    params = FindRelatedCompaniesInput(orgnr="123456789", via="owner", min_overlap=2)
    out = await handle(client, params)

    assert client.last_path == "/api/v1/company/123456789/related"
    assert client.last_params["via"] == "owner"
    assert client.last_params["min_overlap"] == 2
    assert out.via == "owner"
    assert out.total_count == 1
    assert len(out.related) == 1
    rel = out.related[0]
    assert rel.orgnr == "999888777"
    assert rel.navn == "Delt Eier AS"
    assert rel.relation_strength == 2
    assert rel.shared_entities[0]["owner_type"] == "business"


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
    if field_name == "nace_code":
        return "47.110"
    if field_name == "subscription_id":
        return 1
    if field_name == "via":
        return "person"
    if field_name == "entity_type":
        return "company"
    return "placeholder"


# ── Regresjon: timeout_s-videresending (innført + fikset 2026-05-30) ──────────
# Plumbingen går tool → client.post → _DispatchingClient.post →
# FirmaradarClient.post → httpx. _DispatchingClient ble først deployet UTEN
# timeout_s-param → alle kall med per-kall-timeout feilet med 'unexpected
# keyword argument timeout_s'. Kontrakten låses fortsatt på klient-lagene
# under, selv om get_aml_score (den opprinnelige brukeren, sync-først A2/
# v0.5.10) ble lagt om til ren async rapport-flyt 2026-07-07 (aml/score-
# deprecering) og ikke lenger sender timeout_s selv — andre tunge verktøy
# kan trenge den, og plumbingen skal ikke regressere stille.

async def test_get_aml_score_starts_async_report_flow() -> None:
    """aml/score-deprecering (2026-07-07): verktøyet skal gå RETT på async
    rapport-flyten (POST /api/v1/aml/report + DPA-headere) og ALDRI kalle
    den deprecerte synkrone /api/v1/aml/score-ruta."""
    from firmaradar_mcp.tools import get_aml_score as _mod
    from firmaradar_mcp.tools.get_aml_score import handle, GetAmlScoreInput

    captured: dict = {}

    class _FakeClient:
        async def post(self, path, json_body=None, *, extra_headers=None, timeout_s=None):
            captured["post_path"] = path
            captured["extra_headers"] = extra_headers
            return {"rapport_id": "a" * 32, "status": "pending"}

        async def get(self, path, params=None):
            captured["get_path"] = path
            return {"status": "done", "orgnr": "923609016", "score": 25,
                    "level": "low", "rapport_id": "a" * 32}

    # Krymp poll-intervallet så testen ikke sover 3s.
    orig = (_mod._ASYNC_POLL_BUDGET_S, _mod._ASYNC_POLL_INTERVAL_S)
    _mod._ASYNC_POLL_BUDGET_S, _mod._ASYNC_POLL_INTERVAL_S = 0.05, 0.01
    try:
        out = await handle(_FakeClient(), GetAmlScoreInput(orgnr="923609016", purpose="manual"))
    finally:
        _mod._ASYNC_POLL_BUDGET_S, _mod._ASYNC_POLL_INTERVAL_S = orig
    assert captured["post_path"] == "/api/v1/aml/report"
    assert captured["extra_headers"]["X-FR-DPA-Confirmed"] == "true"
    assert captured["get_path"] == "/api/v1/aml/report/" + "a" * 32
    assert out.score == 25 and out.level == "low"


async def test_firmaradar_client_post_forwards_timeout_s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_API_KEY, "test-key")
    from firmaradar_mcp.client import FirmaradarClient

    client = FirmaradarClient()
    captured: dict = {}

    async def fake_httpx_post(path, **kwargs):
        captured.update(kwargs)
        return object()

    client._client.post = fake_httpx_post
    client._handle_response = lambda resp: {}
    try:
        # Med timeout_s → per-kall timeout settes
        await client.post("/x", json_body={"a": 1}, timeout_s=60.0)
        assert captured.get("timeout") == 60.0
        # Uten timeout_s → ingen per-kall timeout (bruker klient-default)
        captured.clear()
        await client.post("/y", json_body={})
        assert "timeout" not in captured
    finally:
        await client.aclose()


def test_dispatching_client_forwards_timeout_s() -> None:
    """Regresjon: _DispatchingClient.post må VIDERESENDE timeout_s til den
    underliggende FirmaradarClient (closure-lokal klasse → source-sjekk, samme
    mønster som test_no_tool_uses_json_kwarg_on_client_post)."""
    import pathlib
    from firmaradar_mcp import remote_server

    src = pathlib.Path(remote_server.__file__).read_text(encoding="utf-8")
    assert "timeout_s=timeout_s" in src, (
        "_DispatchingClient.post videresender ikke timeout_s — "
        "get_aml_score vil feile med TypeError før HTTP-kallet"
    )


async def test_get_person_single_aggregate_call_surfaces_konkurs() -> None:
    """``get_person`` er ETT kall mot server-side-aggregatet
    ``/api/v1/person/<id>`` — ingen klient-side dispatch mot roles-/
    shareholdings-endepunktene. Backendens ``konkurs_eksponering``
    (flagg-for-gjennomgang-signalet) løftes rett inn i output-en."""
    from firmaradar_mcp.tools.get_person import GetPersonInput, handle

    pid = "role-" + "a" * 24
    calls: list[str] = []

    class _StubClient:
        async def get(self, path, params=None):
            calls.append(path)
            assert path == f"/api/v1/person/{pid}"
            return {
                "person_id": pid,
                "navn": "Ola Nordmann",
                "birth_year": 1970,
                "summary": "Ola Nordmann, 1 aktive verv",
                "active_roles": [
                    {"orgnr": "111111111", "company_name": "Aktiv AS",
                     "rolle_type": "Styrets leder", "active": True},
                ],
                "shareholdings": [],
                "aml_pep_hits": [],
                "aml_pep_note": "Dette oppslaget gjør ingen PEP-sjekk.",
                "konkurs_eksponering": {
                    "antall_konkursforetak": 2,
                    "foretak": [
                        {"orgnr": "222222222", "rolletype": "Styrets leder",
                         "konkursdato": "2022-05-01", "tiltradt": "2018-01-01",
                         "tenure_days": 1000},
                        {"orgnr": "333333333", "rolletype": "Daglig leder",
                         "konkursdato": "2020-03-01", "tiltradt": "2015-06-01",
                         "tenure_days": 1200},
                    ],
                    "note": "Navnematch uten fødselsnummer — flagg for gjennomgang.",
                },
            }

    out = await handle(_StubClient(), GetPersonInput(person_id=pid))
    assert calls == [f"/api/v1/person/{pid}"]
    assert out.navn == "Ola Nordmann"
    assert out.birth_year == 1970
    assert out.summary == "Ola Nordmann, 1 aktive verv"
    assert len(out.active_roles) == 1
    assert out.aml_pep_hits == []
    assert "PEP" in (out.aml_pep_note or "")
    assert out.konkurs_eksponering.get("antall_konkursforetak") == 2
    assert len(out.konkurs_eksponering.get("foretak") or []) == 2
    assert "flagg" in (out.konkurs_eksponering.get("note") or "").lower()


async def test_get_person_no_konkurs_eksponering_stays_empty() -> None:
    """Uten treff (antall=0) skal feltet forbli tomt, ikke støy —
    tom-normaliseringen fra fan-out-varianten består i aggregat-kallet."""
    from firmaradar_mcp.tools.get_person import GetPersonInput, handle

    class _StubClient:
        async def get(self, path, params=None):
            return {
                "navn": "Kari Ren",
                "active_roles": [],
                "shareholdings": [],
                "konkurs_eksponering": {"antall_konkursforetak": 0, "foretak": [], "note": ""},
            }

    out = await handle(_StubClient(), GetPersonInput(person_id="role-" + "b" * 24))
    assert out.konkurs_eksponering == {}


async def test_get_person_shareholder_key_same_shape() -> None:
    """Aksjonær-nøkkel (``person-YYYY-…``) går mot samme aggregat og gir
    samme nøkkelsett — aggregatet normaliserer owner_name/name-forskjellen
    server-side. Regresjon for `person-2025-110a167ab75b76464b231f5f`
    (Karl Petter Ulriksen → 3 foretak)."""
    from firmaradar_mcp.tools.get_person import GetPersonInput, handle

    pid = "person-2025-" + "a" * 24

    class _StubClient:
        async def get(self, path, params=None):
            assert path == f"/api/v1/person/{pid}"
            return {
                "person_id": pid,
                "navn": "KARL PETTER ULRIKSEN",
                "birth_year": 1973,
                "shareholdings": [
                    {"child_orgnr": "991045368", "company_name": "FRIHETEN INVEST AS",
                     "ownership_pct": 100.0},
                ],
                "konkurs_eksponering": {
                    "antall_konkursforetak": 3,
                    "foretak": [
                        {"orgnr": "111111111", "rolletype": "Styrets leder",
                         "konkursdato": "2022-05-01", "tiltradt": "2018-01-01",
                         "tenure_days": 1000},
                    ],
                    "note": "Navnematch uten fødselsnummer — flagg for gjennomgang.",
                },
            }

    out = await handle(_StubClient(), GetPersonInput(person_id=pid))
    assert out.navn == "KARL PETTER ULRIKSEN"
    assert out.birth_year == 1973
    assert out.konkurs_eksponering.get("antall_konkursforetak") == 3
    assert len(out.shareholdings) == 1


async def test_get_person_client_error_degrades_to_empty_profile() -> None:
    """Ukjent/ugyldig ID: klient-feil svelges og gir tom profil — samme
    degradering som fan-out-varianten hadde (aldri exception ut av tool-et)."""
    from firmaradar_mcp.client import FirmaradarClientError
    from firmaradar_mcp.tools.get_person import GetPersonInput, handle

    class _StubClient:
        async def get(self, path, params=None):
            raise FirmaradarClientError("404 fra aggregatet")

    pid = "role-" + "c" * 24
    out = await handle(_StubClient(), GetPersonInput(person_id=pid))
    assert out.person_id == pid
    assert out.navn == ""
    assert out.active_roles == []
    assert out.shareholdings == []
    assert out.konkurs_eksponering == {}


async def test_check_konkurs_eksponering_name_lookup() -> None:
    """Navn-basert konkurs-eksponering — for HISTORISKE konkursgjengangere
    uten person-nøkkel. Slår opp roller_history direkte på navn og bevarer
    flagg-for-gjennomgang-rammen i ``note``."""
    from firmaradar_mcp.tools.check_konkurs_eksponering import (
        CheckKonkursEksponeringInput,
        handle,
    )

    class _StubClient:
        async def get(self, path, params=None):
            assert path == "/api/v1/person/konkurs-eksponering"
            assert params == {"navn": "Karl Petter Ulriksen"}
            return {
                "navn": "Karl Petter Ulriksen",
                "konkurs_eksponering": {
                    "antall_konkursforetak": 3,
                    "foretak": [
                        {"orgnr": "111111111", "rolletype": "Styrets leder",
                         "konkursdato": "2022-05-01", "tiltradt": "2018-01-01",
                         "tenure_days": 1000},
                    ],
                    "note": "Navnematch uten fødselsnummer — flagg for gjennomgang.",
                },
            }

    out = await handle(
        _StubClient(),
        CheckKonkursEksponeringInput(navn="Karl Petter Ulriksen"),
    )
    assert out.antall_konkursforetak == 3
    assert len(out.foretak) == 1
    assert out.foretak[0].orgnr == "111111111"
    assert "flagg" in (out.note or "").lower()
