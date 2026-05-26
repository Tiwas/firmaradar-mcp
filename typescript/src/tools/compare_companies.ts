/**
 * Tool: `compare_companies`.
 *
 * Side-by-side financial comparison of up to 5 companies.
 *
 * Backend status: GAP — needs `POST /api/v1/companies/compare`. See
 * `plans/MCP_V01_INVENTORY.md` tool #16.
 */

import { z } from "zod";

export const schema = z.object({
  orgnrs: z.array(z.string().regex(/^\d{9}$/)).min(1).max(5),
  years: z.number().int().min(1).max(10).default(5),
  metrics: z.array(z.string()).optional(),
});

export type CompareCompaniesInput = z.infer<typeof schema>;

export async function handler(_input: unknown): Promise<unknown> {
  throw new Error(
    "compare_companies: GAP — backend POST /api/v1/companies/compare endpoint not implemented yet.",
  );
}
