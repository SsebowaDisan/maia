import { useEffect, useState } from "react";
import { Check, ChevronDown, Shield, Star, X } from "lucide-react";
import { toast } from "sonner";

import {
  approveDeveloper,
  listDeveloperApplications,
  promoteDeveloper,
  rejectDeveloper,
  type DeveloperApplicationRecord,
} from "../../../api/client";

const STATUS_TABS = [
  { value: "pending", label: "Pending" },
  { value: "verified", label: "Verified" },
  { value: "trusted_publisher", label: "Trusted" },
  { value: "rejected", label: "Rejected" },
] as const;

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-amber-50 text-amber-700 border-amber-200",
  verified: "bg-emerald-50 text-emerald-700 border-emerald-200",
  trusted_publisher: "bg-purple-50 text-purple-700 border-purple-200",
  rejected: "bg-red-50 text-red-700 border-red-200",
};

export function AdminDeveloperReviewTab() {
  const [activeTab, setActiveTab] = useState("pending");
  const [applications, setApplications] = useState<DeveloperApplicationRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchApplications = async (status: string) => {
    setLoading(true);
    try {
      const result = await listDeveloperApplications(status);
      setApplications(result);
    } catch {
      toast.error("Failed to load applications.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchApplications(activeTab);
  }, [activeTab]);

  const handleApprove = async (userId: string) => {
    setActionLoading(userId);
    try {
      await approveDeveloper(userId);
      toast.success("Developer approved.");
      fetchApplications(activeTab);
    } catch (error) {
      toast.error(String((error as Error).message || "Approval failed."));
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (userId: string) => {
    if (!rejectReason.trim()) {
      toast.error("Please provide a rejection reason.");
      return;
    }
    setActionLoading(userId);
    try {
      await rejectDeveloper(userId, rejectReason.trim());
      toast.success("Application rejected.");
      setRejectReason("");
      setExpandedId(null);
      fetchApplications(activeTab);
    } catch (error) {
      toast.error(String((error as Error).message || "Rejection failed."));
    } finally {
      setActionLoading(null);
    }
  };

  const handlePromote = async (userId: string) => {
    setActionLoading(userId);
    try {
      await promoteDeveloper(userId);
      toast.success("Developer promoted to trusted publisher.");
      fetchApplications(activeTab);
    } catch (error) {
      toast.error(String((error as Error).message || "Promotion failed."));
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div>
      {/* Status tabs */}
      <div className="mb-4 flex gap-1.5">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            onClick={() => setActiveTab(tab.value)}
            className={`rounded-lg px-3 py-1.5 text-[12px] font-medium transition ${
              activeTab === tab.value
                ? "bg-[#1d1d1f] text-white"
                : "bg-black/[0.04] text-[#6e6e73] hover:bg-black/[0.06]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* List */}
      {loading ? (
        <div className="py-10 text-center text-[13px] text-[#86868b]">Loading…</div>
      ) : applications.length === 0 ? (
        <div className="py-10 text-center text-[13px] text-[#86868b]">
          No {activeTab} applications.
        </div>
      ) : (
        <div className="space-y-2">
          {applications.map((app) => {
            const isExpanded = expandedId === app.user_id;
            const isLoading = actionLoading === app.user_id;
            return (
              <div
                key={app.user_id}
                className="rounded-xl border border-black/[0.06] bg-white p-3"
              >
                <div className="flex items-center justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-[13px] font-medium text-[#1d1d1f]">
                        {app.user_id}
                      </span>
                      <span
                        className={`inline-flex rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${
                          STATUS_COLORS[app.status] || "bg-gray-50 text-gray-600"
                        }`}
                      >
                        {app.status}
                      </span>
                    </div>
                    {app.date_created ? (
                      <span className="text-[11px] text-[#86868b]">
                        Applied {new Date(app.date_created).toLocaleDateString()}
                      </span>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    onClick={() => setExpandedId(isExpanded ? null : app.user_id)}
                    className="ml-2 rounded-lg p-1.5 text-[#86868b] transition hover:bg-black/[0.04]"
                  >
                    <ChevronDown
                      className={`h-4 w-4 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                    />
                  </button>
                </div>

                {isExpanded ? (
                  <div className="mt-3 space-y-3 border-t border-black/[0.06] pt-3">
                    <div>
                      <span className="mb-0.5 block text-[11px] font-medium text-[#86868b]">
                        Motivation
                      </span>
                      <p className="text-[12px] leading-relaxed text-[#1d1d1f]">
                        {app.motivation || "—"}
                      </p>
                    </div>
                    {app.intended_agent_types ? (
                      <div>
                        <span className="mb-0.5 block text-[11px] font-medium text-[#86868b]">
                          Intended agent types
                        </span>
                        <p className="text-[12px] text-[#1d1d1f]">
                          {app.intended_agent_types}
                        </p>
                      </div>
                    ) : null}
                    {app.rejection_reason ? (
                      <div>
                        <span className="mb-0.5 block text-[11px] font-medium text-[#86868b]">
                          Previous rejection reason
                        </span>
                        <p className="text-[12px] text-red-600">{app.rejection_reason}</p>
                      </div>
                    ) : null}

                    {/* Action buttons */}
                    <div className="flex flex-wrap items-center gap-2 pt-1">
                      {app.status === "pending" ? (
                        <>
                          <button
                            type="button"
                            disabled={isLoading}
                            onClick={() => handleApprove(app.user_id)}
                            className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-emerald-600 px-3 text-[12px] font-medium text-white transition hover:bg-emerald-700 disabled:opacity-50"
                          >
                            <Check className="h-3.5 w-3.5" /> Approve
                          </button>
                          <div className="flex items-center gap-1.5">
                            <input
                              value={rejectReason}
                              onChange={(e) => setRejectReason(e.target.value)}
                              placeholder="Rejection reason…"
                              className="h-8 w-[200px] rounded-lg border border-black/[0.08] px-2.5 text-[12px] outline-none focus:border-red-300"
                            />
                            <button
                              type="button"
                              disabled={isLoading || !rejectReason.trim()}
                              onClick={() => handleReject(app.user_id)}
                              className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-red-600 px-3 text-[12px] font-medium text-white transition hover:bg-red-700 disabled:opacity-50"
                            >
                              <X className="h-3.5 w-3.5" /> Reject
                            </button>
                          </div>
                        </>
                      ) : null}
                      {app.status === "verified" ? (
                        <button
                          type="button"
                          disabled={isLoading}
                          onClick={() => handlePromote(app.user_id)}
                          className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-[#7c3aed] px-3 text-[12px] font-medium text-white transition hover:bg-[#6d28d9] disabled:opacity-50"
                        >
                          <Star className="h-3.5 w-3.5" /> Promote to Trusted
                        </button>
                      ) : null}
                      {app.status === "trusted_publisher" ? (
                        <span className="inline-flex items-center gap-1 text-[12px] text-[#7c3aed]">
                          <Shield className="h-3.5 w-3.5" /> Trusted Publisher
                        </span>
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
