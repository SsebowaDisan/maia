import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";

type WorkflowFlowEdgeData = {
  condition?: string;
  animated?: boolean;
};

function WorkflowEdge(props: EdgeProps<WorkflowFlowEdgeData>) {
  const {
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    markerEnd,
    data,
  } = props;

  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    curvature: 0.34,
  });

  const isAnimated = Boolean(data?.animated);
  const condition = String(data?.condition || "").trim();

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={{
          stroke: isAnimated ? "#2563eb" : "#a3b8d9",
          strokeWidth: isAnimated ? 2.2 : 1.8,
          strokeDasharray: isAnimated ? "6 5" : "0",
          opacity: isAnimated ? 0.95 : 0.9,
        }}
      />
      {condition ? (
        <EdgeLabelRenderer>
          <div
            className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full border border-black/[0.08] bg-white/95 px-2 py-0.5 text-[10px] font-medium text-[#344054] shadow-sm"
            style={{
              left: labelX,
              top: labelY,
            }}
          >
            {condition}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

export { WorkflowEdge };
export type { WorkflowFlowEdgeData };
