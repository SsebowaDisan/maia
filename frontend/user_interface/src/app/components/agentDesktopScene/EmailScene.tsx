import { InteractionOverlay } from "./InteractionOverlay";

type EmailSceneProps = {
  activeEventType: string;
  activeDetail: string;
  action: string;
  actionPhase: string;
  actionStatus: string;
  actionTargetLabel: string;
  emailBodyHtml: string;
  emailBodyScrollRef: React.RefObject<HTMLDivElement | null>;
  emailRecipient: string;
  emailSubject: string;
  copyUsageRefs: string[];
  copySourceSnippet: string;
};

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
  const focusPulse = action === "type" && (actionPhase === "start" || actionPhase === "active");
  return (
    <div className="absolute inset-0 bg-[linear-gradient(180deg,#e8eaef_0%,#dfe3ea_100%)] p-4 text-[#1d1d1f]">
      <div className="mx-auto h-full w-full max-w-[920px] rounded-[18px] border border-black/[0.08] bg-white shadow-[0_26px_60px_-40px_rgba(0,0,0,0.55)]">
        <div className="flex items-center gap-2 border-b border-black/[0.08] px-4 py-2.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
          <span className="ml-2 text-[12px] font-semibold tracking-tight text-[#3a3a3c]">Compose</span>
        </div>
        <div className="relative space-y-2 p-4 text-[12px]">
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
            className={`rounded-xl border px-3 py-2.5 transition-all duration-300 ${
              focus === "to" && focusPulse
                ? "border-[#0a84ff]/35 bg-[#eaf4ff]"
                : "border-black/[0.07] bg-[#fafafc]"
            }`}
          >
            <span className="font-semibold text-[#6e6e73]">To:</span>{" "}
            <span className="text-[#1d1d1f]">{emailRecipient}</span>
          </div>
          <div
            className={`rounded-xl border px-3 py-2.5 transition-all duration-300 ${
              focus === "subject" && focusPulse
                ? "border-[#0a84ff]/35 bg-[#eaf4ff]"
                : "border-black/[0.07] bg-[#fafafc]"
            }`}
          >
            <span className="font-semibold text-[#6e6e73]">Subject:</span>{" "}
            <span className="text-[#1d1d1f]">{emailSubject}</span>
          </div>
          <div
            ref={emailBodyScrollRef}
            className={`h-[320px] overflow-y-auto rounded-xl border px-3 py-3 text-[14px] leading-[1.6] text-[#1f1f22] transition-all duration-300 ${
              focus === "body" && focusPulse
                ? "border-[#0a84ff]/35 bg-[#fbfdff]"
                : "border-black/[0.07] bg-white"
            }`}
          >
            <div
              className="[&_h1]:mb-2 [&_h1]:text-[21px] [&_h1]:font-semibold [&_h2]:mb-2 [&_h2]:text-[18px] [&_h2]:font-semibold [&_h3]:mb-1.5 [&_h3]:text-[16px] [&_h3]:font-semibold [&_p]:mb-2 [&_ul]:mb-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:mb-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_code]:rounded [&_code]:bg-[#f2f2f7] [&_code]:px-1 [&_code]:py-0.5 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-[#f2f2f7] [&_pre]:p-2 [&_a]:text-[#0a66d9] hover:[&_a]:underline"
              dangerouslySetInnerHTML={{ __html: emailBodyHtml }}
            />
          </div>
          {activeEventType === "email_click_send" ? (
            <div className="rounded-xl border border-[#0a84ff]/25 bg-[#0a84ff]/10 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#0756a8]">
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
