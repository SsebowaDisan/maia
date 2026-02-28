type EmailSceneProps = {
  emailBodyHtml: string;
  emailBodyScrollRef: React.RefObject<HTMLDivElement | null>;
  emailRecipient: string;
  emailSubject: string;
  activeEventType: string;
};

function EmailScene({
  activeEventType,
  emailBodyHtml,
  emailBodyScrollRef,
  emailRecipient,
  emailSubject,
}: EmailSceneProps) {
  return (
    <div className="absolute inset-0 bg-[linear-gradient(180deg,#e8eaef_0%,#dfe3ea_100%)] p-4 text-[#1d1d1f]">
      <div className="mx-auto h-full w-full max-w-[920px] rounded-[18px] border border-black/[0.08] bg-white shadow-[0_26px_60px_-40px_rgba(0,0,0,0.55)]">
        <div className="flex items-center gap-2 border-b border-black/[0.08] px-4 py-2.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
          <span className="ml-2 text-[12px] font-semibold tracking-tight text-[#3a3a3c]">Compose</span>
        </div>
        <div className="space-y-2 p-4 text-[12px]">
          <div className="rounded-xl border border-black/[0.07] bg-[#fafafc] px-3 py-2.5">
            <span className="font-semibold text-[#6e6e73]">To:</span>{" "}
            <span className="text-[#1d1d1f]">{emailRecipient}</span>
          </div>
          <div className="rounded-xl border border-black/[0.07] bg-[#fafafc] px-3 py-2.5">
            <span className="font-semibold text-[#6e6e73]">Subject:</span>{" "}
            <span className="text-[#1d1d1f]">{emailSubject}</span>
          </div>
          <div
            ref={emailBodyScrollRef}
            className="h-[320px] overflow-y-auto rounded-xl border border-black/[0.07] bg-white px-3 py-3 text-[14px] leading-[1.6] text-[#1f1f22]"
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
        </div>
      </div>
    </div>
  );
}

export { EmailScene };
