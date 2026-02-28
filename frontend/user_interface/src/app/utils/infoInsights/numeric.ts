import { normalizeText } from "./text";
import type { NumericFact } from "./types";

function normalizeUnit(unit: string): string {
  const normalized = unit.toLowerCase().trim();
  if (!normalized) {
    return "";
  }
  if (normalized === "percent") {
    return "%";
  }
  if (normalized === "dollar" || normalized === "dollars") {
    return "usd";
  }
  if (normalized === "day" || normalized === "days") {
    return "day";
  }
  if (normalized === "hour" || normalized === "hours") {
    return "hour";
  }
  if (normalized === "year" || normalized === "years") {
    return "year";
  }
  if (normalized === "month" || normalized === "months") {
    return "month";
  }
  if (normalized === "week" || normalized === "weeks") {
    return "week";
  }
  return normalized;
}

function extractNumericFacts(text: string): NumericFact[] {
  const found: NumericFact[] = [];
  const pattern =
    /(-?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?)(?:\s?(%|percent|usd|eur|ugx|dollars?|days?|hours?|years?|months?|weeks?|kg|g|km|m|cm|mm))?/gi;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    const rawNumber = (match[1] || "").replace(/,/g, "");
    const parsed = Number(rawNumber);
    if (!Number.isFinite(parsed)) {
      continue;
    }
    found.push({
      value: parsed,
      unit: normalizeUnit(match[2] || ""),
      raw: normalizeText(match[0] || rawNumber),
    });
    if (found.length >= 10) {
      break;
    }
  }
  return found;
}

export { extractNumericFacts };
