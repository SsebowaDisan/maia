import { ChevronDown, ChevronRight } from "lucide-react";

import type { MindmapMapType, MindmapNode } from "./types";
import { compactNodeValue } from "./viewerGraph";

type MindMapTreeViewProps = {
  rootNodeId: string;
  nodeById: Map<string, MindmapNode>;
  childrenByParent: Map<string, string[]>;
  visibleNodeIds: Set<string>;
  depthMap: Record<string, number>;
  maxDepth: number;
  collapsedNodeIds: string[];
  selectedNodeId: string | null;
  activeMapType: MindmapMapType;
  onSelectNode: (nodeId: string) => void;
  onToggleNode: (nodeId: string) => void;
};

type RenderTreeNode = {
  id: string;
  title: string;
  subtitle?: string;
  depth: number;
  hasChildren: boolean;
  childCount: number;
  branchIndex: number;
  selected: boolean;
  isCollapsed: boolean;
};

const BRANCH_BACKGROUNDS = ["#fff6ee", "#eefbfd", "#f6f2ff", "#eefbf1", "#fff9ec", "#fdf2f8"];
const BRANCH_BORDERS = ["#e8b48c", "#9ed6e4", "#c2adff", "#a8dfb5", "#e8ca72", "#eab3cf"];

function buildSubtitle(node: MindmapNode, activeMapType: MindmapMapType): string | undefined {
  if (activeMapType === "work_graph") {
    return [
      compactNodeValue(node.status),
      compactNodeValue(node.tool_id),
      compactNodeValue(node.action_class),
    ]
      .filter((value) => value.length > 0)
      .join(" / ") || undefined;
  }
  return [
    compactNodeValue(node.source_name || node.source_id),
    compactNodeValue(node.page_ref || node.page),
    compactNodeValue(node.source_type),
  ]
    .filter((value) => value.length > 0)
    .join(" / ") || undefined;
}

function isVisibleChild(
  childId: string,
  props: Pick<MindMapTreeViewProps, "visibleNodeIds" | "nodeById" | "depthMap" | "maxDepth">,
): boolean {
  const { visibleNodeIds, nodeById, depthMap, maxDepth } = props;
  return (
    visibleNodeIds.has(childId) &&
    nodeById.has(childId) &&
    (depthMap[childId] ?? Number.MAX_SAFE_INTEGER) <= maxDepth
  );
}

function visibleChildren(
  parentId: string,
  props: Pick<
    MindMapTreeViewProps,
    "childrenByParent" | "visibleNodeIds" | "nodeById" | "depthMap" | "maxDepth"
  >,
): string[] {
  return (props.childrenByParent.get(parentId) || []).filter((childId) => isVisibleChild(childId, props));
}

function buildParentByChild(
  props: Pick<
    MindMapTreeViewProps,
    "childrenByParent" | "visibleNodeIds" | "nodeById" | "depthMap" | "maxDepth"
  >,
): Map<string, string> {
  const parentByChild = new Map<string, string>();
  props.childrenByParent.forEach((children, parentId) => {
    children.forEach((childId) => {
      if (isVisibleChild(childId, props) && props.visibleNodeIds.has(parentId)) {
        parentByChild.set(childId, parentId);
      }
    });
  });
  return parentByChild;
}

function pathToRoot(
  rootId: string,
  selectedNodeId: string | null,
  parentByChild: Map<string, string>,
  visibleNodeIds: Set<string>,
): string[] {
  if (!selectedNodeId || !visibleNodeIds.has(selectedNodeId)) {
    return [rootId];
  }
  const chain: string[] = [];
  const seen = new Set<string>();
  let cursor: string | null = selectedNodeId;
  while (cursor && !seen.has(cursor)) {
    chain.push(cursor);
    seen.add(cursor);
    if (cursor === rootId) {
      break;
    }
    cursor = parentByChild.get(cursor) || null;
  }
  if (chain[chain.length - 1] !== rootId) {
    return [rootId];
  }
  return chain.reverse();
}

