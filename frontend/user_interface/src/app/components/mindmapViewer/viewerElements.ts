import {
  MarkerType,
  Position,
  type Edge,
  type Node,
} from "@xyflow/react";

import type { MindNodeData } from "./utils";
import type { MindmapMapType, MindmapNode } from "./types";
import { NODE_HALF_H, NODE_HALF_W, looksNoisyTitle } from "./viewerHelpers";
import { compactNodeValue } from "./viewerGraph";
import { isMachineLikeTitle, resolveProfessionalNodeTitle } from "./titleSanitizer";

const BRANCH_EDGE_COLORS = ["#b6c1f5", "#b8cdef", "#c1c9f6", "#bcd9ef", "#c6cdf7", "#b6d2ee"];

type BuildFlowNodesParams = {
  visibleNodes: MindmapNode[];
  activeMapType: MindmapMapType;
  allNodeIds: Set<string>;
  branchColorIndexMap: Map<string, number>;
  childrenByParent: Map<string, string[]>;
  collapsedNodeIds: string[];
  depthMap: Record<string, number>;
  layout: Record<string, { x: number; y: number }>;
  layoutMode: "balanced" | "horizontal";
  maxDepth: number;
  nodeById: Map<string, MindmapNode>;
  rootId: string;
  selectedNodeId: string | null;
  onToggleNode: (nodeId: string) => void;
  isInteractive: boolean;
};

export function buildFlowNodes({
  visibleNodes,
  activeMapType,
  allNodeIds,
  branchColorIndexMap,
  childrenByParent,
  collapsedNodeIds,
  depthMap,
  layout,
  layoutMode,
  maxDepth,
  nodeById,
  rootId,
  selectedNodeId,
  onToggleNode,
  isInteractive,
}: BuildFlowNodesParams): Array<Node<MindNodeData>> {
  const sourceIndexById = new Map<string, number>();
  let sourceCounter = 0;
  visibleNodes.forEach((node) => {
    const nodeType = String(node.node_type || node.type || "").trim().toLowerCase();
    if (nodeType === "source" || nodeType === "web_source") {
      sourceCounter += 1;
      sourceIndexById.set(node.id, sourceCounter);
    }
  });

  return visibleNodes.map((node, index): Node<MindNodeData> => {
    const depth = depthMap[node.id] ?? 0;
    const hasChildren = (childrenByParent.get(node.id) || []).some(
      (child) => allNodeIds.has(child) && (depthMap[child] ?? Number.MAX_SAFE_INTEGER) <= maxDepth,
    );
    const nodeTitle = String(node.title || node.id || "").trim();
    let displayTitle = nodeTitle || "";
    if (looksNoisyTitle(nodeTitle) || isMachineLikeTitle(nodeTitle)) {
      const promotedTitle = (childrenByParent.get(node.id) || [])
        .map((childId) => {
          const childNode = nodeById.get(childId);
          if (!childNode) {
            return "";
          }
          return resolveProfessionalNodeTitle(childNode, {
            sourceIndex: sourceIndexById.get(childId),
          });
        })
        .find((candidate) => candidate && !looksNoisyTitle(candidate) && !isMachineLikeTitle(candidate));
      if (promotedTitle) {
        displayTitle = promotedTitle;
      }
    }
    if (!displayTitle || looksNoisyTitle(displayTitle) || isMachineLikeTitle(displayTitle)) {
      displayTitle = resolveProfessionalNodeTitle(node, {
        sourceIndex: sourceIndexById.get(node.id),
      });
    }
    return {
      id: node.id,
      type: "mind",
      draggable: false,
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      position: (() => {
        const pos = layout[node.id];
        if (!pos) {
          return { x: depth * 200, y: index * 54 };
        }
        if (layoutMode === "horizontal") {
          return pos;
        }
        const halfWidth = node.id === rootId ? 92 : NODE_HALF_W;
        const halfHeight = node.id === rootId ? 22 : NODE_HALF_H;
        return { x: pos.x - halfWidth, y: pos.y - halfHeight };
      })(),
      data: {
        title: displayTitle,
        subtitle:
          activeMapType === "work_graph"
            ? [
                compactNodeValue((node as Record<string, unknown>).status),
                compactNodeValue((node as Record<string, unknown>).tool_id),
              ]
                .filter((value) => value.length > 0)
                .join(" / ") || undefined
            : undefined,
        hasChildren,
        collapsed: collapsedNodeIds.includes(node.id),
        nodeType: String(node.type || node.node_type || ""),
        isRoot: node.id === rootId,
        isInteractive,
        depth,
        isSelected: selectedNodeId === node.id,
        branchColorIndex: branchColorIndexMap.get(node.id) ?? -1,
        onToggle: onToggleNode,
      },
    };
  });
}

