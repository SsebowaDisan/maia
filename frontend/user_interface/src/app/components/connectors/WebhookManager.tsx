import { useState } from "react";

type WebhookRecord = {
  id: string;
  eventType: string;
  createdAt: string;
  lastReceivedAt: string | null;
  successRate: number;
};

type WebhookManagerProps = {
  connectorId: string;
};

const EVENT_OPTIONS = [
  "salesforce.deal.stage_changed",
  "github.pull_request.opened",
  "jira.issue.created",
  "slack.channel.message",
];

export function WebhookManager({ connectorId }: WebhookManagerProps) {
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);
  const [webhooks, setWebhooks] = useState<WebhookRecord[]>([]);

  const toggleEvent = (eventType: string) => {
    setSelectedEvents((previous) =>
      previous.includes(eventType)
        ? previous.filter((entry) => entry !== eventType)
        : [...previous, eventType],
    );
  };

  const registerSelected = () => {
    const now = new Date().toISOString();
    setWebhooks((previous) => [
      ...previous,
      ...selectedEvents.map((eventType) => ({
        id: `${connectorId}-${eventType}-${Date.now()}`,
        eventType,
        createdAt: now,
        lastReceivedAt: null,
        successRate: 100,
      })),
    ]);
    setSelectedEvents([]);
  };

  return (
    <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
      <h3 className="text-[17px] font-semibold text-[#101828]">Webhooks</h3>
      <p className="mt-1 text-[13px] text-[#667085]">Manage outgoing webhook subscriptions for {connectorId}.</p>

      <div className="mt-3 flex flex-wrap gap-2">
        {EVENT_OPTIONS.map((eventType) => (
          <label key={eventType} className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.12] px-2.5 py-1 text-[12px] text-[#344054]">
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
        onClick={registerSelected}
        disabled={!selectedEvents.length}
        className="mt-3 rounded-full bg-[#111827] px-4 py-2 text-[12px] font-semibold text-white disabled:opacity-40"
      >
        Register webhook
      </button>

      <div className="mt-4 space-y-2">
        {webhooks.map((webhook) => (
          <div key={webhook.id} className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[13px] font-semibold text-[#111827]">{webhook.eventType}</p>
              <button
                type="button"
                onClick={() => setWebhooks((previous) => previous.filter((entry) => entry.id !== webhook.id))}
                className="text-[12px] font-semibold text-[#b42318] hover:underline"
              >
                Delete
              </button>
            </div>
            <p className="text-[11px] text-[#667085]">
              Registered {new Date(webhook.createdAt).toLocaleString()} · Success {webhook.successRate}%
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