function toRenderNode(
  nodeId: string,
  depth: number,
  branchIndex: number,
  props: Pick<
    MindMapTreeViewProps,
    "nodeById" | "childrenByParent" | "visibleNodeIds" | "depthMap" | "maxDepth" | "collapsedNodeIds" | "selectedNodeId" | "activeMapType"
  >,
): RenderTreeNode | null {
  if (!props.visibleNodeIds.has(nodeId)) {
    return null;
  }
  const node = props.nodeById.get(nodeId);
  if (!node) {
    return null;
  }
  const children = visibleChildren(nodeId, props);
  return {
    id: node.id,
    title: node.title || node.id,
    subtitle: buildSubtitle(node, props.activeMapType),
    depth,
    hasChildren: children.length > 0,
    childCount: children.length,
    branchIndex,
    selected: props.selectedNodeId === node.id,
    isCollapsed: props.collapsedNodeIds.includes(node.id),
  };
}

function NodeCard({
  node,
  isRoot,
  isInOpenPath,
  onSelectNode,
  onToggleNode,
}: {
  node: RenderTreeNode;
  isRoot: boolean;
  isInOpenPath: boolean;
  onSelectNode: (nodeId: string) => void;
  onToggleNode: (nodeId: string, isInOpenPath: boolean, isCollapsed: boolean) => void;
}) {
  const isFirstLevel = node.depth === 1;
  const background = isRoot ? "#ffffff" : BRANCH_BACKGROUNDS[node.branchIndex % BRANCH_BACKGROUNDS.length];
  const border = isRoot ? "#d7d8de" : BRANCH_BORDERS[node.branchIndex % BRANCH_BORDERS.length];
  const widthClass = isRoot ? "w-[380px]" : isFirstLevel ? "w-[296px]" : "w-[262px]";
  const titleClass = isRoot
    ? "text-[22px] font-semibold text-[#17171b]"
    : isFirstLevel
      ? "text-[15px] font-semibold text-[#25252b]"
      : "text-[13px] font-medium text-[#2d2d33]";

  return (
    <div className="relative shrink-0">
      <button
        type="button"
        onClick={() => onSelectNode(node.id)}
        className={`rounded-[24px] border px-5 text-left shadow-[0_1px_2px_rgba(15,23,42,0.05)] transition-all hover:-translate-y-[1px] ${widthClass} ${isRoot ? "py-6" : "py-4"} ${node.selected ? "ring-2 ring-[#3b82f6]/30 ring-offset-2" : ""}`}
        style={{ backgroundColor: background, borderColor: border }}
      >
        <p className={`leading-[1.35] ${titleClass}`}>{node.title}</p>
        {node.subtitle ? (
          <p className={`mt-2 ${isRoot ? "text-[12px] leading-5 text-[#676a73]" : "text-[11px] leading-5 text-[#6b6b70]"}`}>
            {node.subtitle}
          </p>
        ) : null}
        {node.hasChildren ? (
          <div className="mt-3">
            <span className={`inline-flex items-center rounded-full border border-black/[0.06] bg-white/76 px-2.5 py-1 font-semibold uppercase tracking-[0.08em] text-[#7b8598] ${isRoot ? "text-[11px]" : "text-[10px]"}`}>
              {node.childCount} {node.childCount === 1 ? "branch" : "branches"}
            </span>
          </div>
        ) : null}
      </button>
      {node.hasChildren ? (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onToggleNode(node.id, isInOpenPath, node.isCollapsed);
          }}
          className="absolute -right-3 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full border border-white/80 bg-[#17171b] text-white shadow-sm"
          title={node.isCollapsed ? "Expand branch" : "Collapse branch"}
        >
          {node.isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      ) : null}
    </div>
  );
}