type BuildFlowEdgesParams = {
  hierarchyEdges: Array<{ id?: string; source: string; target: string }>;
  visibleIds: Set<string>;
  depthMap: Record<string, number>;
  branchColorIndexMap: Map<string, number>;
  selectedNodeId: string | null;
  getCenter: (nodeId: string) => { x: number; y: number };
};

export function buildFlowEdges({
  hierarchyEdges,
  visibleIds,
  depthMap,
  branchColorIndexMap,
  selectedNodeId,
  getCenter,
}: BuildFlowEdgesParams): Edge[] {
  return hierarchyEdges
    .filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target))
    .map((edge): Edge => {
      const sourceDepth = depthMap[edge.source] ?? 0;
      const colorIndex = branchColorIndexMap.get(edge.target) ?? branchColorIndexMap.get(edge.source) ?? -1;
      const branchColor = colorIndex >= 0 ? BRANCH_EDGE_COLORS[colorIndex % BRANCH_EDGE_COLORS.length] : "#A3A3A3";
      const isHighlighted = !selectedNodeId || edge.source === selectedNodeId || edge.target === selectedNodeId;
      const sourceCenter = getCenter(edge.source);
      const targetCenter = getCenter(edge.target);
      return {
        id: edge.id || `${edge.source}->${edge.target}`,
        source: edge.source,
        target: edge.target,
        type: "mindCurve",
        data: {
          sx: sourceCenter.x,
          sy: sourceCenter.y,
          tx: targetCenter.x,
          ty: targetCenter.y,
          sourceDepth,
          targetDepth: depthMap[edge.target] ?? sourceDepth + 1,
        },
        style: {
          stroke: branchColor,
          strokeWidth: sourceDepth === 0 ? 2.4 : sourceDepth === 1 ? 1.8 : 1.4,
          opacity: isHighlighted ? 0.72 : 0.34,
          strokeLinecap: "round",
        },
      };
    });
}

type BuildReasoningOverlayEdgesParams = {
  reasoningEdges: Array<{ id?: string; source: string; target: string }>;
  visibleIds: Set<string>;
  getCenter: (nodeId: string) => { x: number; y: number };
};

export function buildReasoningOverlayEdges({
  reasoningEdges,
  visibleIds,
  getCenter,
}: BuildReasoningOverlayEdgesParams): Edge[] {
  return reasoningEdges
    .filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target))
    .map((edge) => {
      const sourceCenter = getCenter(edge.source);
      const targetCenter = getCenter(edge.target);
      return {
        id: edge.id || `reasoning:${edge.source}->${edge.target}`,
        source: edge.source,
        target: edge.target,
        type: "reasoningCurve",
        data: { sx: sourceCenter.x, sy: sourceCenter.y, tx: targetCenter.x, ty: targetCenter.y },
        style: {
          stroke: "#8B5CF6",
          strokeWidth: 1.8,
          opacity: 0.58,
          strokeDasharray: "6 6",
          strokeLinecap: "round",
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: "#8B5CF6",
          width: 18,
          height: 18,
        },
        zIndex: 2,
      } satisfies Edge;
    });
}
