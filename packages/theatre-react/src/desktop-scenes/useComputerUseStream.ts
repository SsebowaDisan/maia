import { useEffect, useRef, useState } from "react";
import {
  cancelComputerUseSession,
  streamComputerUseSession,
  type ComputerUseStreamEvent,
} from "@maia/computer-use";

export type UseComputerUseStreamOptions = {
  sessionId: string;
  task: string;
  model: string;
  maxIterations: number | null;
  runId: string;
  onCancelled?: () => void;
};

export function useComputerUseStream(options: UseComputerUseStreamOptions) {
  const [screenshotUrl, setScreenshotUrl] = useState("");
  const [narration, setNarration] = useState("");
  const [streamStatus, setStreamStatus] = useState<"idle" | "streaming" | "done" | "max_iterations" | "error">("idle");
  const [iteration, setIteration] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [streamUrl, setStreamUrl] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const cleanupRef = useRef<(() => void) | null>(null);
  const streamKeyRef = useRef("");

  useEffect(
    () => () => {
      if (cleanupRef.current) {
        cleanupRef.current();
        cleanupRef.current = null;
      }
    },
    [],
  );

  useEffect(() => {
    const sessionId = String(options.sessionId || "").trim();
    const task = String(options.task || "").trim();
    if (!sessionId || !task) {
      if (cleanupRef.current) {
        cleanupRef.current();
        cleanupRef.current = null;
      }
      streamKeyRef.current = "";
      setScreenshotUrl("");
      setNarration("");
      setStreamStatus("idle");
      setIteration(null);
      setError("");
      setStreamUrl("");
      return;
    }

    const streamKey = [
      sessionId,
      task,
      String(options.model || ""),
      String(options.maxIterations ?? ""),
      String(options.runId || ""),
    ].join("::");
    if (streamKeyRef.current === streamKey) {
      return;
    }

    if (cleanupRef.current) {
      cleanupRef.current();
      cleanupRef.current = null;
    }

    streamKeyRef.current = streamKey;
    setScreenshotUrl("");
    setNarration("");
    setStreamStatus("streaming");
    setIteration(null);
    setError("");
    setStreamUrl("");

    cleanupRef.current = streamComputerUseSession(sessionId, {
      task,
      model: String(options.model || "").trim() || undefined,
      maxIterations:
        typeof options.maxIterations === "number" && Number.isFinite(options.maxIterations)
          ? options.maxIterations
          : undefined,
      runId: String(options.runId || "").trim() || undefined,
      onEvent: (event: ComputerUseStreamEvent) => {
        const iterationRaw = Number(event.iteration ?? Number.NaN);
        if (Number.isFinite(iterationRaw) && iterationRaw > 0) {
          setIteration(Math.round(iterationRaw));
        }
        switch (event.event_type) {
          case "started": {
            const nextStreamUrl = String(event.url || "").trim();
            if (nextStreamUrl) {
              setStreamUrl(nextStreamUrl);
            }
            return;
          }
          case "screenshot": {
            const screenshotB64 = String(event.screenshot_b64 || "").trim();
            if (screenshotB64) {
              setScreenshotUrl(`data:image/png;base64,${screenshotB64}`);
            }
            const nextStreamUrl = String(event.url || "").trim();
            if (nextStreamUrl) {
              setStreamUrl(nextStreamUrl);
            }
            return;
          }
          case "text": {
            const nextText = String(event.text || "").trim();
            if (!nextText) {
              return;
            }
            setNarration((previous) => {
              const combined = previous ? `${previous}\n${nextText}` : nextText;
              return combined.length > 480 ? combined.slice(combined.length - 480) : combined;
            });
            return;
          }
          case "action": {
            const actionLabel = String(event.action || "").trim();
            if (actionLabel) {
              setNarration(`Running action: ${actionLabel}`);
            }
            return;
          }
          case "done": {
            setStreamStatus("done");
            const nextStreamUrl = String(event.url || "").trim();
            if (nextStreamUrl) {
              setStreamUrl(nextStreamUrl);
            }
            return;
          }
          case "max_iterations":
            setStreamStatus("max_iterations");
            return;
          case "error":
            setStreamStatus("error");
            setError(String(event.detail || "Computer Use stream failed.").trim());
            return;
        }
      },
      onDone: () => {
        setStreamStatus((previous) => (previous === "streaming" ? "done" : previous));
      },
      onError: (streamError) => {
        setStreamStatus("error");
        setError(String(streamError?.message || "Computer Use stream disconnected."));
      },
    });

    return () => {
      if (cleanupRef.current) {
        cleanupRef.current();
        cleanupRef.current = null;
      }
    };
  }, [options.maxIterations, options.model, options.runId, options.sessionId, options.task]);

  const cancel = async () => {
    const sessionId = String(options.sessionId || "").trim();
    if (!sessionId || cancelling) {
      return;
    }
    setCancelling(true);
    try {
      await cancelComputerUseSession(sessionId);
      if (cleanupRef.current) {
        cleanupRef.current();
        cleanupRef.current = null;
      }
      streamKeyRef.current = "";
      setStreamStatus("done");
      setNarration((previous) => previous || "Computer Use session stopped.");
      options.onCancelled?.();
    } catch (cancelError) {
      const message = String(
        (cancelError as { message?: string } | undefined)?.message || cancelError || "Failed to stop session.",
      ).trim();
      setStreamStatus("error");
      setError(message);
    } finally {
      setCancelling(false);
    }
  };

  return {
    cancel,
    cancelling,
    error,
    iteration,
    narration,
    screenshotUrl,
    streamStatus,
    streamUrl,
  };
}
