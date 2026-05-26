/**
 * Tool: `get_company_ownership`.
 *
 * Recursive ownership tree — down (subsidiaries / who this company
 * owns), up (UBO / who owns this company), or both.
 *
 * Backend status: PARTIAL — `GET /api/eierstruktur/<orgnr>` returns
 * down-tree; upstream lookup exists in `ownership_pg.business_owner_holdings`.
 * A unified endpoint with `direction=` + `depth=` parameters must be
 * added. See `plans/MCP_V01_INVENTORY.md` tool #3.
 */

import { z } from "zod";

export const schema = z.object({
  orgnr: z.string().regex(/^\d{9}$/),
  direction: z.enum(["down", "up", "both"]).default("down"),
  depth: z.number().int().min(1).max(10).default(5),
  include_persons: z.boolean().default(false),
  min_share_pct: z.number().min(0).max(100).optional(),
});

export type GetCompanyOwnershipInput = z.infer<typeof schema>;

export async function handler(_input: unknown): Promise<unknown> {
  throw new Error(
    "get_company_ownership: PARTIAL — needs unified GET /api/v1/company/<orgnr>/ownership endpoint with direction param.",
  );
}
