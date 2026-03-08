import type { Edge, Node } from "@xyflow/react";
import {
  sideForRootBranch,
  type GraphNodeData,
  type LayoutMode,
  type MindmapTreeNode,
  type PositionMap,
} from "./graphTypes";

function renderGraphTree(params: {
  treeRoot: MindmapTreeNode;
  layoutMode: LayoutMode;
  collapsedNodeIds: Set<string>;
  positionOverrides: PositionMap;
  onToggleCollapse: (nodeId: string) => void;
}) {
  const { treeRoot, layoutMode, collapsedNodeIds, positionOverrides, onToggleCollapse } = params;
  const sideById = new Map<string, "left" | "right">();
  sideById.set(treeRoot.id, "right");

  const assignSides = (node: MindmapTreeNode, side: "left" | "right") => {
    sideById.set(node.id, side);
    node.children.forEach((child) => assignSides(child, side));
  };
  treeRoot.children.forEach((child, index) => {
    assignSides(child, sideForRootBranch(layoutMode, index));
  });

  const visibleChildren = (node: MindmapTreeNode): MindmapTreeNode[] => {
    if (collapsedNodeIds.has(node.id)) {
      return [];
    }
    return node.children;
  };

  const layoutById = new Map<string, { x: number; y: number }>();
  const topPadding = 24;
  const depthGap = 212;
  const leafGap = 74;
  const rootX = layoutMode === "left" ? 48 : layoutMode === "right" ? 892 : 472;
  let leafCursor = topPadding;

  const assignLayout = (node: MindmapTreeNode, depth: number): number => {
    const nodeSide = sideById.get(node.id) || "right";
    const x = node.id === treeRoot.id
      ? rootX
      : rootX + depth * depthGap * (nodeSide === "right" ? 1 : -1);
    const children = visibleChildren(node);
    if (!children.length) {
      const y = leafCursor;
      leafCursor += leafGap;
      layoutById.set(node.id, { x, y });
      return y;
    }
    const childYs = children.map((child) => assignLayout(child, depth + 1));
    const y = (Math.min(...childYs) + Math.max(...childYs)) / 2;
    layoutById.set(node.id, { x, y });
    return y;
  };
  assignLayout(treeRoot, 0);

  const nodes: Array<Node<GraphNodeData>> = [];
  const edges: Edge[] = [];
  const collapsibleNodeIdsList: string[] = [];

  const collectCollapsibleNodeIds = (node: MindmapTreeNode) => {
    if (node.id !== treeRoot.id && node.children.length > 0) {
      collapsibleNodeIdsList.push(node.id);
    }
    node.children.forEach((child) => collectCollapsibleNodeIds(child));
  };
  collectCollapsibleNodeIds(treeRoot);

  const pushNode = (node: MindmapTreeNode) => {
    const position = positionOverrides[node.id] || layoutById.get(node.id) || { x: 0, y: 0 };
    const side = sideById.get(node.id) || "right";
    const collapsed = collapsedNodeIds.has(node.id);
    const children = visibleChildren(node);
    const hiddenChildrenCount = collapsed ? node.children.length : 0;

    nodes.push({
      id: node.id,
      type: "graphNode",
      position,
      data: {
        ...node.data,
        nodeId: node.id,
        side,
        collapsible: node.id !== treeRoot.id && node.children.length > 0,
        collapsed,
        hiddenChildrenCount,
        onToggleCollapse,
      },
    });

    children.forEach((child) => {
      const childSide = sideById.get(child.id) || "right";
      const childIsTraceNode =
        child.data.kind === "claim" ||
        child.data.kind === "evidence" ||
        Boolean(child.data.active) ||
        Number(child.data.usageClaimCount || 0) > 0;
      edges.push({
        id: `edge-${node.id}-${child.id}`,
        source: node.id,
        sourceHandle: childSide === "right" ? "source-right" : "source-left",
        target: child.id,
        targetHandle: childSide === "right" ? "target-left" : "target-right",
        type: "smoothstep",
        pathOptions: { borderRadius: 34, offset: 12 },
        style: {
          stroke: child.data.branchColor,
          strokeWidth: child.data.kind === "evidence" ? (childIsTraceNode ? 1.9 : 1.4) : (childIsTraceNode ? 2.2 : 1.5),
          opacity: childIsTraceNode ? 0.84 : 0.3,
          strokeLinecap: "round",
        },
      });
      pushNode(child);
    });
  };
  pushNode(treeRoot);

  return {
    nodes,
    edges,
    collapsibleNodeIds: collapsibleNodeIdsList,
  };
}

export { renderGraphTree };
