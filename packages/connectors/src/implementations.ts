/**
 * Real execute functions for all connectors.
 * Each returns a ToolResult via connectorFetch.
 */

import type { ConnectorConfig, ToolResult } from "./types";
import { connectorFetch, slackHeaders, atlassianHeaders } from "./http";

type Exec = (params: Record<string, any>, config: ConnectorConfig) => Promise<ToolResult>;

// ── Helpers ──────────────────────────────────────────────────────

function required(params: Record<string, any>, ...keys: string[]): string | null {
  for (const k of keys) {
    if (!params[k] && params[k] !== 0) return `Missing required parameter: ${k}`;
  }
  return null;
}

// ── Gmail ────────────────────────────────────────────────────────

const gmail_send_email: Exec = async (params, config) => {
  const err = required(params, "to", "subject", "body");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, {
    method: "POST", path: "/gmail/v1/users/me/messages/send",
    baseUrl: "https://gmail.googleapis.com",
    body: { raw: Buffer.from(`To: ${params.to}\r\nSubject: ${params.subject}\r\nContent-Type: text/html\r\n\r\n${params.body}`).toString("base64url") },
  });
};

const gmail_search_email: Exec = async (params, config) => {
  return connectorFetch(config, {
    path: "/gmail/v1/users/me/messages",
    baseUrl: "https://gmail.googleapis.com",
    query: { q: params.query || "", maxResults: String(params.maxResults || 10) },
  });
};

const gmail_read_email: Exec = async (params, config) => {
  const err = required(params, "id");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, {
    path: `/gmail/v1/users/me/messages/${params.id}`,
    baseUrl: "https://gmail.googleapis.com",
    query: { format: "full" },
  });
};

const gmail_list_labels: Exec = async (_params, config) => {
  return connectorFetch(config, {
    path: "/gmail/v1/users/me/labels",
    baseUrl: "https://gmail.googleapis.com",
  });
};

// ── Slack ─────────────────────────────────────────────────────────

const slack_send_message: Exec = async (params, config) => {
  const err = required(params, "channel", "text");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, {
    method: "POST", path: "/api/chat.postMessage",
    baseUrl: "https://slack.com",
    headers: slackHeaders(config),
    body: { channel: params.channel, text: params.text },
  });
};

const slack_list_channels: Exec = async (_params, config) => {
  return connectorFetch(config, {
    path: "/api/conversations.list",
    baseUrl: "https://slack.com",
    headers: slackHeaders(config),
    query: { limit: "100" },
  });
};

const slack_read_thread: Exec = async (params, config) => {
  const err = required(params, "channel", "ts");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, {
    path: "/api/conversations.replies",
    baseUrl: "https://slack.com",
    headers: slackHeaders(config),
    query: { channel: params.channel, ts: params.ts },
  });
};

const slack_search_messages: Exec = async (params, config) => {
  return connectorFetch(config, {
    path: "/api/search.messages",
    baseUrl: "https://slack.com",
    headers: slackHeaders(config),
    query: { query: params.query || "" },
  });
};

// ── Microsoft Teams ──────────────────────────────────────────────

const teams_send_message: Exec = async (params, config) => {
  const err = required(params, "teamId", "channelId", "content");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, {
    method: "POST",
    path: `/v1.0/teams/${params.teamId}/channels/${params.channelId}/messages`,
    baseUrl: "https://graph.microsoft.com",
    body: { body: { content: params.content } },
  });
};

const teams_list_teams: Exec = async (_params, config) => {
  return connectorFetch(config, { path: "/v1.0/me/joinedTeams", baseUrl: "https://graph.microsoft.com" });
};

// ── Discord ──────────────────────────────────────────────────────

const discord_send_message: Exec = async (params, config) => {
  const err = required(params, "channelId", "content");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, {
    method: "POST",
    path: `/api/v10/channels/${params.channelId}/messages`,
    baseUrl: "https://discord.com",
    headers: { Authorization: `Bot ${config.credentials.bot_token}` },
    body: { content: params.content },
  });
};

const discord_list_channels: Exec = async (params, config) => {
  const err = required(params, "guildId");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, {
    path: `/api/v10/guilds/${params.guildId}/channels`,
    baseUrl: "https://discord.com",
    headers: { Authorization: `Bot ${config.credentials.bot_token}` },
  });
};

// ── Twilio ────────────────────────────────────────────────────────

