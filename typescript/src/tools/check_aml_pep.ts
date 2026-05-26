/**
 * Tool: `check_aml_pep`.
 *
 * Screen a name (optionally + birth year) against sanctions and PEP lists.
 *
 * Backend status: PARTIAL — repo exists but no public endpoint. Needs
 * `POST /api/v1/aml/check` with DPA-confirmation header + tight rate
 * limit + per-call audit. See `plans/MCP_V01_INVENTORY.md` tool #12.
 */

import { z } from "zod";

export const schema = z.object({
  name: z.string().min(2),
  birth_year: z.number().int().min(1900).max(2100).optional(),
  kategori: z.enum(["sanksjon", "pep", "both"]).default("both"),
  min_match_ratio: z.number().min(0).max(1).default(0.85),
});

export type CheckAmlPepInput = z.infer<typeof schema>;

export async function handler(_input: unknown): Promise<unknown> {
  throw new Error(
    "check_aml_pep: PARTIAL — needs public POST /api/v1/aml/check endpoint with DPA-confirmation header + audit log.",
  );
}
