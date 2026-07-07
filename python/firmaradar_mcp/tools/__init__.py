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
    add_company_monitoring,
    check_aml_pep,
    check_fiv_bulk,
    check_foretak_i_vanskeligheter,
    compare_companies,
    confirm_risk_score_disclaimer,
    convert_nok,
    delete_subscription,
    find_related_companies,
    find_shared_connections,
    get_aml_report,
    get_aml_score,
    get_company,
    get_company_ip,
    start_aml_report,
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
    get_risk_score_bulk,
    list_companies_in_nace,
    list_my_subscriptions,
    list_nace_codes,
    search_announcements,
    search_companies,
    search_persons,
    subscribe_nace,
)


ALL_TOOLS: list[ToolHandler] = [
    # Selskap (6)
    search_companies.HANDLER,
    get_company.HANDLER,
    get_company_ip.HANDLER,
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
    find_shared_connections.HANDLER,
    compare_companies.HANDLER,
    # Tverr-søk (1)
    search_announcements.HANDLER,
    # ── v0.3 markedsplass-utvidelser (#130, 2026-05-27) (4) ──
    get_risk_score.HANDLER,
    check_foretak_i_vanskeligheter.HANDLER,
    get_aml_score.HANDLER,
    get_konsernstotte.HANDLER,
    # ── AML-rapport async-sti (async-plan §8, arkivert i backups/deleted/2026-06-18-plans-todo-opprydding/plans/arkitektur/AML_SCORE_PERF_PLAN.md; 2026-05-31) (2) ──
    start_aml_report.HANDLER,
    get_aml_report.HANDLER,
    # ── v0.3 compliance-helpers (#134, 2026-05-27) (1) ──
    confirm_risk_score_disclaimer.HANDLER,
    # ── Bulk-portfolio-screening (#134, 2026-05-27) (2) ──
    check_fiv_bulk.HANDLER,
    get_risk_score_bulk.HANDLER,
    # ── i18n: valuta-konvertering (2026-05-29) (1) ──
    convert_nok.HANDLER,
    # ── NACE-overvåkning v0.5 — agent-eksponering (2026-05-31) (4) ──
    list_nace_codes.HANDLER,
    subscribe_nace.HANDLER,
    list_my_subscriptions.HANDLER,
    delete_subscription.HANDLER,
    add_company_monitoring.HANDLER,
]


# ---------------------------------------------------------------------------
# Display metadata for the MCP tool advertisement (``list_tools``).
#
# ``TOOL_TITLES`` gives each tool a short, user-friendly title shown in agent
# clients (Claude, Cursor, …) and required by the MCP connector directories.
# ``WRITE_TOOLS`` lists the tools that are NOT read-only; every other tool is a
# pure registry lookup. Both are read by :mod:`firmaradar_mcp.server` when it
# builds the ``Tool`` objects and their ``ToolAnnotations``.
#
# Titles follow the Firmaradar brand voice (see ``README.md`` § "Brand voice"):
# scope is explicit — company vs. person, AML vs. risk — so agents pick the
# right tool for the user's intent (e.g. ``get_risk_score`` is *company* health,
# not personal credit).
# ---------------------------------------------------------------------------
TOOL_TITLES: dict[str, str] = {
    "firmaradar_search_companies": "Search Companies",
    "firmaradar_get_company": "Get Company Profile",
    "firmaradar_get_company_ownership": "Get Company Ownership",
    "firmaradar_get_company_roles": "Get Company Roles",
    "firmaradar_get_company_financials": "Get Company Financials",
    "firmaradar_get_company_announcements": "Get Company Announcements",
    "firmaradar_get_company_ip": "Get Company IP Rights",
    "firmaradar_search_persons": "Search Persons",
    "firmaradar_get_person": "Get Person Profile",
    "firmaradar_get_person_roles": "Get Person Roles",
    "firmaradar_get_person_companies": "Get Person's Companies",
    "firmaradar_get_company_signals": "Get Company Risk Signals",
    "firmaradar_check_aml_pep": "AML / PEP Screening",
    "firmaradar_get_recent_changes": "Get Recent Changes",
    "firmaradar_list_companies_in_nace": "List Companies by Industry (NACE)",
    "firmaradar_find_related_companies": "Find Related Companies",
    "firmaradar_find_shared_connections": "Find Shared Connections",
    "firmaradar_compare_companies": "Compare Companies",
    "firmaradar_search_announcements": "Search Announcements",
    "firmaradar_get_risk_score": "Get Company Risk Score",
    "firmaradar_check_foretak_i_vanskeligheter": "Check Company in Difficulty (FIV)",
    "firmaradar_get_aml_score": "Get Company AML Risk Score",
    "firmaradar_start_aml_report": "Start AML Report (Async)",
    "firmaradar_get_aml_report": "Get AML Report Status / Result",
    "firmaradar_get_konsernstotte": "Get Group Support (Konsernstøtte)",
    "firmaradar_confirm_risk_score_disclaimer": "Confirm Risk-Score Disclaimer",
    "firmaradar_check_fiv_bulk": "Bulk Check Companies in Difficulty (FIV)",
    "firmaradar_get_risk_score_bulk": "Bulk Company Risk Scores",
    "firmaradar_convert_nok": "Convert NOK to Foreign Currency",
    "firmaradar_list_nace_codes": "Search NACE Industry Codes",
    "firmaradar_subscribe_nace": "Subscribe to Industry Monitoring (NACE)",
    "firmaradar_list_my_subscriptions": "List My Industry Subscriptions",
    "firmaradar_delete_subscription": "Delete Industry Subscription",
    "firmaradar_add_company_monitoring": "Add Company to Monitoring",
}

