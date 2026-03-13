import { useEffect, useMemo, useRef, useState, type ChangeEvent, type RefObject } from "react";
import { AlertCircle, CheckCircle2, Loader2, Upload, X } from "lucide-react";
import type { FileGroupRecord, IngestionJob } from "../../../api/client";
import { NeutralSelect } from "./NeutralSelect";
import type { UploadTab } from "./types";

interface UploadSidebarProps {
  fileGroups: FileGroupRecord[];
  uploadGroupId: string;
  setUploadGroupId: (value: string) => void;
  uploadTab: UploadTab;
  setUploadTab: (tab: UploadTab) => void;
  urlText: string;
  setUrlText: (value: string) => void;
  forceReindex: boolean;
  setForceReindex: (value: boolean) => void;
  isSubmitting: boolean;
  canUploadFilesToGroup: boolean;
  canIndexUrlsToGroup: boolean;
  handleUrlIndex: () => Promise<void>;
  handleFileInputChange: (event: ChangeEvent<HTMLInputElement>) => Promise<void>;
  fileInputRef: RefObject<HTMLInputElement | null>;
  uploadStatus: string;
  uploadProgressPercent?: number | null;
  uploadProgressLabel?: string;
  onCancelUpload?: () => Promise<void>;
  isCancelingUpload?: boolean;
  recentJobs: IngestionJob[];
}

const ACTIVE_JOB_STATUSES = new Set(["queued", "running"]);
const COMPLETED_VISIBLE_MS = 15000;

function normalizeJobStatus(value: unknown): string {
  return String(value ?? "")
    .toLowerCase()
    .trim()
    .replace(/\s+/g, " ");
}

function isActiveJob(job: IngestionJob): boolean {
  return ACTIVE_JOB_STATUSES.has(normalizeJobStatus(job.status));
}

function isFailedJob(job: IngestionJob): boolean {
  return normalizeJobStatus(job.status) === "failed";
}

function isCompletedJob(job: IngestionJob): boolean {
  return normalizeJobStatus(job.status) === "completed";
}

function parseTimestamp(value: string | null | undefined): number {
  if (!value) {
    return 0;
  }
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
}

function computeJobProgressPercent(job: IngestionJob): number | null {
  const totalBytes = Math.max(0, Number(job.bytes_total || 0));
  const indexedBytes = Math.max(0, Number(job.bytes_indexed || 0));
  if (totalBytes > 0) {
    return Math.max(0, Math.min(100, Math.round((indexedBytes / totalBytes) * 100)));
  }
  const totalItems = Math.max(0, Number(job.total_items || 0));
  const processedItems = Math.max(0, Number(job.processed_items || 0));
  if (totalItems > 0) {
    return Math.max(0, Math.min(100, Math.round((processedItems / totalItems) * 100)));
  }
  return null;
}

function jobKindLabel(job: IngestionJob): string {
  return job.kind === "urls" ? "URL indexing" : "File indexing";
}

function statusPillClass(status: string): string {
  const normalized = normalizeJobStatus(status);
  if (normalized === "failed") {
    return "border-[#d44848]/30 bg-[#fff2f2] text-[#b42323]";
  }
  if (normalized === "completed") {
    return "border-[#2f8f3e]/30 bg-[#eefaf0] text-[#1f7a32]";
  }
  if (normalized === "running") {
    return "border-black/[0.14] bg-[#f4f4f7] text-[#1d1d1f]";
  }
  return "border-black/[0.1] bg-[#f6f6f8] text-[#6e6e73]";
}

function formatJobMeta(job: IngestionJob): string {
  const processed = Math.max(0, Number(job.processed_items || 0));
  const total = Math.max(0, Number(job.total_items || 0));
  const normalized = normalizeJobStatus(job.status);
  return `${processed}/${total} ${normalized}`;
}

function formatRelativeTime(value: string | null | undefined): string {
  const timestamp = parseTimestamp(value);
  if (!timestamp) {
    return "";
  }
  const deltaMs = Date.now() - timestamp;
  if (deltaMs < 60_000) {
    return "just now";
  }
  const deltaMinutes = Math.round(deltaMs / 60_000);
  if (deltaMinutes < 60) {
    return `${deltaMinutes}m ago`;
  }
  const deltaHours = Math.round(deltaMinutes / 60);
  if (deltaHours < 24) {
    return `${deltaHours}h ago`;
  }
  return new Date(timestamp).toLocaleDateString([], { month: "short", day: "numeric" });
}

