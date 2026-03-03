type IngestionProgressSnapshot = {
  status?: string | null;
  message?: string | null;
  processed_items?: number | null;
  total_items?: number | null;
  bytes_total?: number | null;
  bytes_indexed?: number | null;
  success_count?: number | null;
  failure_count?: number | null;
};

const clampPercent = (value: number) => Math.max(0, Math.min(100, Math.round(value)));

const toSafeNumber = (value: unknown) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
};

const computePercent = (snapshot: IngestionProgressSnapshot) => {
  const bytesTotal = Math.max(0, toSafeNumber(snapshot.bytes_total));
  const bytesIndexed = Math.max(0, toSafeNumber(snapshot.bytes_indexed));
  if (bytesTotal > 0) {
    return clampPercent((bytesIndexed / bytesTotal) * 100);
  }

  const totalItems = Math.max(0, toSafeNumber(snapshot.total_items));
  const processedItems = Math.max(0, toSafeNumber(snapshot.processed_items));
  if (totalItems > 0) {
    return clampPercent((processedItems / totalItems) * 100);
  }

  const status = String(snapshot.status || "").trim().toLowerCase();
  if (status === "completed") {
    return 100;
  }
  return 0;
};

const stageLabel = (snapshot: IngestionProgressSnapshot, percent: number) => {
  const status = String(snapshot.status || "").trim().toLowerCase();
  if (status === "queued") {
    return "Queued for indexing";
  }
  if (status === "running") {
    if (percent <= 3) {
      return "Preparing files";
    }
    if (percent < 90) {
      return "Extracting and indexing";
    }
    return "Finalizing index";
  }
  if (status === "completed") {
    return "Indexing complete";
  }
  if (status === "failed") {
    return "Indexing failed";
  }
  if (status === "canceled") {
    return "Indexing canceled";
  }
  const message = String(snapshot.message || "").trim();
  return message || "Processing";
};

function formatIngestionJobProgress(snapshot: IngestionProgressSnapshot): string {
  const percent = computePercent(snapshot);
  const stage = stageLabel(snapshot, percent);
  const totalItems = Math.max(0, toSafeNumber(snapshot.total_items));
  const processedItems = Math.max(0, toSafeNumber(snapshot.processed_items));
  const successCount = Math.max(0, toSafeNumber(snapshot.success_count));
  const failureCount = Math.max(0, toSafeNumber(snapshot.failure_count));

  const parts = [`${stage} ${percent}%`];
  if (totalItems > 0) {
    const noun = totalItems === 1 ? "file" : "files";
    parts.push(`${Math.min(totalItems, processedItems)}/${totalItems} ${noun}`);
  }

  if (successCount > 0 || failureCount > 0) {
    const statusParts: string[] = [];
    if (successCount > 0) {
      statusParts.push(`${successCount} indexed`);
    }
    if (failureCount > 0) {
      statusParts.push(`${failureCount} failed`);
    }
    parts.push(statusParts.join(", "));
  }
  return parts.join(" | ");
}

function formatUploadProgress(
  loadedBytes: number,
  totalBytes: number,
  doneSuffix?: string,
): string {
  if (!totalBytes || totalBytes <= 0) {
    return "Uploading to server";
  }
  const percent = clampPercent((Math.max(0, loadedBytes) / totalBytes) * 100);
  if (percent >= 100 && doneSuffix) {
    return `Uploading to server 100% | ${doneSuffix}`;
  }
  return `Uploading to server ${percent}%`;
}

export type { IngestionProgressSnapshot };
export { formatIngestionJobProgress, formatUploadProgress };
