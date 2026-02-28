import type { ChangeEvent, RefObject } from "react";
import { Upload } from "lucide-react";
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
  recentJobs: IngestionJob[];
  onRefreshIngestionJobs?: () => Promise<void>;
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
  recentJobs,
  onRefreshIngestionJobs,
}: UploadSidebarProps) {
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

      {uploadStatus ? <p className="mt-3 text-[12px] text-[#6e6e73]">{uploadStatus}</p> : null}

      <div className="mt-8">
        <div className="flex items-center justify-between">
          <p className="text-[12px] uppercase tracking-[0.08em] text-[#8d8d93]">Ingestion Jobs</p>
          <button
            onClick={() => void onRefreshIngestionJobs?.()}
            className="text-[12px] text-[#6e6e73] hover:text-[#1d1d1f]"
          >
            Refresh
          </button>
        </div>
        <div className="mt-3 space-y-2">
          {recentJobs.length === 0 ? (
            <p className="text-[12px] text-[#8d8d93]">No jobs yet.</p>
          ) : (
            recentJobs.map((job) => (
              <div key={job.id} className="rounded-xl border border-black/[0.06] bg-white px-3 py-2.5">
                <p className="truncate text-[12px] text-[#1d1d1f]">
                  {job.kind === "urls" ? "URL indexing" : "File indexing"}
                </p>
                <p className="text-[11px] text-[#8d8d93]">
                  {job.processed_items}/{job.total_items} | {job.status}
                </p>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export { UploadSidebar };
