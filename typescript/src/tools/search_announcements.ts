/**
 * Tool: `search_announcements`.
 *
 * Cross-orgnr search across BRREG kunngjøringer filtered by type, date
 * range, NACE-code or kommune.
 *
 * Backend status: GAP — needs `GET /api/v1/announcements/search` with
 * proper indexing. See `plans/MCP_V01_INVENTORY.md` tool #17.
 */

import { z } from "zod";

export const schema = z.object({
  type: z.string().optional(),
  from_date: z.string().optional().describe("ISO 8601 date, inclusive lower bound."),
  to_date: z.string().optional().describe("ISO 8601 date, inclusive upper bound."),
  nace: z.string().optional(),
  kommune: z.string().optional(),
  fylke: z.string().optional(),
  q: z.string().optional().describe("Free-text on company name."),
  limit: z.number().int().min(1).max(200).default(50),
  cursor: z.string().optional(),
});

export type SearchAnnouncementsInput = z.infer<typeof schema>;

export async function handler(_input: unknown): Promise<unknown> {
  throw new Error(
    "search_announcements: GAP — cross-orgnr endpoint GET /api/v1/announcements/search not implemented yet.",
  );
}
