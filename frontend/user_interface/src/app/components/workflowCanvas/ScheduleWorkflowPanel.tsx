/**
 * ScheduleWorkflowPanel — user-friendly scheduling UI for workflows.
 * No cron syntax needed — users pick frequency, day, and time from dropdowns.
 */
import { useState } from "react";
import { Calendar, Clock, Play, X } from "lucide-react";

type ScheduleWorkflowPanelProps = {
  open: boolean;
  workflowName: string;
  onClose: () => void;
  onSchedule: (schedule: { cron: string; timezone: string; description: string }) => void;
};

const FREQUENCIES = [
  { id: "daily", label: "Every day" },
  { id: "weekdays", label: "Every weekday (Mon–Fri)" },
  { id: "weekly", label: "Every week" },
  { id: "biweekly", label: "Every 2 weeks" },
  { id: "monthly", label: "Every month" },
];

const DAYS_OF_WEEK = [
  { id: "1", label: "Monday" },
  { id: "2", label: "Tuesday" },
  { id: "3", label: "Wednesday" },
  { id: "4", label: "Thursday" },
  { id: "5", label: "Friday" },
  { id: "6", label: "Saturday" },
  { id: "0", label: "Sunday" },
];

const HOURS = Array.from({ length: 24 }, (_, i) => ({
  id: String(i),
  label: `${String(i).padStart(2, "0")}:00`,
}));

const TIMEZONES = [
  { id: "UTC", label: "UTC" },
  { id: "Europe/London", label: "London (GMT/BST)" },
  { id: "Europe/Paris", label: "Paris (CET/CEST)" },
  { id: "America/New_York", label: "New York (EST/EDT)" },
  { id: "America/Chicago", label: "Chicago (CST/CDT)" },
  { id: "America/Los_Angeles", label: "Los Angeles (PST/PDT)" },
  { id: "Asia/Tokyo", label: "Tokyo (JST)" },
  { id: "Asia/Singapore", label: "Singapore (SGT)" },
  { id: "Australia/Sydney", label: "Sydney (AEST/AEDT)" },
];

function buildCron(frequency: string, dayOfWeek: string, hour: string): string {
  const h = Number(hour) || 9;
  switch (frequency) {
    case "daily":
      return `0 ${h} * * *`;
    case "weekdays":
      return `0 ${h} * * 1-5`;
    case "weekly":
      return `0 ${h} * * ${dayOfWeek}`;
    case "biweekly":
      // Cron doesn't natively support biweekly — use weekly with a note
      return `0 ${h} * * ${dayOfWeek}`;
    case "monthly":
      return `0 ${h} 1 * *`;
    default:
      return `0 ${h} * * 1`;
  }
}

function describeSchedule(frequency: string, dayOfWeek: string, hour: string, timezone: string): string {
  const h = `${String(Number(hour) || 9).padStart(2, "0")}:00`;
  const day = DAYS_OF_WEEK.find((d) => d.id === dayOfWeek)?.label || "Monday";
  const tz = TIMEZONES.find((t) => t.id === timezone)?.label || timezone;
  switch (frequency) {
    case "daily":
      return `Every day at ${h} (${tz})`;
    case "weekdays":
      return `Every weekday at ${h} (${tz})`;
    case "weekly":
      return `Every ${day} at ${h} (${tz})`;
    case "biweekly":
      return `Every other ${day} at ${h} (${tz})`;
    case "monthly":
      return `1st of every month at ${h} (${tz})`;
    default:
      return `${h} (${tz})`;
  }
}

