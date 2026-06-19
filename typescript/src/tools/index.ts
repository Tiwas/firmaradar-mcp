/**
 * Registry of all MCP tools exposed by @firmaradar/mcp-server v0.1.
 *
 * Each tool lives in its own module under this directory so that
 * input/output schemas and the eventual implementation can evolve
 * independently. {@link ALL_TOOLS} is the single source of truth that
 * `index.ts` reads at startup.
 *
 * Adding a new tool: drop a module here exporting a `HANDLER` of
 * type {@link ToolHandler}, then append it to ALL_TOOLS.
 */

import type { z } from "zod";

import { handler as searchCompanies, schema as searchCompaniesSchema } from "./search_companies.js";
import { handler as getCompany, schema as getCompanySchema } from "./get_company.js";
import { handler as getCompanyOwnership, schema as getCompanyOwnershipSchema } from "./get_company_ownership.js";
import { handler as getCompanyRoles, schema as getCompanyRolesSchema } from "./get_company_roles.js";
import { handler as getCompanyFinancials, schema as getCompanyFinancialsSchema } from "./get_company_financials.js";
import { handler as getCompanyAnnouncements, schema as getCompanyAnnouncementsSchema } from "./get_company_announcements.js";
import { handler as searchPersons, schema as searchPersonsSchema } from "./search_persons.js";
import { handler as getPerson, schema as getPersonSchema } from "./get_person.js";
import { handler as getPersonRoles, schema as getPersonRolesSchema } from "./get_person_roles.js";
import { handler as getPersonCompanies, schema as getPersonCompaniesSchema } from "./get_person_companies.js";
import { handler as getCompanySignals, schema as getCompanySignalsSchema } from "./get_company_signals.js";
import { handler as checkAmlPep, schema as checkAmlPepSchema } from "./check_aml_pep.js";
import { handler as getRecentChanges, schema as getRecentChangesSchema } from "./get_recent_changes.js";
import { handler as listCompaniesInNace, schema as listCompaniesInNaceSchema } from "./list_companies_in_nace.js";
import { handler as findRelatedCompanies, schema as findRelatedCompaniesSchema } from "./find_related_companies.js";
import { handler as compareCompanies, schema as compareCompaniesSchema } from "./compare_companies.js";
import { handler as searchAnnouncements, schema as searchAnnouncementsSchema } from "./search_announcements.js";

export interface ToolHandler {
  name: string;
  description: string;
  inputSchema: z.ZodTypeAny;
  handler: (input: unknown) => Promise<unknown>;
}

