/**
 * Tool: `get_recent_changes`.
 *
 * Recent changes for either a company (uses `/changes` endpoint) or a
 * person (role + ownership changes — needs new join logic server-side).
 *
 * Backend status: PARTIAL — company-side covered. Person-side needs
 * new endpoint. See `plans/MCP_V01_INVENTORY.md` tool #13.
 */

import { z } from "zod";

export const schema = z.object({
  entity_type: z.enum(["company", "person"]),
  id: z.string().describe("Orgnr (9 digits) or person_id depending on entity_type."),
  days: z.number().int().min(1).max(365).default(90),
  category: z.string().optional(),
});

export type GetRecentChangesInput = z.infer<typeof schema>;

export async function handler(_input: unknown): Promise<unknown> {
  throw new Error(
    "get_recent_changes: PARTIAL — company-side works via /api/v1/company/<orgnr>/changes; person-side needs new endpoint.",
  );
}
