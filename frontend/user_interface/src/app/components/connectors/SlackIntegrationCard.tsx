import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Copy, MessageSquare, RefreshCw, XCircle } from "lucide-react";
import { toast } from "sonner";

import { getSlackIntegrationStatus, type SlackIntegrationStatus } from "../../../api/client";

type SlackIntegrationCardProps = {
  compact?: boolean;
  onOpenConnector?: () => void;
};

function normalizeCommandsUrl(path: string): string {
  const trimmed = String(path || "").trim();
  if (!trimmed) {
    return "";
  }
  if (/^https?:\/\//i.test(trimmed)) {
    return trimmed;
  }
  if (typeof window !== "undefined") {
    return `${window.location.origin}${trimmed.startsWith("/") ? "" : "/"}${trimmed}`;
  }
  return trimmed;
}

const FALLBACK_STATUS: SlackIntegrationStatus = {
  configured: false,
  bot_token_set: false,
  commands_url: "/api/integrations/slack/commands",
};

export function SlackIntegrationCard({ compact = false, onOpenConnector }: SlackIntegrationCardProps) {
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<SlackIntegrationStatus>(FALLBACK_STATUS);
  const [loadError, setLoadError] = useState("");

  const load = async () => {
    setLoading(true);
    setLoadError("");
    try {
      const nextStatus = await getSlackIntegrationStatus();
      setStatus(nextStatus || FALLBACK_STATUS);
    } catch (error) {
      setLoadError(String(error || "Failed to load Slack status."));
      setStatus(FALLBACK_STATUS);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const commandsUrl = useMemo(
    () => normalizeCommandsUrl(status.commands_url || FALLBACK_STATUS.commands_url),
    [status.commands_url],
  );

  const connectionHealthy = status.configured && status.bot_token_set;

  return (
    <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <span className="mt-0.5 inline-flex h-8 w-8 items-center justify-center rounded-lg bg-[#f5f3ff] text-[#7c3aed]">
            <MessageSquare size={15} />
          </span>
          <div>
            <p className="text-[14px] font-semibold text-[#101828]">Slack integration</p>
            <p className="mt-0.5 text-[12px] text-[#667085]">
              Configure slash commands and inbound events for agents.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => {
            void load();
          }}
          className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-black/[0.1] text-[#344054] hover:bg-[#f8fafc]"
          title="Refresh Slack status"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-black/[0.08] bg-[#f8fafc] px-3 py-1 text-[11px] font-semibold">
        {connectionHealthy ? (
          <>
            <CheckCircle2 size={13} className="text-[#16a34a]" />
            <span className="text-[#166534]">Connected</span>
          </>
        ) : (
          <>
            <XCircle size={13} className="text-[#b42318]" />
            <span className="text-[#b42318]">Setup required</span>
          </>
        )}
      </div>

      {!compact ? (
        <ol className="mt-3 list-decimal space-y-1 pl-4 text-[12px] text-[#475467]">
          <li>Create a Slack app and slash command named <code>/maia</code>.</li>
          <li>Paste the request URL below into the command configuration.</li>
          <li>Install or re-install the app in your workspace.</li>
        </ol>
      ) : null}

      <div className="mt-3 rounded-xl border border-black/[0.08] bg-[#f8fafc] p-2.5">
        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#667085]">Request URL</p>
        <div className="mt-1 flex items-center gap-2">
          <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap rounded-lg bg-white px-2 py-1 text-[11px] text-[#1f2937]">
            {commandsUrl || "Unavailable"}
          </code>
          <button
            type="button"
            onClick={() => {
              if (!commandsUrl) {
                return;
              }
              void navigator.clipboard.writeText(commandsUrl);
              toast.success("Slack webhook URL copied.");
            }}
            className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-black/[0.1] text-[#344054] hover:bg-white"
            title="Copy webhook URL"
          >
            <Copy size={12} />
          </button>
        </div>
      </div>

      {loadError ? (
        <p className="mt-2 rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#b42318]">
          {loadError}
        </p>
      ) : null}

      {onOpenConnector ? (
        <button
          type="button"
          onClick={onOpenConnector}
          className="mt-3 rounded-full border border-black/[0.12] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#344054] hover:bg-[#f8fafc]"
        >
          Open Slack connector
        </button>
      ) : null}
    </section>
  );
}
