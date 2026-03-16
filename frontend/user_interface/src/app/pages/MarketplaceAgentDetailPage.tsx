import { useEffect, useMemo, useState } from "react";

import {
  getMarketplaceAgent,
  getMarketplaceAgentReviews,
  listConnectorHealth,
  type MarketplaceAgentDetail,
  type MarketplaceAgentReview,
} from "../../api/client";

type MarketplaceAgentDetailPageProps = {
  agentId: string;
};

function navigateToPath(path: string) {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function normalizeLabel(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function MarketplaceAgentDetailPage({ agentId }: MarketplaceAgentDetailPageProps) {
  const [agent, setAgent] = useState<MarketplaceAgentDetail | null>(null);
  const [reviews, setReviews] = useState<MarketplaceAgentReview[]>([]);
  const [connectedConnectorIds, setConnectedConnectorIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const [detail, reviewRows, healthRows] = await Promise.all([
          getMarketplaceAgent(agentId),
          getMarketplaceAgentReviews(agentId, { limit: 20 }),
          listConnectorHealth(),
        ]);
        setAgent(detail);
        setReviews(reviewRows || []);
        setConnectedConnectorIds(
          (healthRows || [])
            .filter((row) => Boolean(row?.ok))
            .map((row) => String(row?.connector_id || ""))
            .filter(Boolean),
        );
      } catch (nextError) {
        setError(String(nextError || "Failed to load marketplace agent."));
      } finally {
        setLoading(false);
      }
    };
    if (!agentId) {
      setLoading(false);
      setError("Missing agent id.");
      return;
    }
    void load();
  }, [agentId]);

  const requiredConnectors = useMemo(() => agent?.required_connectors || [], [agent]);
  const tags = useMemo(
    () =>
      Array.isArray(agent?.tags)
        ? agent.tags.map((tag) => String(tag || "").trim()).filter(Boolean)
        : [],
    [agent?.tags],
  );

  if (loading) {
    return (
      <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
        <div className="mx-auto max-w-[1080px] rounded-2xl border border-black/[0.08] bg-white p-5 text-[14px] text-[#667085]">
          Loading agent details...
        </div>
      </div>
    );
  }

  if (!agent || error) {
    return (
      <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
        <div className="mx-auto max-w-[980px] rounded-2xl border border-black/[0.08] bg-white p-5">
          <h1 className="text-[24px] font-semibold text-[#101828]">Agent not found</h1>
          <p className="mt-2 text-[14px] text-[#667085]">{error || "No marketplace entry for this agent id."}</p>
          <button
            type="button"
            onClick={() => navigateToPath("/marketplace")}
            className="mt-3 inline-block text-[13px] font-semibold text-[#1d4ed8] hover:underline"
          >
            Back to marketplace
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1080px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5 shadow-[0_20px_54px_rgba(15,23,42,0.1)]">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">
            Marketplace agent
          </p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">{agent.name}</h1>
          <p className="mt-2 text-[15px] text-[#475467]">{agent.description}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="rounded-full border border-[#d0d5dd] bg-[#f8fafc] px-2.5 py-1 text-[11px] font-semibold text-[#344054]">
              {Number(agent.avg_rating || 0).toFixed(1)} rating
            </span>
            <span className="rounded-full border border-[#d0d5dd] bg-[#f8fafc] px-2.5 py-1 text-[11px] font-semibold text-[#344054]">
              {(agent.install_count || 0).toLocaleString()} installs
            </span>
            <span className="rounded-full border border-[#d0d5dd] bg-white px-2.5 py-1 text-[11px] font-semibold uppercase text-[#344054]">
              {agent.pricing_tier}
            </span>
          </div>
          {tags.length ? (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {tags.map((tag) => (
                <span
                  key={tag}
                  className="rounded-full border border-black/[0.08] bg-[#f9fafb] px-2 py-0.5 text-[11px] font-semibold text-[#475467]"
                >
                  #{tag}
                </span>
              ))}
            </div>
          ) : null}
        </section>

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <h2 className="text-[18px] font-semibold text-[#111827]">Required connectors</h2>
            <div className="mt-3 space-y-2">
              {requiredConnectors.map((required) => {
                const connected = connectedConnectorIds.includes(required);
                return (
                  <div key={required} className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] px-3 py-2">
                    <p className="text-[13px] font-semibold text-[#111827]">{normalizeLabel(required)}</p>
                    <p className={`text-[12px] ${connected ? "text-[#166534]" : "text-[#b42318]"}`}>
                      {connected ? "Connected in tenant" : "Not connected yet"}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="space-y-4">
            {agent.definition?.trigger && (agent.definition.trigger as Record<string, unknown>)?.family === "scheduled" ? (
              <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
                <h2 className="text-[18px] font-semibold text-[#111827]">Schedule</h2>
                <div className="mt-2 flex items-center gap-2">
                  <span className="rounded-full bg-[#f0fdf4] px-2.5 py-1 text-[11px] font-semibold text-[#166534] border border-[#bbf7d0]">
                    Automated
                  </span>
                  <span className="text-[12px] text-[#667085]">
                    Runs on cron: <code className="rounded bg-[#f1f5f9] px-1 text-[#344054]">{String((agent.definition.trigger as Record<string, unknown>)?.cron_expression ?? "")}</code>
                  </span>
                </div>
                <p className="mt-2 text-[12px] text-[#667085]">
                  This agent runs automatically on a schedule. No manual trigger required after installation.
                </p>
              </div>
            ) : null}

            <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
              <h2 className="text-[18px] font-semibold text-[#111827]">Tools</h2>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {Array.isArray(agent.definition?.tools) && (agent.definition.tools as string[]).length ? (
                  (agent.definition.tools as string[]).map((tool) => (
                    <span key={tool} className="rounded-full border border-[#e2e8f0] bg-[#f8fafc] px-2 py-0.5 text-[11px] font-mono text-[#475467]">
                      {tool}
                    </span>
                  ))
                ) : (
                  <p className="text-[12px] text-[#667085]">No tools listed.</p>
                )}
              </div>
            </div>

            <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
              <h2 className="text-[18px] font-semibold text-[#111827]">Changelog</h2>
              <ul className="mt-3 list-disc space-y-1 pl-4 text-[13px] text-[#475467]">
                <li>Version {agent.version}</li>
              </ul>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
          <h2 className="text-[18px] font-semibold text-[#111827]">Reviews</h2>
          <div className="mt-3 space-y-2">
            {reviews.length ? (
              reviews.map((review) => (
                <div key={review.id} className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3">
                  <p className="text-[13px] font-semibold text-[#111827]">
                    {"★".repeat(Math.max(1, Math.min(5, Number(review.rating || 0))))}
                  </p>
                  <p className="mt-1 text-[12px] text-[#667085]">
                    {String(review.review_text || "").trim() || "No written review."}
                  </p>
                  {review.publisher_response ? (
                    <p className="mt-2 text-[12px] text-[#475467]">
                      Publisher response: {review.publisher_response}
                    </p>
                  ) : null}
                </div>
              ))
            ) : (
              <p className="text-[13px] text-[#667085]">No reviews yet.</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
