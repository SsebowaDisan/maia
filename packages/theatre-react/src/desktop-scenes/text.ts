function sanitizeComputerUseText(value: unknown): string {
  let text = String(value || "").trim();
  if (!text) {
    return "";
  }

  text = text.replace(/\bbrowser[.\s_-]*playwright[.\s_-]*inspect\b/gi, "browser inspect");
  text = text.replace(/\bplaywright_contact_form\b/gi, "computer use browser");
  text = text.replace(/\bplaywright_browser\b/gi, "computer use browser");
  text = text.replace(/\bgmail_playwright\b/gi, "gmail");
  text = text.replace(/\bplaywright\b/gi, "computer use");
  text = text.replace(/\[n\]/gi, "citations");
  text = text.replace(
    /\b(?:each inline citation marker|every citation marker|every citations?|all citations?)\b[^.?!]*\b(?:numbered|distinct sentences?|distinct domains?|evidence citations?)\b[^.?!]*[.?!]?/gi,
    "Verify citations before finalizing.",
  );
  text = text.replace(
    /\bverify all citations?\b[^.?!]*\bdistinct sentences?\b[^.?!]*\bdomains?\b[^.?!]*[.?!]?/gi,
    "Verify citations before finalizing.",
  );
  text = text.replace(/\bverify all citations?\b/gi, "Verify citations");
  text = text.replace(/\bDomains before finalizing\b/gi, "Finalize after source review");
  text = text.replace(/\bCitations cite\b/gi, "Citations reference");
  text = text.replace(/\bEach citations\b/gi, "Each citation");
  text = text.replace(/\bEvery citations\b/gi, "Every citation");
  text = text.replace(/\bcitations\s+citations\b/gi, "citations");
  text = text.replace(/\bVerify\s+Verify\s+citations\b/gi, "Verify citations");
  text = text.replace(/\s+/g, " ").trim();

  return text;
}

export { sanitizeComputerUseText };
