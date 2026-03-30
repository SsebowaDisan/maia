type IngestionProgressSnapshot = {
  status?: string | null;
  message?: string | null;
  processed_items?: number | null;
  total_items?: number | null;
  bytes_total?: number | null;
  bytes_persisted?: number | null;
  bytes_indexed?: number | null;
  success_count?: number | null;
  failure_count?: number | null;
  debug?: string[] | null;
  kind?: string | null;
};

type IngestionProgressState = {
  percent: number;
  currentStep: string;
  detail: string;
  completedSteps: string[];
  remainingSteps: string[];
  explanation: string;
  stageKey:
    | "queued"
    | "preparing"
    | "classifying_pdf"
    | "ocr"
    | "extracting"
    | "indexing"
    | "finalizing"
    | "completed"
    | "failed"
    | "canceled";
};

const clampPercent = (value: number) => Math.max(0, Math.min(100, Math.round(value)));

const toSafeNumber = (value: unknown) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
};

const normalizeStatus = (value: unknown) => String(value || "").trim().toLowerCase();

const normalizeDebugRows = (snapshot: IngestionProgressSnapshot) =>
  Array.isArray(snapshot.debug)
    ? snapshot.debug
        .map((row) => String(row || "").trim())
        .filter(Boolean)
        .slice(-20)
    : [];

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

  const status = normalizeStatus(snapshot.status);
  if (status === "completed") {
    return 100;
  }
  return 0;
};

const buildStageOrder = (snapshot: IngestionProgressSnapshot, debugRows: string[]) => {
  const joinedDebug = debugRows.join(" ").toLowerCase();
  const kind = normalizeStatus(snapshot.kind);
  const isFilesJob = kind !== "urls";
  const touchesPdf =
    joinedDebug.includes(".pdf") ||
    joinedDebug.includes("pdf route=") ||
    joinedDebug.includes("page-unit precompute");
  const usesOcr =
    joinedDebug.includes("paddleocr") ||
    joinedDebug.includes("ocr_route") ||
    joinedDebug.includes("ocr route") ||
    joinedDebug.includes(" route=heavy") ||
    joinedDebug.includes("reader_mode=ocr");

  const steps = ["Queued"];
  if (isFilesJob) {
    steps.push("Preparing document");
  } else {
    steps.push("Preparing sources");
  }
  if (touchesPdf) {
    steps.push("Checking PDF structure");
  }
  if (usesOcr) {
    steps.push("Running OCR");
  }
  steps.push("Extracting text");
  steps.push(kind === "urls" ? "Indexing sources" : "Indexing for answers");
  steps.push("Finalizing");
  steps.push("Ready");
  return steps;
};

const detectStage = (snapshot: IngestionProgressSnapshot, percent: number, debugRows: string[]) => {
  const status = normalizeStatus(snapshot.status);
  const processedItems = Math.max(0, toSafeNumber(snapshot.processed_items));
  const totalItems = Math.max(0, toSafeNumber(snapshot.total_items));
  const joinedDebug = debugRows.join(" ").toLowerCase();

  if (status === "completed") {
    return "completed" as const;
  }
  if (status === "failed") {
    return "failed" as const;
  }
  if (status === "canceled") {
    return "canceled" as const;
  }
  if (status === "queued") {
    return "queued" as const;
  }

  if (joinedDebug.includes("scheduled page-unit precompute")) {
    return "finalizing" as const;
  }
  if (
    joinedDebug.includes("paddleocr") ||
    joinedDebug.includes("ocr route") ||
    joinedDebug.includes("ocr_route") ||
    joinedDebug.includes(" route=heavy")
  ) {
    return "ocr" as const;
  }
  if (joinedDebug.includes("pdf route=")) {
    return "classifying_pdf" as const;
  }
  if (/indexing \[\d+\/\d+\]/i.test(joinedDebug)) {
    return "indexing" as const;
  }
  if (processedItems >= totalItems && totalItems > 0) {
    return "finalizing" as const;
  }
  if (percent >= 85) {
    return "finalizing" as const;
  }
  if (percent > 30 || processedItems > 0) {
    return "indexing" as const;
  }
  if (percent > 5) {
    return "extracting" as const;
  }
  return "preparing" as const;
};