const twilio_send_sms: Exec = async (params, config) => {
  const err = required(params, "to", "body");
  if (err) return { success: false, error: err, summary: err };
  const sid = config.credentials.account_sid;
  return connectorFetch(config, {
    method: "POST",
    path: `/2010-04-01/Accounts/${sid}/Messages.json`,
    baseUrl: "https://api.twilio.com",
    headers: {
      Authorization: `Basic ${Buffer.from(`${sid}:${config.credentials.auth_token}`).toString("base64")}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({ To: params.to, From: params.from || config.credentials.from_number || "", Body: params.body }).toString(),
  });
};

const twilio_make_call: Exec = async (params, config) => {
  const err = required(params, "to");
  if (err) return { success: false, error: err, summary: err };
  const sid = config.credentials.account_sid;
  return connectorFetch(config, {
    method: "POST",
    path: `/2010-04-01/Accounts/${sid}/Calls.json`,
    baseUrl: "https://api.twilio.com",
    headers: { Authorization: `Basic ${Buffer.from(`${sid}:${config.credentials.auth_token}`).toString("base64")}` },
    body: { To: params.to, From: params.from || "" },
  });
};

// ── Jira ──────────────────────────────────────────────────────────

const jira_base = (config: ConnectorConfig) => `https://${config.credentials.domain}.atlassian.net`;

const jira_create_issue: Exec = async (params, config) => {
  const err = required(params, "project", "summary", "issueType");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, {
    method: "POST", path: "/rest/api/3/issue",
    baseUrl: jira_base(config), headers: atlassianHeaders(config),
    body: { fields: { project: { key: params.project }, summary: params.summary, issuetype: { name: params.issueType }, description: params.description ? { type: "doc", version: 1, content: [{ type: "paragraph", content: [{ type: "text", text: params.description }] }] } : undefined } },
  });
};

const jira_search_issues: Exec = async (params, config) => {
  return connectorFetch(config, {
    path: "/rest/api/3/search", baseUrl: jira_base(config), headers: atlassianHeaders(config),
    query: { jql: params.jql || params.query || "", maxResults: String(params.maxResults || 20) },
  });
};

const jira_update_issue: Exec = async (params, config) => {
  const err = required(params, "issueKey");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, {
    method: "PUT", path: `/rest/api/3/issue/${params.issueKey}`,
    baseUrl: jira_base(config), headers: atlassianHeaders(config),
    body: { fields: params.fields || {} },
  });
};

const jira_list_projects: Exec = async (_params, config) => {
  return connectorFetch(config, { path: "/rest/api/3/project", baseUrl: jira_base(config), headers: atlassianHeaders(config) });
};

// ── Linear ────────────────────────────────────────────────────────

const linear_gql: Exec = async (params, config) => {
  return connectorFetch(config, {
    method: "POST", path: "/graphql", baseUrl: "https://api.linear.app",
    body: { query: params._gql, variables: params._vars },
  });
};

const linear_create_issue: Exec = async (params, config) => {
  const err = required(params, "title", "teamId");
  if (err) return { success: false, error: err, summary: err };
  return linear_gql({ _gql: `mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { id identifier title } } }`, _vars: { input: { title: params.title, teamId: params.teamId, description: params.description } } }, config);
};

const linear_search_issues: Exec = async (params, config) => {
  return linear_gql({ _gql: `query($filter: IssueFilter) { issues(filter: $filter, first: 20) { nodes { id identifier title state { name } } } }`, _vars: { filter: params.filter || {} } }, config);
};

const linear_list_projects: Exec = async (_params, config) => {
  return linear_gql({ _gql: `query { projects(first: 50) { nodes { id name state } } }`, _vars: {} }, config);
};

// ── Asana / Trello / Monday (REST) ───────────────────────────────

const asana_create_task: Exec = async (params, config) => {
  const err = required(params, "name");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: "/api/1.0/tasks", baseUrl: "https://app.asana.com", body: { data: { name: params.name, notes: params.notes, projects: params.projectId ? [params.projectId] : [] } } });
};
const asana_list_tasks: Exec = async (params, config) => connectorFetch(config, { path: "/api/1.0/tasks", baseUrl: "https://app.asana.com", query: { project: params.projectId, limit: "50" } });

const trello_create_card: Exec = async (params, config) => {
  const err = required(params, "name", "idList");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: "/1/cards", baseUrl: "https://api.trello.com", query: { key: config.credentials.api_key, token: config.credentials.token }, body: { name: params.name, idList: params.idList, desc: params.desc } });
};
const trello_list_boards: Exec = async (_params, config) => connectorFetch(config, { path: "/1/members/me/boards", baseUrl: "https://api.trello.com", query: { key: config.credentials.api_key, token: config.credentials.token } });

const monday_create_item: Exec = async (params, config) => {
  const err = required(params, "boardId", "itemName");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: "/v2", baseUrl: "https://api.monday.com", body: { query: `mutation { create_item (board_id: ${params.boardId}, item_name: "${params.itemName}") { id } }` } });
};
const monday_list_boards: Exec = async (_params, config) => connectorFetch(config, { method: "POST", path: "/v2", baseUrl: "https://api.monday.com", body: { query: `{ boards(limit: 50) { id name } }` } });

// ── GitHub ────────────────────────────────────────────────────────

const gh_base = "https://api.github.com";

const github_create_issue: Exec = async (params, config) => {
  const err = required(params, "owner", "repo", "title");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: `/repos/${params.owner}/${params.repo}/issues`, baseUrl: gh_base, body: { title: params.title, body: params.body } });
};
const github_create_pr: Exec = async (params, config) => {
  const err = required(params, "owner", "repo", "title", "head", "base");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: `/repos/${params.owner}/${params.repo}/pulls`, baseUrl: gh_base, body: { title: params.title, head: params.head, base: params.base, body: params.body } });
};
const github_list_repos: Exec = async (_params, config) => connectorFetch(config, { path: "/user/repos", baseUrl: gh_base, query: { per_page: "30", sort: "updated" } });
const github_search_code: Exec = async (params, config) => connectorFetch(config, { path: "/search/code", baseUrl: gh_base, query: { q: params.query || "" } });

