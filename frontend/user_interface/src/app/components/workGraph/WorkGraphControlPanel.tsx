import type { RefObject } from "react";

type CollaboratorPresence = {
  userId: string;
  userLabel: string;
  nodeId: string;
  timestamp: string;
};

type NodeComment = {
  commentId: string;
  userId: string;
  userLabel: string;
  text: string;
  timestamp: string;
};

type WorkGraphControlPanelProps = {
  searchInputRef: RefObject<HTMLInputElement | null>;
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  statusFilter: string;
  onStatusFilterChange: (value: string) => void;
  roleFilter: string;
  onRoleFilterChange: (value: string) => void;
  roleOptions: string[];
  confidenceFilter: "all" | "low" | "medium_high";
  onConfidenceFilterChange: (value: "all" | "low" | "medium_high") => void;
  edgeFamilyFilter: string;
  onEdgeFamilyFilterChange: (value: string) => void;
  focusMode: boolean;
  onToggleFocusMode: () => void;
  onToggleCollapseSelectedNode: () => void;
  hasSelectedNode: boolean;
  onExpandAll: () => void;
  canExpandAll: boolean;
  visibleNodeCount: number;
  totalNodeCount: number;
  collaboratorPresence: CollaboratorPresence[];
  selectedNodeId: string | null;
  selectedNodeComments: NodeComment[];
  commentDraft: string;
  onCommentDraftChange: (value: string) => void;
  onSubmitNodeComment: () => void;
};

