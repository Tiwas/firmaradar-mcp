/**
 * Tool: `search_persons`.
 *
 * Search for persons across shareholders and role-holders by name +
 * optional birth-year hint.
 *
 * Backend status: EXISTS — wraps `GET /api/v1/person/search?q=` (see
 * `src/firmaradar/portal/routes_api.py:312`). PII-sensitive.
 */

import { z } from "zod";

export const schema = z.object({
  q: z.string().min(2),
  birth_year: z.number().int().min(1900).max(2100).optional(),
  kommune_hint: z.string().optional(),
  limit: z.number().int().min(1).max(100).default(30),
});

export type SearchPersonsInput = z.infer<typeof schema>;

export async function handler(_input: unknown): Promise<unknown> {
  throw new Error("search_persons: REST endpoint exists (/api/v1/person/search) — MCP wiring pending.");
}
