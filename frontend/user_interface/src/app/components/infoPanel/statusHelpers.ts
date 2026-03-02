import type { ClaimInsight } from "../../utils/infoInsights";

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

export {
  claimStatusLabel,
  claimStatusStyle,
};
