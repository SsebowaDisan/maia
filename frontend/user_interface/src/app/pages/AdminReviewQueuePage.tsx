import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  approveMarketplaceAgent,
  claimMarketplaceReview,
  listMarketplaceReviewQueue,
  rejectMarketplaceAgent,
  type MarketplaceReviewQueueItem,
  type MarketplaceReviewStatus,
} from "../../api/client";
import { useAuthStore } from "../stores/authStore";

type QueueFilter = MarketplaceReviewStatus;

const FILTERS: QueueFilter[] = [
  "pending_review",
  "approved",
  "rejected",
  "published",
  "deprecated",
];

function formatLabel(value: string) {
  return String(value || "")
    .replace(/[_-]+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatDate(value?: string | null) {
  const text = String(value || "").trim();
  if (!text) {
    return "n/a";
  }
  const time = new Date(text);
  if (Number.isNaN(time.getTime())) {
    return text;
  }
  return time.toLocaleString();
}

export function AdminReviewQueuePage() {
  const user = useAuthStore((state) => state.user);
  const isSuperAdmin = useAuthStore((state) => state.isSuperAdmin());
  const [statusFilter, setStatusFilter] = useState<QueueFilter>("pending_review");
  const [rows, setRows] = useState<MarketplaceReviewQueueItem[]>([]);
  const [expandedAgentId, setExpandedAgentId] = useState<string | null>(null);
  const [rejectDraftById, setRejectDraftById] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [busyAgentId, setBusyAgentId] = useState("");
  const [error, setError] = useState("");

  const loadQueue = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await listMarketplaceReviewQueue(statusFilter);
      setRows(Array.isArray(response) ? response : []);
    } catch (nextError) {
      setError(String(nextError || "Failed to load review queue."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isSuperAdmin) {
      return;
    }
    void loadQueue();
  }, [isSuperAdmin, statusFilter]);

  const emptyText = useMemo(() => {
    if (loading) {
      return "Loading submissions...";
    }
    if (error) {
      return error;
    }
    return `No agents in ${formatLabel(statusFilter)}.`;
  }, [loading, error, statusFilter]);

  if (!isSuperAdmin) {
    return (
      <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
        <div className="mx-auto max-w-[980px] rounded-2xl border border-black/[0.08] bg-white p-5">
          <h1 className="text-[24px] font-semibold text-[#101828]">Admin review queue</h1>
          <p className="mt-2 text-[14px] text-[#667085]">
            Super-admin access is required to review marketplace submissions.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1240px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Admin</p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">Review queue</h1>
          <p className="mt-2 text-[14px] text-[#475467]">
            Review and action marketplace submissions. Signed in as{" "}
            <span className="font-semibold text-[#111827]">{user?.email || "super_admin"}</span>.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {FILTERS.map((filter) => (
              <button
                key={filter}
                type="button"
                onClick={() => setStatusFilter(filter)}
                className={`rounded-full px-3 py-1.5 text-[12px] font-semibold ${
                  statusFilter === filter
                    ? "bg-[#111827] text-white"
                    : "border border-black/[0.12] bg-white text-[#344054]"
                }`}
              >
                {formatLabel(filter)}
              </button>
            ))}
          </div>
        </section>

        <section className="space-y-3">
          {rows.length === 0 ? (
            <div className="rounded-2xl border border-black/[0.08] bg-white p-4 text-[13px] text-[#667085]">
              {emptyText}
            </div>
          ) : null}

          {rows.map((row) => {
            const expanded = expandedAgentId === row.agent_id;
            const rejectReason = rejectDraftById[row.agent_id] || "";
            const claimingMine = String(row.reviewer_id || "") === String(user?.id || "");
            const isBusy = busyAgentId === row.agent_id;
            const statusText = formatLabel(row.status);
            return (
              <article key={row.id} className="rounded-2xl border border-black/[0.08] bg-white p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[18px] font-semibold text-[#101828]">{row.name}</p>
                    <p className="mt-1 text-[12px] text-[#667085]">
                      {row.agent_id} · v{row.version} · submitted {formatDate(row.published_at || undefined)}
                    </p>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <span className="rounded-full border border-black/[0.08] bg-[#f8fafc] px-2 py-0.5 text-[11px] font-semibold text-[#344054]">
                        {statusText}
                      </span>
                      {row.reviewer_id ? (
                        <span className="rounded-full border border-black/[0.08] bg-white px-2 py-0.5 text-[11px] text-[#475467]">
                          Claimed: {claimingMine ? "you" : row.reviewer_id}
                        </span>
                      ) : null}
                      {(row.tags || []).slice(0, 5).map((tag) => (
                        <span
                          key={`${row.agent_id}-${tag}`}
                          className="rounded-full border border-black/[0.08] bg-white px-2 py-0.5 text-[11px] text-[#475467]"
                        >
                          #{tag}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => setExpandedAgentId(expanded ? null : row.agent_id)}
                      className="rounded-full border border-black/[0.12] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#344054]"
                    >
                      {expanded ? "Hide definition" : "View definition"}
                    </button>
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={async () => {
                        setBusyAgentId(row.agent_id);
                        try {
                          await claimMarketplaceReview(row.agent_id, !claimingMine);
                          toast.success(claimingMine ? "Review unclaimed." : "Review claimed.");
                          await loadQueue();
                        } catch (nextError) {
                          toast.error(String(nextError || "Claim update failed."));
                        } finally {
                          setBusyAgentId("");
                        }
                      }}
                      className="rounded-full border border-black/[0.12] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#344054] disabled:opacity-60"
                    >
                      {claimingMine ? "Unclaim" : "Claim"}
                    </button>
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={async () => {
                        setBusyAgentId(row.agent_id);
                        try {
                          await approveMarketplaceAgent(row.agent_id);
                          toast.success(`Approved ${row.name}.`);
                          await loadQueue();
                        } catch (nextError) {
                          toast.error(String(nextError || "Approval failed."));
                        } finally {
                          setBusyAgentId("");
                        }
                      }}
                      className="rounded-full bg-[#111827] px-3 py-1.5 text-[12px] font-semibold text-white disabled:opacity-60"
                    >
                      Approve
                    </button>
                  </div>
                </div>

                <p className="mt-2 text-[13px] text-[#475467]">{row.description}</p>

                {row.rejection_reason ? (
                  <p className="mt-2 rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#9f1239]">
                    Last rejection reason: {row.rejection_reason}
                  </p>
                ) : null}

                {expanded ? (
                  <pre className="mt-3 max-h-[320px] overflow-auto rounded-xl border border-black/[0.08] bg-[#f8fafc] p-3 text-[12px] text-[#344054]">
                    <code>{JSON.stringify(row.definition || {}, null, 2)}</code>
                  </pre>
                ) : null}

                <div className="mt-3 rounded-xl border border-black/[0.08] bg-[#fcfcfd] p-3">
                  <label className="block text-[12px] font-semibold text-[#344054]">Reject reason</label>
                  <textarea
                    value={rejectReason}
                    onChange={(event) =>
                      setRejectDraftById((previous) => ({
                        ...previous,
                        [row.agent_id]: event.target.value,
                      }))
                    }
                    rows={2}
                    placeholder="Explain what must change before approval."
                    className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px] text-[#111827]"
                  />
                  <div className="mt-2 flex justify-end">
                    <button
                      type="button"
                      disabled={isBusy || !rejectReason.trim()}
                      onClick={async () => {
                        setBusyAgentId(row.agent_id);
                        try {
                          await rejectMarketplaceAgent(row.agent_id, rejectReason.trim());
                          setRejectDraftById((previous) => ({ ...previous, [row.agent_id]: "" }));
                          toast.success(`Rejected ${row.name}.`);
                          await loadQueue();
                        } catch (nextError) {
                          toast.error(String(nextError || "Rejection failed."));
                        } finally {
                          setBusyAgentId("");
                        }
                      }}
                      className="rounded-full border border-[#fca5a5] bg-[#fff1f2] px-3 py-1.5 text-[12px] font-semibold text-[#9f1239] disabled:opacity-60"
                    >
                      Reject
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
        </section>
      </div>
    </div>
  );
}
