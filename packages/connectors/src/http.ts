/**
 * Lightweight HTTP client for connector API calls.
 * Handles auth injection, error wrapping, and response parsing.
 */

import type { ConnectorConfig, ToolResult } from "./types";

interface RequestOptions {
  method?: string;
  path: string;
  body?: unknown;
  query?: Record<string, string>;
  headers?: Record<string, string>;
  /** Override base URL (e.g., for per-request endpoints). */
  baseUrl?: string;
}

function buildUrl(base: string, path: string, query?: Record<string, string>): string {
  const url = new URL(path, base.endsWith("/") ? base : `${base}/`);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null) url.searchParams.set(k, v);
    }
  }
  return url.toString();
}

function injectAuth(headers: Record<string, string>, config: ConnectorConfig): Record<string, string> {
  const creds = config.credentials;
  switch (config.authKind) {
    case "api_key":
      if (creds.api_key) headers["Authorization"] = `Bearer ${creds.api_key}`;
      if (creds.api_token) headers["Authorization"] = `Bearer ${creds.api_token}`;
      if (creds.secret_key) headers["Authorization"] = `Bearer ${creds.secret_key}`;
      break;
    case "token":
      if (creds.access_token) headers["Authorization"] = `Bearer ${creds.access_token}`;
      if (creds.token) headers["Authorization"] = `token ${creds.token}`;
      if (creds.bot_token) headers["Authorization"] = `Bearer ${creds.bot_token}`;
      break;
    case "oauth2":
      if (creds.access_token) headers["Authorization"] = `Bearer ${creds.access_token}`;
      break;
    case "basic":
      if (creds.user && creds.password) {
        const encoded = Buffer.from(`${creds.user}:${creds.password}`).toString("base64");
        headers["Authorization"] = `Basic ${encoded}`;
      }
      if (creds.email && creds.api_token) {
        const encoded = Buffer.from(`${creds.email}:${creds.api_token}`).toString("base64");
        headers["Authorization"] = `Basic ${encoded}`;
      }
      break;
  }
  return headers;
}

/** Make an authenticated API call and return a ToolResult. */
export async function connectorFetch(
  config: ConnectorConfig,
  opts: RequestOptions,
): Promise<ToolResult> {
  const base = opts.baseUrl || config.baseUrl;
  if (!base) {
    return { success: false, error: "No base URL configured", summary: "Missing base URL" };
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
    ...opts.headers,
  };
  injectAuth(headers, config);

  const url = buildUrl(base, opts.path, opts.query);
  const method = (opts.method || "GET").toUpperCase();

  try {
    const response = await fetch(url, {
      method,
      headers,
      body: opts.body && method !== "GET" ? JSON.stringify(opts.body) : undefined,
    });

    const text = await response.text();
    let data: any;
    try {
      data = JSON.parse(text);
    } catch {
      data = { raw: text };
    }

    if (!response.ok) {
      const errMsg = data?.error?.message || data?.message || data?.detail || `HTTP ${response.status}`;
      return { success: false, error: errMsg, data, summary: `Failed: ${errMsg}` };
    }

    return { success: true, data, summary: `${method} ${opts.path} → ${response.status}` };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { success: false, error: msg, summary: `Network error: ${msg}` };
  }
}

/** Shorthand for Slack-style bot token auth. */
export function slackHeaders(config: ConnectorConfig): Record<string, string> {
  return { Authorization: `Bearer ${config.credentials.bot_token}` };
}

/** Shorthand for Jira/Confluence basic auth (email:api_token). */
export function atlassianHeaders(config: ConnectorConfig): Record<string, string> {
  const encoded = Buffer.from(
    `${config.credentials.email}:${config.credentials.api_token}`,
  ).toString("base64");
  return { Authorization: `Basic ${encoded}` };
}