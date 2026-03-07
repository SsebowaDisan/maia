type ArtifactRow = {
  id: string;
  title: string;
  detail: string;
  sourceUrl?: string;
  evidenceId?: string;
};

function extractArtifactRows(infoPanel: Record<string, unknown>): ArtifactRow[] {
  const rows: ArtifactRow[] = [];
  const panelArtifacts = (infoPanel as { artifacts?: unknown }).artifacts;
  if (Array.isArray(panelArtifacts)) {
    for (const item of panelArtifacts.slice(0, 24)) {
      if (item && typeof item === "object") {
        const row = item as Record<string, unknown>;
        const id = String(row.id || row.artifact_id || "").trim();
        const title = String(row.title || row.name || id || "Artifact").trim();
        const detail = String(row.summary || row.description || row.url || row.file_id || "").trim();
        const sourceUrl = String(row.url || row.source_url || "").trim();
        const evidenceId = String(row.evidence_id || row.evidenceId || "").trim();
        rows.push({ id: id || title, title, detail, sourceUrl, evidenceId });
        continue;
      }
      const text = String(item || "").trim();
      if (text) {
        rows.push({ id: text, title: text, detail: "", sourceUrl: "", evidenceId: "" });
      }
    }
  }
  const artifactRefs = (infoPanel as { artifact_refs?: unknown }).artifact_refs;
  if (Array.isArray(artifactRefs)) {
    for (const item of artifactRefs.slice(0, 24)) {
      const text = String(item || "").trim();
      if (!text) {
        continue;
      }
      rows.push({ id: text, title: text, detail: "", sourceUrl: "", evidenceId: "" });
    }
  }
  const deduped: ArtifactRow[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    const key = `${row.id}|${row.title}`.toLowerCase();
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    deduped.push(row);
  }
  return deduped;
}

export { extractArtifactRows };
export type { ArtifactRow };
