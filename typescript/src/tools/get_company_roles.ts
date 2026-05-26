/**
 * Tool: `get_company_roles`.
 *
 * Board, daglig leder, signatur, prokura and revisor for a company,
 * optionally with history.
 *
 * Backend status: GAP — no public endpoint. See
 * `plans/MCP_V01_INVENTORY.md` tool #4.
 */

import { z } from "zod";

export const schema = z.object({
  orgnr: z.string().regex(/^\d{9}$/),
  include_historic: z.boolean().default(false),
  role_type: z
    .enum([
      "styreleder",
      "styremedlem",
      "varamedlem",
      "daglig_leder",
      "signatur",
      "prokura",
      "revisor",
    ])
    .optional(),
});

export type GetCompanyRolesInput = z.infer<typeof schema>;

export async function handler(_input: unknown): Promise<unknown> {
  throw new Error(
    "get_company_roles: GAP — backend endpoint not implemented. Add RollerCacheRepository.list_roles_for_company() and GET /api/v1/company/<orgnr>/roles.",
  );
}
