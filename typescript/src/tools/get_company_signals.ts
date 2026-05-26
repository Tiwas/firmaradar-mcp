/**
 * Tool: `get_company_signals`.
 *
 * Aggregated risk signals envelope: bankruptcy/distress score,
 * capital-loss flags, recent role/signature changes, M&A interim-balance
 * signals and KYC announcement anomalies.
 *
 * Backend status: PARTIAL — three sources exist server-side, no unified
 * endpoint yet. See `plans/MCP_V01_INVENTORY.md` tool #11.
 */

import { z } from "zod";

export const schema = z.object({
  orgnr: z.string().regex(/^\d{9}$/),
  since: z.string().optional().describe("ISO 8601 date — defaults to 90 days back."),
});

export type GetCompanySignalsInput = z.infer<typeof schema>;

export async function handler(_input: unknown): Promise<unknown> {
  throw new Error(
    "get_company_signals: PARTIAL — needs unified GET /api/v1/company/<orgnr>/signals envelope endpoint.",
  );
}
