/**
 * Tool: `search_companies`.
 *
 * Search the Norwegian company registry with structured filters: name
 * fragment, NACE code, kommune/fylke, status, employee-range,
 * revenue-range, founding-date range.
 *
 * Backend status (2026-05-25): PARTIAL — only `/api/autocomplete` exists
 * today. A new `GET /api/v1/companies/search` endpoint with the full
 * filter-set must be added before this tool can ship. See
 * `plans/MCP_V01_INVENTORY.md` tool #1.
 */

import { z } from "zod";

export const schema = z.object({
  q: z.string().optional().describe("Free-text search across company names."),
  nace: z.string().optional().describe("NACE code or prefix, e.g. '47.11' or '47'."),
  kommune: z.string().optional(),
  fylke: z.string().optional(),
  status: z.enum(["aktiv", "konkurs", "under_avvikling", "avregistrert"]).optional(),
  min_ansatte: z.number().int().min(0).optional(),
  max_ansatte: z.number().int().min(0).optional(),
  min_omsetning_nok: z.number().int().min(0).optional(),
  max_omsetning_nok: z.number().int().min(0).optional(),
  stiftet_etter: z.string().optional().describe("ISO 8601 date."),
  stiftet_for: z.string().optional().describe("ISO 8601 date."),
  limit: z.number().int().min(1).max(100).default(25),
  cursor: z.string().optional(),
});

export type SearchCompaniesInput = z.infer<typeof schema>;

export async function handler(_input: unknown): Promise<unknown> {
  throw new Error(
    "search_companies: backend endpoint GET /api/v1/companies/search " +
      "not yet implemented — see plans/MCP_V01_INVENTORY.md tool #1.",
  );
}
