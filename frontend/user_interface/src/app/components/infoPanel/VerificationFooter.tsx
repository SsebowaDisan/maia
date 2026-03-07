import type { EvidenceQualitySummary } from "./verificationModels";

type VerificationFooterProps = {
  quality: EvidenceQualitySummary;
  sourceCount: number;
  evidenceCount: number;
};

function levelStyle(level: EvidenceQualitySummary["level"]): string {
  if (level === "high") {
    return "border-[#b8e8c5] bg-[#eefbf2] text-[#1a7f37]";
  }
  if (level === "medium") {
    return "border-[#f3d5a2] bg-[#fff7ea] text-[#9a6700]";
  }
  return "border-[#efcdcd] bg-[#fff4f4] text-[#b42323]";
}

function VerificationFooter({ quality, sourceCount, evidenceCount }: VerificationFooterProps) {
  return (
    <div className="rounded-2xl border border-[#d2d2d7] bg-white px-3 py-3 shadow-sm">
      <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Verification summary</p>
      <div className="mt-1.5 flex items-center justify-between gap-2">
        <p className="text-[13px] text-[#1d1d1f]">
          Evidence quality: <span className="font-semibold capitalize">{quality.level}</span>
        </p>
        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${levelStyle(quality.level)}`}>
          {Math.round(quality.score * 100)}%
        </span>
      </div>
      <p className="mt-1 text-[11px] text-[#6e6e73]">
        {sourceCount} source{sourceCount === 1 ? "" : "s"} • {evidenceCount} evidence snippet{evidenceCount === 1 ? "" : "s"}
      </p>
      {quality.warning ? <p className="mt-2 text-[11px] text-[#8a3a2d]">{quality.warning}</p> : null}
    </div>
  );
}

export { VerificationFooter };