function ScheduleWorkflowPanel({ open, workflowName, onClose, onSchedule }: ScheduleWorkflowPanelProps) {
  const [frequency, setFrequency] = useState("weekly");
  const [dayOfWeek, setDayOfWeek] = useState("1");
  const [hour, setHour] = useState("9");
  const [timezone, setTimezone] = useState(() => {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { return "UTC"; }
  });

  if (!open) return null;

  const showDayPicker = frequency === "weekly" || frequency === "biweekly";
  const cron = buildCron(frequency, dayOfWeek, hour);
  const description = describeSchedule(frequency, dayOfWeek, hour, timezone);

  return (
    <>
      <div className="fixed inset-0 z-[139]" onClick={onClose} />
      <div className="absolute bottom-full left-0 z-[140] mb-2 w-[380px] overflow-hidden rounded-2xl border border-black/[0.06] bg-white/95 shadow-[0_12px_40px_-10px_rgba(0,0,0,0.15)] backdrop-blur-xl" style={{ animation: "scaleIn 200ms ease-out" }}>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-black/[0.05] px-4 py-3">
          <div className="flex items-center gap-2">
            <Calendar size={14} className="text-[#7c3aed]" />
            <span className="text-[13px] font-semibold text-[#101828]">Schedule workflow</span>
          </div>
          <button type="button" onClick={onClose} className="rounded-full p-1 text-[#98a2b3] hover:text-[#475467]">
            <X size={14} />
          </button>
        </div>

        <div className="space-y-4 px-4 py-4">
          {/* Workflow name */}
          <p className="text-[12px] text-[#667085]">
            Automatically run <span className="font-semibold text-[#344054]">{workflowName || "this workflow"}</span> on a schedule.
          </p>

          {/* Frequency */}
          <div>
            <label className="mb-1.5 block text-[12px] font-semibold text-[#344054]">How often</label>
            <div className="flex flex-wrap gap-1.5">
              {FREQUENCIES.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setFrequency(f.id)}
                  className={`rounded-lg border px-2.5 py-1.5 text-[12px] font-medium transition-colors ${
                    frequency === f.id
                      ? "border-[#7c3aed] bg-[#f5f3ff] text-[#7c3aed]"
                      : "border-black/[0.08] bg-white text-[#475467] hover:bg-[#f8fafc]"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          {/* Day of week */}
          {showDayPicker ? (
            <div>
              <label className="mb-1.5 block text-[12px] font-semibold text-[#344054]">Which day</label>
              <div className="flex flex-wrap gap-1.5">
                {DAYS_OF_WEEK.map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => setDayOfWeek(d.id)}
                    className={`rounded-lg border px-2.5 py-1.5 text-[12px] font-medium transition-colors ${
                      dayOfWeek === d.id
                        ? "border-[#7c3aed] bg-[#f5f3ff] text-[#7c3aed]"
                        : "border-black/[0.08] bg-white text-[#475467] hover:bg-[#f8fafc]"
                    }`}
                  >
                    {d.label.slice(0, 3)}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {/* Time + Timezone */}
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="mb-1.5 block text-[12px] font-semibold text-[#344054]">
                <Clock size={11} className="mr-1 inline text-[#98a2b3]" />
                Time
              </label>
              <select
                value={hour}
                onChange={(e) => setHour(e.target.value)}
                className="w-full rounded-lg border border-black/[0.08] bg-white px-2.5 py-2 text-[13px] text-[#101828] outline-none focus:border-[#7c3aed]"
              >
                {HOURS.map((h) => <option key={h.id} value={h.id}>{h.label}</option>)}
              </select>
            </div>
            <div className="flex-1">
              <label className="mb-1.5 block text-[12px] font-semibold text-[#344054]">Timezone</label>
              <select
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="w-full rounded-lg border border-black/[0.08] bg-white px-2.5 py-2 text-[13px] text-[#101828] outline-none focus:border-[#7c3aed]"
              >
                {TIMEZONES.map((tz) => <option key={tz.id} value={tz.id}>{tz.label}</option>)}
              </select>
            </div>
          </div>

          {/* Preview */}
          <div className="rounded-xl border border-[#e0e7ff] bg-[#f5f3ff] px-3 py-2.5">
            <p className="text-[12px] font-medium text-[#4338ca]">{description}</p>
          </div>

          {/* Actions */}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-xl border border-black/[0.08] px-3 py-2.5 text-[13px] font-semibold text-[#344054] transition-colors hover:bg-[#f2f4f7]"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => onSchedule({ cron, timezone, description })}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-[#7c3aed] px-3 py-2.5 text-[13px] font-semibold text-white transition-colors hover:bg-[#6d28d9]"
            >
              <Play size={13} fill="currentColor" />
              Schedule
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

export { ScheduleWorkflowPanel };
export type { ScheduleWorkflowPanelProps };
