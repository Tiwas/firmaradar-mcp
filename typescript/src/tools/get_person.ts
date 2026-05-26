/**
 * Tool: `get_person`.
 *
 * Unified summary for one person — active roles + shareholdings +
 * AML/PEP risk flags in a single payload.
 *
 * Backend status: PARTIAL — shareholdings and roles each have their
 * own endpoint, but no aggregate. v0.1 may fan out client-side. See
 * `plans/MCP_V01_INVENTORY.md` tool #8.
 */

import { z } from "zod";

export const schema = z.object({
  person_id: z
    .string()
    .describe("`person-YYYY-[24 hex]` or `role-[24 hex]` from search_persons."),
  purpose: z.string().optional().describe("Purpose-of-processing for F10.11 audit."),
});

export type GetPersonInput = z.infer<typeof schema>;

export async function handler(_input: unknown): Promise<unknown> {
  throw new Error(
    "get_person: PARTIAL — fan-out across shareholdings + roles + aml_pep endpoints not implemented yet.",
  );
}
