/**
 * Tool: `get_person_roles`.
 *
 * All company roles (current + historic) held by one person.
 *
 * Backend status: EXISTS — wraps `GET /api/v1/person/roles/<role_person_id>`
 * (see `src/firmaradar/portal/routes_api.py:381`).
 */

import { z } from "zod";

export const schema = z.object({
  role_person_id: z.string().regex(/^role-[0-9a-f]{24}$/),
  include_historic: z.boolean().default(true),
});

export type GetPersonRolesInput = z.infer<typeof schema>;

export async function handler(_input: unknown): Promise<unknown> {
  throw new Error(
    "get_person_roles: REST endpoint exists (/api/v1/person/roles/<role_person_id>) — MCP wiring pending.",
  );
}
