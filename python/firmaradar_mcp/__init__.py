"""Firmaradar MCP server package.

Exposes 35 company, person, risk, compliance and monitoring tools over
the Model Context Protocol. Tool annotations distinguish read-only
lookups from operations that mutate private account, audit or report
state.

See ``tools/mcp_server/README.md`` for setup, and
``plans/MCP_V01_INVENTORY.md`` for the tool ↔ REST-endpoint mapping.
"""

from __future__ import annotations

__version__ = "0.5.12"
__all__ = ["__version__"]
