const STOPWORDS = new Set([
  "about",
  "after",
  "also",
  "among",
  "and",
  "are",
  "been",
  "being",
  "between",
  "both",
  "but",
  "can",
  "does",
  "each",
  "from",
  "have",
  "into",
  "its",
  "more",
  "most",
  "much",
  "other",
  "over",
  "that",
  "their",
  "them",
  "then",
  "there",
  "these",
  "they",
  "this",
  "those",
  "under",
  "very",
  "what",
  "when",
  "where",
  "which",
  "while",
  "with",
  "would",
  "your",
]);

function normalizeText(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function plainText(input: string): string {
  if (!input.trim()) {
    return "";
  }
  const hasHtmlTags = /<[a-z][\s\S]*>/i.test(input);
  if (!hasHtmlTags) {
    return normalizeText(input);
  }
  const doc = new DOMParser().parseFromString(input, "text/html");
  return normalizeText(doc.body.textContent || "");
}

function tokenize(text: string): string[] {
  return Array.from(
    new Set(
      text
        .toLowerCase()
        .split(/[^a-z0-9]+/i)
        .filter((token) => token.length > 2 && !STOPWORDS.has(token)),
    ),
  );
}

function compactLabel(text: string, maxLength: number): string {
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, Math.max(0, maxLength - 1)).trimEnd()}...`;
}

function cleanSourceLabel(source: string): string {
  const normalized = normalizeText(source).replace(/^\[\d+\]\s*/, "");
  if (!normalized) {
    return "Indexed source";
  }
  return compactLabel(normalized, 44);
}

export { cleanSourceLabel, compactLabel, normalizeText, plainText, tokenize };
