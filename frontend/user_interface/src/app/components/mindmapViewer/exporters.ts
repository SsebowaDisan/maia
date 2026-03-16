import type { MindmapNode, MindmapPayload } from "./types";

export function downloadMindmapJson(payload: MindmapPayload, activeMapType: string) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `mindmap-${activeMapType}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function downloadMindmapMarkdown(params: {
  payload: MindmapPayload;
  activeMapType: string;
  nodeById: Map<string, MindmapNode>;
  childrenByParent: Map<string, string[]>;
  rootId: string;
}) {
  const { payload, activeMapType, nodeById, childrenByParent, rootId } = params;
  if (!payload.nodes?.length) {
    return;
  }
  const lines: string[] = [`# ${payload.title || "Knowledge Map"}\n`];
  const buildLines = (nodeId: string, depth: number) => {
    const node = nodeById.get(nodeId);
    if (!node) {
      return;
    }
    const indent = "  ".repeat(Math.max(0, depth - 1));
    const prefix = depth === 0 ? "" : `${indent}- `;
    lines.push(`${prefix}**${node.title || node.id}**${node.text ? `: ${node.text}` : ""}`);
    for (const childId of childrenByParent.get(nodeId) || []) {
      buildLines(childId, depth + 1);
    }
  };
  if (rootId) {
    buildLines(rootId, 0);
  }
  const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `mindmap-${activeMapType}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function downloadMindmapMarkdownText(markdown: string, activeMapType: string) {
  if (!String(markdown || "").trim()) {
    return;
  }
  const blob = new Blob([markdown], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `mindmap-${activeMapType}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}
