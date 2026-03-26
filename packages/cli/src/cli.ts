#!/usr/bin/env node
/**
 * Maia CLI (Node.js) — stream, replay, and validate ACP events.
 *
 * Commands:
 *   maia stream <url>     Connect to a live ACP stream
 *   maia replay <file>    Replay a recorded JSONL file
 *   maia validate <file>  Validate ACP events
 *   maia info             Show version and environment info
 */

import * as fs from "fs";
import { renderEvent, LOGO, RESET, RED, GREEN, YELLOW, CYAN, DIM, BOLD } from "./render";

// ── Commands ─────────────────────────────────────────────────────────────────

async function cmdStream(url: string, raw: boolean, savePath?: string) {
  console.log(LOGO);
  console.log(`  Connecting to ${CYAN}${url}${RESET}`);
  console.log(`  ${DIM}Press Ctrl+C to stop${RESET}\n`);

  let saveStream: fs.WriteStream | null = null;
  if (savePath) {
    saveStream = fs.createWriteStream(savePath, { flags: "a" });
    console.log(`  Saving to ${GREEN}${savePath}${RESET}\n`);
  }

  let count = 0;
  const response = await fetch(url, { headers: { Accept: "text/event-stream" } });
  if (!response.ok || !response.body) {
    console.error(`${RED}Connection failed: ${response.status}${RESET}`);
    process.exit(1);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const t = line.trim();
      if (!t || !t.startsWith("data: ")) continue;
      const d = t.slice(6);
      if (d === "[DONE]") break;
      try {
        const event = JSON.parse(d);
        count++;
        console.log(raw ? JSON.stringify(event) : renderEvent(event));
        if (!raw) console.log();
        saveStream?.write(JSON.stringify(event) + "\n");
      } catch { /* skip */ }
    }
  }

  saveStream?.end();
  console.log(`\n  ${DIM}${count} events received.${RESET}`);
}

function cmdReplay(filePath: string, speed: number, raw: boolean) {
  console.log(LOGO);
  console.log(`  Replaying ${CYAN}${filePath}${RESET} at ${speed}x\n`);

  if (!fs.existsSync(filePath)) {
    console.error(`${RED}File not found: ${filePath}${RESET}`);
    process.exit(1);
  }

  const events: Record<string, any>[] = [];
  for (const line of fs.readFileSync(filePath, "utf-8").split("\n")) {
    if (line.trim()) { try { events.push(JSON.parse(line)); } catch { /* skip */ } }
  }
  console.log(`  ${DIM}${events.length} events loaded${RESET}\n`);

  let i = 0;
  function next() {
    if (i >= events.length) {
      console.log(`\n  ${DIM}Replay complete.${RESET}`);
      return;
    }
    console.log(raw ? JSON.stringify(events[i]) : renderEvent(events[i]));
    if (!raw) console.log();
    i++;
    let delay = 300;
    if (i < events.length) {
      try {
        const p = new Date(events[i - 1].timestamp).getTime();
        const c = new Date(events[i].timestamp).getTime();
        delay = Math.max(50, Math.min(3000, c - p));
      } catch { /* default */ }
    }
    setTimeout(next, delay / speed);
  }
  next();
}

function cmdValidate(filePath: string) {
  console.log(LOGO);
  console.log(`  Validating ${CYAN}${filePath}${RESET}\n`);

  if (!fs.existsSync(filePath)) {
    console.error(`${RED}File not found: ${filePath}${RESET}`);
    process.exit(1);
  }

  const req = new Set(["acp_version", "run_id", "agent_id", "event_type", "timestamp", "payload"]);
  const types = new Set(["message", "handoff", "review", "artifact", "event", "capabilities"]);
  let valid = 0, invalid = 0, warnings = 0;

  for (const [i, line] of fs.readFileSync(filePath, "utf-8").split("\n").entries()) {
    if (!line.trim()) continue;
    let ev: Record<string, any>;
    try { ev = JSON.parse(line); } catch { console.log(`  ${RED}Line ${i + 1}: Invalid JSON${RESET}`); invalid++; continue; }
    const missing = [...req].filter((k) => !(k in ev));
    if (missing.length) { console.log(`  ${RED}Line ${i + 1}: Missing: ${missing.join(", ")}${RESET}`); invalid++; continue; }
    if (ev.acp_version !== "1.0") { console.log(`  ${YELLOW}Line ${i + 1}: Version: ${ev.acp_version}${RESET}`); warnings++; }
    if (!types.has(ev.event_type)) { console.log(`  ${YELLOW}Line ${i + 1}: Type: ${ev.event_type}${RESET}`); warnings++; }
    if (!String(ev.agent_id || "").startsWith("agent://")) { console.log(`  ${YELLOW}Line ${i + 1}: agent_id format${RESET}`); warnings++; }
    valid++;
  }

  console.log(`\n  ${GREEN}${valid}${RESET} valid, ${invalid ? `${RED}${invalid}${RESET}` : `${DIM}0${RESET}`} invalid, ${warnings ? `${YELLOW}${warnings}${RESET}` : `${DIM}0${RESET}`} warnings`);
  if (invalid > 0) process.exit(1);
}

function cmdInfo() {
  console.log(LOGO);
  console.log(`  ${BOLD}Versions${RESET}`);
  console.log(`    CLI:  0.1.0`);
  console.log(`    Node: ${process.version}`);
  console.log(`\n  ${BOLD}Links${RESET}`);
  console.log(`    Docs:   https://docs.maia.ai`);
  console.log(`    GitHub: https://github.com/maia-ai/maia-sdk`);
}

// ── Dispatch ─────────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
const cmd = args[0];

if (!cmd || cmd === "-h" || cmd === "--help") {
  console.log(LOGO);
  console.log("  Usage: maia <command> [options]\n");
  console.log("    stream <url>       Live ACP stream");
  console.log("    replay <file>      Replay JSONL");
  console.log("    validate <file>    Validate events");
  console.log("    info               Version info");
  console.log("\n    --raw    Raw JSON   --speed <n>  Playback speed   --save <f>  Save stream");
} else if (cmd === "stream") {
  const url = args[1];
  if (!url) { console.error(`${RED}Usage: maia stream <url>${RESET}`); process.exit(1); }
  cmdStream(url, args.includes("--raw"), args[args.indexOf("--save") + 1]).catch((e) => { console.error(`${RED}${e}${RESET}`); process.exit(1); });
} else if (cmd === "replay") {
  if (!args[1]) { console.error(`${RED}Usage: maia replay <file>${RESET}`); process.exit(1); }
  const si = args.indexOf("--speed");
  cmdReplay(args[1], si >= 0 ? parseFloat(args[si + 1]) || 1 : 1, args.includes("--raw"));
} else if (cmd === "validate") {
  if (!args[1]) { console.error(`${RED}Usage: maia validate <file>${RESET}`); process.exit(1); }
  cmdValidate(args[1]);
} else if (cmd === "info") {
  cmdInfo();
} else {
  console.error(`${RED}Unknown command: ${cmd}${RESET}`);
  process.exit(1);
}
