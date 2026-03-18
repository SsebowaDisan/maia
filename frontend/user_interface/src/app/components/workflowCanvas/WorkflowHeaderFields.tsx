import { useCallback, useEffect, useRef, useState } from "react";
import { Calendar, ChevronDown, ChevronRight, Clock, Settings } from "lucide-react";
import { toast } from "sonner";

import { useWorkflowStore } from "../../stores/workflowStore";

type WorkflowHeaderFieldsProps = {
  onBackToGallery?: () => void;
};

// ── Schedule helpers ──────────────────────────────────────────────────────────

const FREQUENCIES = [
  { id: "daily", label: "Every day" },
  { id: "weekdays", label: "Weekdays" },
  { id: "weekly", label: "Weekly" },
  { id: "monthly", label: "Monthly" },
];

const DAYS = [
  { id: "1", label: "Mon" }, { id: "2", label: "Tue" }, { id: "3", label: "Wed" },
  { id: "4", label: "Thu" }, { id: "5", label: "Fri" }, { id: "6", label: "Sat" }, { id: "0", label: "Sun" },
];

const HOURS = Array.from({ length: 24 }, (_, i) => ({
  id: String(i),
  label: `${String(i).padStart(2, "0")}:00`,
}));

function buildCron(freq: string, day: string, hour: string): string {
  const h = Number(hour) || 9;
  if (freq === "daily") return `0 ${h} * * *`;
  if (freq === "weekdays") return `0 ${h} * * 1-5`;
  if (freq === "weekly") return `0 ${h} * * ${day}`;
  if (freq === "monthly") return `0 ${h} 1 * *`;
  return `0 ${h} * * 1`;
}

