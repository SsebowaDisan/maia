import {
  BaseEdge,
  type EdgeProps,
  MarkerType,
} from "@xyflow/react";
import { MindNodeCard } from "./MindNodeCard";
import { NODE_HALF_H, NODE_HALF_W } from "./viewerHelpers";
import type { MindmapMapType, MindmapPayload } from "./types";

function CurvedMindEdge({ id, data, style }: EdgeProps) {
  const edge = (data ?? {}) as {
    sx?: number;
    sy?: number;
    tx?: number;
    ty?: number;
    sourceDepth?: number;
    targetDepth?: number;
  };
  const srcX = Number(edge.sx ?? 0);
  const srcY = Number(edge.sy ?? 0);
  const tgtX = Number(edge.tx ?? 0);
  const tgtY = Number(edge.ty ?? 0);
  const sourceDepth = Number(edge.sourceDepth ?? 0);
  const targetDepth = Number(edge.targetDepth ?? sourceDepth + 1);

  // srcX/srcY and tgtX/tgtY are already node centers (from getCenter).
  // Half-widths must match getCenter so lines start at the node's right edge.
  const sourceHalfW = sourceDepth <= 0 ? 200 : sourceDepth === 1 ? 160 : 140;
  const targetHalfW = targetDepth <= 0 ? 200 : targetDepth === 1 ? 160 : 140;
  // Note: the card CSS widths are 400/320/280 → halves are 200/160/140.
  const startX = srcX + sourceHalfW;
  const startY = srcY;
  const endX = tgtX - targetHalfW;
  const endY = tgtY;
  const span = Math.max(140, endX - startX);
  const outbound = sourceDepth <= 0 ? Math.min(260, span * 0.42) : Math.min(180, span * 0.34);
  const inbound = targetDepth <= 1 ? Math.min(210, span * 0.4) : Math.min(150, span * 0.3);
  const c1X = startX + outbound;
  const c1Y = startY;
  const c2X = endX - inbound;
  const c2Y = endY;
  return (
    <BaseEdge
      id={id}
      path={`M ${startX} ${startY} C ${c1X} ${c1Y} ${c2X} ${c2Y} ${endX} ${endY}`}
      style={style}
    />
  );
}

function ReasoningCurvedEdge({ id, data, style, markerEnd }: EdgeProps) {
  const edge = (data ?? {}) as { sx?: number; sy?: number; tx?: number; ty?: number };
  const srcX = Number(edge.sx ?? 0);
  const srcY = Number(edge.sy ?? 0);
  const tgtX = Number(edge.tx ?? 0);
  const tgtY = Number(edge.ty ?? 0);
  const startX = srcX + NODE_HALF_W;
  const startY = srcY;
  const endX = tgtX - NODE_HALF_W;
  const endY = tgtY;
  const midX = (startX + endX) / 2;
  const midY = (startY + endY) / 2;
  const deltaX = endX - startX;
  const deltaY = endY - startY;
  const length = Math.sqrt(deltaX * deltaX + deltaY * deltaY) || 1;
  const normalX = -(deltaY / length);
  const normalY = deltaX / length;
  const bow = Math.min(38, length * 0.16);
  const cpx = midX + normalX * bow;
  const cpy = midY + normalY * bow;
  return (
    <BaseEdge
      id={id}
      path={`M ${startX} ${startY} Q ${cpx} ${cpy} ${endX} ${endY}`}
      style={style}
      markerEnd={markerEnd}
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
  const windowed = text.slice(0, 41);
  const sentenceCut = Math.max(windowed.lastIndexOf("."), windowed.lastIndexOf("!"), windowed.lastIndexOf("?"));
  if (sentenceCut >= 24) {
    return windowed.slice(0, sentenceCut + 1).trim();
  }
  const wordCut = windowed.lastIndexOf(" ");
  if (wordCut >= 20) {
    return windowed.slice(0, wordCut).trim();
  }
  return windowed.slice(0, 40).trim();
}

function payloadSupportsMapType(payload: MindmapPayload | null, mapType: MindmapMapType): boolean {
  if (!payload) {
    return false;
  }
  if (Array.isArray(payload.available_map_types)) {
    const available = payload.available_map_types.map((entry) => normalizeMapType(entry));
    if (available.includes(mapType)) {
      return true;
    }
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
const edgeTypes = { mindCurve: CurvedMindEdge, reasoningCurve: ReasoningCurvedEdge };

export {
  compactNodeValue,
  detectDefaultMapType,
  edgeTypes,
  MarkerType,
  nodeTypes,
  payloadSupportsMapType,
};
