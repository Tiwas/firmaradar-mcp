/**
 * Thin REST-client wrapper around the Firmaradar HTTP API.
 *
 * All tools route through this client so we have one place to handle
 * auth, retries, rate-limit headers and base-URL configuration.
 *
 * Configuration is read from environment variables only — never embed
 * credentials in source.
 *
 *  - `FIRMARADAR_API_KEY`  — long-lived API key for service-auth.
 *  - `FIRMARADAR_API_BASE` — base URL. Defaults to https://stage.firmaradar.no
 *    (dedicated MCP-tier per Lars decision 2026-05-25).
 *  - `FIRMARADAR_TIMEOUT_MS` — per-request timeout in ms. Default 30000.
 */

const DEFAULT_BASE_URL = "https://stage.firmaradar.no";
const DEFAULT_TIMEOUT_MS = 30_000;
export const ENV_API_KEY = "FIRMARADAR_API_KEY";
export const ENV_API_BASE = "FIRMARADAR_API_BASE";
export const ENV_TIMEOUT = "FIRMARADAR_TIMEOUT_MS";

export class FirmaradarClientError extends Error {
  public readonly statusCode?: number;
  public readonly errorCode?: string;
  public readonly retryAfterS?: number;

  constructor(
    message: string,
    opts: { statusCode?: number; errorCode?: string; retryAfterS?: number } = {},
  ) {
    super(message);
    this.name = "FirmaradarClientError";
    this.statusCode = opts.statusCode;
    this.errorCode = opts.errorCode;
    this.retryAfterS = opts.retryAfterS;
  }
}

export interface ClientConfig {
  apiKey: string;
  baseUrl: string;
  timeoutMs: number;
}

export function loadClientConfigFromEnv(): ClientConfig {
  const apiKey = (process.env[ENV_API_KEY] ?? "").trim();
  if (!apiKey) {
    throw new Error(
      `Missing required environment variable ${ENV_API_KEY}. ` +
        "Set it to your Firmaradar API key before launching the MCP-server.",
    );
  }
  const baseUrl = (process.env[ENV_API_BASE] ?? DEFAULT_BASE_URL).replace(/\/$/, "");
  const timeoutRaw = process.env[ENV_TIMEOUT];
  const timeoutMs = timeoutRaw ? Number(timeoutRaw) : DEFAULT_TIMEOUT_MS;
  return {
    apiKey,
    baseUrl,
    timeoutMs: Number.isFinite(timeoutMs) ? timeoutMs : DEFAULT_TIMEOUT_MS,
  };
}

/**
 * Thin async fetch wrapper. Methods return parsed JSON or throw
 * {@link FirmaradarClientError} on non-2xx responses.
 *
 * Note (skeleton): the methods are functional but every concrete tool
 * currently throws "not implemented" before reaching them. They are
 * exposed here so future implementation work can wire them up without
 * re-designing this layer.
 */
export class FirmaradarClient {
  private readonly config: ClientConfig;

  constructor(config?: ClientConfig) {
    this.config = config ?? loadClientConfigFromEnv();
  }

  get baseUrl(): string {
    return this.config.baseUrl;
  }

  async get(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<unknown> {
    const url = new URL(path, this.config.baseUrl + "/");
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
      }
    }
    const response = await this.fetchWithTimeout(url.toString(), { method: "GET" });
    return this.handleResponse(response);
  }

  async post(path: string, body?: unknown): Promise<unknown> {
    const url = new URL(path, this.config.baseUrl + "/");
    const response = await this.fetchWithTimeout(url.toString(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    return this.handleResponse(response);
  }

  private async fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.config.timeoutMs);
    try {
      return await fetch(url, {
        ...init,
        headers: {
          ...(init.headers ?? {}),
          Authorization: `Bearer ${this.config.apiKey}`,
          "User-Agent": "firmaradar-mcp/0.1 (+https://firmaradar.no)",
          Accept: "application/json",
        },
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timer);
    }
  }

  private async handleResponse(response: Response): Promise<unknown> {
    if (response.ok) {
      return response.json();
    }
    let payload: Record<string, unknown> = {};
    try {
      payload = (await response.json()) as Record<string, unknown>;
    } catch {
      payload = { error: await response.text() };
    }
    const retryAfter = response.headers.get("Retry-After");
    throw new FirmaradarClientError(
      (payload.error as string | undefined) ??
        (payload.message as string | undefined) ??
        response.statusText,
      {
        statusCode: response.status,
        errorCode: payload.error_code as string | undefined,
        retryAfterS: retryAfter && /^\d+$/.test(retryAfter) ? Number(retryAfter) : undefined,
      },
    );
  }
}
