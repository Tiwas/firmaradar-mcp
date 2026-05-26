/**
 * Smoke tests for the @firmaradar/mcp-server skeleton.
 *
 * Verifies:
 *  - The 17-tool registry exposes all expected names.
 *  - Each tool stub throws "not implemented" (skeleton phase).
 *  - Each tool has a Zod input schema and a description.
 */

import { describe, expect, it } from "vitest";

import { ALL_TOOLS } from "./tools/index.js";

const EXPECTED_TOOL_NAMES = new Set([
  // Selskap (6)
  "firmaradar.search_companies",
  "firmaradar.get_company",
  "firmaradar.get_company_ownership",
  "firmaradar.get_company_roles",
  "firmaradar.get_company_financials",
  "firmaradar.get_company_announcements",
  // Person (4)
  "firmaradar.search_persons",
  "firmaradar.get_person",
  "firmaradar.get_person_roles",
  "firmaradar.get_person_companies",
  // Risikosignaler (3)
  "firmaradar.get_company_signals",
  "firmaradar.check_aml_pep",
  "firmaradar.get_recent_changes",
  // Bransje/relasjon (3)
  "firmaradar.list_companies_in_nace",
  "firmaradar.find_related_companies",
  "firmaradar.compare_companies",
  // Tverr-søk (1)
  "firmaradar.search_announcements",
]);

describe("MCP tool registry", () => {
  it("lists all 17 expected tools", () => {
    const names = new Set(ALL_TOOLS.map((t) => t.name));
    expect(names).toEqual(EXPECTED_TOOL_NAMES);
    expect(ALL_TOOLS).toHaveLength(17);
  });

  it("gives every tool a non-empty description and a schema", () => {
    for (const tool of ALL_TOOLS) {
      expect(tool.description.trim().length, `${tool.name} description`).toBeGreaterThan(0);
      expect(tool.inputSchema, `${tool.name} inputSchema`).toBeDefined();
      expect(typeof tool.handler, `${tool.name} handler`).toBe("function");
    }
  });

  it("every handler currently throws 'not implemented'", async () => {
    for (const tool of ALL_TOOLS) {
      await expect(tool.handler({})).rejects.toThrow();
    }
  });
});
