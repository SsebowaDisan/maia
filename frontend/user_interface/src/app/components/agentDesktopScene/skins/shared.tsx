import type { ApiFieldDiff, ApiSceneState, ApiValidationCheck } from "../api_scene_state";
import type { SkinDescriptor, SkinPalette } from "./skinTypes";

// ── Status tone (reusable across all skins) ──────────────────────────────────
function statusTone(status: string): string {
  const n = String(status || "").trim().toLowerCase();
  if (n === "failed") return "border-[#f1b7b7] bg-[#fff5f5] text-[#9a2323]";
  if (n === "completed" || n === "success") return "border-[#bfd9c3] bg-[#f3fbf4] text-[#245437]";
  return "border-[#d2d2d7] bg-[#f5f5f7] text-[#3a3a3c]";
}

function validationTone(status: "passed" | "failed" | "pending"): string {
  if (status === "failed") return "border-[#f1b7b7] bg-[#fff5f5] text-[#9a2323]";
  if (status === "passed") return "border-[#bfd9c3] bg-[#f3fbf4] text-[#245437]";
  return "border-[#d2d2d7] bg-[#f5f5f7] text-[#3a3a3c]";
}

// ── Shell — wraps every skin ─────────────────────────────────────────────────
function SkinShell({
  palette,
  children,
}: {
  palette: SkinPalette;
  children: React.ReactNode;
}) {
  return (
    <div className={`absolute inset-0 px-5 py-4 ${palette.shellGradient}`}>
      <div
        className={`mx-auto flex h-full w-full max-w-[920px] flex-col gap-3 rounded-2xl border ${palette.cardBorder} ${palette.cardBg} p-4 shadow-[0_16px_48px_rgba(2,6,23,0.35)] overflow-y-auto`}
      >
        {children}
      </div>
    </div>
  );
}

// ── Header — brand label + title + status pill ───────────────────────────────
function SkinHeader({
  palette,
  descriptor,
  title,
  status,
  subtitle,
}: {
  palette: SkinPalette;
  descriptor: SkinDescriptor;
  title: string;
  status: string;
  subtitle?: string;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <p className={`text-[11px] uppercase tracking-[0.11em] ${palette.textSecondary}`}>
          {descriptor.brand} — {descriptor.theatreLabel}
        </p>
        <h3 className={`mt-1 truncate text-[20px] font-semibold leading-tight ${palette.textPrimary}`}>
          {title}
        </h3>
        {subtitle ? (
          <p className={`mt-1 text-[13px] ${palette.textSecondary}`}>{subtitle}</p>
        ) : null}
      </div>
      <div className={`shrink-0 rounded-full border px-3 py-1 text-[12px] font-semibold ${statusTone(status)}`}>
        {status || "in_progress"}
      </div>
    </div>
  );
}

// ── Info Grid — 3-column metadata ────────────────────────────────────────────
function InfoCell({
  label,
  value,
  sub,
  palette,
}: {
  label: string;
  value: string;
  sub?: string;
  palette: SkinPalette;
}) {
  return (
    <div className={`rounded-xl border ${palette.cardBorder} bg-white/60 p-3`}>
      <p className={`text-[11px] uppercase tracking-[0.09em] ${palette.textSecondary}`}>{label}</p>
      <p className={`mt-1 text-[14px] font-semibold ${palette.textPrimary}`}>{value}</p>
      {sub ? <p className={`text-[11px] ${palette.textSecondary}`}>{sub}</p> : null}
    </div>
  );
}

// ── Field Diffs ──────────────────────────────────────────────────────────────
function FieldDiffsList({ diffs, palette }: { diffs: ApiFieldDiff[]; palette: SkinPalette }) {
  if (!diffs.length) return null;
  return (
    <div className={`rounded-xl border ${palette.cardBorder} bg-white/60 p-3`}>
      <p className={`text-[12px] font-semibold ${palette.textPrimary}`}>Field changes</p>
      <div className="mt-2 space-y-1.5">
        {diffs.map((d) => (
          <div key={`${d.field}-${d.toValue}`} className={`flex items-center gap-2 rounded-lg ${palette.accentBg} px-3 py-1.5 text-[12px]`}>
            <span className={`font-medium ${palette.accentText}`}>{d.field}</span>
            <span className={palette.textSecondary}>
              {d.fromValue || "—"} → {d.toValue || "—"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Validations ──────────────────────────────────────────────────────────────
function ValidationBadges({ validations }: { validations: ApiValidationCheck[] }) {
  if (!validations.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {validations.map((v) => (
        <span
          key={`${v.label}-${v.status}`}
          className={`rounded-full border px-3 py-1 text-[11px] font-medium ${validationTone(v.status)}`}
        >
          {v.label}: {v.status}
        </span>
      ))}
    </div>
  );
}

// ── Approval Banner ──────────────────────────────────────────────────────────
function ApprovalBanner({ state }: { state: ApiSceneState }) {
  if (!state.approvalRequired) return null;
  return (
    <div className="rounded-xl border border-[#f1cd8a] bg-[#fff7e8] px-3 py-2 text-[12px] text-[#8a5a04]">
      Approval required. {state.approvalReason || "Review and confirm to continue."}
    </div>
  );
}

// ── Tool Params Preview (rich data from tool execution) ──────────────────────
function ToolParamsPreview({
  data,
  palette,
  fields,
}: {
  data: Record<string, unknown>;
  palette: SkinPalette;
  fields: { key: string; label: string }[];
}) {
  const rows = fields
    .map((f) => ({ label: f.label, value: String(data[f.key] || "") }))
    .filter((r) => r.value);
  if (!rows.length) return null;
  return (
    <div className={`space-y-2 rounded-xl border ${palette.cardBorder} bg-white/60 p-3`}>
      {rows.map((r) => (
        <div key={r.label}>
          <p className={`text-[11px] uppercase tracking-[0.08em] ${palette.textSecondary}`}>{r.label}</p>
          <p className={`mt-0.5 text-[13px] leading-relaxed ${palette.textPrimary}`}>
            {r.value.length > 300 ? r.value.slice(0, 300) + "…" : r.value}
          </p>
        </div>
      ))}
    </div>
  );
}

export {
  ApprovalBanner,
  FieldDiffsList,
  InfoCell,
  SkinHeader,
  SkinShell,
  ToolParamsPreview,
  ValidationBadges,
  statusTone,
  validationTone,
};
