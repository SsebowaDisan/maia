import { useEffect, useMemo, useRef, useState } from "react";
import { Bell, CheckCheck, Loader2 } from "lucide-react";
import {
  getMarketplaceNotificationUnreadCount,
  listMarketplaceNotifications,
  markAllMarketplaceNotificationsRead,
  markMarketplaceNotificationRead,
  type MarketplaceNotificationRecord,
} from "../../../api/client";

type MarketplaceNotificationBellProps = {
  onNavigate: (path: string) => void;
};

function formatDate(value?: string | null) {
  const text = String(value || "").trim();
  if (!text) {
    return "now";
  }
  const time = new Date(text);
  if (Number.isNaN(time.getTime())) {
    return text;
  }
  return time.toLocaleString();
}

function MarketplaceNotificationBell({ onNavigate }: MarketplaceNotificationBellProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [markingAll, setMarkingAll] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [rows, setRows] = useState<MarketplaceNotificationRecord[]>([]);
  const [error, setError] = useState("");
  const rootRef = useRef<HTMLDivElement | null>(null);

  const refreshUnreadCount = async () => {
    try {
      const response = await getMarketplaceNotificationUnreadCount();
      const count = Math.max(0, Number(response?.count || 0));
      if (Number.isFinite(count)) {
        setUnreadCount(count);
      }
    } catch {
      // Keep UI stable when notifications API is unavailable.
    }
  };

  const refreshRows = async (includeLoading = true) => {
    if (includeLoading) {
      setLoading(true);
    }
    setError("");
    try {
      const response = await listMarketplaceNotifications(false, 40);
      setRows(Array.isArray(response) ? response : []);
      await refreshUnreadCount();
    } catch (nextError) {
      setError(String(nextError || "Failed to load notifications."));
    } finally {
      if (includeLoading) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    void refreshUnreadCount();
    const timer = window.setInterval(() => {
      void refreshUnreadCount();
    }, 30000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!open) {
      return;
    }
    void refreshRows();
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current) {
        return;
      }
      if (!rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", onPointerDown);
    return () => window.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  const unreadLabel = useMemo(() => {
    if (unreadCount <= 0) {
      return "";
    }
    if (unreadCount > 99) {
      return "99+";
    }
    return String(unreadCount);
  }, [unreadCount]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="relative inline-flex h-7 w-7 items-center justify-center rounded-full border border-black/[0.08] bg-white text-[#6e6e73] transition-colors hover:bg-[#f5f5f7] hover:text-[#1d1d1f]"
        title="Notifications"
      >
        <Bell className="h-3.5 w-3.5" />
        {unreadLabel ? (
          <span className="absolute -right-1 -top-1 inline-flex min-w-[16px] items-center justify-center rounded-full bg-[#111827] px-1 text-[10px] font-semibold text-white">
            {unreadLabel}
          </span>
        ) : null}
      </button>

      {open ? (
        <section className="absolute right-0 top-9 z-50 w-[360px] overflow-hidden rounded-2xl border border-black/[0.08] bg-white shadow-[0_22px_54px_rgba(15,23,42,0.24)]">
          <header className="flex items-center justify-between border-b border-black/[0.06] px-3 py-2.5">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
                Notifications
              </p>
              <p className="text-[13px] font-semibold text-[#101828]">Marketplace activity</p>
            </div>
            <button
              type="button"
              disabled={markingAll || unreadCount === 0}
              onClick={async () => {
                setMarkingAll(true);
                try {
                  await markAllMarketplaceNotificationsRead();
                  setRows((previous) =>
                    previous.map((row) => ({
                      ...row,
                      is_read: true,
                    })),
                  );
                  setUnreadCount(0);
                } finally {
                  setMarkingAll(false);
                }
              }}
              className="inline-flex items-center gap-1 rounded-full border border-black/[0.1] px-2.5 py-1 text-[11px] font-semibold text-[#344054] disabled:opacity-50"
            >
              {markingAll ? <Loader2 size={12} className="animate-spin" /> : <CheckCheck size={12} />}
              Mark all read
            </button>
          </header>

          <div className="max-h-[360px] overflow-y-auto px-2 py-2">
            {loading ? (
              <div className="flex items-center gap-2 rounded-xl border border-black/[0.06] bg-[#fcfcfd] px-3 py-2 text-[12px] text-[#475467]">
                <Loader2 size={12} className="animate-spin" />
                Loading notifications...
              </div>
            ) : null}
            {!loading && error ? (
              <p className="rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#b42318]">
                {error}
              </p>
            ) : null}
            {!loading && !error && rows.length === 0 ? (
              <p className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] px-3 py-2 text-[12px] text-[#667085]">
                No notifications yet.
              </p>
            ) : null}
            {!loading && !error
              ? rows.map((row) => (
                  <button
                    key={row.id}
                    type="button"
                    onClick={async () => {
                      if (!row.is_read) {
                        try {
                          await markMarketplaceNotificationRead(row.id);
                        } catch {
                          // Keep navigation available even if mark-read fails.
                        }
                        setRows((previous) =>
                          previous.map((entry) =>
                            entry.id === row.id ? { ...entry, is_read: true } : entry,
                          ),
                        );
                        setUnreadCount((current) => Math.max(0, current - 1));
                      }
                      setOpen(false);
                      if (row.agent_id) {
                        onNavigate(`/developer?agent=${encodeURIComponent(String(row.agent_id))}`);
                        return;
                      }
                      onNavigate("/developer");
                    }}
                    className={`mb-1 w-full rounded-xl border px-3 py-2 text-left transition ${
                      row.is_read
                        ? "border-black/[0.06] bg-white hover:bg-[#f9fafb]"
                        : "border-[#bfdbfe] bg-[#eff6ff] hover:bg-[#e0ecff]"
                    }`}
                  >
                    <p className="text-[12px] font-semibold text-[#111827]">{row.message}</p>
                    {row.detail ? (
                      <p className="mt-1 line-clamp-2 text-[11px] text-[#475467]">{row.detail}</p>
                    ) : null}
                    <p className="mt-1 text-[10px] uppercase tracking-[0.08em] text-[#98a2b3]">
                      {formatDate(row.created_at)}
                    </p>
                  </button>
                ))
              : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}

export { MarketplaceNotificationBell };
export type { MarketplaceNotificationBellProps };
