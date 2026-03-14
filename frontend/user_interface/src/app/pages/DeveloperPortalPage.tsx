import { useState } from "react";
import { toast } from "sonner";

import { AGENT_OS_MARKETPLACE } from "./agentOsData";

export function DeveloperPortalPage() {
  const [releaseVersion, setReleaseVersion] = useState("1.3.0");
  const [releaseNotes, setReleaseNotes] = useState("Improved tool routing and cleaner evidence summaries.");

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1240px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Developer portal</p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">Publisher operations</h1>
          <p className="mt-2 text-[15px] text-[#475467]">Track marketplace agents, publish updates, and manage feedback loops.</p>
        </section>

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <article className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <p className="text-[12px] text-[#667085]">Published agents</p>
            <p className="mt-1 text-[26px] font-semibold text-[#111827]">{AGENT_OS_MARKETPLACE.length}</p>
          </article>
          <article className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <p className="text-[12px] text-[#667085]">Total installs</p>
            <p className="mt-1 text-[26px] font-semibold text-[#111827]">
              {AGENT_OS_MARKETPLACE.reduce((total, agent) => total + agent.installs, 0).toLocaleString()}
            </p>
          </article>
          <article className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <p className="text-[12px] text-[#667085]">Average rating</p>
            <p className="mt-1 text-[26px] font-semibold text-[#111827]">
              {(AGENT_OS_MARKETPLACE.reduce((total, agent) => total + agent.rating, 0) / AGENT_OS_MARKETPLACE.length).toFixed(2)}
            </p>
          </article>
        </section>

        <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
          <h2 className="text-[18px] font-semibold text-[#111827]">Publish new version</h2>
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            <label>
              <span className="text-[12px] font-semibold text-[#667085]">Version</span>
              <input
                value={releaseVersion}
                onChange={(event) => setReleaseVersion(event.target.value)}
                className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
              />
            </label>
            <label>
              <span className="text-[12px] font-semibold text-[#667085]">Release notes</span>
              <input
                value={releaseNotes}
                onChange={(event) => setReleaseNotes(event.target.value)}
                className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
              />
            </label>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => toast.success(`Submitted ${releaseVersion} for review.`)}
              className="rounded-full bg-[#111827] px-4 py-2 text-[12px] font-semibold text-white"
            >
              Submit for review
            </button>
            <a
              href="/developer/docs"
              className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[12px] font-semibold text-[#344054]"
            >
              Open SDK docs
            </a>
          </div>
        </section>
      </div>
    </div>
  );
}