export const ALL_TOOLS: ToolHandler[] = [
  // Selskap (6)
  { name: "firmaradar.search_companies", description: "Search Norwegian companies with filters (name, NACE, location, status, size, founding date). Returns paginated list of candidate orgnr to investigate. Use when you have a description and need to find matching companies; use `get_company` once you have a specific orgnr.", inputSchema: searchCompaniesSchema, handler: searchCompanies },
  { name: "firmaradar.get_company", description: "Fetch the full profile for one Norwegian company by orgnr: name, group structure, ownership data, grants, recent BRREG announcements and financial metrics. Opt-in `fields` add deeper enrichment — notably `fields=['ip']` for the company's intellectual-property portfolio (patents, trademarks and designs from Patentstyret). The primary 'show me this company' tool — use after `search_companies` returns an orgnr.", inputSchema: getCompanySchema, handler: getCompany },
  { name: "firmaradar.get_company_ownership", description: "Get the ownership tree for a Norwegian company: who they own (direction=down), who owns them (direction=up / UBO), or both. Use when the user asks 'who owns X AS?' or to map a corporate group.", inputSchema: getCompanyOwnershipSchema, handler: getCompanyOwnership },
  { name: "firmaradar.get_company_roles", description: "List board members, daglig leder, signature holders, prokura and revisor for a Norwegian company. Set include_historic=true for people who previously held roles. Use when the user asks 'who runs X AS?' or 'who is on the board?'.", inputSchema: getCompanyRolesSchema, handler: getCompanyRoles },
  { name: "firmaradar.get_company_financials", description: "Fetch the last N years (default 5) of financial metrics for a Norwegian company: revenue, operating result, equity, debt, employees. Use when the user asks 'how is X AS doing financially?' or 'show me the revenue trend'.", inputSchema: getCompanyFinancialsSchema, handler: getCompanyFinancials },
  { name: "firmaradar.get_company_announcements", description: "List BRREG kunngjøringer (official announcements) for a Norwegian company: bankruptcy, mergers, demergers, ownership changes, address changes, etc. Free-text fields are wrapped in <untrusted_content> tags to prevent prompt injection from BRREG-sourced text.", inputSchema: getCompanyAnnouncementsSchema, handler: getCompanyAnnouncements },
  // Person (4)
  { name: "firmaradar.search_persons", description: "Search for Norwegian persons in the shareholder/role-holder dataset by name. PII-sensitive — requires the search_full_enabled tier. Returns separate shareholder and role-holder hit lists with stable IDs that can be passed to `get_person_companies` and `get_person_roles`.", inputSchema: searchPersonsSchema, handler: searchPersons },
  { name: "firmaradar.get_person", description: "Aggregated person profile: name, birth year, active roles, shareholdings and any AML/PEP risk hits. Strict PII-sensitive — requires search_full_enabled tier and F10.11 purpose confirmation. Minors are blocked except for super-admin accounts.", inputSchema: getPersonSchema, handler: getPerson },
  { name: "firmaradar.get_person_roles", description: "List all company roles (styreleder, daglig leder, etc.) held by a person, current and historic. Use when the user asks 'what roles does Person A hold?' Pass the role_person_id returned by `search_persons`.", inputSchema: getPersonRolesSchema, handler: getPersonRoles },
  { name: "firmaradar.get_person_companies", description: "List all Norwegian companies where the given person holds shares. Use when the user asks 'what does Person A own?' Pass the owner_person_key returned by `search_persons`.", inputSchema: getPersonCompaniesSchema, handler: getPersonCompanies },
  // Risikosignaler (3)
  { name: "firmaradar.get_company_signals", description: "Aggregated risk signals for one company: bankruptcy/distress score, capital-loss flags, recent role/signature changes, M&A interim-balance signals and KYC announcement anomalies. Use as the second step after `get_company` to evaluate whether a company needs deeper due diligence.", inputSchema: getCompanySignalsSchema, handler: getCompanySignals },
  { name: "firmaradar.check_aml_pep", description: "Screen a person's name against sanctions (OFAC, EU, UN) and PEP lists. Compliance-critical: PII-sensitive, requires search_full_enabled tier and a signed DPA. Tighter rate limit (50/30min) — burst use will be throttled or flagged. Returns structured hits with category, sources, and match-ratio.", inputSchema: checkAmlPepSchema, handler: checkAmlPep },
  { name: "firmaradar.get_recent_changes", description: "List changes (kunngjøringer for companies; role + ownership movements for persons) in the last N days. Use when monitoring a target entity for triggers ('has anything changed for X AS in the last month?'). Pair with `subscribe_company` for push notifications.", inputSchema: getRecentChangesSchema, handler: getRecentChanges },
  // Bransje/relasjon (3)
  { name: "firmaradar.list_companies_in_nace", description: "List Norwegian companies in a specific NACE industry code (or code prefix), optionally filtered by status, kommune and size. Useful for sector analysis ('all active restaurants in Oslo with > 5 employees').", inputSchema: listCompaniesInNaceSchema, handler: listCompaniesInNace },
  { name: "firmaradar.find_related_companies", description: "Find companies related to the given orgnr via shared persons (board members/shareholders), shared registered address, or shared ultimate owners. Use for cluster analysis, hidden-relation detection in DD, or fraud-pattern research.", inputSchema: findRelatedCompaniesSchema, handler: findRelatedCompanies },
  { name: "firmaradar.compare_companies", description: "Compare key financial metrics of up to 5 Norwegian companies side-by-side across the last N years (default 5). Use for competitor analysis, benchmark research or 'which of these three companies is the strongest?'.", inputSchema: compareCompaniesSchema, handler: compareCompanies },
  // Tverr-søk (1)
  { name: "firmaradar.search_announcements", description: "Search BRREG kunngjøringer across all Norwegian companies — filter by type (konkurs, fusjon, ...), date range, NACE-code, or location. Use for trend analysis ('all konkurser in restaurant sector last quarter') or radar-style monitoring.", inputSchema: searchAnnouncementsSchema, handler: searchAnnouncements },
];