function UploadSidebar({
  fileGroups,
  uploadGroupId,
  setUploadGroupId,
  uploadTab,
  setUploadTab,
  urlText,
  setUrlText,
  forceReindex,
  setForceReindex,
  isSubmitting,
  canUploadFilesToGroup,
  canIndexUrlsToGroup,
  handleUrlIndex,
  handleFileInputChange,
  fileInputRef,
  uploadStatus,
  uploadProgressPercent = null,
  uploadProgressLabel = "",
  onCancelUpload,
  isCancelingUpload = false,
  recentJobs,
}: UploadSidebarProps) {
  const [showActivityModal, setShowActivityModal] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const urlTextAreaRef = useRef<HTMLTextAreaElement | null>(null);

  const sortedJobs = useMemo(
    () =>
      [...recentJobs].sort(
        (left, right) =>
          parseTimestamp(right.date_created || right.date_updated || null) -
          parseTimestamp(left.date_created || left.date_updated || null),
      ),
    [recentJobs],
  );
  const activeJobs = useMemo(() => sortedJobs.filter((job) => isActiveJob(job)), [sortedJobs]);
  const failedJobs = useMemo(() => sortedJobs.filter((job) => isFailedJob(job)), [sortedJobs]);
  const recentlyCompletedJobs = useMemo(
    () =>
      sortedJobs.filter((job) => {
        if (!isCompletedJob(job)) {
          return false;
        }
        const finishedAt = parseTimestamp(job.date_finished || job.date_updated || job.date_created);
        if (!finishedAt) {
          return false;
        }
        return nowMs - finishedAt <= COMPLETED_VISIBLE_MS;
      }),
    [sortedJobs, nowMs],
  );

  useEffect(() => {
    if (recentlyCompletedJobs.length === 0) {
      return;
    }
    const timerId = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);
    return () => window.clearInterval(timerId);
  }, [recentlyCompletedJobs.length]);

  useEffect(() => {
    if (!showActivityModal) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setShowActivityModal(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showActivityModal]);

  const hasActiveFileJob = recentJobs.some(
    (job) => job.kind === "files" && (job.status === "queued" || job.status === "running"),
  );
  const showCancelUpload = Boolean(
    onCancelUpload && (isSubmitting || hasActiveFileJob || typeof uploadProgressPercent === "number"),
  );
  const hasActiveJobs = activeJobs.length > 0;
  const hasFailedJobs = failedJobs.length > 0;
  const hasRecentCompleted = recentlyCompletedJobs.length > 0;
  const primaryActiveJob = activeJobs[0] || null;
  const primaryFailedJob = failedJobs[0] || null;
  const compactProgressPercent =
    typeof uploadProgressPercent === "number"
      ? Math.max(0, Math.min(100, uploadProgressPercent))
      : primaryActiveJob
        ? computeJobProgressPercent(primaryActiveJob)
        : null;

  const compactTitle = hasActiveJobs
    ? activeJobs.length > 1
      ? `Indexing ${activeJobs.length} jobs`
      : jobKindLabel(activeJobs[0])
    : hasFailedJobs
      ? failedJobs.length > 1
        ? `${failedJobs.length} jobs need attention`
        : `${jobKindLabel(failedJobs[0])} failed`
      : hasRecentCompleted
        ? "Indexing complete"
        : "";
  const shouldShowCompactStatus =
    hasActiveJobs || hasFailedJobs || hasRecentCompleted || showCancelUpload;
  const compactDetail = hasActiveJobs
    ? uploadStatus || uploadProgressLabel || formatJobMeta(activeJobs[0])
    : hasFailedJobs
      ? uploadStatus || primaryFailedJob?.errors?.[0] || primaryFailedJob?.message || "Fix and retry upload."
      : uploadStatus || "Your latest ingestion finished.";

  const retryJob = (job: IngestionJob | null) => {
    if (!job) {
      return;
    }
    if (job.kind === "urls") {
      setUploadTab("webLinks");
      window.requestAnimationFrame(() => {
        urlTextAreaRef.current?.focus();
      });
    } else {
      setUploadTab("upload");
      window.requestAnimationFrame(() => {
        fileInputRef.current?.click();
      });
    }
    setShowActivityModal(false);
  };

  return (
    <div className="w-[320px] min-h-0 overflow-y-auto border-r border-black/[0.06] bg-white px-6 py-8">
      <p className="text-[18px] font-semibold tracking-tight text-[#1d1d1f]">Upload Files</p>
      <p className="mt-1 text-[13px] text-[#6e6e73]">Upload into a selected group.</p>

      <p className="mt-6 text-[11px] uppercase tracking-[0.08em] text-[#8d8d93]">Destination Group</p>
      <NeutralSelect
        value={uploadGroupId}
        placeholder={fileGroups.length ? "Choose group" : "Create a group first"}
        disabled={fileGroups.length === 0}
        options={fileGroups.map((group) => ({ value: group.id, label: group.name }))}
        onChange={setUploadGroupId}
        buttonClassName="mt-2 h-11 w-full rounded-xl border border-black/[0.08] bg-white px-3 text-[13px] text-[#1d1d1f]"
      />

      <div className="mt-6 rounded-3xl border border-black/[0.06] bg-[#fafafc] p-5">
        <div className="inline-flex rounded-full border border-black/[0.06] bg-white p-1">
          <button
            onClick={() => setUploadTab("upload")}
            className={`rounded-full px-4 py-1.5 text-[12px] ${
              uploadTab === "upload" ? "bg-[#1d1d1f] text-white" : "text-[#6e6e73]"
            }`}
          >
            Files
          </button>
          <button
            onClick={() => setUploadTab("webLinks")}
            className={`rounded-full px-4 py-1.5 text-[12px] ${
              uploadTab === "webLinks" ? "bg-[#1d1d1f] text-white" : "text-[#6e6e73]"
            }`}
          >
            Links
          </button>
        </div>

        {uploadTab === "upload" ? (
          <>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(event) => void handleFileInputChange(event)}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isSubmitting || !canUploadFilesToGroup}
              className="mt-5 w-full rounded-2xl border border-black/[0.08] bg-white px-6 py-14 text-center transition-colors hover:bg-[#fcfcfd] disabled:opacity-50"
            >
              <Upload className="mx-auto mb-3 h-8 w-8 text-[#8d8d93]" />
              <p className="text-[15px] text-[#1d1d1f]">Drag files here</p>
              <p className="mt-1 text-[14px] text-[#6e6e73]">or click to browse</p>
            </button>
          </>
        ) : (
          <textarea
            ref={urlTextAreaRef}
            value={urlText}
            onChange={(event) => setUrlText(event.target.value)}
            placeholder="https://example.com"
            className="mt-5 min-h-[140px] w-full rounded-2xl border border-black/[0.08] bg-white px-3 py-3 text-[13px] text-[#1d1d1f] placeholder:text-[#8d8d93] focus:outline-none focus:ring-2 focus:ring-black/10"
          />
        )}

        <div className="mt-5 flex items-center justify-between">
          <span className="text-[13px] text-[#1d1d1f]">Force reindex</span>
          <button
            type="button"
            role="switch"
            aria-checked={forceReindex}
            onClick={() => setForceReindex(!forceReindex)}
            className={`relative h-6 w-11 rounded-full transition-colors ${
              forceReindex ? "bg-[#1d1d1f]" : "bg-[#d7d7dc]"
            }`}
          >
            <span
              className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                forceReindex ? "translate-x-[22px]" : "translate-x-[2px]"
              }`}
            />
          </button>
        </div>

        <button
          type="button"
          onClick={() => (uploadTab === "upload" ? fileInputRef.current?.click() : void handleUrlIndex())}
          disabled={isSubmitting || (uploadTab === "upload" ? !canUploadFilesToGroup : !canIndexUrlsToGroup)}
          className="mt-5 h-11 w-full rounded-xl bg-[#1d1d1f] text-[14px] text-white hover:bg-[#2c2c30] disabled:opacity-40"
        >
          {uploadTab === "upload" ? "Upload to Group" : "Index URLs to Group"}
        </button>
      </div>

      {shouldShowCompactStatus ? (
        <div className="mt-4 rounded-2xl border border-black/[0.08] bg-white p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-[13px] font-semibold text-[#1d1d1f]">{compactTitle || "Upload status"}</p>
              <p className="mt-0.5 truncate text-[11px] text-[#6e6e73]">{compactDetail}</p>
            </div>
            {hasActiveJobs ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-black/[0.1] bg-[#f4f4f7] px-2 py-0.5 text-[10px] font-medium text-[#1d1d1f]">
                <Loader2 className="h-3 w-3 animate-spin" />
                <span>Indexing</span>
              </span>
            ) : hasFailedJobs ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-[#d44848]/30 bg-[#fff2f2] px-2 py-0.5 text-[10px] font-medium text-[#b42323]">
                <AlertCircle className="h-3 w-3" />
                <span>Failed</span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full border border-[#2f8f3e]/30 bg-[#eefaf0] px-2 py-0.5 text-[10px] font-medium text-[#1f7a32]">
                <CheckCircle2 className="h-3 w-3" />
                <span>Done</span>
              </span>
            )}
          </div>
          {typeof compactProgressPercent === "number" ? (
            <div className="mt-2">
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-black/[0.08]">
                <div
                  className="h-full rounded-full bg-[#1d1d1f] transition-[width] duration-300"
                  style={{ width: `${compactProgressPercent}%` }}
                />
              </div>
              <p className="mt-1 text-[10px] text-[#8d8d93]">
                {uploadProgressLabel || `Progress ${compactProgressPercent}%`}
              </p>
            </div>
          ) : null}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {showCancelUpload ? (
              <button
                type="button"
                onClick={() => void onCancelUpload?.()}
                disabled={isCancelingUpload}
                className="inline-flex h-8 items-center justify-center rounded-xl border border-black/[0.1] bg-white px-3 text-[12px] font-medium text-[#1d1d1f] transition-colors hover:bg-[#f6f6f8] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isCancelingUpload ? "Canceling..." : "Cancel"}
              </button>
            ) : null}
            {hasFailedJobs ? (
              <button
                type="button"
                onClick={() => retryJob(primaryFailedJob)}
                className="inline-flex h-8 items-center justify-center rounded-xl border border-black/[0.1] bg-white px-3 text-[12px] font-medium text-[#1d1d1f] transition-colors hover:bg-[#f6f6f8]"
              >
                Retry
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => setShowActivityModal(true)}
              className="inline-flex h-8 items-center justify-center rounded-xl border border-black/[0.1] bg-white px-3 text-[12px] font-medium text-[#1d1d1f] transition-colors hover:bg-[#f6f6f8]"
            >
              View details
            </button>
          </div>
        </div>
      ) : null}
      <button
        type="button"
        onClick={() => setShowActivityModal(true)}
        className="mt-3 inline-flex h-9 items-center justify-center rounded-xl border border-black/[0.1] bg-white px-3 text-[12px] font-medium text-[#1d1d1f] transition-colors hover:bg-[#f6f6f8]"
      >
        Upload activity
      </button>

      {showActivityModal ? (
        <div
          className="fixed inset-0 z-[150] flex items-center justify-center p-4"
          onClick={() => setShowActivityModal(false)}
          role="dialog"
          aria-modal="true"
          aria-label="Upload activity"
        >
          <div className="absolute inset-0 bg-black/35 backdrop-blur-[10px]" />
          <div
            className="relative z-[151] flex max-h-[80vh] w-full max-w-[640px] flex-col overflow-hidden rounded-2xl border border-black/[0.12] bg-white shadow-[0_26px_70px_rgba(0,0,0,0.28)]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3 border-b border-black/[0.08] px-5 py-4">
              <div className="min-w-0">
                <p className="truncate text-[16px] font-semibold text-[#1d1d1f]">Upload activity</p>
                <p className="mt-0.5 text-[12px] text-[#6e6e73]">
                  Auto-refresh runs while indexing is active.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowActivityModal(false)}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-black/[0.08] text-[#6e6e73] transition-colors hover:bg-[#f5f5f7] hover:text-[#1d1d1f]"
                aria-label="Close upload activity"
                title="Close"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-5 py-4">
              {sortedJobs.length === 0 ? (
                <p className="text-[13px] text-[#8d8d93]">No ingestion jobs yet.</p>
              ) : (
                sortedJobs.map((job) => (
                  <div key={job.id} className="rounded-xl border border-black/[0.08] bg-[#fafafc] px-3 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-[13px] font-medium text-[#1d1d1f]">{jobKindLabel(job)}</p>
                      <span
                        className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-medium ${statusPillClass(job.status)}`}
                      >
                        {normalizeJobStatus(job.status) || "unknown"}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-[#6e6e73]">{formatJobMeta(job)}</p>
                    <p className="mt-0.5 text-[11px] text-[#8d8d93]">
                      {formatRelativeTime(job.date_updated || job.date_created || null)}
                    </p>
                    {job.message ? (
                      <p className="mt-1 truncate text-[11px] text-[#6e6e73]">{job.message}</p>
                    ) : null}
                    {job.errors?.length ? (
                      <p className="mt-1 truncate text-[11px] text-[#b42323]">{job.errors[0]}</p>
                    ) : null}
                    {isFailedJob(job) ? (
                      <div className="mt-2">
                        <button
                          type="button"
                          onClick={() => retryJob(job)}
                          className="inline-flex h-8 items-center justify-center rounded-xl border border-black/[0.1] bg-white px-3 text-[12px] font-medium text-[#1d1d1f] transition-colors hover:bg-[#f6f6f8]"
                        >
                          Retry
                        </button>
                      </div>
                    ) : null}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export { UploadSidebar };
