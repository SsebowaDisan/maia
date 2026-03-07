import { BaseEdge, getSmoothStepPath, type EdgeProps } from "@xyflow/react";

function edgeColor(edgeFamily: string): string {
  const normalized = String(edgeFamily || "").trim().toLowerCase();
  if (normalized === "evidence") {
    return "#0ea5e9";
  }
  if (normalized === "verification") {
    return "#16a34a";
  }
  if (normalized === "handoff") {
    return "#7c3aed";
  }
  if (normalized === "dependency") {
    return "#f59e0b";
  }
  return "#9ca3af";
}

function edgeWidth(edgeFamily: string): number {
  const normalized = String(edgeFamily || "").trim().toLowerCase();
  if (normalized === "hierarchy") {
    return 1.4;
  }
  if (normalized === "verification") {
    return 2.1;
  }
  return 1.8;
}

function WorkGraphEdgeRenderer(props: EdgeProps) {
  const [path] = getSmoothStepPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX,
    targetY: props.targetY,
    targetPosition: props.targetPosition,
  });
  const family = String(props.data?.["edge_family"] || props.type || "hierarchy");
  return (
    <BaseEdge
      id={props.id}
      path={path}
      style={{
        stroke: edgeColor(family),
        strokeWidth: edgeWidth(family),
        strokeDasharray: family === "handoff" ? "5 4" : undefined,
      }}
    />
  );
}

export { WorkGraphEdgeRenderer, edgeColor, edgeWidth };

