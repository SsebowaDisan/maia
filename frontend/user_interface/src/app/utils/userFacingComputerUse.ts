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
  text = text.replace(/\s+/g, " ").trim();

  return text;
}

export { sanitizeComputerUseText };
