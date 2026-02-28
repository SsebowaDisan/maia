import type { ClaimInsight, ContradictionSeverity } from "../../utils/infoInsights";

function claimStatusStyle(status: ClaimInsight["status"]) {
  if (status === "supported") return "bg-[#e8f6ed] text-[#1f8f4c] border-[#1f8f4c]/20";
  if (status === "weak") return "bg-[#fff7e5] text-[#9c6a00] border-[#9c6a00]/20";
  return "bg-[#fdecec] text-[#c9342e] border-[#c9342e]/20";
}

function claimStatusLabel(status: ClaimInsight["status"]) {
  if (status === "supported") return "Supported";
  if (status === "weak") return "Weak";
  return "Missing";
}

function contradictionStyle(severity: ContradictionSeverity) {
  if (severity === "high") return "bg-[#fdecec] text-[#b42318] border-[#f7c1c1]";
  if (severity === "medium") return "bg-[#fff7e5] text-[#9c6a00] border-[#f0d9a1]";
  return "bg-[#f1f3f5] text-[#5d5d63] border-[#dcdde2]";
}

function contradictionLabel(severity: ContradictionSeverity) {
  if (severity === "high") return "High risk";
  if (severity === "medium") return "Needs review";
  return "Possible";
}

export {
  claimStatusLabel,
  claimStatusStyle,
  contradictionLabel,
  contradictionStyle,
};
