/**
 * Tool: `get_person_companies`.
 *
 * All companies where a person holds shares (current).
 *
 * Backend status: EXISTS — wraps
 * `GET /api/v1/person/shareholdings/<owner_person_key>` (see
 * `src/firmaradar/portal/routes_api.py:363`).
 */

import { z } from "zod";

export const schema = z.object({
  person_key: z.string().regex(/^person-\d{4}-[0-9a-f]{24}$/),
  include_historic: z.boolean().default(false),
});

export type GetPersonCompaniesInput = z.infer<typeof schema>;

export async function handler(_input: unknown): Promise<unknown> {
  throw new Error(
    "get_person_companies: REST endpoint exists (/api/v1/person/shareholdings/<person_key>) — MCP wiring pending.",
  );
}
