/**
 * MCP stdio-server entry point for @firmaradar/mcp-server.
 *
 * Boots the Model Context Protocol server, registers all 17 tools,
 * and runs the stdio event loop. Each tool is implemented as a small
 * self-contained module under `./tools/`; this file is just
 * orchestration.
 *
 * Run with `node dist/index.js` or via the `firmaradar-mcp` bin
 * shortcut (see `package.json`).
 */

import { FirmaradarClient } from "./client.js";
import { ALL_TOOLS } from "./tools/index.js";

function configureLogging(): void {
  // MCP uses stdout for the protocol, so we must log to stderr.
  const level = (process.env.FIRMARADAR_MCP_LOG_LEVEL ?? "INFO").toUpperCase();
  if (level === "DEBUG") {
    process.env.NODE_DEBUG = "firmaradar-mcp";
  }
}

async function serve(client: FirmaradarClient): Promise<void> {
  // Skeleton implementation — the actual MCP-SDK wiring is left to the
  // first implementation PR so we can pick the exact SDK API surface
  // once backend gaps in plans/MCP_V01_INVENTORY.md are closed.
  process.stderr.write(
    `firmaradar-mcp skeleton: ${ALL_TOOLS.length} tools registered against base_url=${client.baseUrl}\n`,
  );
  for (const tool of ALL_TOOLS) {
    process.stderr.write(`  - ${tool.name}\n`);
  }
  throw new Error(
    "MCP runtime wiring not implemented yet — see plans/MCP_V01_INVENTORY.md for backend status.",
  );
}

export async function main(): Promise<number> {
  configureLogging();
  const client = new FirmaradarClient();
  try {
    await serve(client);
    return 0;
  } catch (err) {
    process.stderr.write(`${(err as Error).message}\n`);
    return 2;
  }
}

// Direct-execute guard (ES module).
const isDirect = import.meta.url === `file://${process.argv[1]}`;
if (isDirect) {
  void main().then((code) => process.exit(code));
}
