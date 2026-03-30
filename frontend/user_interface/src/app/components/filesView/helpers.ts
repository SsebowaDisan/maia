import type { UploadResponse } from "../../../api/client";
import type { FileKind } from "./types";

const UNGROUPED_FILTER = "__ungrouped__";

function inferFileKind(name: string): FileKind {
  const ext = name.toLowerCase().split(".").pop() || "";
  if (ext === "pdf") return "pdf";
  if (["doc", "docx", "xls", "xlsx", "ppt", "pptx"].includes(ext)) return "office";
  if (["txt", "md", "csv", "json", "xml", "html", "mhtml"].includes(ext)) return "text";
  if (["png", "jpg", "jpeg", "gif", "bmp", "tif", "tiff", "svg", "webp"].includes(ext)) {
    return "image";
  }
  return "other";
}

function formatSize(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let idx = 0;
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024;
    idx += 1;
  }
  const rounded = size >= 100 ? Math.round(size) : Math.round(size * 10) / 10;
  return `${rounded} ${units[idx]}`;
}

function formatDate(value: string) {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
}

function tokenNumber(note: Record<string, unknown>) {
  for (const key of ["token", "tokens", "n_tokens", "num_tokens", "token_count"]) {
    const raw = note[key];
    if (typeof raw === "number" && Number.isFinite(raw)) return raw;
    if (typeof raw === "string") {
      const parsed = Number(raw);
      if (Number.isFinite(parsed)) return parsed;
    }
  }
  return 0;
}

function tokenText(note: Record<string, unknown>) {
  const value = tokenNumber(note);
  return value > 0 ? String(Math.round(value)) : "-";
}

function loaderText(note: Record<string, unknown>) {
  for (const key of ["loader", "reader", "doc_loader", "source_type", "type"]) {
    const raw = note[key];
    if (typeof raw === "string" && raw.trim()) return raw;
  }
  return "-";
}

function readinessLabel(note: Record<string, unknown>) {
  const ragReady = Boolean(note["rag_ready"]);
  const citationReady = Boolean(note["citation_ready"]);
  if (ragReady && !citationReady) {
    return "Ready for RAG · Citations refining";
  }
  if (ragReady) {
    return "Ready for RAG";
  }
  return "Processing";
}

function readinessTone(note: Record<string, unknown>) {
  const ragReady = Boolean(note["rag_ready"]);
  const citationReady = Boolean(note["citation_ready"]);
  if (ragReady && !citationReady) {
    return "warning";
  }
  if (ragReady) {
    return "ready";
  }
  return "neutral";
}

function extractSuccessfulFileIds(response: UploadResponse) {
  const byItem = response.items
    .filter((item) => item.status === "success" && item.file_id)
    .map((item) => item.file_id as string);
  return Array.from(new Set([...response.file_ids, ...byItem]));
}

export {
  extractSuccessfulFileIds,
  formatDate,
  formatSize,
  inferFileKind,
  loaderText,
  readinessLabel,
  readinessTone,
  tokenNumber,
  tokenText,
  UNGROUPED_FILTER,
};
