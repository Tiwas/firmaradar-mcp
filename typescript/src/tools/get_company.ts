/**
 * Tool: `get_company`.
 *
 * Full company profile — group structure, owners, grants, recent
 * announcements and financial-metrics summary in one call.
 *
 * Backend status: EXISTS — wraps `GET /api/v1/company/<orgnr>` (see
 * `src/firmaradar/portal/routes_api.py:251`).
 */

import { z } from "zod";

export const schema = z.object({
  orgnr: z.string().regex(/^\d{9}$/, "orgnr must be exactly 9 digits"),
  fields: z
    .array(
      z.enum([
        "group",
        "owners",
        "business_owners",
        "full_owners",
        "grants",
        "brreg_grants",
        "ip",
        "changes",
        "financial_metrics",
      ]),
    )
    .describe(
      "Opt-in sections. Notably `ip` — intellectual-property portfolio (patents, " +
        "trademarks and designs from Patentstyret).",
    )
    .optional(),
  owners: z.enum(["business", "full"]).optional(),
  include_financial_metrics: z.boolean().default(false),
});

export type GetCompanyInput = z.infer<typeof schema>;

export async function handler(_input: unknown): Promise<unknown> {
  throw new Error(
    "get_company: REST endpoint exists (/api/v1/company/<orgnr>) but MCP wiring not implemented yet.",
  );
}
