import { AlertTriangle, Check, Minus } from "lucide-react";

type ConnectorStatusPillProps = {
  status: "connected" | "missing" | "not_required" | string;
  label?: string;
  compact?: boolean;
};

function toneForStatus(status: string): {
  className: string;
  text: string;
  icon: "check" | "warning" | "minus";
} {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "connected") {
    return {
      className: "border-[#bbf7d0] bg-[#ecfdf3] text-[#166534]",
      text: "Connected",
      icon: "check",
    };
  }
  if (normalized === "missing") {
    return {
      className: "border-[#fde68a] bg-[#fffbeb] text-[#92400e]",
      text: "Missing",
      icon: "warning",
    };
  }
  return {
    className: "border-[#d0d5dd] bg-[#f8fafc] text-[#475467]",
    text: "Not required",
    icon: "minus",
  };
}

export function ConnectorStatusPill({ status, label, compact = false }: ConnectorStatusPillProps) {
  const tone = toneForStatus(status);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${tone.className}`}
      title={label ? `${label}: ${tone.text}` : tone.text}
    >
      {tone.icon === "check" ? <Check className="h-3.5 w-3.5" /> : null}
      {tone.icon === "warning" ? <AlertTriangle className="h-3.5 w-3.5" /> : null}
      {tone.icon === "minus" ? <Minus className="h-3.5 w-3.5" /> : null}
      {!compact ? (
        <>
          {label ? <span>{label}</span> : null}
          {label ? <span className="opacity-70">?</span> : null}
          <span>{tone.text}</span>
        </>
      ) : null}
    </span>
  );
}
