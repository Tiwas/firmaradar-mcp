/**
 * Tool: `find_related_companies`.
 *
 * Find companies related to a given orgnr via shared person, shared
 * address, or shared owner-group.
 *
 * Backend status: GAP — net-new feature. v0.1 starts with via=person
 * + via=address; via=owner deferred. See `plans/MCP_V01_INVENTORY.md`
 * tool #15.
 */

import { z } from "zod";

export const schema = z.object({
  orgnr: z.string().regex(/^\d{9}$/),
  via: z.enum(["person", "address", "owner"]),
  limit: z.number().int().min(1).max(100).default(25),
  min_overlap: z.number().int().min(1).default(1),
});

export type FindRelatedCompaniesInput = z.infer<typeof schema>;

export async function handler(_input: unknown): Promise<unknown> {
  throw new Error(
    "find_related_companies: GAP — no backend implementation yet. Start with via=person + via=address.",
  );
}
