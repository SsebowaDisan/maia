import { useEffect, useState } from "react";

import { listMyFeed } from "../../../api/client";

type FeedPageProps = {
  onNavigate: (path: string) => void;
};

export function FeedPage({ onNavigate }: FeedPageProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [events, setEvents] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const rows = await listMyFeed(50);
        setEvents(rows || []);
      } catch (nextError) {
        setError(String(nextError || "Failed to load feed."));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  return (
    <div className="space-y-4">
      <section className="rounded-[24px] border border-black/[0.08] bg-white p-6">
        <h1 className="text-[30px] font-semibold tracking-[-0.03em] text-[#111827]">Updates from creators you follow</h1>
        <p className="mt-1 text-[14px] text-[#667085]">Stay on top of new team and agent releases.</p>
      </section>

      {loading ? <p className="text-[14px] text-[#64748b]">Loading feed...</p> : null}
      {error ? <p className="text-[14px] text-[#b42318]">{error}</p> : null}

      <div className="space-y-2">
        {events.length ? (
          events.map((item) => (
            <button
              key={String(item.id || Math.random())}
              type="button"
              onClick={() => {
                const slug = String(item.slug || "").trim();
                if (slug) {
                  onNavigate(`/marketplace/teams/${encodeURIComponent(slug)}`);
                }
              }}
              className="w-full rounded-xl border border-black/[0.08] bg-white px-4 py-3 text-left transition hover:bg-[#f8fafc]"
            >
              <p className="text-[13px] font-semibold text-[#111827]">
                {String(item.creator_display_name || item.creator_username || "Creator")}
              </p>
              <p className="text-[13px] text-[#334155]">{String(item.title || item.event_type || "Update")}</p>
              <p className="text-[12px] text-[#667085]">{String(item.summary || "")}</p>
            </button>
          ))
        ) : (
          <div className="rounded-xl border border-dashed border-black/[0.15] bg-white px-4 py-6 text-center text-[13px] text-[#667085]">
            No feed events yet. Follow creators from their profile pages to populate this feed.
          </div>
        )}
      </div>
    </div>
  );
}
