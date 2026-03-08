import {
  BaseEdge,
  type EdgeProps,
} from "@xyflow/react";
import { MindNodeCard } from "./MindNodeCard";
import { NODE_HALF_H, NODE_HALF_W } from "./viewerHelpers";
import type { MindmapMapType, MindmapPayload } from "./types";

function trimEdge(
  cx: number,
  cy: number,
  ox: number,
  oy: number,
  hw: number,
  hh: number,
): { x: number; y: number } {
  const dx = ox - cx;
  const dy = oy - cy;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len < 1) {
    return { x: cx, y: cy };
  }
  const abscos = Math.abs(dx / len);
  const abssin = Math.abs(dy / len);
  const d = abscos > 0 && abssin > 0 ? Math.min(hw / abscos, hh / abssin) : abscos > 0 ? hw : hh;
  return { x: cx + (dx / len) * d, y: cy + (dy / len) * d };
}

function CurvedMindEdge({ id, data, style }: EdgeProps) {
  const edge = (data ?? {}) as { sx?: number; sy?: number; tx?: number; ty?: number };
  const srcX = Number(edge.sx ?? 0);
  const srcY = Number(edge.sy ?? 0);
  const tgtX = Number(edge.tx ?? 0);
  const tgtY = Number(edge.ty ?? 0);
  const isRoot = srcX * srcX + srcY * srcY < 25;
  const start = trimEdge(srcX, srcY, tgtX, tgtY, isRoot ? 92 : NODE_HALF_W, isRoot ? 22 : NODE_HALF_H);
  const end = trimEdge(tgtX, tgtY, srcX, srcY, NODE_HALF_W, NODE_HALF_H);
  const mx = (start.x + end.x) / 2;
  const my = (start.y + end.y) / 2;
  const midLen = Math.sqrt(mx * mx + my * my) || 1;
  const edgeLen = Math.sqrt((end.x - start.x) ** 2 + (end.y - start.y) ** 2);
  const bow = Math.min(32, edgeLen * 0.12);
  const cpx = mx - (mx / midLen) * bow;
  const cpy = my - (my / midLen) * bow;
  return (
    <BaseEdge
      id={id}
      path={`M ${start.x} ${start.y} Q ${cpx} ${cpy} ${end.x} ${end.y}`}
      style={style}
    />
  );
}

function normalizeMapType(raw: unknown): MindmapMapType {
  const value = String(raw || "").trim().toLowerCase();
  if (value === "context_mindmap") {
    return "context_mindmap";
  }
  if (value === "work_graph") {
    return "work_graph";
  }
  if (value === "evidence") {
    return "evidence";
  }
  return "structure";
}

function detectDefaultMapType(payload: MindmapPayload | null): MindmapMapType {
  if (!payload) {
    return "structure";
  }
  const direct = normalizeMapType(payload.map_type);
  if (direct === "context_mindmap" || String(payload.kind || "").trim().toLowerCase() === "context_mindmap") {
    return "context_mindmap";
  }
  if (direct === "work_graph" || String(payload.kind || "").trim().toLowerCase() === "work_graph") {
    return "work_graph";
  }
  const variants = payload.variants;
  if (variants && typeof variants === "object" && Object.prototype.hasOwnProperty.call(variants, "context_mindmap")) {
    return "context_mindmap";
  }
  if (variants && typeof variants === "object" && Object.prototype.hasOwnProperty.call(variants, "work_graph")) {
    return "work_graph";
  }
  return direct;
}

function compactNodeValue(raw: unknown): string {
  const text = String(raw || "").trim();
  if (!text) {
    return "";
  }
  if (text.length <= 40) {
    return text;
  }
  return `${text.slice(0, 37).trimEnd()}...`;
}

function payloadSupportsMapType(payload: MindmapPayload | null, mapType: MindmapMapType): boolean {
  if (!payload) {
    return false;
  }
  if (normalizeMapType(payload.map_type) === mapType) {
    return true;
  }
  const variants = payload.variants;
  if (!variants || typeof variants !== "object") {
    return false;
  }
  return Object.prototype.hasOwnProperty.call(variants, mapType);
}

const nodeTypes = { mind: MindNodeCard };
const edgeTypes = { mindCurve: CurvedMindEdge };

export {
  compactNodeValue,
  detectDefaultMapType,
  edgeTypes,
  nodeTypes,
  payloadSupportsMapType,
};
