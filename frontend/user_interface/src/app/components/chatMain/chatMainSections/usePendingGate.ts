import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { listPendingGates } from "../../../../api/client";
import { readEventPayload } from "../../../utils/eventPayload";
import { toPreviewText, type PendingGateView } from "./common";

type ActivityEvent = Record<string, unknown>;

type UsePendingGateParams = {
  activeRunId: string;
  activityEvents: ActivityEvent[];
};

export function usePendingGate({ activeRunId, activityEvents }: UsePendingGateParams) {
  const pendingGateToastRef = useRef<string>("");
  const [pendingGateFromApi, setPendingGateFromApi] = useState<PendingGateView | null>(null);

  const pendingGateFromEvents = useMemo(() => {
    const orderedEvents = Array.isArray(activityEvents) ? [...activityEvents] : [];
    if (!orderedEvents.length) {
      return null;
    }
    let latestPending: PendingGateView | null = null;
    const resolvedGates = new Set<string>();
    for (let index = orderedEvents.length - 1; index >= 0; index -= 1) {
      const event = orderedEvents[index];
      const eventType = String(event?.event_type || event?.type || "").trim().toLowerCase();
      const payload = readEventPayload(event);
      const gateId = String(payload.gate_id || "").trim();
      if (eventType === "gate_approved" || eventType === "gate_rejected" || eventType === "gate_resolved") {
        if (gateId) {
          resolvedGates.add(gateId);
        }
        continue;
      }
      const isApprovalEvent = eventType === "gate_pending" || eventType === "approval_required";
      if (!isApprovalEvent || (gateId && resolvedGates.has(gateId))) {
        continue;
      }
      const runId = String(event?.run_id || payload.run_id || "").trim();
      const toolId = String(payload.tool_id || payload.action_label || event.title || "tool").trim();
      const previewPayload = (payload.preview ?? null) as Record<string, unknown> | null;
      const paramsPreview = toPreviewText(
        payload.params_preview ||
          previewPayload ||
          event.detail ||
          "Review tool call parameters before continuing.",
      );
      const numericCost = Number(payload.cost_estimate ?? Number.NaN);
      latestPending = {
        runId: runId || activeRunId || "",
        gateId,
        toolId: toolId || "tool",
        paramsPreview: paramsPreview || "Review tool call parameters before continuing.",
        actionLabel: String(payload.action_label || "").trim() || undefined,
        preview: previewPayload,
        costEstimateUsd: Number.isFinite(numericCost) ? numericCost : null,
      };
      break;
    }
    return latestPending;
  }, [activeRunId, activityEvents]);

  const pendingGate = pendingGateFromEvents || pendingGateFromApi;

  useEffect(() => {
    const gateId = String(pendingGate?.gateId || "").trim();
    if (!gateId || pendingGateToastRef.current === gateId) {
      return;
    }
    pendingGateToastRef.current = gateId;
    toast.info(`Approval required for ${pendingGate?.toolId || "tool action"}.`);
  }, [pendingGate?.gateId, pendingGate?.toolId]);

  useEffect(() => {
    if (!activeRunId || pendingGateFromEvents) {
      setPendingGateFromApi(null);
      return;
    }
    let disposed = false;
    const poll = async () => {
      try {
        const rows = await listPendingGates(activeRunId);
        if (disposed || !Array.isArray(rows) || !rows.length) {
          if (!disposed) {
            setPendingGateFromApi(null);
          }
          return;
        }
        const gate = rows[0];
        const numericCost = Number(gate.cost_estimate ?? Number.NaN);
        const previewPayload =
          gate.preview && typeof gate.preview === "object"
            ? (gate.preview as Record<string, unknown>)
            : null;
        const paramsPreview = toPreviewText(
          gate.params_preview || previewPayload || "Review tool call parameters before continuing.",
        );
        setPendingGateFromApi({
          runId: String(gate.run_id || activeRunId),
          gateId: String(gate.gate_id || ""),
          toolId: String(gate.tool_id || "tool"),
          paramsPreview,
          actionLabel: String(gate.action_label || "").trim() || undefined,
          preview: previewPayload,
          costEstimateUsd: Number.isFinite(numericCost) ? numericCost : null,
        });
      } catch {
        if (!disposed) {
          setPendingGateFromApi(null);
        }
      }
    };
    void poll();
    const timer = window.setInterval(() => {
      void poll();
    }, 3000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [activeRunId, pendingGateFromEvents]);

  return pendingGate;
}