const mapStageToStep = (stageKey: IngestionProgressState["stageKey"]) => {
  switch (stageKey) {
    case "queued":
      return "Queued";
    case "preparing":
      return "Preparing document";
    case "classifying_pdf":
      return "Checking PDF structure";
    case "ocr":
      return "Running OCR";
    case "extracting":
      return "Extracting text";
    case "indexing":
      return "Indexing for answers";
    case "finalizing":
      return "Finalizing";
    case "completed":
      return "Ready";
    case "failed":
      return "Indexing failed";
    case "canceled":
      return "Indexing canceled";
    default:
      return "Processing";
  }
};

const buildExplanation = (
  snapshot: IngestionProgressSnapshot,
  stageKey: IngestionProgressState["stageKey"],
  debugRows: string[],
) => {
  const status = normalizeStatus(snapshot.status);
  const explicitMessage = String(snapshot.message || "").trim();
  const lowerDebug = debugRows.join(" ").toLowerCase();
  if (stageKey === "ocr") {
    return "This PDF is taking the OCR route, so Maia has to render pages and extract text before indexing.";
  }
  if (stageKey === "classifying_pdf") {
    return "Maia is checking the PDF structure first to decide whether standard parsing or OCR is required.";
  }
  if (stageKey === "finalizing" && lowerDebug.includes("page-unit precompute")) {
    return "The file is indexed. Maia is preparing page-level evidence targets so citations can jump to the right section.";
  }
  if (status === "failed" || status === "canceled") {
    return explicitMessage || "The ingestion job did not finish.";
  }
  if (explicitMessage) {
    return explicitMessage;
  }
  return "Maia is preparing this source so it can be used for grounded answers.";
};

function deriveIngestionJobProgress(snapshot: IngestionProgressSnapshot): IngestionProgressState {
  const percent = computePercent(snapshot);
  const debugRows = normalizeDebugRows(snapshot);
  const stageOrder = buildStageOrder(snapshot, debugRows);
  const stageKey = detectStage(snapshot, percent, debugRows);
  const currentStep = mapStageToStep(stageKey);
  const currentStepIndex = Math.max(0, stageOrder.indexOf(currentStep));
  const completedSteps =
    stageKey === "completed"
      ? stageOrder.slice(0, -1)
      : stageOrder.slice(0, currentStepIndex);
  const remainingSteps =
    stageKey === "completed" || stageKey === "failed" || stageKey === "canceled"
      ? []
      : stageOrder.slice(currentStepIndex + 1);
  const totalItems = Math.max(0, toSafeNumber(snapshot.total_items));
  const processedItems = Math.max(0, toSafeNumber(snapshot.processed_items));
  const successCount = Math.max(0, toSafeNumber(snapshot.success_count));
  const failureCount = Math.max(0, toSafeNumber(snapshot.failure_count));

  const detailParts = [`${currentStep} ${percent}%`];
  if (totalItems > 0) {
    const noun = totalItems === 1 ? "file" : "files";
    detailParts.push(`${Math.min(totalItems, processedItems)}/${totalItems} ${noun}`);
  }
  if (successCount > 0 || failureCount > 0) {
    const counts: string[] = [];
    if (successCount > 0) {
      counts.push(`${successCount} ready`);
    }
    if (failureCount > 0) {
      counts.push(`${failureCount} failed`);
    }
    detailParts.push(counts.join(", "));
  }
  if (remainingSteps.length > 0) {
    detailParts.push(`Remaining: ${remainingSteps.join(" -> ")}`);
  }

  return {
    percent,
    currentStep,
    detail: detailParts.join(" | "),
    completedSteps,
    remainingSteps,
    explanation: buildExplanation(snapshot, stageKey, debugRows),
    stageKey,
  };
}

function formatIngestionJobProgress(snapshot: IngestionProgressSnapshot): string {
  return deriveIngestionJobProgress(snapshot).detail;
}

function formatUploadProgress(
  loadedBytes: number,
  totalBytes: number,
  doneSuffix?: string,
): string {
  if (!totalBytes || totalBytes <= 0) {
    return "Uploading to Maia";
  }
  const percent = clampPercent((Math.max(0, loadedBytes) / totalBytes) * 100);
  if (percent >= 100 && doneSuffix) {
    return `Uploading to Maia 100% | ${doneSuffix}`;
  }
  return `Uploading to Maia ${percent}%`;
}

export type { IngestionProgressSnapshot, IngestionProgressState };
export { deriveIngestionJobProgress, formatIngestionJobProgress, formatUploadProgress };
