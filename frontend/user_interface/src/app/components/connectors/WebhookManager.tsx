import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { deregisterWebhook, listWebhooks, registerWebhook } from "../../../api/client";

type WebhookManagerProps = {
  connectorId: string;
};

type UiStatus = "active" | "inactive" | "error";

type UiWebhookRecord = {
  id: string;
  eventType: string;
  createdAt: string;
  status: UiStatus;
};

const EVENT_OPTIONS = [
  "salesforce.deal.stage_changed",
  "github.pull_request.opened",
  "jira.issue.created",
  "slack.channel.message",
];

function normalizeEventTypes(raw: unknown): string[] {
  if (Array.isArray(raw)) {
    return raw
      .map((value) => String(value || "").trim())
      .filter(Boolean);
  }
  const text = String(raw || "").trim();
  if (!text) {
    return [];
  }
  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) {
      return parsed
        .map((value) => String(value || "").trim())
        .filter(Boolean);
    }
  } catch {
    // Fall through to delimiter split.
  }
  return text
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

function normalizeRow(row: Record<string, unknown>): UiWebhookRecord[] {
  const id = String(row.id || "").trim();
  const connector = String(row.connector_id || "").trim();
  if (!id || !connector) {
    return [];
  }
  const eventTypes = normalizeEventTypes(
    row.event_types ?? row.event_types_json ?? row.eventTypes ?? row.events,
  );
  if (!eventTypes.length) {
    return [];
  }
  const isActive = Boolean(row.active ?? row.is_active ?? true);
  const hasError = Boolean(row.error);
  const status: UiStatus = hasError ? "error" : isActive ? "active" : "inactive";
  const createdAtRaw = row.created_at ?? row.createdAt ?? Date.now();
  const createdAt =
    typeof createdAtRaw === "number"
      ? new Date(createdAtRaw * (createdAtRaw > 10_000_000_000 ? 1 : 1000)).toISOString()
      : new Date(String(createdAtRaw || Date.now())).toISOString();
  return eventTypes.map((eventType) => ({
    id: `${id}::${eventType}`,
    eventType,
    createdAt,
    status,
  }));
}

function statusBadgeClass(status: UiStatus): string {
  if (status === "active") {
    return "border-[#bbf7d0] bg-[#ecfdf3] text-[#166534]";
  }
  if (status === "inactive") {
    return "border-[#e5e7eb] bg-[#f8fafc] text-[#475467]";
  }
  return "border-[#fecaca] bg-[#fff1f2] text-[#b42318]";
}

export function WebhookManager({ connectorId }: WebhookManagerProps) {
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);
  const [webhooks, setWebhooks] = useState<UiWebhookRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const loadWebhooks = async () => {
    setLoading(true);
    setError("");
    try {
      const rows = await listWebhooks();
      const normalized = (rows as Array<Record<string, unknown>>)
        .filter((row) => String(row.connector_id || "").trim() === connectorId)
        .flatMap(normalizeRow);
      setWebhooks(normalized);
    } catch (nextError) {
      const message = String(nextError || "Failed to load webhooks.").trim();
      setError(message);
      setWebhooks([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadWebhooks();
  }, [connectorId]);

  const toggleEvent = (eventType: string) => {
    setSelectedEvents((previous) =>
      previous.includes(eventType)
        ? previous.filter((entry) => entry !== eventType)
        : [...previous, eventType],
    );
  };

  const registerSelected = async () => {
    if (!selectedEvents.length || saving) {
      return;
    }
    setSaving(true);
    try {
      await registerWebhook(connectorId, selectedEvents);
      toast.success("Webhook registered.");
      setSelectedEvents([]);
      await loadWebhooks();
    } catch (nextError) {
      toast.error(`Failed to register webhook: ${String(nextError)}`);
    } finally {
      setSaving(false);
    }
  };

  const groupedByWebhookId = useMemo(() => {
    const rows = new Map<string, UiWebhookRecord[]>();
    for (const row of webhooks) {
      const webhookId = row.id.split("::")[0];
      const existing = rows.get(webhookId) || [];
      existing.push(row);
      rows.set(webhookId, existing);
    }
    return Array.from(rows.entries()).map(([webhookId, entries]) => ({
      webhookId,
      entries,
      createdAt: entries[0]?.createdAt || new Date().toISOString(),
      status: entries.find((entry) => entry.status === "error")?.status || entries[0]?.status || "inactive",
    }));
  }, [webhooks]);

  const handleDelete = async (webhookId: string) => {
    try {
      await deregisterWebhook(webhookId);
      toast.success("Webhook removed.");
      await loadWebhooks();
    } catch (nextError) {
      toast.error(`Failed to remove webhook: ${String(nextError)}`);
    }
  };

  return (
    <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
      <h3 className="text-[17px] font-semibold text-[#101828]">Webhooks</h3>
      <p className="mt-1 text-[13px] text-[#667085]">
        Manage outgoing webhook subscriptions for {connectorId}.
      </p>

      <div className="mt-3 flex flex-wrap gap-2">
        {EVENT_OPTIONS.map((eventType) => (
          <label
            key={eventType}
            className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.12] px-2.5 py-1 text-[12px] text-[#344054]"
          >
            <input
              type="checkbox"
              checked={selectedEvents.includes(eventType)}
              onChange={() => toggleEvent(eventType)}
            />
            {eventType}
          </label>
        ))}
      </div>
      <button
        type="button"
        onClick={() => {
          void registerSelected();
        }}
        disabled={!selectedEvents.length || saving}
        className="mt-3 rounded-full bg-[#7c3aed] hover:bg-[#6d28d9] transition-colors px-4 py-2 text-[12px] font-semibold text-white disabled:opacity-40"
      >
        {saving ? "Registering..." : "Register webhook"}
      </button>

      {loading ? (
        <p className="mt-4 text-[12px] text-[#667085]">Loading webhooks...</p>
      ) : null}
      {error ? (
        <p className="mt-3 rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#b42318]">
          {error}
        </p>
      ) : null}

      <div className="mt-4 space-y-2">
        {groupedByWebhookId.map((webhook) => (
          <div key={webhook.webhookId} className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                {webhook.entries.map((entry) => (
                  <span key={entry.id} className="text-[13px] font-semibold text-[#111827]">
                    {entry.eventType}
                  </span>
                ))}
                <span
                  className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] ${statusBadgeClass(webhook.status)}`}
                >
                  {webhook.status}
                </span>
              </div>
              <button
                type="button"
                onClick={() => {
                  void handleDelete(webhook.webhookId);
                }}
                className="text-[12px] font-semibold text-[#b42318] hover:underline"
              >
                Delete
              </button>
            </div>
            <p className="text-[11px] text-[#667085]">
              Registered {new Date(webhook.createdAt).toLocaleString()}
            </p>
          </div>
        ))}
        {!loading && !groupedByWebhookId.length && !error ? (
          <p className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] px-3 py-2 text-[12px] text-[#667085]">
            No webhooks registered yet.
          </p>
        ) : null}
      </div>
    </section>
  );
}
