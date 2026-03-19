import { useEffect, useState } from "react";

import {
  getMarketplaceWorkflow,
  installMarketplaceWorkflow,
  listMarketplaceWorkflowReviews,
  listRelatedMarketplaceWorkflows,
  type HubReviewRecord,
  type MarketplaceWorkflowRecord,
} from "../../../api/client";

type TeamDetailPageProps = {
  slug: string;
  onNavigate: (path: string) => void;
};

function buildWorkflowPath(workflowId: string): string {
  const params = new URLSearchParams();
  params.set("workflow", workflowId);
  return `/?${params.toString()}`;
}

export function TeamDetailPage({ slug, onNavigate }: TeamDetailPageProps) {
  const [loading, setLoading] = useState(true);
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState("");
  const [team, setTeam] = useState<MarketplaceWorkflowRecord | null>(null);
  const [reviews, setReviews] = useState<HubReviewRecord[]>([]);
  const [related, setRelated] = useState<MarketplaceWorkflowRecord[]>([]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const [detail, reviewRows, relatedRows] = await Promise.all([
          getMarketplaceWorkflow(slug),
          listMarketplaceWorkflowReviews(slug, 12),
          listRelatedMarketplaceWorkflows(slug, 6),
        ]);
        setTeam(detail);
        setReviews(reviewRows || []);
        setRelated(relatedRows || []);
      } catch (nextError) {
        setError(String(nextError || "Failed to load team."));
      } finally {
        setLoading(false);
      }
    };
    if (!slug) {
      setError("Missing team slug.");
      setLoading(false);
      return;
    }
    void load();
  }, [slug]);

  const installTeam = async () => {
    if (!team) {
      return;
    }
    setInstalling(true);
    setError("");
    try {
      const result = await installMarketplaceWorkflow(team.slug);
      if (!result.installed) {
        throw new Error("Install failed.");
      }
      const missingConnectors = Array.isArray(result.missing_connectors)
        ? result.missing_connectors
            .map((item) => String(item || "").trim())
            .filter(Boolean)
        : [];
      const redirectPath = String(result.redirect_path || "").trim();
      if (redirectPath) {
        if (missingConnectors.length) {
          const url = new URL(redirectPath, window.location.origin);
          url.searchParams.set("missing_connectors", missingConnectors.join(","));
          onNavigate(`${url.pathname}${url.search}`);
          return;
        }
        onNavigate(redirectPath);
        return;
      }
      if (result.workflow_id) {
        const nextPath = buildWorkflowPath(result.workflow_id);
        if (missingConnectors.length) {
          const url = new URL(nextPath, window.location.origin);
          url.searchParams.set("missing_connectors", missingConnectors.join(","));
          onNavigate(`${url.pathname}${url.search}`);
          return;
        }
        onNavigate(nextPath);
      }
    } catch (nextError) {
      setError(String(nextError || "Install failed."));
    } finally {
      setInstalling(false);
    }
  };

  if (loading) {
    return <p className="text-[14px] text-[#64748b]">Loading team details...</p>;
  }
  if (error) {
    return <p className="text-[14px] text-[#b42318]">{error}</p>;
  }
  if (!team) {
    return <p className="text-[14px] text-[#64748b]">Team not found.</p>;
  }

  return (
    <div className="space-y-6">
      <section className="rounded-[24px] border border-black/[0.08] bg-white p-6 shadow-[0_16px_32px_rgba(15,23,42,0.08)]">
        <button
          type="button"
          onClick={() => onNavigate("/marketplace")}
          className="text-[12px] font-semibold text-[#667085] hover:text-[#111827]"
        >
          Back to Marketplace
        </button>
        <h1 className="mt-4 text-[32px] font-semibold tracking-[-0.03em] text-[#0f172a]">{team.name}</h1>
        <button
          type="button"
          onClick={() => {
            if (team.creator_username) {
              onNavigate(`/creators/${encodeURIComponent(team.creator_username)}`);
            }
          }}
          className="mt-1 text-[13px] text-[#475467] hover:text-[#0f172a]"
        >
          {team.creator_display_name || team.creator_username || "Community creator"}
        </button>
        <p className="mt-4 whitespace-pre-wrap text-[14px] leading-6 text-[#334155]">
          {team.readme_md || team.description || "No team README yet."}
        </p>
        <button
          type="button"
          onClick={installTeam}
          disabled={installing}
          className="mt-5 h-11 rounded-2xl bg-[#111827] px-5 text-[13px] font-semibold text-white transition hover:bg-[#0b1220] disabled:opacity-60"
        >
          {installing ? "Installing..." : "Use this team"}
        </button>
      </section>

      <section className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-[22px] border border-black/[0.08] bg-white p-5">
          <h2 className="text-[16px] font-semibold text-[#111827]">Agent lineup</h2>
          <div className="mt-3 space-y-2">
            {(team.agent_lineup || []).length ? (
              team.agent_lineup.map((row) => (
                <div key={`${row.agent_id}-${row.step_id || ""}`} className="rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2">
                  <p className="text-[13px] font-semibold text-[#111827]">{row.agent_id}</p>
                  <p className="text-[12px] text-[#667085]">{row.description || "Agent step"}</p>
                </div>
              ))
            ) : (
              <p className="text-[13px] text-[#64748b]">No agent lineup published.</p>
            )}
          </div>
          <h3 className="mt-5 text-[13px] font-semibold uppercase tracking-[0.08em] text-[#64748b]">Required connectors</h3>
          <div className="mt-2 flex flex-wrap gap-2">
            {(team.required_connectors || []).length ? (
              team.required_connectors.map((connectorId) => (
                <span key={connectorId} className="rounded-full bg-[#eef2ff] px-3 py-1 text-[12px] font-semibold text-[#334155]">
                  {connectorId}
                </span>
              ))
            ) : (
              <span className="text-[12px] text-[#667085]">No connectors required.</span>
            )}
          </div>
        </div>

        <div className="space-y-5">
          <div className="rounded-[22px] border border-black/[0.08] bg-white p-5">
            <h2 className="text-[16px] font-semibold text-[#111827]">Reviews</h2>
            <div className="mt-2 space-y-2">
              {reviews.length ? (
                reviews.map((review) => (
                  <div key={review.id} className="rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2">
                    <p className="text-[12px] font-semibold text-[#111827]">{review.rating} / 5</p>
                    <p className="text-[12px] text-[#475467]">{review.review_text || "No comment provided."}</p>
                  </div>
                ))
              ) : (
                <p className="text-[12px] text-[#667085]">No reviews yet.</p>
              )}
            </div>
          </div>

          <div className="rounded-[22px] border border-black/[0.08] bg-white p-5">
            <h2 className="text-[16px] font-semibold text-[#111827]">Related teams</h2>
            <div className="mt-2 space-y-2">
              {related.length ? (
                related.map((row) => (
                  <button
                    key={row.slug}
                    type="button"
                    onClick={() => onNavigate(`/marketplace/teams/${encodeURIComponent(row.slug)}`)}
                    className="w-full rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-left transition hover:bg-[#eef2ff]"
                  >
                    <p className="text-[13px] font-semibold text-[#111827]">{row.name}</p>
                    <p className="text-[12px] text-[#667085] line-clamp-1">{row.description}</p>
                  </button>
                ))
              ) : (
                <p className="text-[12px] text-[#667085]">No related teams yet.</p>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