// ── Confluence ────────────────────────────────────────────────────

const confluence_base = (config: ConnectorConfig) => `https://${config.credentials.domain}.atlassian.net/wiki`;

const confluence_create_page: Exec = async (params, config) => {
  const err = required(params, "spaceKey", "title", "body");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: "/rest/api/content", baseUrl: confluence_base(config), headers: atlassianHeaders(config), body: { type: "page", title: params.title, space: { key: params.spaceKey }, body: { storage: { value: params.body, representation: "storage" } } } });
};
const confluence_search_pages: Exec = async (params, config) => connectorFetch(config, { path: "/rest/api/content/search", baseUrl: confluence_base(config), headers: atlassianHeaders(config), query: { cql: params.query || "" } });

// ── Salesforce ────────────────────────────────────────────────────

const sf_base = (config: ConnectorConfig) => config.credentials.instance_url || "https://login.salesforce.com";

const salesforce_create_lead: Exec = async (params, config) => {
  const err = required(params, "LastName", "Company");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: "/services/data/v59.0/sobjects/Lead", baseUrl: sf_base(config), body: params });
};
const salesforce_search_contacts: Exec = async (params, config) => connectorFetch(config, { path: "/services/data/v59.0/query", baseUrl: sf_base(config), query: { q: params.soql || `SELECT Id, Name, Email FROM Contact LIMIT 20` } });
const salesforce_create_opportunity: Exec = async (params, config) => {
  const err = required(params, "Name", "StageName", "CloseDate");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: "/services/data/v59.0/sobjects/Opportunity", baseUrl: sf_base(config), body: params });
};

// ── HubSpot ──────────────────────────────────────────────────────

const hs_base = "https://api.hubapi.com";

const hubspot_create_contact: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: "/crm/v3/objects/contacts", baseUrl: hs_base, body: { properties: params } });
const hubspot_search_contacts: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: "/crm/v3/objects/contacts/search", baseUrl: hs_base, body: { query: params.query || "" } });
const hubspot_create_deal: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: "/crm/v3/objects/deals", baseUrl: hs_base, body: { properties: params } });

// ── Google Analytics / Ads ───────────────────────────────────────

const ga_get_report: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: `/v1beta/${params.property || "properties/0"}:runReport`, baseUrl: "https://analyticsdata.googleapis.com", body: { dateRanges: [{ startDate: params.startDate || "30daysAgo", endDate: params.endDate || "today" }], metrics: (params.metrics || ["sessions"]).map((m: string) => ({ name: m })) } });
const ga_get_realtime: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: `/v1beta/${params.property || "properties/0"}:runRealtimeReport`, baseUrl: "https://analyticsdata.googleapis.com", body: { metrics: [{ name: "activeUsers" }] } });
const gads_list_campaigns: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: `/v16/customers/${config.credentials.customer_id}/googleAds:searchStream`, baseUrl: "https://googleads.googleapis.com", headers: { "developer-token": config.credentials.developer_token }, body: { query: "SELECT campaign.id, campaign.name, campaign.status FROM campaign LIMIT 50" } });
const gads_get_report: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: `/v16/customers/${config.credentials.customer_id}/googleAds:searchStream`, baseUrl: "https://googleads.googleapis.com", headers: { "developer-token": config.credentials.developer_token }, body: { query: params.query || "SELECT campaign.name, metrics.impressions FROM campaign" } });

// ── BigQuery / PostgreSQL / Supabase ─────────────────────────────

const bq_run_query: Exec = async (params, config) => {
  const err = required(params, "query", "projectId");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: `/bigquery/v2/projects/${params.projectId}/queries`, baseUrl: "https://bigquery.googleapis.com", body: { query: params.query, useLegacySql: false } });
};
const bq_list_datasets: Exec = async (params, config) => connectorFetch(config, { path: `/bigquery/v2/projects/${params.projectId}/datasets`, baseUrl: "https://bigquery.googleapis.com" });

const pg_run_query: Exec = async (params, config) => {
  const err = required(params, "query");
  if (err) return { success: false, error: err, summary: err };
  try {
    // @ts-ignore — pg is an optional peer dependency, resolved at runtime
    const { default: pg } = await import("pg");
    const client = new pg.Client({
      host: config.credentials.host,
      port: Number(config.credentials.port || 5432),
      database: config.credentials.database,
      user: config.credentials.user,
      password: config.credentials.password,
      ssl: config.credentials.ssl === "true" ? { rejectUnauthorized: false } : undefined,
    });
    await client.connect();
    try {
      const result = await client.query(params.query);
      return { success: true, data: { rows: result.rows, rowCount: result.rowCount, fields: result.fields?.map((f: any) => f.name) }, summary: `${result.rowCount ?? 0} rows returned` };
    } finally {
      await client.end();
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (msg.includes("Cannot find module") || msg.includes("MODULE_NOT_FOUND")) {
      return { success: false, error: "Install 'pg' package: npm install pg", summary: "Missing pg driver" };
    }
    return { success: false, error: msg, summary: `Query failed: ${msg}` };
  }
};
const pg_list_tables: Exec = async (params, config) => {
  return pg_run_query({ ...params, query: "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name" }, config);
};

const supabase_query: Exec = async (params, config) => {
  const err = required(params, "table");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { path: `/rest/v1/${params.table}`, baseUrl: config.credentials.url, headers: { apikey: config.credentials.anon_key }, query: { select: params.select || "*", limit: String(params.limit || 50) } });
};
const supabase_insert: Exec = async (params, config) => {
  const err = required(params, "table", "row");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: `/rest/v1/${params.table}`, baseUrl: config.credentials.url, headers: { apikey: config.credentials.anon_key, Prefer: "return=representation" }, body: params.row });
};

