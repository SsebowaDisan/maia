import { useEffect, useRef } from "react";
import { emitTheatreMetric } from "./theatreTelemetry";
import type { TheatreStage } from "./deriveTheatreStage";

function useTheatreTelemetry({
  streaming,
  theatreStage,
  manualTabOverride,
  runId,
}: {
  streaming: boolean;
  theatreStage: TheatreStage;
  manualTabOverride: boolean;
  runId: string;
}) {
  const previousStageRef = useRef<string>("");
  const runStartedAtRef = useRef<number | null>(null);
  const firstSurfaceAtRef = useRef<number | null>(null);
  const previousStreamingRef = useRef(streaming);

  useEffect(() => {
    if (streaming && !previousStreamingRef.current) {
      runStartedAtRef.current = Date.now();
      firstSurfaceAtRef.current = null;
    }
    previousStreamingRef.current = streaming;
  }, [streaming]);

  useEffect(() => {
    const previousStage = previousStageRef.current;
    if (previousStage === theatreStage) {
      return;
    }
    previousStageRef.current = theatreStage;
    emitTheatreMetric("stage_transition", {
      previous_stage: previousStage || null,
      next_stage: theatreStage,
      run_id: runId,
      manual_override: manualTabOverride,
    });

    if ((theatreStage === "surface" || theatreStage === "execute") && firstSurfaceAtRef.current === null) {
      firstSurfaceAtRef.current = Date.now();
      if (runStartedAtRef.current) {
        emitTheatreMetric("understand_to_surface_ms", {
          value: firstSurfaceAtRef.current - runStartedAtRef.current,
          run_id: runId,
        });
      }
    }

    if (theatreStage === "review" && firstSurfaceAtRef.current !== null) {
      emitTheatreMetric("surface_to_review_ms", {
        value: Date.now() - firstSurfaceAtRef.current,
        run_id: runId,
      });
    }
  }, [manualTabOverride, runId, theatreStage]);

  useEffect(() => {
    emitTheatreMetric("manual_tab_override", {
      active: manualTabOverride,
      run_id: runId,
    });
  }, [manualTabOverride, runId]);
}

export { useTheatreTelemetry };

