import {
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
  type ReactFlowInstance,
} from "@xyflow/react";

import type { MindNodeData } from "./utils";
import { edgeTypes, nodeTypes } from "./viewerGraph";

type MindMapFlowCanvasProps = {
  height: number;
  nodes: Array<Node<MindNodeData>>;
  edges: Edge[];
  onInit: (instance: ReactFlowInstance<Node<MindNodeData>, Edge>) => void;
  onNodeClick: NodeMouseHandler<Node<MindNodeData>>;
};

export function MindMapFlowCanvas({
  height,
  nodes,
  edges,
  onInit,
  onNodeClick,
}: MindMapFlowCanvasProps) {
  return (
    <div className="w-full bg-[#eef2f7]" style={{ height: `${height}px` }}>
      <ReactFlow
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodes={nodes}
        edges={edges}
        onInit={onInit}
        onNodeClick={onNodeClick}
        fitView
        fitViewOptions={{ padding: 0.12, maxZoom: 1.08 }}
        minZoom={0.2}
        maxZoom={1.7}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        zoomOnDoubleClick={false}
        panOnDrag
        zoomOnPinch
        zoomOnScroll
        proOptions={{ hideAttribution: true }}
        className="bg-[#eef2f7]"
      />
    </div>
  );
}
