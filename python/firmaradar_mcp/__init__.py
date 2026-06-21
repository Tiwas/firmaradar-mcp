"""Firmaradar MCP stdio-server — v0.3.

Exposes 17 read-only "melk og brød"-tools (company, person, risk,
sector, announcement) over the Model Context Protocol so that
Claude/GPT/n8n and other MCP-aware clients can query Firmaradar
directly.

See ``tools/mcp_server/README.md`` for setup, and
``plans/MCP_V01_INVENTORY.md`` for the tool ↔ REST-endpoint mapping.
"""

from __future__ import annotations

__version__ = "0.5.5"
__all__ = ["__version__"]