// ── Notion ────────────────────────────────────────────────────────

const notion_base = "https://api.notion.com";
const notion_headers = (config: ConnectorConfig) => ({ Authorization: `Bearer ${config.credentials.api_key}`, "Notion-Version": "2022-06-28" });

const notion_create_page: Exec = async (params, config) => {
  const err = required(params, "parentId", "title");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: "/v1/pages", baseUrl: notion_base, headers: notion_headers(config), body: { parent: { page_id: params.parentId }, properties: { title: { title: [{ text: { content: params.title } }] } }, children: params.content ? [{ object: "block", type: "paragraph", paragraph: { rich_text: [{ text: { content: params.content } }] } }] : [] } });
};
const notion_search: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: "/v1/search", baseUrl: notion_base, headers: notion_headers(config), body: { query: params.query || "" } });
const notion_query_database: Exec = async (params, config) => {
  const err = required(params, "databaseId");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: `/v1/databases/${params.databaseId}/query`, baseUrl: notion_base, headers: notion_headers(config), body: params.filter ? { filter: params.filter } : {} });
};

// ── Airtable ─────────────────────────────────────────────────────

const airtable_list_records: Exec = async (params, config) => {
  const err = required(params, "baseId", "tableId");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { path: `/v0/${params.baseId}/${params.tableId}`, baseUrl: "https://api.airtable.com", query: { maxRecords: String(params.maxRecords || 50) } });
};
const airtable_create_record: Exec = async (params, config) => {
  const err = required(params, "baseId", "tableId", "fields");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: `/v0/${params.baseId}/${params.tableId}`, baseUrl: "https://api.airtable.com", body: { fields: params.fields } });
};

// ── Google Calendar / Calendly ───────────────────────────────────

const gcal_create_event: Exec = async (params, config) => {
  const err = required(params, "summary", "start", "end");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: `/calendar/v3/calendars/${params.calendarId || "primary"}/events`, baseUrl: "https://www.googleapis.com", body: { summary: params.summary, start: { dateTime: params.start }, end: { dateTime: params.end } } });
};
const gcal_list_events: Exec = async (params, config) => connectorFetch(config, { path: `/calendar/v3/calendars/${params.calendarId || "primary"}/events`, baseUrl: "https://www.googleapis.com", query: { maxResults: "20", timeMin: new Date().toISOString(), singleEvents: "true", orderBy: "startTime" } });
const calendly_list_events: Exec = async (_params, config) => connectorFetch(config, { path: "/api/v2/scheduled_events", baseUrl: "https://api.calendly.com", query: { count: "20" } });
const calendly_get_availability: Exec = async (params, config) => connectorFetch(config, { path: `/api/v2/user_availability_schedules`, baseUrl: "https://api.calendly.com" });

// ── Storage (Google Drive, Dropbox, Box) ─────────────────────────

const gdrive_search: Exec = async (params, config) => connectorFetch(config, { path: "/drive/v3/files", baseUrl: "https://www.googleapis.com", query: { q: params.query || "", pageSize: "20" } });
const gdrive_upload: Exec = async (params, config) => {
  const err = required(params, "name", "content");
  if (err) return { success: false, error: err, summary: err };
  const metadata = JSON.stringify({ name: params.name, mimeType: params.mimeType || "application/octet-stream", parents: params.folderId ? [params.folderId] : undefined });
  const boundary = `maia_${Date.now()}`;
  const body = `--${boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${metadata}\r\n--${boundary}\r\nContent-Type: ${params.mimeType || "application/octet-stream"}\r\nContent-Transfer-Encoding: base64\r\n\r\n${typeof params.content === "string" ? params.content : Buffer.from(params.content).toString("base64")}\r\n--${boundary}--`;
  try {
    const response = await fetch("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart", {
      method: "POST",
      headers: { Authorization: `Bearer ${config.credentials.access_token}`, "Content-Type": `multipart/related; boundary=${boundary}` },
      body,
    });
    const data = await response.json();
    if (!response.ok) return { success: false, error: data?.error?.message || `HTTP ${response.status}`, data, summary: `Upload failed` };
    return { success: true, data, summary: `Uploaded ${params.name} (${data.id})` };
  } catch (e) { const msg = e instanceof Error ? e.message : String(e); return { success: false, error: msg, summary: `Upload error: ${msg}` }; }
};
const gdrive_download: Exec = async (params, config) => {
  const err = required(params, "fileId");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { path: `/drive/v3/files/${params.fileId}`, baseUrl: "https://www.googleapis.com", query: { alt: "media" } });
};

