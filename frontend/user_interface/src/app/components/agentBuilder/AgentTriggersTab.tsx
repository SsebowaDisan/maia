import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Play, Plus, Trash2, Zap } from "lucide-react";
import { toast } from "sonner";

import {
  createAgentTrigger,
  deleteAgentTrigger,
  listAgentTriggers,
  listTriggerEventTypes,
  testAgentTrigger,
  type TriggerEventTypeRecord,
  type TriggerRecord,
} from "../../../api/client";

type AgentTriggersTabProps = {
  agentId: string;
};

function safeParseJson(text: string): Record<string, unknown> {
  const trimmed = String(text || "").trim();
  if (!trimmed) {
    return {};
  }
  try {
    const parsed = JSON.parse(trimmed) as Record<string, unknown>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    throw new Error("Payload JSON is invalid.");
  }
}

export function AgentTriggersTab({ agentId }: AgentTriggersTabProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [triggers, setTriggers] = useState<TriggerRecord[]>([]);
  const [eventTypes, setEventTypes] = useState<TriggerEventTypeRecord[]>([]);
  const [eventType, setEventType] = useState("webhook.inbound");
  const [sourceConnectorId, setSourceConnectorId] = useState("");
  const [description, setDescription] = useState("");
  const [testPayload, setTestPayload] = useState("{\n  \"sample\": true\n}");
  const [testResult, setTestResult] = useState<string>("");
  const [testingTriggerId, setTestingTriggerId] = useState<string>("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [triggerRows, eventTypeRows] = await Promise.all([
        listAgentTriggers(),
        listTriggerEventTypes(),
      ]);
      const safeTriggers = Array.isArray(triggerRows) ? triggerRows : [];
      setTriggers(safeTriggers);
      const safeEventTypes = Array.isArray(eventTypeRows) ? eventTypeRows : [];
      setEventTypes(safeEventTypes);
      if (safeEventTypes.length > 0 && !safeEventTypes.some((row) => row.event_type === eventType)) {
        setEventType(String(safeEventTypes[0].event_type || "webhook.inbound"));
      }
    } catch (error) {
      toast.error(`Failed to load triggers: ${String(error)}`);
    } finally {
      setLoading(false);
    }
  }, [eventType]);

  useEffect(() => {
    void load();
  }, [load]);

  const filteredTriggers = useMemo(
    () =>
      triggers.filter((row) => String(row.agent_id || "").trim() === String(agentId || "").trim()),
    [agentId, triggers],
  );

  const createTrigger = async () => {
    if (!agentId) {
      return;
    }
    if (!eventType.trim()) {
      toast.error("Pick an event type first.");
      return;
    }
    setSaving(true);
    try {
      await createAgentTrigger({
        agent_id: agentId,
        event_type: eventType.trim(),
        source_connector_id: sourceConnectorId.trim(),
        description: description.trim(),
      });
      toast.success("Trigger created.");
      setDescription("");
      await load();
    } catch (error) {
      toast.error(`Failed to create trigger: ${String(error)}`);
    } finally {
      setSaving(false);
    }
  };

  const deleteTrigger = async (triggerId: string) => {
    try {
      await deleteAgentTrigger(triggerId);
      toast.success("Trigger removed.");
      await load();
    } catch (error) {
      toast.error(`Failed to delete trigger: ${String(error)}`);
    }
  };

  const runTest = async (eventTypeOverride?: string, triggerId?: string) => {
    try {
      setTestingTriggerId(triggerId || "__global__");
      const payload = safeParseJson(testPayload);
      const result = await testAgentTrigger(
        String(eventTypeOverride || eventType || "").trim(),
        payload,
      );
      const count = Number(result.count || 0);
      setTestResult(
        count > 0
          ? `Matched ${count} trigger(s): ${(result.matched_agents || []).join(", ")}`
          : "No triggers matched this test event.",
      );
    } catch (error) {
      setTestResult(`Test failed: ${String(error)}`);
    } finally {
      setTestingTriggerId("");
    }
  };

  return (
    <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
            Triggers
          </p>
          <p className="mt-1 text-[13px] text-[#475467]">
            Run this agent automatically when external events arrive.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-full border border-black/[0.1] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#344054] hover:bg-[#f8fafc]"
        >
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-4">
        <label className="lg:col-span-2">
          <span className="text-[12px] font-semibold text-[#344054]">Event type</span>
          <select
            value={eventType}
            onChange={(event) => setEventType(event.target.value)}
            className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
          >
            {(eventTypes.length ? eventTypes : [{ event_type: "webhook.inbound", label: "Inbound webhook" }]).map(
              (row) => (
                <option key={row.event_type} value={row.event_type}>
                  {row.label || row.event_type}
                </option>
              ),
            )}
          </select>
        </label>
        <label>
          <span className="text-[12px] font-semibold text-[#344054]">Source connector</span>
          <input
            value={sourceConnectorId}
            onChange={(event) => setSourceConnectorId(event.target.value)}
            placeholder="slack, salesforce, github..."
            className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
          />
        </label>
        <label>
          <span className="text-[12px] font-semibold text-[#344054]">Description</span>
          <input
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Notify account team on CRM update"
            className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
          />
        </label>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={saving || !eventType.trim()}
          onClick={() => {
            void createTrigger();
          }}
          className="inline-flex items-center gap-1 rounded-full bg-[#7c3aed] px-4 py-2 text-[12px] font-semibold text-white disabled:opacity-60"
        >
          {saving ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
          Add trigger
        </button>
        <button
          type="button"
          disabled={testingTriggerId.length > 0}
          onClick={() => {
            void runTest();
          }}
          className="inline-flex items-center gap-1 rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[12px] font-semibold text-[#344054] disabled:opacity-60"
        >
          {testingTriggerId === "__global__" ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Play size={12} />
          )}
          Test event
        </button>
      </div>

      <label className="mt-3 block">
        <span className="text-[12px] font-semibold text-[#344054]">Test payload (JSON)</span>
        <textarea
          value={testPayload}
          onChange={(event) => setTestPayload(event.target.value)}
          className="mt-1 h-24 w-full resize-y rounded-xl border border-black/[0.12] bg-[#f8fafc] px-3 py-2 font-mono text-[12px]"
        />
      </label>

      {testResult ? (
        <p className="mt-2 rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-[12px] text-[#344054]">
          {testResult}
        </p>
      ) : null}

      <div className="mt-4 space-y-2">
        {loading ? (
          <p className="rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-[12px] text-[#667085]">
            Loading triggers...
          </p>
        ) : null}

        {!loading && filteredTriggers.length === 0 ? (
          <p className="rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-[12px] text-[#667085]">
            No triggers configured for this agent.
          </p>
        ) : null}

        {filteredTriggers.map((row) => (
          <article
            key={row.trigger_id}
            className="rounded-xl border border-black/[0.08] bg-white px-3 py-2"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-[13px] font-semibold text-[#111827]">{row.event_type}</p>
                <p className="mt-0.5 text-[11px] text-[#667085]">
                  Source: {String(row.source_connector_id || "any connector")}
                </p>
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => {
                    void runTest(row.event_type, row.trigger_id);
                  }}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-black/[0.1] text-[#344054] hover:bg-[#f8fafc]"
                  title="Test this trigger"
                >
                  {testingTriggerId === row.trigger_id ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Zap size={12} />
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    void deleteTrigger(row.trigger_id);
                  }}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-[#fecaca] text-[#b42318] hover:bg-[#fff1f2]"
                  title="Delete trigger"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
