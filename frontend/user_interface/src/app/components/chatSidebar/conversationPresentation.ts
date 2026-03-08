import {
  BarChart3,
  BookOpen,
  Briefcase,
  Building2,
  CalendarDays,
  Code2,
  FileText,
  Globe,
  Lightbulb,
  ListChecks,
  Mail,
  MessageCircle,
  Rocket,
  Search,
  Shield,
  Wrench,
} from "lucide-react";

const LETTER_OR_NUMBER_RE = /^[\p{L}\p{N}]$/u;
const EXTENDED_PICTOGRAPHIC_RE = /^\p{Extended_Pictographic}$/u;

export function startsWithIcon(text: string) {
  const chars = Array.from(text);
  if (!chars.length) {
    return false;
  }
  const first = chars[0] || "";
  if (!first || LETTER_OR_NUMBER_RE.test(first)) {
    return false;
  }
  const codePoint = first.codePointAt(0) || 0;
  return EXTENDED_PICTOGRAPHIC_RE.test(first) || codePoint >= 0x2600;
}

export function stripChatIcon(name: string) {
  const cleaned = String(name || "").trim();
  const chars = Array.from(cleaned);
  if (chars.length >= 2 && startsWithIcon(cleaned) && chars[1] === " ") {
    return chars.slice(2).join("").trim();
  }
  return cleaned;
}

export function displayConversationName(name: string) {
  const cleaned = stripChatIcon(String(name || "").trim());
  if (!cleaned) {
    return "New chat";
  }
  return cleaned;
}

export const CHAT_ICON_COMPONENTS = {
  "message-circle": MessageCircle,
  briefcase: Briefcase,
  "bar-chart-3": BarChart3,
  globe: Globe,
  "file-text": FileText,
  search: Search,
  lightbulb: Lightbulb,
  calendar: CalendarDays,
  mail: Mail,
  "building-2": Building2,
  shield: Shield,
  rocket: Rocket,
  wrench: Wrench,
  "code-2": Code2,
  "book-open": BookOpen,
  "list-checks": ListChecks,
} as const;

export type ChatIconKey = keyof typeof CHAT_ICON_COMPONENTS;

export function normalizeChatIconKey(value: unknown): ChatIconKey {
  const text = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/_/g, "-")
    .replace(/\s+/g, "-");
  const aliases: Record<string, ChatIconKey> = {
    message: "message-circle",
    chat: "message-circle",
    company: "building-2",
    business: "briefcase",
    chart: "bar-chart-3",
    analytics: "bar-chart-3",
    file: "file-text",
    document: "file-text",
    idea: "lightbulb",
    email: "mail",
    code: "code-2",
    checklist: "list-checks",
    list: "list-checks",
  };
  if (text in CHAT_ICON_COMPONENTS) {
    return text as ChatIconKey;
  }
  if (text in aliases) {
    return aliases[text];
  }
  return "message-circle";
}

export type ConversationDayGroup = "Today" | "Yesterday" | "Earlier";

function parseDate(value: string): Date | null {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

export function conversationDayGroup(dateUpdated: string, now: Date): ConversationDayGroup {
  const parsed = parseDate(dateUpdated);
  if (!parsed) {
    return "Earlier";
  }
  const today = startOfDay(now).getTime();
  const target = startOfDay(parsed).getTime();
  const days = Math.floor((today - target) / 86_400_000);
  if (days <= 0) {
    return "Today";
  }
  if (days === 1) {
    return "Yesterday";
  }
  return "Earlier";
}

export function conversationMetaLabel(dateUpdated: string, now: Date): string {
  const parsed = parseDate(dateUpdated);
  if (!parsed) {
    return "Updated recently";
  }
  const group = conversationDayGroup(dateUpdated, now);
  if (group === "Today" || group === "Yesterday") {
    return parsed.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }
  return parsed.toLocaleDateString([], { month: "short", day: "numeric" });
}