const dropbox_list: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: "/2/files/list_folder", baseUrl: "https://api.dropboxapi.com", body: { path: params.path || "" } });
const dropbox_upload: Exec = async (params, config) => {
  const err = required(params, "path", "content");
  if (err) return { success: false, error: err, summary: err };
  const contentBytes = typeof params.content === "string" ? Buffer.from(params.content, "base64") : params.content;
  try {
    const response = await fetch("https://content.dropboxapi.com/2/files/upload", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${config.credentials.access_token}`,
        "Content-Type": "application/octet-stream",
        "Dropbox-API-Arg": JSON.stringify({ path: params.path, mode: "overwrite", autorename: true }),
      },
      body: contentBytes,
    });
    const data = await response.json();
    if (!response.ok) return { success: false, error: data?.error_summary || `HTTP ${response.status}`, data, summary: "Upload failed" };
    return { success: true, data, summary: `Uploaded to ${data.path_display || params.path}` };
  } catch (e) { const msg = e instanceof Error ? e.message : String(e); return { success: false, error: msg, summary: `Upload error: ${msg}` }; }
};

const box_search: Exec = async (params, config) => connectorFetch(config, { path: "/2.0/search", baseUrl: "https://api.box.com", query: { query: params.query || "" } });
const box_upload: Exec = async (params, config) => {
  const err = required(params, "folderId", "name", "content");
  if (err) return { success: false, error: err, summary: err };
  const boundary = `maia_${Date.now()}`;
  const attributes = JSON.stringify({ name: params.name, parent: { id: params.folderId } });
  const contentBytes = typeof params.content === "string" ? Buffer.from(params.content, "base64") : params.content;
  const body = `--${boundary}\r\nContent-Disposition: form-data; name="attributes"\r\n\r\n${attributes}\r\n--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${params.name}"\r\nContent-Type: application/octet-stream\r\n\r\n${contentBytes}\r\n--${boundary}--`;
  try {
    const response = await fetch("https://upload.box.com/api/2.0/files/content", {
      method: "POST",
      headers: { Authorization: `Bearer ${config.credentials.access_token}`, "Content-Type": `multipart/form-data; boundary=${boundary}` },
      body,
    });
    const data = await response.json();
    if (!response.ok) return { success: false, error: data?.message || `HTTP ${response.status}`, data, summary: "Upload failed" };
    return { success: true, data, summary: `Uploaded ${params.name}` };
  } catch (e) { const msg = e instanceof Error ? e.message : String(e); return { success: false, error: msg, summary: `Upload error: ${msg}` }; }
};

// ── Commerce (Stripe, Shopify, QuickBooks, Xero) ────────────────

const stripe_create_invoice: Exec = async (params, config) => {
  const err = required(params, "customer");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: "/v1/invoices", baseUrl: "https://api.stripe.com", body: { customer: params.customer } });
};
const stripe_list_customers: Exec = async (_params, config) => connectorFetch(config, { path: "/v1/customers", baseUrl: "https://api.stripe.com", query: { limit: "20" } });
const stripe_get_balance: Exec = async (_params, config) => connectorFetch(config, { path: "/v1/balance", baseUrl: "https://api.stripe.com" });

const shopify_base = (config: ConnectorConfig) => `https://${config.credentials.shop_domain}.myshopify.com`;
const shopify_list_products: Exec = async (_params, config) => connectorFetch(config, { path: "/admin/api/2024-01/products.json", baseUrl: shopify_base(config), query: { limit: "20" } });
const shopify_list_orders: Exec = async (_params, config) => connectorFetch(config, { path: "/admin/api/2024-01/orders.json", baseUrl: shopify_base(config), query: { limit: "20" } });
const shopify_create_product: Exec = async (params, config) => {
  const err = required(params, "title");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: "/admin/api/2024-01/products.json", baseUrl: shopify_base(config), body: { product: { title: params.title, body_html: params.description } } });
};

const qb_create_invoice: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: `/v3/company/${config.credentials.realm_id}/invoice`, baseUrl: "https://quickbooks.api.intuit.com", body: params });
const qb_list_customers: Exec = async (_params, config) => connectorFetch(config, { path: `/v3/company/${config.credentials.realm_id}/query`, baseUrl: "https://quickbooks.api.intuit.com", query: { query: "SELECT * FROM Customer MAXRESULTS 20" } });

const xero_create_invoice: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: "/api.xro/2.0/Invoices", baseUrl: "https://api.xero.com", headers: { "Xero-Tenant-Id": config.credentials.tenant_id || "" }, body: params });
const xero_list_contacts: Exec = async (_params, config) => connectorFetch(config, { path: "/api.xro/2.0/Contacts", baseUrl: "https://api.xero.com", headers: { "Xero-Tenant-Id": config.credentials.tenant_id || "" } });

// ── Mailchimp ────────────────────────────────────────────────────

