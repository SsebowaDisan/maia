import type { CitationFocus } from "../../types";

type WorkspaceFocusSummaryProps = {
  citationFocus: CitationFocus | null;
};

function trimText(value: unknown): string {
  return String(value || "").trim();
}

function WorkspaceFocusSummary({ citationFocus }: WorkspaceFocusSummaryProps) {
  const sourceName = trimText(citationFocus?.sourceName);
  const sourceUrl = trimText(citationFocus?.sourceUrl);
  const page = trimText(citationFocus?.page);
  const graphNodeId = trimText(citationFocus?.graphNodeIds?.[0]);
  const sceneRef = trimText(citationFocus?.sceneRefs?.[0]);
  const eventRef = trimText(citationFocus?.eventRefs?.[0]);
  const hasFocus = Boolean(sourceName || sourceUrl || page || graphNodeId || sceneRef || eventRef);
  if (!hasFocus) {
    return null;
  }

  return (
    <div className="mx-5 mt-3 rounded-xl border border-black/[0.08] bg-[#fafafc] p-2.5">
      <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Active focus</p>
      <div className="mt-1.5 flex flex-wrap gap-1.5 text-[11px] text-[#4c4c50]">
        {sourceName ? <span className="rounded-full bg-white px-2 py-0.5">{sourceName}</span> : null}
        {!sourceName && sourceUrl ? <span className="rounded-full bg-white px-2 py-0.5">{sourceUrl}</span> : null}
        {page ? <span className="rounded-full bg-white px-2 py-0.5">Page {page}</span> : null}
        {graphNodeId ? <span className="rounded-full bg-white px-2 py-0.5">Node {graphNodeId}</span> : null}
        {sceneRef ? <span className="rounded-full bg-white px-2 py-0.5">Scene {sceneRef}</span> : null}
        {eventRef ? <span className="rounded-full bg-white px-2 py-0.5">Event {eventRef}</span> : null}
      </div>
    </div>
  );
}

export { WorkspaceFocusSummary };
