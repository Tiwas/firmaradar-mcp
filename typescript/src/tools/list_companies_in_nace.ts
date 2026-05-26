/**
 * Tool: `list_companies_in_nace`.
 *
 * Paginated list of all Norwegian companies in a given NACE-code (or
 * prefix), with optional size/location filters.
 *
 * Backend status: GAP — needs new
 * `GET /api/v1/nace/<code>/companies` endpoint. See
 * `plans/MCP_V01_INVENTORY.md` tool #14.
 */

import { z } from "zod";

export const schema = z.object({
  code: z.string().describe("NACE code or prefix, e.g. '47.11' or '47'."),
  status: z.enum(["aktiv", "konkurs", "under_avvikling", "avregistrert"]).optional(),
  kommune: z.string().optional(),
  min_ansatte: z.number().int().min(0).optional(),
  max_ansatte: z.number().int().min(0).optional(),
  limit: z.number().int().min(1).max(200).default(50),
  cursor: z.string().optional(),
});

export type ListCompaniesInNaceInput = z.infer<typeof schema>;

export async function handler(_input: unknown): Promise<unknown> {
  throw new Error("list_companies_in_nace: GAP — backend endpoint not implemented yet.");
}
