"""MCP stdio-server entry point.

Boots the Model Context Protocol server, registers all 35 tools, and
runs the stdio event loop. Each tool is implemented as a small
self-contained module under :mod:`firmaradar_mcp.tools`; this file
orchestrates registration and dispatch.

Run with ``python -m firmaradar_mcp.server`` or via the
``firmaradar-mcp`` console-script (see ``pyproject.toml``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

from mcp import types
from mcp.server import NotificationOptions, Server, ServerRequestContext
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from pydantic import BaseModel

from .client import FirmaradarClient, FirmaradarClientError
from .tools import (
    ALL_TOOLS,
    DESTRUCTIVE_TOOLS,
    NON_IDEMPOTENT_TOOLS,
    OPEN_WORLD_TOOLS,
    TOOL_TITLES,
    WRITE_TOOLS,
    ToolHandler,
)


_LOG = logging.getLogger("firmaradar_mcp.server")

# MCP-server-navn vises i agent-klienten (Claude Desktop, Cursor, etc.).
# Holdes stabilt på tvers av versjoner så bruker ikke får "ny server"-prompt
# ved hver oppgradering.
_SERVER_NAME = "firmaradar-mcp"
_SERVER_VERSION = "0.6.0"

# Server-nivå instructions: gis til klienten i initialize-responsen og brukes
# av LLM-en som kontekst om hva Firmaradar dekker. Forhindrer at modellen
# avviser dekkede emner (f.eks. IP-rettigheter) fra priors uten å kalle et
# verktøy. Brand voice: enrichment-plattform, offisielle kilder navngis,
# scraper-vendorer navngis ALDRI (se README § Brand voice).
_INSTRUCTIONS = (
    "Firmaradar is an enrichment platform for Norwegian company intelligence — "
    "multi-source fusion of official registers (BRREG, Skatteetaten, Patentstyret) "
    "plus its own enrichment. Coverage includes: company profiles, group structure, "
    "ownership and beneficial owners, board roles, financials and key figures, BRREG "
    "announcements, public grants, merger/demerger relations, risk/AML/KYC signals, "
    "and intellectual-property portfolios — patents, trademarks and designs from "
    "Patentstyret (via `get_company` with `fields=['ip']`). For any question about a "
    "Norwegian company — including its patents, trademarks or designs — use these "
    "tools rather than relying on prior knowledge; the data is authoritative and "
    "refreshed daily."
)


def _configure_logging() -> None:
    """Send logs to stderr so they don't corrupt stdio MCP messages."""
    level = os.environ.get("FIRMARADAR_MCP_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _tools_by_name(tools: list[ToolHandler]) -> dict[str, ToolHandler]:
    """Indeks for rask dispatch fra call_tool-handleren."""
    return {t.name: t for t in tools}


def _input_schema_to_json(handler: ToolHandler) -> dict[str, Any]:
    """Konverter pydantic input-modellen til JSON Schema for MCP-protokollen.

    MCP forventer ``inputSchema``-objekt med ``type: object`` og
    ``properties``. Pydantic ``BaseModel.model_json_schema()`` produserer
    et kompatibelt schema by default. Vi strip-er bort
    ``$defs``-referanser for å holde det flatt og enklere for LLM-er å
    forstå direkte i prompt-en.
    """
    schema = handler.input_schema.model_json_schema()
    # Strip pydantic-spesifikke metadata som LLM-en ikke trenger
    schema.pop("title", None)
    return schema


def _output_schema_to_json(handler: ToolHandler) -> dict[str, Any]:
    """Konverter pydantic output-modellen til JSON Schema for MCP ``outputSchema``.

    Speiler :func:`_input_schema_to_json`. MCP-connector-katalogene (OpenAI
    Apps SDK, Claude) anbefaler at verktøy deklarerer ``outputSchema`` slik at
    agenten kan forutse svar-formen og validere strukturerte resultater.
    Pydantic ``model_json_schema()`` er JSON Schema-kompatibelt.
    """
    schema = handler.output_schema.model_json_schema()
    schema.pop("title", None)
    return schema


def _structured_content(handler: ToolHandler, result: Any) -> dict[str, Any] | None:
    """Bygg ``structuredContent`` (dict) som speiler ``outputSchema``, best-effort.

    Når et verktøy deklarerer ``outputSchema`` bør kallet også returnere
    strukturerte data (MCP-spec 2025-06-18). Vi serialiserer handler-resultatet
    til en dict på samme måte som tekst-innholdet (``exclude_none=True`` for
    kompakthet).

    Returnerer ``None`` hvis resultatet ikke lar seg representere som et objekt
    (f.eks. en streng eller en tuple som ikke coerce-er rent gjennom modellen).
    Det er trygt: :func:`build_server` returnerer alltid en ``CallToolResult``,
    så SDK-en kjører ingen streng ``outputSchema``-validering som ville feilet
    på manglende struktur.
    """
    if isinstance(result, BaseModel):
        return _strip_citation_fields(result.model_dump(mode="json", exclude_none=True))
    if isinstance(result, dict):
        return _strip_citation_fields(result)
    # tuple/str/annet — prøv å coerce via den deklarerte output-modellen.
    try:
        coerced = handler.output_schema.model_validate(result)
    except Exception:  # noqa: BLE001 — best-effort; faller tilbake på ren tekst
        return None
    return _strip_citation_fields(coerced.model_dump(mode="json", exclude_none=True))


def _strip_citation_fields(d: dict[str, Any]) -> dict[str, Any]:
    """Fjern ``url``/``source`` fra ``structuredContent``.

    ChatGPT siterer et ``url``-felt i den strukturerte output-en som en generisk
    «File»-kilde i Sources-panelet. Vi vil heller at Firmaradar-lenken skal være en
    KLIKKBAR markdown-lenke i tekst-kanalen (lagt til i ``_result_to_text_content``),
    ikke en fil-chip. Feltene fjernes derfor KUN fra det strukturerte speilet —
    tekst-kanalen beholder lenken. Per-treff-``url`` inne i lister (search-resultat)
    fjernes også rekursivt så listene ikke gir N «File»-kilder.
    """
    if not isinstance(d, dict):
        return d
    out: dict[str, Any] = {}
    for k, v in d.items():
        if k in ("url", "source"):
            continue
        if isinstance(v, dict):
            out[k] = _strip_citation_fields(v)
        elif isinstance(v, list):
            out[k] = [
                _strip_citation_fields(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            out[k] = v
    return out


def _handler_to_tool(handler: ToolHandler) -> types.Tool:
    """Bygg MCP ``Tool``-annonsen for én handler, med tittel + annotations.

    Setter en menneskevennlig ``title`` (vist i agent-klienten) og fyller
    ``ToolAnnotations`` slik MCP-connector-katalogene krever:

    * ``readOnlyHint`` — ``True`` for alle rene oppslag; ``False`` for verktøy i
      :data:`~firmaradar_mcp.tools.WRITE_TOOLS` (skriver state, f.eks.
      disclaimer-bekreftelse).
    * ``destructiveHint`` — ``True`` for verktøy i
      :data:`~firmaradar_mcp.tools.DESTRUCTIVE_TOOLS` (fjerner en ressurs,
      f.eks. ``delete_subscription``); ``False`` for alle andre.
    * ``idempotentHint`` — ``True`` for de aller fleste verktøy (oppslag har
      ingen effekt; ``subscribe_nace``/``delete_subscription``/
      ``confirm_risk_score_disclaimer`` konvergerer til samme state ved gjentak).
      ``False`` for verktøy i :data:`~firmaradar_mcp.tools.NON_IDEMPOTENT_TOOLS`
      (``check_aml_pep``/``get_aml_score``/``start_aml_report``) som skriver en NY
      audit-/report-/job-rad ved HVERT kall.
    * ``openWorldHint`` — ``True`` only for tools that can write to public
      internet state or external third-party systems. Current Firmaradar tools
      do not; they read source-backed data or mutate private Firmaradar account
      state.

    Tittel hentes fra :data:`~firmaradar_mcp.tools.TOOL_TITLES`; mangler den
    faller vi tilbake på selve verktøynavnet.

    Args:
        handler: tool-handleren fra :data:`~firmaradar_mcp.tools.ALL_TOOLS`.

    Returns:
        En ferdig ``types.Tool`` klar for ``list_tools``-svaret.

    Called by:
        - build_server._list_tools() - bygger hele tool-katalogen.

    Calls:
        - _input_schema_to_json() - JSON Schema for input-modellen.
        - _output_schema_to_json() - JSON Schema for output-modellen.
    """
    title = TOOL_TITLES.get(handler.name, handler.name)
    read_only = handler.name not in WRITE_TOOLS
    destructive = handler.name in DESTRUCTIVE_TOOLS
    open_world = handler.name in OPEN_WORLD_TOOLS
    idempotent = handler.name not in NON_IDEMPOTENT_TOOLS
    return types.Tool(
        name=handler.name,
        title=title,
        description=handler.description,
        input_schema=_input_schema_to_json(handler),
        output_schema=_output_schema_to_json(handler),
        annotations=types.ToolAnnotations(
            title=title,
            read_only_hint=read_only,
            destructive_hint=destructive,
            idempotent_hint=idempotent,
            open_world_hint=open_world,
        ),
        # securitySchemes lever under _meta, IKKE som top-level Tool-felt —
        # se _TOOL_SECURITY_SCHEMES-kommentaren for hvorfor det er den ENESTE
        # plasseringen som overlever tools/list sin wire-serialisering i 2.0.
        # NB: _meta (ikke meta) — Tool.meta sin alias er eksplisitt satt via
        # Field(alias=...), så det er navnet mypy faktisk gjenkjenner som
        # kwarg (i motsetning til input_schema/output_schema sin generiske
        # alias_generator, der mypy vil ha feltnavnet).
        _meta={"securitySchemes": _TOOL_SECURITY_SCHEMES},
    )


def _result_to_text_content(result: Any) -> list[types.TextContent]:
    """Pakke handler-resultatet inn i MCP TextContent.

    OpenAI Apps/ChatGPT-mønster: lever LESBAR tekst i ``content``, ikke en rå
    JSON-blob. ChatGPT rendrer en stor JSON-blob som en «file»-ressurs (og
    trunkerer den for store svar → agenten faller tilbake). Vi leder derfor med
    ``summary`` når verktøyet har en (eks. en markdown-tabell for bulk), og legger
    til en KLIKKBAR Firmaradar-lenke fra ``url`` — så kilden vises som en lenke,
    ikke en generisk fil-chip. Full struktur ligger uansett i ``structuredContent``
    (for klienter/widgets). Verktøy uten ``summary`` faller tilbake på JSON.
    """
    if isinstance(result, str):
        return [types.TextContent(type="text", text=result)]
    if hasattr(result, "model_dump"):
        payload = result.model_dump(mode="json", exclude_none=True)
    elif isinstance(result, dict):
        payload = result
    else:
        payload = {"result": result}

    summary = payload.get("summary") if isinstance(payload, dict) else None
    url = payload.get("url") if isinstance(payload, dict) else None

    if summary and str(summary).strip():
        text = str(summary).strip()
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    if url:
        text = f"{text}\n\n[Åpne i Firmaradar →]({url})"
    return [types.TextContent(type="text", text=text)]


# ── Re-auth-signal for ChatGPT (OpenAI MCP-connector) ──────────────────
# ChatGPT viser sin inline re-auth-UI under et tools/call KUN når selve
# verktøy-resultatet bærer ``_meta["mcp/www_authenticate"]`` med både
# ``error`` og ``error_description`` (bekreftet av OpenAI support 2026-03;
# et bart HTTP 401 holder ikke for ChatGPT slik det gjør for Claude).
#
# Vi legger derfor denne challenge-en på ALLE 401-feilresultater fra
# backend. ``_meta`` er namespaced og ignoreres av klienter som ikke
# forstår den (Claude/Cursor/Desktop), så det er trygt på tvers — Claude
# fortsetter å bruke HTTP-401-stien fra ``remote_server``-middlewaren.
# ``resource_metadata`` peker til vår RFC 9728-discovery.
_REAUTH_RESOURCE_METADATA_URL = (
    "https://mcp.firmaradar.no/.well-known/oauth-protected-resource"
)
_REAUTH_WWW_AUTHENTICATE = (
    f'Bearer resource_metadata="{_REAUTH_RESOURCE_METADATA_URL}", '
    'error="invalid_token", '
    'error_description="Firmaradar-tilgang utløpt eller tilbakekalt — '
    'logg inn på nytt."'
)
_REAUTH_META: dict[str, Any] = {"mcp/www_authenticate": [_REAUTH_WWW_AUTHENTICATE]}

# Per-verktøy securitySchemes — OpenAI Apps SDK krever dette i tillegg til
# runtime-``_meta`` for at ChatGPT sin inline re-auth-UI skal trigges.
#
# BEVISST plassert under ``Tool.meta``/``_meta``, IKKE som top-level felt
# (slik det lå til og med 0.5.11, da mcp_types sin ``Tool`` hadde
# ``extra="allow"``): mcp_types 2.0.0 sin per-metode wire-sieve
# (``mcp_types.methods.serialize_server_result``, kjørt av
# ``ServerRunner._serialize`` for alle spec-metoder inkl. ``tools/list``)
# validerer resultatet mot protokollens EGEN skjema med ``extra="ignore"`` —
# ETHVERT top-level felt utenfor spec-en droppes ubetinget, uansett om
# handleren returnerer en ``ListToolsResult``, et rått dict, eller en
# ``Tool``-subclass med ``extra="allow"``. ``_meta`` er derimot et ekte
# deklarert felt (åpen ``dict[str, Any]``) og er protokollens SANKSJONERTE
# utvidelsespunkt — verifisert å overleve hele pipeline (_dump_result +
# serialize_server_result) mot ekte ``mcp==2.0.0`` på alle forhandlingsbare
# protokollversjoner. Se ``_handler_to_tool``.
#
# KJENT RISIKO (uverifisert herfra): dette ER en wire-formendring — feltet
# flytter fra ``tool.securitySchemes`` til ``tool._meta.securitySchemes``.
# Om OpenAI sin Apps SDK-klient faktisk leser ``_meta`` for dette (vs. kun
# top-level, som var den opprinnelig OpenAI-support-bekreftede plasseringen
# 2026-03) er IKKE bekreftet — krever test mot en ekte ChatGPT-connector
# før dette strekkes til å garantere at re-auth-UI-en fortsatt trigges.
_TOOL_SECURITY_SCHEMES: list[dict[str, Any]] = [
    {"type": "oauth2", "scopes": ["mcp"]},
]


def _error_result(
    payload: dict[str, Any],
    *,
    meta: dict[str, Any] | None = None,
) -> types.CallToolResult:
    """Bygg et MCP-feilsvar (``isError=True``) fra en feil-payload.

    Returnerer en ``CallToolResult`` slik at SDK-en tar den as-is (early
    return) og *ikke* kjører ``outputSchema``-validering — feilsvar matcher
    aldri suksess-skjemaet, og ``isError=True`` er korrekt MCP-semantikk så
    klienter kan skille feil fra gyldige resultater.

    ``meta`` legges på som ``_meta`` på resultatet — brukes til å bære
    ``mcp/www_authenticate``-challenge-en på 401-feil (ChatGPT re-auth).
    """
    kwargs: dict[str, Any] = {
        "content": [types.TextContent(
            type="text",
            text=json.dumps(payload, ensure_ascii=False),
        )],
        "is_error": True,
    }
    if meta is not None:
        kwargs["meta"] = meta
    return types.CallToolResult(**kwargs)


def build_server(tools: list[ToolHandler], client: FirmaradarClient) -> Server:
    """Konstruér MCP Server-instans med list_tools + call_tool wired.

    Eksponert som offentlig funksjon (ikke prefix _) så tester kan bygge
    en server mot mock-client uten å gå via stdio-loopen.

    MCP-SDK 2.0 fjernet ``@server.list_tools()``/``@server.call_tool()``-
    dekoratorene (``Server.list_tools``/``call_tool`` finnes ikke lenger) —
    handlere wires nå inn via ``on_list_tools=``/``on_call_tool=`` på
    konstruktøren, og mottar begge ``(ctx, params)`` i stedet for de gamle
    positional-argumentene.
    """
    tools_index = _tools_by_name(tools)

    async def _list_tools(
        ctx: ServerRequestContext[Any], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[_handler_to_tool(h) for h in tools])

    async def _call_tool(
        ctx: ServerRequestContext[Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        # Vi returnerer alltid en CallToolResult: suksess med ``content`` +
        # ``structuredContent`` (speiler outputSchema), feil med ``isError=True``.
        # Det gjør at SDK-en tar resultatet as-is og hopper over streng
        # outputSchema-validering, så heterogene handler-retur-typer (modell,
        # dict, tuple) aldri kan crashe et kall.
        name = params.name
        arguments = params.arguments or {}
        handler = tools_index.get(name)
        if handler is None:
            return _error_result({
                "error": f"Unknown tool: {name}",
                "available_tools": sorted(tools_index.keys()),
            })
        try:
            # Validér + parse argumenter via pydantic-modellen
            tool_args = handler.input_schema(**arguments)
        except Exception as exc:  # pydantic.ValidationError er en Exception
            return _error_result({
                "error": "Invalid arguments",
                "tool": name,
                "details": str(exc),
            })
        try:
            result = await handler.handler(client, tool_args)
        except NotImplementedError as exc:
            # v0.1-tools som ennå ikke har backend — gi pent feilsvar
            # istedenfor å crashe hele MCP-økten.
            return _error_result({
                "error": "Tool not implemented in this version",
                "tool": name,
                "details": str(exc),
            })
        except FirmaradarClientError as exc:
            # 401 fra backend = dødt/utløpt token. Bær re-auth-challenge i
            # ``_meta`` så ChatGPT viser sin inline innloggings-UI (Claude
            # håndteres allerede av HTTP-401-stien i middlewaren).
            reauth_meta = _REAUTH_META if exc.status_code == 401 else None
            return _error_result(
                {
                    "error": "Firmaradar API error",
                    "tool": name,
                    "status_code": exc.status_code,
                    "error_code": exc.error_code,
                    "details": str(exc),
                    "retry_after_s": exc.retry_after_s,
                },
                meta=reauth_meta,
            )
        except Exception as exc:  # noqa: BLE001
            _LOG.exception("Tool %s raised", name)
            return _error_result({
                "error": "Internal error",
                "tool": name,
                "details": str(exc),
            })
        return types.CallToolResult(
            content=_result_to_text_content(result),
            structured_content=_structured_content(handler, result),
        )

    return Server(
        _SERVER_NAME,
        # Pre-eksisterende hull, funnet + fikset i samme slag som 2.0-
        # migreringen (samme konstruktør-kall): uten dette rapporterte
        # ``initialize``-svarets ``serverInfo.version`` feil verdi på
        # remote-stien (StreamableHTTPSessionManager bygger init-options fra
        # Server-objektet selv, IKKE fra _amain() sin InitializationOptions —
        # den brukes kun av stdio). v1 falt tilbake til mcp-SDK-ens EGEN
        # versjon (f.eks. "1.29.0"); v2 faller tilbake til tom streng. Stdio-
        # stien var alltid korrekt (egen InitializationOptions med
        # server_version=_SERVER_VERSION i _amain()) — uendret her.
        version=_SERVER_VERSION,
        instructions=_INSTRUCTIONS,
        on_list_tools=_list_tools,
        on_call_tool=_call_tool,
    )


async def _amain() -> int:
    _configure_logging()
    client = FirmaradarClient()
    try:
        server = build_server(ALL_TOOLS, client)
        _LOG.info(
            "%s v%s starting (base_url=%s, tools=%d)",
            _SERVER_NAME, _SERVER_VERSION, client.base_url, len(ALL_TOOLS),
        )
        init_options = InitializationOptions(
            server_name=_SERVER_NAME,
            server_version=_SERVER_VERSION,
            capabilities=server.get_capabilities(
                notification_options=NotificationOptions(),
                experimental_capabilities={},
            ),
        )
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, init_options)
    finally:
        await client.aclose()
    return 0


_HELP_TEXT = f"""\
firmaradar-mcp v{_SERVER_VERSION} — Norwegian company-intelligence MCP server

Usage:
  firmaradar-mcp              Run the stdio MCP server (default).
                              Waits for an MCP client to connect via stdin/stdout.
  firmaradar-mcp --help, -h   Show this help and exit.
  firmaradar-mcp --version    Show version and exit.

Environment variables:
  FIRMARADAR_API_KEY          (required) Your Firmaradar API key.
                              Get one at https://firmaradar.no/min-side/api-keys
  FIRMARADAR_BASE_URL         (optional) Override backend URL.
                              Default: https://firmaradar.no
  FIRMARADAR_MCP_LOG_LEVEL    (optional) DEBUG | INFO | WARNING | ERROR.
                              Default: INFO. Logs go to stderr.

Typical use:
  Add this server to your agent client config (Claude Desktop, Cursor, etc.).
  Example for Claude Desktop (claude_desktop_config.json):

    {{
      "mcpServers": {{
        "firmaradar": {{
          "command": "firmaradar-mcp",
          "env": {{ "FIRMARADAR_API_KEY": "your-key-here" }}
        }}
      }}
    }}

Documentation: https://firmaradar.no/agentisk-flyt
Tool catalog:  https://firmaradar.no/api-dokumentasjon
"""


def main() -> int:
    # Handle --help / --version BEFORE we try to construct the client,
    # so the user can discover the env-var requirement without first
    # setting it. Previously the client was instantiated unconditionally
    # in _amain() which crashed --help on missing FIRMARADAR_API_KEY.
    argv = sys.argv[1:]
    if argv and argv[0] in {"-h", "--help"}:
        print(_HELP_TEXT)
        return 0
    if argv and argv[0] in {"--version", "-V"}:
        print(f"firmaradar-mcp {_SERVER_VERSION}")
        return 0

    try:
        return asyncio.run(_amain())
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        _LOG.exception("firmaradar-mcp failed: %s", exc)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
