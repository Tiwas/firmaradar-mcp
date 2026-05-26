/**
 * Tool: `get_company_financials`.
 *
 * Historic financial metrics (omsetning, driftsresultat, ek, gjeld,
 * antall ansatte) for a company. Defaults to the last 5 years.
 *
 * Backend status: EXISTS — wraps `GET /api/regnskap/<orgnr>/historikk?years=5`
 * (see `src/firmaradar/portal/routes_search.py:763`).
 */

import { z } from "zod";

export const schema = z.object({
  orgnr: z.string().regex(/^\d{9}$/),
  years: z.number().int().min(1).max(20).default(5),
  regnskapstype: z.enum(["SELSKAP", "KONSERN"]).default("SELSKAP"),
  skip_freshness: z.boolean().default(false),
});

export type GetCompanyFinancialsInput = z.infer<typeof schema>;

export async function handler(_input: unknown): Promise<unknown> {
  throw new Error(
    "get_company_financials: REST endpoint exists (/api/regnskap/<orgnr>/historikk) — MCP wiring pending.",
  );
}
