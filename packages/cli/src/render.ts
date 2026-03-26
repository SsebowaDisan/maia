/**
 * Terminal renderer — formats ACP events for CLI output.
 */

const RESET = "\x1b[0m";
const BOLD = "\x1b[1m";
const DIM = "\x1b[2m";
const RED = "\x1b[31m";
const GREEN = "\x1b[32m";
const YELLOW = "\x1b[33m";
const BLUE = "\x1b[34m";
const MAGENTA = "\x1b[35m";
const CYAN = "\x1b[36m";
const GRAY = "\x1b[90m";

const AGENT_COLORS = [MAGENTA, BLUE, GREEN, YELLOW, CYAN, RED];

export function agentColor(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h += id.charCodeAt(i);
  return AGENT_COLORS[Math.abs(h) % AGENT_COLORS.length];
}

const INTENT_COLORS: Record<string, string> = {
  propose: BLUE, challenge: RED, clarify: YELLOW, review: MAGENTA,
  handoff: GREEN, summarize: GRAY, agree: GREEN, escalate: RED,
};

const ACTIVITY_ICONS: Record<string, string> = {
  thinking: "\u2728", searching: "\uD83D\uDD0D", reading: "\uD83D\uDCD6",
  writing: "\u270F\uFE0F", browsing: "\uD83C\uDF10", coding: "\uD83D\uDCBB",
  analyzing: "\uD83D\uDCCA", tool_calling: "\uD83D\uDD27", waiting: "\u23F3",
  reviewing: "\uD83D\uDD0E", error: "\u26A0\uFE0F",
};

function shortId(id: string): string {
  return id.replace("agent://", "");
}

export function renderEvent(event: Record<string, any>): string {
  const type = event.event_type;
  const payload = event.payload || {};
  const ts = (event.timestamp || "").slice(11, 19);

  if (type === "message") {
    const from = shortId(payload.from || event.agent_id || "?");
    const intent = payload.intent || "";
    const content = payload.content || "";
    const thinking = payload.thinking || "";
    const color = agentColor(payload.from || "");
    const ic = INTENT_COLORS[intent] || GRAY;

    let out = `${color}${BOLD}${from}${RESET} ${ic}${BOLD}[${intent}]${RESET} ${DIM}${ts}${RESET}\n`;
    if (thinking) out += `  ${DIM}${YELLOW}> ${thinking}${RESET}\n`;
    out += `  ${content}`;
    return out;
  }

  if (type === "handoff") {
    const from = shortId(payload.from || "?");
    const to = shortId(payload.to || "?");
    const desc = (payload.task?.description || "").slice(0, 120);
    return `${agentColor(payload.from || "")}${BOLD}${from}${RESET} ${DIM}-->${RESET} ${agentColor(payload.to || "")}${BOLD}${to}${RESET} ${GREEN}${BOLD}[handoff]${RESET} ${DIM}${ts}${RESET}\n  ${desc}`;
  }

  if (type === "review") {
    const reviewer = shortId(payload.reviewer || "?");
    const author = shortId(payload.author || "?");
    const verdict = payload.verdict || "";
    const vc: Record<string, string> = { approve: GREEN, revise: YELLOW, reject: RED, escalate: RED };
    const feedback = (payload.feedback || "").slice(0, 200);
    let out = `${agentColor(payload.reviewer || "")}${BOLD}${reviewer}${RESET} reviews ${agentColor(payload.author || "")}${BOLD}${author}${RESET} ${(vc[verdict] || GRAY)}${BOLD}[${verdict}]${RESET} ${DIM}${ts}${RESET}`;
    if (feedback) out += `\n  ${feedback}`;
    return out;
  }

  if (type === "event") {
    const agentId = payload.agent_id || event.agent_id || "?";
    const act = payload.activity || "";
    const detail = (payload.detail || "").slice(0, 100);
    const icon = ACTIVITY_ICONS[act] || "\u2022";
    let out = `  ${icon} ${DIM}${shortId(agentId)}${RESET} ${act}`;
    if (detail) out += ` ${DIM}-- ${detail}${RESET}`;
    out += ` ${DIM}${ts}${RESET}`;
    return out;
  }

  if (type === "capabilities") {
    const name = payload.name || shortId(payload.agent_id || "?");
    const role = payload.role || "";
    return `  ${GREEN}+${RESET} ${agentColor(payload.agent_id || "")}${BOLD}${name}${RESET}${role ? ` ${DIM}(${role})${RESET}` : ""} joined`;
  }

  return `  ${DIM}[${type}] ${JSON.stringify(payload).slice(0, 100)}${RESET}`;
}

export const LOGO = `${MAGENTA}${BOLD}
  \u2554\u2566\u2557\u2554\u2550\u2557\u2566\u2554\u2550\u2557
  \u2551\u2551\u2551\u2560\u2550\u2563\u2551\u2560\u2550\u2563
  \u2569 \u2569\u2569 \u2569\u2569\u2569 \u2569${RESET} ${DIM}CLI v0.1.0${RESET}
`;

export { RESET, BOLD, DIM, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, GRAY };
