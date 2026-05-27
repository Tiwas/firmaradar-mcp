"""MCP stdio-server entry point.

Boots the Model Context Protocol server, registers all 17 tools, and
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
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from .client import FirmaradarClient, FirmaradarClientError
from .tools import ALL_TOOLS, ToolHandler


_LOG = logging.getLogger("firmaradar_mcp.server")

# MCP-server-navn vises i agent-klienten (Claude Desktop, Cursor, etc.).
# Holdes stabilt på tvers av versjoner så bruker ikke får "ny server"-prompt
# ved hver oppgradering.
_SERVER_NAME = "firmaradar-mcp"
_SERVER_VERSION = "0.3.0"


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


def _result_to_text_content(result: Any) -> list[types.TextContent]:
    """Pakke handler-resultatet inn i MCP TextContent.

    Handler kan returnere en pydantic BaseModel, en dict, eller en
    streng. Vi serialiserer som JSON for konsistent agent-konsum.
    """
    if hasattr(result, "model_dump"):
        payload = result.model_dump(mode="json", exclude_none=True)
    elif isinstance(result, dict):
        payload = result
    elif isinstance(result, str):
        return [types.TextContent(type="text", text=result)]
    else:
        payload = {"result": result}
    return [types.TextContent(
        type="text",
        text=json.dumps(payload, ensure_ascii=False, indent=2),
    )]


def build_server(tools: list[ToolHandler], client: FirmaradarClient) -> Server:
    """Konstruér MCP Server-instans med list_tools + call_tool wired.

    Eksponert som offentlig funksjon (ikke prefix _) så tester kan bygge
    en server mot mock-client uten å gå via stdio-loopen.
    """
    server = Server(_SERVER_NAME)
    tools_index = _tools_by_name(tools)

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=h.name,
                description=h.description,
                inputSchema=_input_schema_to_json(h),
            )
            for h in tools
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
        handler = tools_index.get(name)
        if handler is None:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Unknown tool: {name}",
                    "available_tools": sorted(tools_index.keys()),
                }, ensure_ascii=False),
            )]
        try:
            # Validér + parse argumenter via pydantic-modellen
            params = handler.input_schema(**(arguments or {}))
        except Exception as exc:  # pydantic.ValidationError er en Exception
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "Invalid arguments",
                    "tool": name,
                    "details": str(exc),
                }, ensure_ascii=False),
            )]
        try:
            result = await handler.handler(client, params)
        except NotImplementedError as exc:
            # v0.1-tools som ennå ikke har backend — gi pent feilsvar
            # istedenfor å crashe hele MCP-økten.
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "Tool not implemented in this version",
                    "tool": name,
                    "details": str(exc),
                }, ensure_ascii=False),
            )]
        except FirmaradarClientError as exc:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "Firmaradar API error",
                    "tool": name,
                    "status_code": exc.status_code,
                    "error_code": exc.error_code,
                    "details": str(exc),
                    "retry_after_s": exc.retry_after_s,
                }, ensure_ascii=False),
            )]
        except Exception as exc:  # noqa: BLE001
            _LOG.exception("Tool %s raised", name)
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "Internal error",
                    "tool": name,
                    "details": str(exc),
                }, ensure_ascii=False),
            )]
        return _result_to_text_content(result)

    return server


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


def main() -> int:
    try:
        return asyncio.run(_amain())
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        _LOG.exception("firmaradar-mcp failed: %s", exc)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