function describeCron(freq: string, day: string, hour: string): string {
  const h = `${String(Number(hour) || 9).padStart(2, "0")}:00`;
  const d = DAYS.find((x) => x.id === day)?.label || "Mon";
  if (freq === "daily") return `Daily at ${h}`;
  if (freq === "weekdays") return `Weekdays at ${h}`;
  if (freq === "weekly") return `${d} at ${h}`;
  if (freq === "monthly") return `1st of month at ${h}`;
  return `${h}`;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function WorkflowHeaderFields({ onBackToGallery }: WorkflowHeaderFieldsProps) {
  const workflowName = useWorkflowStore((state) => state.workflowName);
  const workflowDescription = useWorkflowStore((state) => state.workflowDescription);
  const isDirty = useWorkflowStore((state) => state.isDirty);
  const setMetadata = useWorkflowStore((state) => state.setMetadata);

  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [scheduleFreq, setScheduleFreq] = useState("weekly");
  const [scheduleDay, setScheduleDay] = useState("1");
  const [scheduleHour, setScheduleHour] = useState("9");
  const inputRef = useRef<HTMLInputElement | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const displayName = String(workflowName || "").trim() || "Untitled workflow";

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  useEffect(() => {
    if (!settingsOpen) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current) return;
      if (event.target && !rootRef.current.contains(event.target as Node)) {
        setSettingsOpen(false);
      }
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSettingsOpen(false);
    };
    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleEscape);
    };
  }, [settingsOpen]);

  const commitEdit = useCallback(() => {
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== workflowName) {
      setMetadata({ workflowName: trimmed });
    }
    setEditing(false);
  }, [editValue, workflowName, setMetadata]);

  const startEditing = useCallback(() => {
    setEditValue(displayName);
    setEditing(true);
    setSettingsOpen(false);
  }, [displayName]);

  const handleSaveSchedule = async () => {
    const wfId = useWorkflowStore.getState().workflowId;
    if (!wfId) {
      toast.error("Save the workflow first before scheduling.");
      return;
    }
    const cron = buildCron(scheduleFreq, scheduleDay, scheduleHour);
    const desc = describeCron(scheduleFreq, scheduleDay, scheduleHour);
    try {
      const response = await fetch("/api/agent/schedules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: `${workflowName} — ${desc}`,
          prompt: `Run workflow ${wfId}`,
          frequency: cron,
          enabled: true,
        }),
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `${response.status}`);
      }
      toast.success(`Scheduled: ${desc}`);
    } catch (err) {
      toast.error(`Failed to schedule: ${String(err)}`);
    }
  };

  return (
    <div ref={rootRef} className="relative inline-flex items-center">
      {/* Breadcrumb pill */}
      <div className="inline-flex h-8 items-center rounded-lg bg-black/[0.04] backdrop-blur-xl transition-colors hover:bg-black/[0.06]">
        {onBackToGallery ? (
          <>
            <button type="button" onClick={onBackToGallery} className="flex h-full items-center px-3 text-[13px] font-medium text-[#86868b] transition-colors hover:text-[#1d1d1f]">
              Workflows
            </button>
            <ChevronRight size={12} strokeWidth={2} className="shrink-0 text-[#c7c7cc]" />
          </>
        ) : null}

        {editing ? (
          <input
            ref={inputRef}
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={commitEdit}
            onKeyDown={(e) => { if (e.key === "Enter") commitEdit(); if (e.key === "Escape") setEditing(false); }}
            className="h-full min-w-[80px] max-w-[200px] bg-transparent px-2.5 text-[13px] font-medium text-[#1d1d1f] outline-none selection:bg-[#0071e3]/20"
            style={{ width: `${Math.max(80, editValue.length * 7.5 + 24)}px` }}
          />
        ) : (
          <button type="button" onDoubleClick={startEditing} onClick={() => setSettingsOpen((v) => !v)} className="flex h-full cursor-default items-center gap-1.5 px-2.5">
            <span className="max-w-[180px] truncate text-[13px] font-medium text-[#1d1d1f]">{displayName}</span>
            {isDirty ? <span className="h-[5px] w-[5px] rounded-full bg-[#1d1d1f]/50" /> : null}
          </button>
        )}

        {!editing ? (
          <button type="button" onClick={() => setSettingsOpen((v) => !v)} className="flex h-full items-center border-l border-black/[0.08] px-2 text-[#86868b] transition-colors hover:text-[#1d1d1f]">
            <ChevronDown size={11} strokeWidth={2.5} className={`transition-transform duration-200 ${settingsOpen ? "rotate-180" : ""}`} />
          </button>
        ) : null}
      </div>

      {/* Settings panel */}
      {settingsOpen ? (
        <div className="absolute right-0 top-[calc(100%+6px)] z-[190] w-[320px] overflow-hidden rounded-2xl border border-black/[0.08] bg-white/95 shadow-[0_12px_40px_-12px_rgba(0,0,0,0.18)] backdrop-blur-2xl" style={{ animation: "scaleIn 200ms ease-out" }}>
          <div className="flex items-center gap-2 border-b border-black/[0.05] px-4 py-2.5">
            <Settings size={13} className="text-[#86868b]" />
            <span className="text-[12px] font-semibold text-[#667085]">Workflow settings</span>
          </div>

          <div className="space-y-3 px-4 py-3">
            {/* Name */}
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold text-[#344054]">Name</span>
              <input
                value={workflowName}
                onChange={(e) => setMetadata({ workflowName: e.target.value.slice(0, 60) })}
                maxLength={60}
                placeholder="Workflow name"
                className="w-full rounded-lg border border-black/[0.08] bg-[#f8fafc] px-2.5 py-1.5 text-[13px] text-[#1d1d1f] outline-none focus:border-[#7c3aed]"
              />
            </label>

            {/* Description */}
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold text-[#344054]">Description</span>
              <input
                value={workflowDescription}
                onChange={(e) => setMetadata({ workflowDescription: e.target.value })}
                placeholder="What does this workflow do?"
                className="w-full rounded-lg border border-black/[0.08] bg-[#f8fafc] px-2.5 py-1.5 text-[13px] text-[#1d1d1f] outline-none focus:border-[#7c3aed]"
              />
            </label>

            {/* Divider */}
            <div className="border-t border-black/[0.06]" />

            {/* Schedule */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-[11px] font-semibold text-[#344054]">
                  <Calendar size={12} className="text-[#7c3aed]" />
                  Schedule
                </span>
                <button
                  type="button"
                  onClick={() => setScheduleEnabled((v) => !v)}
                  className={`relative h-5 w-9 rounded-full transition-colors ${scheduleEnabled ? "bg-[#7c3aed]" : "bg-black/[0.12]"}`}
                >
                  <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${scheduleEnabled ? "translate-x-4" : "translate-x-0.5"}`} />
                </button>
              </div>

              {scheduleEnabled ? (
                <div className="space-y-2.5 rounded-xl border border-[#e0e7ff] bg-[#f5f3ff] p-3">
                  {/* Frequency */}
                  <div className="flex flex-wrap gap-1">
                    {FREQUENCIES.map((f) => (
                      <button key={f.id} type="button" onClick={() => setScheduleFreq(f.id)} className={`rounded-md border px-2 py-1 text-[11px] font-medium transition-colors ${scheduleFreq === f.id ? "border-[#7c3aed] bg-white text-[#7c3aed]" : "border-transparent text-[#667085] hover:text-[#344054]"}`}>
                        {f.label}
                      </button>
                    ))}
                  </div>

                  {/* Day picker */}
                  {scheduleFreq === "weekly" ? (
                    <div className="flex gap-1">
                      {DAYS.map((d) => (
                        <button key={d.id} type="button" onClick={() => setScheduleDay(d.id)} className={`flex-1 rounded-md border py-1 text-[10px] font-semibold transition-colors ${scheduleDay === d.id ? "border-[#7c3aed] bg-white text-[#7c3aed]" : "border-transparent text-[#667085]"}`}>
                          {d.label}
                        </button>
                      ))}
                    </div>
                  ) : null}

                  {/* Time */}
                  <div className="flex items-center gap-2">
                    <Clock size={11} className="text-[#7c3aed]" />
                    <select value={scheduleHour} onChange={(e) => setScheduleHour(e.target.value)} className="rounded-md border border-[#c7d2fe] bg-white px-2 py-1 text-[12px] text-[#344054] outline-none">
                      {HOURS.map((h) => <option key={h.id} value={h.id}>{h.label}</option>)}
                    </select>
                    <span className="ml-auto text-[11px] text-[#7c3aed]">{describeCron(scheduleFreq, scheduleDay, scheduleHour)}</span>
                  </div>

                  <button
                    type="button"
                    onClick={() => { void handleSaveSchedule(); setSettingsOpen(false); }}
                    className="w-full rounded-lg bg-[#7c3aed] py-1.5 text-[12px] font-semibold text-white transition-colors hover:bg-[#6d28d9]"
                  >
                    Save schedule
                  </button>
                </div>
              ) : (
                <p className="text-[11px] text-[#98a2b3]">Enable to run this workflow automatically on a schedule.</p>
              )}
            </div>
          </div>

          <div className="border-t border-black/[0.05] px-4 py-2">
            <button type="button" onClick={() => setSettingsOpen(false)} className="w-full rounded-lg bg-black/[0.04] py-1.5 text-[12px] font-medium text-[#86868b] transition hover:bg-black/[0.06] hover:text-[#1d1d1f]">
              Done
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
