import { useCallback, useEffect, useRef, useState } from "react";
import { startComputerUseSession } from "../../../api/client";
import { compactValue } from "./helpers";

type SceneRecord = Record<string, unknown>;

type UseComputerUseBootstrapOptions = {
  activeDetail: string;
  activeEventType: string;
  activeSceneData: SceneRecord;
  activeStepIndex: number | null;
  activeTitle: string;
  actionMetadata: SceneRecord;
  actionTarget: SceneRecord;
  browserUrl: string;
  computerUseMaxIterationsProp: number | null;
  computerUseModelProp: string;
  computerUseSessionIdProp: string;
  computerUseTaskProp: string;
  runId: string;
  sceneText: string;
};

function useComputerUseBootstrap({
  activeDetail,
  activeEventType,
  activeSceneData,
  activeStepIndex,
  activeTitle,
  actionMetadata,
  actionTarget,
  browserUrl,
  computerUseMaxIterationsProp,
  computerUseModelProp,
  computerUseSessionIdProp,
  computerUseTaskProp,
  runId,
  sceneText,
}: UseComputerUseBootstrapOptions) {
  const [fallbackComputerUseSessionId, setFallbackComputerUseSessionId] = useState("");
  const [fallbackComputerUseTask, setFallbackComputerUseTask] = useState("");
  const [fallbackComputerUseModel, setFallbackComputerUseModel] = useState("");
  const [fallbackComputerUseMaxIterations, setFallbackComputerUseMaxIterations] = useState<number | null>(null);
  const computerUseBootstrapRef = useRef("");

  const computerUseSessionId =
    compactValue(computerUseSessionIdProp) ||
    compactValue(activeSceneData["computer_use_session_id"]) ||
    compactValue(actionMetadata["computer_use_session_id"]) ||
    compactValue(actionTarget["computer_use_session_id"]) ||
    compactValue(fallbackComputerUseSessionId);
  const computerUseTask =
    compactValue(computerUseTaskProp) ||
    compactValue(activeSceneData["computer_use_task"]) ||
    compactValue(actionMetadata["computer_use_task"]) ||
    compactValue(actionTarget["computer_use_task"]) ||
    compactValue(fallbackComputerUseTask) ||
    (computerUseSessionId ? compactValue(activeDetail || sceneText || activeTitle) : "");
  const computerUseModel =
    compactValue(computerUseModelProp) ||
    compactValue(activeSceneData["computer_use_model"]) ||
    compactValue(actionMetadata["computer_use_model"]) ||
    compactValue(actionTarget["computer_use_model"]) ||
    compactValue(fallbackComputerUseModel);
  const computerUseMaxIterationsRaw = Number(
    computerUseMaxIterationsProp ??
      activeSceneData["computer_use_max_iterations"] ??
      actionMetadata["computer_use_max_iterations"] ??
      actionTarget["computer_use_max_iterations"] ??
      fallbackComputerUseMaxIterations,
  );
  const computerUseMaxIterations =
    Number.isFinite(computerUseMaxIterationsRaw) && computerUseMaxIterationsRaw > 0
      ? Math.round(computerUseMaxIterationsRaw)
      : null;

  useEffect(() => {
    if (computerUseSessionId) {
      return;
    }
    const normalizedEventType = String(activeEventType || "").trim().toLowerCase();
    const toolHintCandidates = [
      activeSceneData["tool_id"],
      activeSceneData["tool_name"],
      actionMetadata["tool_id"],
      actionMetadata["tool_name"],
      actionTarget["tool_id"],
      actionTarget["tool_name"],
    ]
      .map((value) => compactValue(value).toLowerCase())
      .filter(Boolean);
    const isComputerUseToolEvent =
      normalizedEventType.includes("computer_use") ||
      toolHintCandidates.some((value) => value.includes("computer_use"));
    if (!isComputerUseToolEvent) {
      return;
    }
    const startUrl =
      compactValue(activeSceneData["computer_use_start_url"]) ||
      compactValue(actionMetadata["start_url"]) ||
      compactValue(activeSceneData["start_url"]) ||
      compactValue(activeSceneData["url"]) ||
      compactValue(activeSceneData["source_url"]) ||
      compactValue(browserUrl);
    if (!startUrl || (!startUrl.startsWith("http://") && !startUrl.startsWith("https://"))) {
      return;
    }
    const bootstrapTask =
      compactValue(computerUseTaskProp) ||
      compactValue(activeSceneData["computer_use_task"]) ||
      compactValue(activeDetail || sceneText || activeTitle) ||
      "Review this page and continue the requested task.";
    const bootstrapKey = [runId || "run", String(activeStepIndex ?? "step"), startUrl, bootstrapTask].join("::");
    if (computerUseBootstrapRef.current === bootstrapKey) {
      return;
    }
    computerUseBootstrapRef.current = bootstrapKey;
    let disposed = false;
    void startComputerUseSession({ url: startUrl, requestId: bootstrapKey })
      .then((session) => {
        if (disposed) {
          return;
        }
        const sessionId = String(session?.session_id || "").trim();
        if (!sessionId) {
          return;
        }
        setFallbackComputerUseSessionId(sessionId);
        setFallbackComputerUseTask(bootstrapTask);
        setFallbackComputerUseModel(
          compactValue(computerUseModelProp) || compactValue(activeSceneData["computer_use_model"]) || "",
        );
        setFallbackComputerUseMaxIterations(computerUseMaxIterations);
      })
      .catch(() => {
        if (!disposed) {
          computerUseBootstrapRef.current = "";
        }
      });
    return () => {
      disposed = true;
    };
  }, [
    activeDetail,
    activeEventType,
    activeSceneData,
    activeStepIndex,
    activeTitle,
    actionMetadata,
    actionTarget,
    browserUrl,
    computerUseMaxIterations,
    computerUseModelProp,
    computerUseSessionId,
    computerUseTaskProp,
    runId,
    sceneText,
  ]);

  const resetComputerUseFallback = useCallback(() => {
    setFallbackComputerUseSessionId("");
    setFallbackComputerUseTask("");
    setFallbackComputerUseModel("");
    setFallbackComputerUseMaxIterations(null);
    computerUseBootstrapRef.current = "";
  }, []);

  return {
    computerUseMaxIterations,
    computerUseModel,
    computerUseSessionId,
    computerUseTask,
    resetComputerUseFallback,
  };
}

export { useComputerUseBootstrap };
