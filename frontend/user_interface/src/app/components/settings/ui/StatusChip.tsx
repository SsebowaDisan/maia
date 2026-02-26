type StatusTone = "success" | "neutral" | "warning" | "error";

type StatusChipProps = {
  label: string;
  tone?: StatusTone;
  className?: string;
};

const toneClass: Record<StatusTone, string> = {
  success: "border-[#5f8a68] bg-[#f0f7f1] text-[#2d5937]",
  neutral: "border-[#d2d2d7] bg-[#f5f5f7] text-[#6e6e73]",
  warning: "border-[#d2b37b] bg-[#faf5ea] text-[#7c5a1f]",
  error: "border-[#be7b7b] bg-[#f9efef] text-[#7a3030]",
};

export function StatusChip({ label, tone = "neutral", className = "" }: StatusChipProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold ${toneClass[tone]} ${className}`.trim()}
    >
      {label}
    </span>
  );
}

export function toneFromBoolean(value: boolean, labels?: { trueLabel?: string; falseLabel?: string }) {
  return {
    tone: value ? ("success" as const) : ("neutral" as const),
    label: value ? labels?.trueLabel || "Connected" : labels?.falseLabel || "Not connected",
  };
}