export function MindMapTreeView(props: MindMapTreeViewProps) {
  const rootNode = props.nodeById.get(props.rootNodeId);
  if (!rootNode || !props.visibleNodeIds.has(props.rootNodeId)) {
    return (
      <div className="flex h-full items-center justify-center rounded-[22px] border border-dashed border-black/[0.08] bg-[#fbfbfc] text-[12px] text-[#6e6e73]">
        No tree structure is available for this map.
      </div>
    );
  }

  const parentByChild = buildParentByChild(props);
  const openPath = pathToRoot(props.rootNodeId, props.selectedNodeId, parentByChild, props.visibleNodeIds);
  const openPathSet = new Set(openPath);

  const topLevelIds = visibleChildren(props.rootNodeId, props);
  const topBranchIndex = new Map<string, number>();
  topLevelIds.forEach((childId, index) => {
    topBranchIndex.set(childId, index);
  });

  const resolveBranchIndex = (nodeId: string): number => {
    let cursor = nodeId;
    while (cursor && cursor !== props.rootNodeId) {
      const parentId = parentByChild.get(cursor);
      if (!parentId) {
        break;
      }
      if (parentId === props.rootNodeId) {
        return topBranchIndex.get(cursor) ?? 0;
      }
      cursor = parentId;
    }
    return 0;
  };

  const columns: Array<{ parentId: string; nodes: RenderTreeNode[] }> = [];
  let parentId = props.rootNodeId;
  let depth = 1;
  while (depth <= props.maxDepth) {
    if (props.collapsedNodeIds.includes(parentId)) {
      break;
    }
    const childIds = visibleChildren(parentId, props);
    if (!childIds.length) {
      break;
    }
    const nodes = childIds
      .map((childId) => toRenderNode(childId, depth, resolveBranchIndex(childId), props))
      .filter((node): node is RenderTreeNode => Boolean(node));
    if (!nodes.length) {
      break;
    }
    columns.push({ parentId, nodes });
    const nextFromPath = openPath[depth];
    if (!nextFromPath || !childIds.includes(nextFromPath)) {
      break;
    }
    parentId = nextFromPath;
    depth += 1;
  }

  const rootRenderNode = toRenderNode(props.rootNodeId, 0, 0, props);
  if (!rootRenderNode) {
    return null;
  }

  const handleToggleNode = (nodeId: string, isInOpenPath: boolean, isCollapsed: boolean) => {
    if (isCollapsed) {
      props.onToggleNode(nodeId);
      props.onSelectNode(nodeId);
      return;
    }
    if (isInOpenPath) {
      props.onToggleNode(nodeId);
      return;
    }
    props.onSelectNode(nodeId);
  };

  return (
    <div className="h-full overflow-auto bg-[linear-gradient(180deg,#fcfcfa_0%,#f7f7f3_100%)] px-8 py-8 md:px-10 md:py-10">
      <div className="min-w-max pb-24">
        <div className="flex items-start gap-10">
          <div className="sticky left-0 z-10 rounded-[28px] bg-[linear-gradient(90deg,#f7f7f3_0%,rgba(247,247,243,0.94)_78%,rgba(247,247,243,0)_100%)] pr-6">
            <NodeCard
              node={rootRenderNode}
              isRoot
              isInOpenPath
              onSelectNode={props.onSelectNode}
              onToggleNode={handleToggleNode}
            />
          </div>

          {columns.map((column) => (
            <div
              key={column.parentId}
              className="relative flex flex-col gap-4 pl-10 before:absolute before:bottom-6 before:left-0 before:top-6 before:w-px before:bg-[#dcdde3]"
            >
              {column.nodes.map((node) => (
                <div
                  key={node.id}
                  className="relative before:absolute before:-left-10 before:top-1/2 before:h-px before:w-10 before:-translate-y-1/2 before:bg-[#dcdde3]"
                >
                  <NodeCard
                    node={node}
                    isRoot={false}
                    isInOpenPath={openPathSet.has(node.id)}
                    onSelectNode={props.onSelectNode}
                    onToggleNode={handleToggleNode}
                  />
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