const mc_base = (config: ConnectorConfig) => { const dc = config.credentials.api_key?.split("-").pop() || "us1"; return `https://${dc}.api.mailchimp.com`; };
const mailchimp_send_campaign: Exec = async (params, config) => {
  const err = required(params, "campaignId");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: `/3.0/campaigns/${params.campaignId}/actions/send`, baseUrl: mc_base(config) });
};
const mailchimp_list_audiences: Exec = async (_params, config) => connectorFetch(config, { path: "/3.0/lists", baseUrl: mc_base(config) });

// ── Social (Twitter, LinkedIn) ───────────────────────────────────

const twitter_post_tweet: Exec = async (params, config) => {
  const err = required(params, "text");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: "/2/tweets", baseUrl: "https://api.twitter.com", body: { text: params.text } });
};
const twitter_search_tweets: Exec = async (params, config) => connectorFetch(config, { path: "/2/tweets/search/recent", baseUrl: "https://api.twitter.com", query: { query: params.query || "", max_results: "20" } });

const linkedin_create_post: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: "/v2/ugcPosts", baseUrl: "https://api.linkedin.com", body: { author: params.author || "", lifecycleState: "PUBLISHED", specificContent: { "com.linkedin.ugc.ShareContent": { shareCommentary: { text: params.text || "" }, shareMediaCategory: "NONE" } }, visibility: { "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC" } } });
const linkedin_get_profile: Exec = async (_params, config) => connectorFetch(config, { path: "/v2/userinfo", baseUrl: "https://api.linkedin.com" });

// ── Search (Brave) ───────────────────────────────────────────────

const brave_web_search: Exec = async (params, config) => connectorFetch(config, { path: "/res/v1/web/search", baseUrl: "https://api.search.brave.com", headers: { "X-Subscription-Token": config.credentials.api_key }, query: { q: params.query || "", count: String(params.count || 10) } });
const brave_news_search: Exec = async (params, config) => connectorFetch(config, { path: "/res/v1/news/search", baseUrl: "https://api.search.brave.com", headers: { "X-Subscription-Token": config.credentials.api_key }, query: { q: params.query || "", count: String(params.count || 10) } });

// ── Support (Zendesk, Intercom) ──────────────────────────────────

const zd_base = (config: ConnectorConfig) => `https://${config.credentials.subdomain}.zendesk.com`;
const zendesk_create_ticket: Exec = async (params, config) => {
  const err = required(params, "subject");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: "/api/v2/tickets.json", baseUrl: zd_base(config), headers: { Authorization: `Basic ${Buffer.from(`${config.credentials.email}/token:${config.credentials.api_token}`).toString("base64")}` }, body: { ticket: { subject: params.subject, description: params.description, priority: params.priority || "normal" } } });
};
const zendesk_search_tickets: Exec = async (params, config) => connectorFetch(config, { path: "/api/v2/search.json", baseUrl: zd_base(config), headers: { Authorization: `Basic ${Buffer.from(`${config.credentials.email}/token:${config.credentials.api_token}`).toString("base64")}` }, query: { query: `type:ticket ${params.query || ""}` } });

const intercom_send_message: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: "/messages", baseUrl: "https://api.intercom.io", body: { message_type: "inapp", body: params.body, from: { type: "admin", id: params.adminId }, to: { type: "user", user_id: params.userId } } });
const intercom_list_conversations: Exec = async (_params, config) => connectorFetch(config, { path: "/conversations", baseUrl: "https://api.intercom.io" });

// ── Design (Figma) ───────────────────────────────────────────────

const figma_get_file: Exec = async (params, config) => {
  const err = required(params, "fileKey");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { path: `/v1/files/${params.fileKey}`, baseUrl: "https://api.figma.com" });
};
const figma_list_components: Exec = async (params, config) => {
  const err = required(params, "fileKey");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { path: `/v1/files/${params.fileKey}/components`, baseUrl: "https://api.figma.com" });
};

// ── Automation (Zapier, Make) ────────────────────────────────────

const webhook_trigger: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: "", baseUrl: config.credentials.webhook_url, body: params.data || params });

// ── Cloud (AWS, Vercel, Cloudflare) ──────────────────────────────

