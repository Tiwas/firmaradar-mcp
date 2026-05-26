/**
 * Tool: `get_company_announcements`.
 *
 * BRREG kunngjøringer (announcements) for one company.
 *
 * Backend status: EXISTS — wraps `GET /api/v1/company/<orgnr>/changes`
 * (see `src/firmaradar/portal/routes_api.py:236`).
 */

import { z } from "zod";

export const schema = z.object({
  orgnr: z.string().regex(/^\d{9}$/),
});

export type GetCompanyAnnouncementsInput = z.infer<typeof schema>;

export async function handler(_input: unknown): Promise<unknown> {
  throw new Error(
    "get_company_announcements: REST endpoint exists (/api/v1/company/<orgnr>/changes) — MCP wiring pending.",
  );
}
