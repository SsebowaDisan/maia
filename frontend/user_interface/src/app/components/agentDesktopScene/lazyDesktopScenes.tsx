import { lazy, Suspense } from "react";

const BrowserScene = lazy(async () => ({
  default: (await import("@maia/theatre")).BrowserScene,
}));
const ApiScene = lazy(async () => ({
  default: (await import("@maia/theatre")).ApiScene,
}));
const DocsScene = lazy(async () => ({
  default: (await import("@maia/theatre")).DocsScene,
}));
const DocumentFallbackScene = lazy(async () => ({
  default: (await import("@maia/theatre")).DocumentFallbackScene,
}));
const DocumentPdfScene = lazy(async () => ({
  default: (await import("@maia/theatre")).DocumentPdfScene,
}));
const EmailScene = lazy(async () => ({
  default: (await import("@maia/theatre")).EmailScene,
}));
const SheetsScene = lazy(async () => ({
  default: (await import("@maia/theatre")).SheetsScene,
}));
const SnapshotScene = lazy(async () => ({
  default: (await import("@maia/theatre")).SnapshotScene,
}));
const SystemScene = lazy(async () => ({
  default: (await import("@maia/theatre")).SystemScene,
}));

function SceneFallback() {
  return <div className="absolute inset-0 animate-pulse bg-[#0b0c10]" aria-hidden="true" />;
}

function SceneBoundary({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<SceneFallback />}>{children}</Suspense>;
}

export {
  ApiScene,
  BrowserScene,
  DocsScene,
  DocumentFallbackScene,
  DocumentPdfScene,
  EmailScene,
  SceneBoundary,
  SheetsScene,
  SnapshotScene,
  SystemScene,
};