const aws_s3_list: Exec = async (params, config) => {
  try {
    // @ts-ignore — @aws-sdk/client-s3 is an optional peer dependency
    const { S3Client, ListBucketsCommand, ListObjectsV2Command } = await import("@aws-sdk/client-s3");
    const client = new S3Client({
      region: config.credentials.region || "us-east-1",
      credentials: { accessKeyId: config.credentials.access_key_id, secretAccessKey: config.credentials.secret_access_key },
    });
    if (params.bucket) {
      const res = await client.send(new ListObjectsV2Command({ Bucket: params.bucket, MaxKeys: Number(params.maxKeys || 50), Prefix: params.prefix }));
      return { success: true, data: { keys: (res.Contents || []).map((o: any) => ({ key: o.Key, size: o.Size, modified: o.LastModified })), truncated: res.IsTruncated }, summary: `${(res.Contents || []).length} objects in ${params.bucket}` };
    }
    const res = await client.send(new ListBucketsCommand({}));
    return { success: true, data: { buckets: (res.Buckets || []).map((b: any) => ({ name: b.Name, created: b.CreationDate })) }, summary: `${(res.Buckets || []).length} buckets` };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (msg.includes("Cannot find module") || msg.includes("MODULE_NOT_FOUND")) return { success: false, error: "Install AWS SDK: npm install @aws-sdk/client-s3", summary: "Missing @aws-sdk/client-s3" };
    return { success: false, error: msg, summary: `AWS error: ${msg}` };
  }
};
const aws_lambda_invoke: Exec = async (params, config) => {
  const err = required(params, "functionName");
  if (err) return { success: false, error: err, summary: err };
  try {
    // @ts-ignore — @aws-sdk/client-lambda is an optional peer dependency
    const { LambdaClient, InvokeCommand } = await import("@aws-sdk/client-lambda");
    const client = new LambdaClient({
      region: config.credentials.region || "us-east-1",
      credentials: { accessKeyId: config.credentials.access_key_id, secretAccessKey: config.credentials.secret_access_key },
    });
    const res = await client.send(new InvokeCommand({
      FunctionName: params.functionName,
      Payload: params.payload ? Buffer.from(JSON.stringify(params.payload)) : undefined,
      InvocationType: params.async ? "Event" : "RequestResponse",
    }));
    const payload = res.Payload ? JSON.parse(Buffer.from(res.Payload).toString()) : null;
    return { success: true, data: { statusCode: res.StatusCode, payload }, summary: `Lambda ${params.functionName} → ${res.StatusCode}` };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (msg.includes("Cannot find module") || msg.includes("MODULE_NOT_FOUND")) return { success: false, error: "Install AWS SDK: npm install @aws-sdk/client-lambda", summary: "Missing @aws-sdk/client-lambda" };
    return { success: false, error: msg, summary: `Lambda error: ${msg}` };
  }
};

const vercel_list_deployments: Exec = async (_params, config) => connectorFetch(config, { path: "/v6/deployments", baseUrl: "https://api.vercel.com" });
const vercel_trigger_deploy: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: "/v13/deployments", baseUrl: "https://api.vercel.com", body: { name: params.name, target: params.target || "production" } });

const cf_list_zones: Exec = async (_params, config) => connectorFetch(config, { path: "/client/v4/zones", baseUrl: "https://api.cloudflare.com" });
const cf_purge_cache: Exec = async (params, config) => {
  const err = required(params, "zoneId");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: `/client/v4/zones/${params.zoneId}/purge_cache`, baseUrl: "https://api.cloudflare.com", body: { purge_everything: true } });
};

// ── AI/ML (OpenAI, Pinecone) ─────────────────────────────────────

const openai_chat: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: "/v1/chat/completions", baseUrl: "https://api.openai.com", body: { model: params.model || "gpt-4o-mini", messages: params.messages || [{ role: "user", content: params.prompt || "" }] } });
const openai_image: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: "/v1/images/generations", baseUrl: "https://api.openai.com", body: { model: "dall-e-3", prompt: params.prompt || "", size: params.size || "1024x1024", n: 1 } });
const pinecone_upsert: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: "/vectors/upsert", baseUrl: config.credentials.host || `https://${config.credentials.index}-${config.credentials.environment}.svc.pinecone.io`, body: { vectors: params.vectors } });
const pinecone_query: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: "/query", baseUrl: config.credentials.host || `https://${config.credentials.index}-${config.credentials.environment}.svc.pinecone.io`, body: { vector: params.vector, topK: params.topK || 10 } });

// ── Enterprise (SAP, DocuSign) ───────────────────────────────────

const sap_read_entity: Exec = async (params, config) => {
  const err = required(params, "entitySet");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { path: `/sap/opu/odata/sap/${params.entitySet}`, baseUrl: config.credentials.base_url || "" });
};
const sap_create_entity: Exec = async (params, config) => {
  const err = required(params, "entitySet");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { method: "POST", path: `/sap/opu/odata/sap/${params.entitySet}`, baseUrl: config.credentials.base_url || "", body: params.data });
};

const docusign_send_envelope: Exec = async (params, config) => connectorFetch(config, { method: "POST", path: "/restapi/v2.1/accounts/me/envelopes", baseUrl: "https://demo.docusign.net", body: params });
const docusign_list_envelopes: Exec = async (_params, config) => connectorFetch(config, { path: "/restapi/v2.1/accounts/me/envelopes", baseUrl: "https://demo.docusign.net", query: { from_date: new Date(Date.now() - 30 * 86400000).toISOString() } });

// ── Media (YouTube, Spotify) ─────────────────────────────────────

const youtube_search: Exec = async (params, config) => connectorFetch(config, { path: "/youtube/v3/search", baseUrl: "https://www.googleapis.com", query: { part: "snippet", q: params.query || "", maxResults: "10", key: config.credentials.api_key } });
const youtube_get_video: Exec = async (params, config) => connectorFetch(config, { path: "/youtube/v3/videos", baseUrl: "https://www.googleapis.com", query: { part: "snippet,statistics", id: params.videoId, key: config.credentials.api_key } });

const spotify_search: Exec = async (params, config) => connectorFetch(config, { path: "/v1/search", baseUrl: "https://api.spotify.com", query: { q: params.query || "", type: "track", limit: "20" } });
const spotify_get_playlist: Exec = async (params, config) => connectorFetch(config, { path: `/v1/playlists/${params.playlistId}`, baseUrl: "https://api.spotify.com" });

