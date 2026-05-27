"""Registry of all MCP tools exposed by ``firmaradar-mcp`` v0.1.

Each tool lives in its own module under this package so that input/
output schemas and the eventual implementation can evolve
independently. The :data:`ALL_TOOLS` list is the single source of
truth that ``server.py`` reads at startup.

Adding a new tool: drop a module here with a module-level ``HANDLER``
that conforms to :class:`ToolHandler`, then append it to
``ALL_TOOLS``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:  # pragma: no cover — avoid circular import in runtime
    from ..client import FirmaradarClient


InputModel = type[BaseModel]
OutputModel = type[BaseModel]
# Signatur: handler(client, validated_params) -> BaseModel | dict
# Endret 2026-05-25 fra (params) -> ... slik at hvert tool får
# klienten injected uten å lage globale state-bryggere.
ToolFunc = Callable[["FirmaradarClient", Any], Awaitable[Any]]


@dataclass(frozen=True)
class ToolHandler:
    """Metadata + callable for a single MCP tool."""

    name: str
    description: str
    input_schema: InputModel
    output_schema: OutputModel
    handler: ToolFunc


# ---------------------------------------------------------------------------
# Imports kept at the bottom to avoid circular references — each tool module
# only depends on :mod:`firmaradar_mcp.tools` for the ToolHandler dataclass.
# ---------------------------------------------------------------------------

from . import (  # noqa: E402
    check_aml_pep,
    check_foretak_i_vanskeligheter,
    compare_companies,
    find_related_companies,
    get_aml_score,
    get_company,
    get_company_announcements,
    get_company_financials,
    get_company_ownership,
    get_company_roles,
    get_company_signals,
    get_konsernstotte,
    get_person,
    get_person_companies,
    get_person_roles,
    get_recent_changes,
    get_risk_score,
    get_skattelister,
    list_companies_in_nace,
    search_announcements,
    search_companies,
    search_persons,
)


ALL_TOOLS: list[ToolHandler] = [
    # Selskap (6)
    search_companies.HANDLER,
    get_company.HANDLER,
    get_company_ownership.HANDLER,
    get_company_roles.HANDLER,
    get_company_financials.HANDLER,
    get_company_announcements.HANDLER,
    # Person (4)
    search_persons.HANDLER,
    get_person.HANDLER,
    get_person_roles.HANDLER,
    get_person_companies.HANDLER,
    # Risikosignaler (3)
    get_company_signals.HANDLER,
    check_aml_pep.HANDLER,
    get_recent_changes.HANDLER,
    # Bransje/relasjon (3)
    list_companies_in_nace.HANDLER,
    find_related_companies.HANDLER,
    compare_companies.HANDLER,
    # Tverr-søk (1)
    search_announcements.HANDLER,
    # ── v0.3 markedsplass-utvidelser (#130, 2026-05-27) (5) ──
    get_risk_score.HANDLER,
    check_foretak_i_vanskeligheter.HANDLER,
    get_aml_score.HANDLER,
    get_konsernstotte.HANDLER,
    get_skattelister.HANDLER,
]


__all__ = ["ALL_TOOLS", "ToolHandler"]