function WorkGraphControlPanel({
  searchInputRef,
  searchQuery,
  onSearchQueryChange,
  statusFilter,
  onStatusFilterChange,
  roleFilter,
  onRoleFilterChange,
  roleOptions,
  confidenceFilter,
  onConfidenceFilterChange,
  edgeFamilyFilter,
  onEdgeFamilyFilterChange,
  focusMode,
  onToggleFocusMode,
  onToggleCollapseSelectedNode,
  hasSelectedNode,
  onExpandAll,
  canExpandAll,
  visibleNodeCount,
  totalNodeCount,
  collaboratorPresence,
  selectedNodeId,
  selectedNodeComments,
  commentDraft,
  onCommentDraftChange,
  onSubmitNodeComment,
}: WorkGraphControlPanelProps) {
  return (
    <div className="mb-2 rounded-xl border border-[#d2d2d7] bg-white/90 px-3 py-2">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <input
          ref={searchInputRef}
          value={searchQuery}
          onChange={(event) => onSearchQueryChange(event.target.value)}
          placeholder="Search nodes (/)"
          className="h-8 rounded-lg border border-black/[0.08] bg-white px-2 text-[12px] text-[#1d1d1f] outline-none focus:border-[#3b82f6]"
        />
        <select
          value={statusFilter}
          onChange={(event) => onStatusFilterChange(event.target.value)}
          className="h-8 rounded-lg border border-black/[0.08] bg-white px-2 text-[12px] text-[#1d1d1f]"
        >
          <option value="all">All statuses</option>
          <option value="running">Running</option>
          <option value="blocked">Blocked</option>
          <option value="failed">Failed</option>
          <option value="completed">Completed</option>
          <option value="queued">Queued</option>
        </select>
        <select
          value={roleFilter}
          onChange={(event) => onRoleFilterChange(event.target.value)}
          className="h-8 rounded-lg border border-black/[0.08] bg-white px-2 text-[12px] text-[#1d1d1f]"
        >
          <option value="all">All roles</option>
          {roleOptions.map((role) => (
            <option key={role} value={role}>
              {role}
            </option>
          ))}
        </select>
        <select
          value={confidenceFilter}
          onChange={(event) =>
            onConfidenceFilterChange(event.target.value as "all" | "low" | "medium_high")
          }
          className="h-8 rounded-lg border border-black/[0.08] bg-white px-2 text-[12px] text-[#1d1d1f]"
        >
          <option value="all">All confidence</option>
          <option value="low">Low confidence</option>
          <option value="medium_high">Medium and high confidence</option>
        </select>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <select
          value={edgeFamilyFilter}
          onChange={(event) => onEdgeFamilyFilterChange(event.target.value)}
          className="h-8 rounded-lg border border-black/[0.08] bg-white px-2 text-[12px] text-[#1d1d1f]"
        >
          <option value="all">All edge families</option>
          <option value="hierarchy">Hierarchy</option>
          <option value="dependency">Dependency</option>
          <option value="evidence">Evidence</option>
          <option value="verification">Verification</option>
          <option value="handoff">Handoff</option>
        </select>
        <button
          type="button"
          onClick={onToggleFocusMode}
          className={`rounded-lg border px-2.5 py-1 text-[11px] transition ${
            focusMode
              ? "border-[#2563eb]/40 bg-[#eff6ff] text-[#1d4ed8]"
              : "border-black/[0.08] bg-white text-[#1d1d1f] hover:bg-[#f5f5f7]"
          }`}
          title="Toggle unresolved focus mode (U)"
        >
          {focusMode ? "Focus mode on" : "Focus mode off"}
        </button>
        <button
          type="button"
          onClick={onToggleCollapseSelectedNode}
          disabled={!hasSelectedNode}
          className="rounded-lg border border-black/[0.08] bg-white px-2.5 py-1 text-[11px] text-[#1d1d1f] transition hover:bg-[#f5f5f7] disabled:opacity-40"
          title="Collapse/expand selected branch (C)"
        >
          Toggle collapse
        </button>
        <button
          type="button"
          onClick={onExpandAll}
          disabled={!canExpandAll}
          className="rounded-lg border border-black/[0.08] bg-white px-2.5 py-1 text-[11px] text-[#1d1d1f] transition hover:bg-[#f5f5f7] disabled:opacity-40"
          title="Expand all branches (X)"
        >
          Expand all
        </button>
        <span className="text-[10px] text-[#6e6e73]">
          {visibleNodeCount}/{totalNodeCount} nodes visible
        </span>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Presence</span>
        {collaboratorPresence.length ? (
          collaboratorPresence.map((row) => (
            <span
              key={`${row.userId}:${row.nodeId}`}
              className="inline-flex items-center gap-1 rounded-full border border-black/[0.08] bg-[#f8f8fa] px-2 py-0.5 text-[10px] text-[#4c4c50]"
              title={`Viewing ${row.nodeId}`}
            >
              {row.userLabel}
              <span className="max-w-[90px] truncate text-[#6e6e73]">@{row.nodeId}</span>
            </span>
          ))
        ) : (
          <span className="text-[10px] text-[#6e6e73]">No active collaborators yet</span>
        )}
      </div>
      {selectedNodeId ? (
        <div className="mt-2 rounded-lg border border-black/[0.08] bg-[#fafafc] p-2">
          <p className="mb-1 text-[10px] uppercase tracking-wide text-[#8e8e93]">
            Comments for {selectedNodeId}
          </p>
          <div className="mb-1.5 max-h-20 space-y-1 overflow-y-auto pr-1">
            {selectedNodeComments.length ? (
              selectedNodeComments.map((comment) => (
                <p key={comment.commentId} className="text-[11px] text-[#1d1d1f]">
                  <span className="font-medium">{comment.userLabel}:</span> {comment.text}
                </p>
              ))
            ) : (
              <p className="text-[11px] text-[#6e6e73]">No comments yet.</p>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            <input
              value={commentDraft}
              onChange={(event) => onCommentDraftChange(event.target.value)}
              placeholder="Add node comment"
              className="h-7 flex-1 rounded-md border border-black/[0.08] bg-white px-2 text-[11px] text-[#1d1d1f] outline-none focus:border-[#3b82f6]"
            />
            <button
              type="button"
              onClick={onSubmitNodeComment}
              disabled={!String(commentDraft || "").trim()}
              className="h-7 rounded-md border border-black/[0.08] bg-white px-2 text-[11px] text-[#1d1d1f] transition hover:bg-[#f5f5f7] disabled:opacity-40"
            >
              Send
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export { WorkGraphControlPanel };
export type { CollaboratorPresence, NodeComment };