// ── Website (Webflow) ────────────────────────────────────────────

const webflow_list_sites: Exec = async (_params, config) => connectorFetch(config, { path: "/v2/sites", baseUrl: "https://api.webflow.com" });
const webflow_list_items: Exec = async (params, config) => {
  const err = required(params, "collectionId");
  if (err) return { success: false, error: err, summary: err };
  return connectorFetch(config, { path: `/v2/collections/${params.collectionId}/items`, baseUrl: "https://api.webflow.com" });
};

// ── Export: tool ID → execute function ───────────────────────────

export const IMPLEMENTATIONS: Record<string, Record<string, Exec>> = {
  gmail: { send_email: gmail_send_email, search_email: gmail_search_email, read_email: gmail_read_email, list_labels: gmail_list_labels },
  slack: { send_message: slack_send_message, list_channels: slack_list_channels, read_thread: slack_read_thread, search_messages: slack_search_messages },
  microsoft_teams: { send_message: teams_send_message, list_teams: teams_list_teams },
  discord: { send_message: discord_send_message, list_channels: discord_list_channels },
  twilio: { send_sms: twilio_send_sms, make_call: twilio_make_call },
  jira: { create_issue: jira_create_issue, search_issues: jira_search_issues, update_issue: jira_update_issue, list_projects: jira_list_projects },
  linear: { create_issue: linear_create_issue, search_issues: linear_search_issues, list_projects: linear_list_projects },
  asana: { create_task: asana_create_task, list_tasks: asana_list_tasks },
  trello: { create_card: trello_create_card, list_boards: trello_list_boards },
  monday: { create_item: monday_create_item, list_boards: monday_list_boards },
  github: { create_issue: github_create_issue, create_pr: github_create_pr, list_repos: github_list_repos, search_code: github_search_code },
  confluence: { create_page: confluence_create_page, search_pages: confluence_search_pages },
  salesforce: { create_lead: salesforce_create_lead, search_contacts: salesforce_search_contacts, create_opportunity: salesforce_create_opportunity },
  hubspot: { create_contact: hubspot_create_contact, search_contacts: hubspot_search_contacts, create_deal: hubspot_create_deal },
  google_analytics: { get_report: ga_get_report, get_realtime: ga_get_realtime },
  google_ads: { list_campaigns: gads_list_campaigns, get_report: gads_get_report },
  bigquery: { run_query: bq_run_query, list_datasets: bq_list_datasets },
  postgresql: { run_query: pg_run_query, list_tables: pg_list_tables },
  supabase: { query: supabase_query, insert: supabase_insert },
  notion: { create_page: notion_create_page, search: notion_search, query_database: notion_query_database },
  airtable: { list_records: airtable_list_records, create_record: airtable_create_record },
  google_calendar: { create_event: gcal_create_event, list_events: gcal_list_events },
  calendly: { list_events: calendly_list_events, get_availability: calendly_get_availability },
  google_drive: { search_files: gdrive_search, upload_file: gdrive_upload, download_file: gdrive_download },
  dropbox: { list_files: dropbox_list, upload_file: dropbox_upload },
  box: { search_files: box_search, upload_file: box_upload },
  stripe: { create_invoice: stripe_create_invoice, list_customers: stripe_list_customers, get_balance: stripe_get_balance },
  shopify: { list_products: shopify_list_products, list_orders: shopify_list_orders, create_product: shopify_create_product },
  quickbooks: { create_invoice: qb_create_invoice, list_customers: qb_list_customers },
  xero: { create_invoice: xero_create_invoice, list_contacts: xero_list_contacts },
  mailchimp: { send_campaign: mailchimp_send_campaign, list_audiences: mailchimp_list_audiences },
  twitter: { post_tweet: twitter_post_tweet, search_tweets: twitter_search_tweets },
  linkedin: { create_post: linkedin_create_post, get_profile: linkedin_get_profile },
  brave_search: { web_search: brave_web_search, news_search: brave_news_search },
  zendesk: { create_ticket: zendesk_create_ticket, search_tickets: zendesk_search_tickets },
  intercom: { send_message: intercom_send_message, list_conversations: intercom_list_conversations },
  figma: { get_file: figma_get_file, list_components: figma_list_components },
  zapier_webhooks: { trigger: webhook_trigger },
  make: { trigger: webhook_trigger },
  aws: { s3_list: aws_s3_list, lambda_invoke: aws_lambda_invoke },
  vercel: { list_deployments: vercel_list_deployments, trigger_deploy: vercel_trigger_deploy },
  cloudflare: { list_zones: cf_list_zones, purge_cache: cf_purge_cache },
  openai: { chat_completion: openai_chat, create_image: openai_image },
  pinecone: { upsert: pinecone_upsert, query: pinecone_query },
  sap: { read_entity: sap_read_entity, create_entity: sap_create_entity },
  docusign: { send_envelope: docusign_send_envelope, list_envelopes: docusign_list_envelopes },
  youtube: { search_videos: youtube_search, get_video: youtube_get_video },
  spotify: { search_tracks: spotify_search, get_playlist: spotify_get_playlist },
  webflow: { list_sites: webflow_list_sites, list_items: webflow_list_items },
};