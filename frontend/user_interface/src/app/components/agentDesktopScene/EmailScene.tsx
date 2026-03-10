import { InteractionOverlay } from "./InteractionOverlay";

type EmailSceneProps = {
  activeEventType: string;
  activeDetail: string;
  action: string;
  actionPhase: string;
  actionStatus: string;
  actionTargetLabel: string;
  emailBodyPreview: string;
  emailBodyHtml: string;
  emailBodyScrollRef: React.RefObject<HTMLDivElement | null>;
  emailRecipient: string;
  emailSubject: string;
  copyUsageRefs: string[];
  copySourceSnippet: string;
};

const TITLE_CASE_WORD_RE = /^[A-Z][A-Za-z0-9'&/.-]*$/;
const MIN_PARAGRAPH_CHARS_FOR_SPLIT = 48;

function isTitleCaseHeadingCandidate(value: string): boolean {
  const words = String(value || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (words.length < 2 || words.length > 6) {
    return false;
  }
  return words.every((word) => TITLE_CASE_WORD_RE.test(word));
}

function splitLeadingHeading(text: string): { heading: string; body: string } | null {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (normalized.length < MIN_PARAGRAPH_CHARS_FOR_SPLIT) {
    return null;
  }
  const match = normalized.match(/^(.{4,64}?)\s{1,3}([A-Z][\s\S]{32,})$/);
  if (!match) {
    return null;
  }
  const heading = String(match[1] || "").trim();
  const body = String(match[2] || "").trim();
  if (!heading || !body) {
    return null;
  }
  if (/[.!?;:]$/.test(heading)) {
    return null;
  }
  if (!isTitleCaseHeadingCandidate(heading)) {
    return null;
  }
  return { heading, body };
}

function normalizeEmailBodyHtml(value: string): string {
  const raw = String(value || "").trim();
  if (!raw) {
    return "";
  }

  const parser = new DOMParser();
  const doc = parser.parseFromString(raw, "text/html");
  const { body } = doc;
  const hasBlockChildren = Array.from(body.children).some((element) =>
    /^(P|H[1-6]|UL|OL|LI|TABLE|BLOCKQUOTE|PRE|HR|DETAILS|FIGURE|DIV)$/.test(element.tagName),
  );

  if (!hasBlockChildren) {
    const plainText = String(body.textContent || "").trim();
    if (!plainText) {
      return "";
    }
    const sections = plainText
      .split(/\n{2,}/)
      .map((section) => section.replace(/\n+/g, " ").trim())
      .filter(Boolean);
    body.innerHTML = "";
    sections.forEach((section) => {
      const paragraph = doc.createElement("p");
      paragraph.textContent = section;
      body.appendChild(paragraph);
    });
  }

  Array.from(body.querySelectorAll("p")).forEach((paragraph) => {
    if (paragraph.childElementCount > 0) {
      return;
    }
    const text = String(paragraph.textContent || "").trim();
    const split = splitLeadingHeading(text);
    if (!split) {
      return;
    }
    const heading = doc.createElement("h3");
    heading.textContent = split.heading;
    const bodyParagraph = doc.createElement("p");
    bodyParagraph.textContent = split.body;
    paragraph.replaceWith(heading, bodyParagraph);
  });

  return body.innerHTML;
}

function focusedEmailField({
  eventType,
  action,
  actionTargetLabel,
}: {
  eventType: string;
  action: string;
  actionTargetLabel: string;
}): "to" | "subject" | "body" | null {
  const normalizedType = String(eventType || "").trim().toLowerCase();
  if (normalizedType === "email_set_to") {
    return "to";
  }
  if (normalizedType === "email_set_subject") {
    return "subject";
  }
  if (normalizedType === "email_set_body" || normalizedType === "email_type_body") {
    return "body";
  }
  if (String(action || "").trim().toLowerCase() !== "type") {
    return null;
  }
  const label = String(actionTargetLabel || "").trim().toLowerCase();
  if (!label) {
    return "body";
  }
  if (label.includes("subject")) {
    return "subject";
  }
  if (label.includes("recipient") || label.includes("email") || label.includes("to")) {
    return "to";
  }
  if (label.includes("message") || label.includes("body") || label.includes("content")) {
    return "body";
  }
  return "body";
}

function EmailScene({
  activeEventType,
  activeDetail,
  action,
  actionPhase,
  actionStatus,
  actionTargetLabel,
  emailBodyPreview,
  emailBodyHtml,
  emailBodyScrollRef,
  emailRecipient,
  emailSubject,
  copyUsageRefs,
  copySourceSnippet,
}: EmailSceneProps) {
  const focus = focusedEmailField({
    eventType: activeEventType,
    action,
    actionTargetLabel,
  });
  const isStreamingBodyEvent = activeEventType === "email_type_body";
  const isFieldUpdateEvent =
    activeEventType === "email_set_to" ||
    activeEventType === "email_set_subject" ||
    activeEventType === "email_set_body" ||
    isStreamingBodyEvent;
  const focusPulse =
    isFieldUpdateEvent || (action === "type" && (actionPhase === "start" || actionPhase === "active"));
  const normalizedBodyHtml = normalizeEmailBodyHtml(emailBodyHtml);
  const showBodyCaret = focus === "body" && (isStreamingBodyEvent || focusPulse);
  const bodyHtmlWithCaret = showBodyCaret
    ? `${normalizedBodyHtml}<p><span class="inline-block h-[1.05em] w-[2px] rounded bg-[#1d1d1f] align-middle"></span></p>`
    : normalizedBodyHtml;
  const bodyCharacterCount = String(emailBodyPreview || "").length;

  return (
    <div className="absolute inset-0 bg-[linear-gradient(180deg,#ebecef_0%,#e3e4e8_100%)] p-4 text-[#1d1d1f]">
      <div className="mx-auto flex h-full w-full max-w-[920px] flex-col overflow-hidden rounded-[20px] border border-black/[0.1] bg-[#fcfcfd] shadow-[0_26px_58px_-42px_rgba(0,0,0,0.52)]">
        <div className="flex items-center gap-2 border-b border-black/[0.08] px-5 py-3">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
          <span className="ml-2 text-[12px] font-semibold tracking-[0.01em] text-[#3a3a3c]">Compose</span>
          <span className="ml-auto rounded-full border border-black/[0.08] bg-white px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#5f6368]">
            Draft
          </span>
        </div>
        <div className="relative flex min-h-0 flex-1 flex-col gap-3 overflow-hidden p-5 pt-12 text-[12px]">
          <InteractionOverlay
            sceneSurface="email"
            activeEventType={activeEventType}
            activeDetail={activeDetail}
            scrollDirection=""
            action={action}
            actionPhase={actionPhase}
            actionStatus={actionStatus}
            actionTargetLabel={actionTargetLabel}
          />
          <div
            className={`grid grid-cols-[70px_minmax(0,1fr)] items-center rounded-[14px] border px-4 py-2.5 transition-all duration-300 ${
              focus === "to" && focusPulse
                ? "border-black/25 bg-[#f2f2f4]"
                : "border-black/[0.07] bg-[#fafafc]"
            }`}
          >
            <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#8b8b91]">To</span>
            <span className="truncate text-[13px] text-[#1d1d1f]">
              {emailRecipient || "recipient@example.com"}
            </span>
          </div>
          <div
            className={`grid grid-cols-[70px_minmax(0,1fr)] items-center rounded-[14px] border px-4 py-2.5 transition-all duration-300 ${
              focus === "subject" && focusPulse
                ? "border-black/25 bg-[#f2f2f4]"
                : "border-black/[0.07] bg-[#fafafc]"
            }`}
          >
            <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#8b8b91]">Subject</span>
            <span className="truncate text-[13px] font-medium text-[#1d1d1f]">
              {emailSubject || "No subject"}
            </span>
          </div>
          <div
            className={`flex min-h-0 flex-1 flex-col overflow-hidden rounded-[16px] border transition-all duration-300 ${
              focus === "body" && focusPulse
                ? "border-black/25 bg-[#f9f9fa]"
                : "border-black/[0.07] bg-white"
            }`}
          >
            <div className="border-b border-black/[0.06] px-4 py-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#8b8b91]">Message</span>
                <span className="text-[10px] text-[#86868b]">
                  {isStreamingBodyEvent ? "Live typing" : "Ready"} - {bodyCharacterCount} chars
                </span>
              </div>
            </div>
            <div
              ref={emailBodyScrollRef}
              className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-4 py-3.5 text-[14px] leading-[1.65] text-[#1f1f22]"
            >
              <div
                className="break-words [overflow-wrap:anywhere] [&_*]:break-words [&_*]:[overflow-wrap:anywhere] [&_h1]:mb-3 [&_h1]:text-[24px] [&_h1]:font-semibold [&_h1]:tracking-[-0.02em] [&_h2]:mb-2.5 [&_h2]:mt-5 [&_h2]:text-[20px] [&_h2]:font-semibold [&_h2]:tracking-[-0.015em] [&_h3]:mb-2 [&_h3]:mt-4 [&_h3]:text-[17px] [&_h3]:font-semibold [&_h3]:tracking-[-0.01em] [&_p]:mb-3 [&_ul]:mb-3 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:mb-3 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:mb-1.5 [&_code]:rounded [&_code]:bg-[#f2f2f7] [&_code]:px-1 [&_code]:py-0.5 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-[#f2f2f7] [&_pre]:p-2.5 [&_a]:break-all [&_a]:text-[#1d1d1f] hover:[&_a]:underline"
                dangerouslySetInnerHTML={{ __html: bodyHtmlWithCaret }}
              />
            </div>
          </div>
          {activeEventType === "email_click_send" ? (
            <div className="rounded-xl border border-black/15 bg-[#f2f2f4] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#1d1d1f]">
              Send action confirmed
            </div>
          ) : null}
          {copyUsageRefs.length ? (
            <div className="rounded-xl border border-[#b37a17]/30 bg-[#fff5e7] px-3 py-1.5 text-[10px] text-[#7d4f16]">
              <p className="font-semibold uppercase tracking-[0.08em]">Copy provenance</p>
              <p className="mt-0.5">
                Using copied source {copyUsageRefs.slice(0, 2).join(", ")}
              </p>
              {copySourceSnippet ? (
                <p className="mt-0.5 line-clamp-2 text-[#8a5d1a]">{copySourceSnippet}</p>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export { EmailScene };