# Tools that mutate state (not read-only). Everything else is a pure lookup and
# is advertised with ``readOnlyHint=True``.
#
# * ``check_aml_pep`` writes the legally required per-call AML/PEP audit trail.
# * ``get_aml_score`` generates an auditable AML report record.
# * ``start_aml_report`` creates an async AML report job/result record.
# * ``confirm_risk_score_disclaimer`` writes a consent/audit record
#   (``extension_kundebekreftelse_event``).
# * ``subscribe_nace`` upserts a NACE industry-monitoring subscription.
# * ``delete_subscription`` removes one (see ``DESTRUCTIVE_TOOLS``).
WRITE_TOOLS: frozenset[str] = frozenset({
    "firmaradar_check_aml_pep",
    "firmaradar_get_aml_score",
    "firmaradar_start_aml_report",
    "firmaradar_confirm_risk_score_disclaimer",
    "firmaradar_subscribe_nace",
    "firmaradar_delete_subscription",
    "firmaradar_add_company_monitoring",
})

# Tools that can write to public internet state or external third-party
# systems. Current Firmaradar tools either read source-backed data or mutate
# private Firmaradar account/compliance state only, so none qualify.
OPEN_WORLD_TOOLS: frozenset[str] = frozenset()

# Tools that perform a destructive update (remove a resource). Advertised with
# ``destructiveHint=True`` so agent clients can prompt for confirmation. Only
# ``delete_subscription`` qualifies — it removes a user-owned monitoring
# subscription (reversible only by re-subscribing). All other write-tools are
# additive/idempotent upserts and stay ``destructiveHint=False``.
DESTRUCTIVE_TOOLS: frozenset[str] = frozenset({
    "firmaradar_delete_subscription",
})

# Tools that are NOT idempotent — calling them again with the same arguments
# produces an ADDITIONAL effect, so they are advertised with
# ``idempotentHint=False``. Every other tool is idempotent: pure lookups have no
# effect, and the remaining write-tools converge to the same state on repeat
# (``subscribe_nace`` upserts on ``(user, nace_code)``; ``delete_subscription``
# 404-no-ops once gone; ``confirm_risk_score_disclaimer`` returns the existing
# confirmation without writing a duplicate row).
#
# * ``check_aml_pep`` appends a new per-call AML/PEP audit record every time.
# * ``get_aml_score`` stores a new auditable AML report record every time.
# * ``start_aml_report`` creates a new async AML report job every time.
NON_IDEMPOTENT_TOOLS: frozenset[str] = frozenset({
    "firmaradar_check_aml_pep",
    "firmaradar_get_aml_score",
    "firmaradar_start_aml_report",
})


__all__ = [
    "ALL_TOOLS",
    "ToolHandler",
    "TOOL_TITLES",
    "WRITE_TOOLS",
    "OPEN_WORLD_TOOLS",
    "DESTRUCTIVE_TOOLS",
    "NON_IDEMPOTENT_TOOLS",
]
