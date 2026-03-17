import katex from "katex";

import { renderMathInMarkdown, renderRichText } from "../../utils/richText";
import type { CanvasDocumentRecord, MessageBlock } from "../../messageBlocks";
import { useCanvasStore } from "../../stores/canvasStore";
import { ChatTurnPlot } from "../chatMain/ChatTurnPlot";
import { resolveWidget, type LensWidgetProps, type WidgetComponentProps } from "../widgets/registry";
import { SortableTableWidget } from "../widgets/SortableTableWidget";
import { WidgetRenderBoundary } from "./WidgetRenderBoundary";

type BlockRendererProps = {
  block: MessageBlock;
  documents?: CanvasDocumentRecord[];
};

function renderMathHtml(latex: string, displayMode = false): string {
  const source = String(latex || "");
  try {
    return katex.renderToString(source, {
      displayMode,
      throwOnError: true,
    });
  } catch {
    return `<code>${source
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")}</code>`;
  }
}

function readFiniteNumber(value: unknown): number | undefined {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return undefined;
  }
  return value;
}

function buildLensWidgetProps(props: Record<string, unknown>): LensWidgetProps {
  const unitsCandidate = String(props.units || "").trim();
  return {
    focalLength: readFiniteNumber(props.focalLength),
    objectDistance: readFiniteNumber(props.objectDistance),
    showRays: typeof props.showRays === "boolean" ? props.showRays : undefined,
    units: unitsCandidate ? unitsCandidate : undefined,
  };
}

function BlockRenderer({ block, documents = [] }: BlockRendererProps) {
  const openDocument = useCanvasStore((state) => state.openDocument);
  const upsertDocuments = useCanvasStore((state) => state.upsertDocuments);

  if (block.type === "text") {
    return <p className="whitespace-pre-wrap text-[14px] leading-7 text-[#1d1d1f]">{block.text}</p>;
  }

  if (block.type === "markdown") {
    return (
      <div
        className="chat-answer-html assistantAnswerBody"
        dangerouslySetInnerHTML={{ __html: renderRichText(renderMathInMarkdown(block.markdown)) }}
      />
    );
  }

  if (block.type === "math") {
    return (
      <div
        className={`overflow-x-auto rounded-2xl border border-black/[0.06] bg-[#fafafa] px-4 py-3 text-[#111827] ${
          block.display ? "text-center" : ""
        }`}
        dangerouslySetInnerHTML={{ __html: renderMathHtml(block.latex, Boolean(block.display)) }}
      />
    );
  }

  if (block.type === "code") {
    return (
      <div className="overflow-hidden rounded-2xl border border-black/[0.08] bg-[#111827] shadow-[0_18px_40px_rgba(15,23,42,0.16)]">
        {block.language ? (
          <div className="border-b border-white/10 px-4 py-2 text-[11px] font-medium uppercase tracking-[0.12em] text-white/70">
            {block.language}
          </div>
        ) : null}
        <pre className="overflow-x-auto px-4 py-4 text-[13px] leading-6 text-white">
          <code>{block.code}</code>
        </pre>
      </div>
    );
  }

  if (block.type === "image") {
    return (
      <figure className="overflow-hidden rounded-2xl border border-black/[0.08] bg-white shadow-[0_18px_40px_rgba(15,23,42,0.08)]">
        <img src={block.src} alt={block.alt || ""} className="h-auto w-full object-cover" />
        {block.alt ? <figcaption className="px-4 py-3 text-[12px] text-[#667085]">{block.alt}</figcaption> : null}
      </figure>
    );
  }

  if (block.type === "table") {
    return (
      <SortableTableWidget
        title="Table"
        columns={block.columns}
        rows={block.rows}
      />
    );
  }

  if (block.type === "notice") {
    const noticeTone =
      block.level === "error"
        ? "border-[#fecaca] bg-[#fef2f2] text-[#991b1b]"
        : block.level === "warning"
          ? "border-[#fde68a] bg-[#fffbeb] text-[#92400e]"
          : "border-[#bfdbfe] bg-[#eff6ff] text-[#1d4ed8]";
    return (
      <div className={`rounded-2xl border px-4 py-3 text-[13px] leading-6 ${noticeTone}`}>
        {block.text}
      </div>
    );
  }

  if (block.type === "chart") {
    return <ChatTurnPlot plot={block.plot} />;
  }

  if (block.type === "widget") {
    const widgetKind = String(block.widget.kind || "").trim().toLowerCase();
    const widgetProps = (block.widget.props || {}) as Record<string, unknown>;
    const UnknownWidget = resolveWidget("json");

    if (widgetKind === "lens_equation") {
      const Widget = resolveWidget(widgetKind);
      if (!Widget) {
        return null;
      }
      const safeProps = buildLensWidgetProps(block.widget.props || {});
      return (
        <WidgetRenderBoundary>
          <Widget {...(safeProps as unknown as WidgetComponentProps)} />
        </WidgetRenderBoundary>
      );
    }

    const Widget = resolveWidget(widgetKind);
    if (!Widget) {
      if (!UnknownWidget) {
        return (
          <div className="rounded-2xl border border-[#fde68a] bg-[#fffbeb] px-4 py-3 text-[12px] text-[#92400e]">
            Unsupported widget: {widgetKind || "unknown"}
          </div>
        );
      }
      return (
        <WidgetRenderBoundary>
          <UnknownWidget
            title={`Unsupported widget: ${widgetKind || "unknown"}`}
            kind={widgetKind || "unknown"}
            props={widgetProps}
          />
        </WidgetRenderBoundary>
      );
    }

    return (
      <WidgetRenderBoundary>
        <Widget {...(widgetProps as WidgetComponentProps)} />
      </WidgetRenderBoundary>
    );
  }

  if (block.type === "document_action") {
    const matchingDocument =
      documents.find((document) => document.id === block.action.documentId) || null;
    return (
      <button
        type="button"
        onClick={() => {
          if (matchingDocument) {
            upsertDocuments([matchingDocument]);
          } else {
            upsertDocuments([
              {
                id: block.action.documentId,
                title: block.action.title || "Untitled document",
                content: "",
              },
            ]);
          }
          openDocument(block.action.documentId);
        }}
        className="inline-flex items-center rounded-full border border-black/[0.08] bg-white px-4 py-2 text-[13px] font-medium text-[#111827] shadow-[0_10px_24px_rgba(15,23,42,0.06)] transition hover:border-black/[0.18] hover:shadow-[0_14px_30px_rgba(15,23,42,0.1)]"
      >
        {block.action.title || "Open document"}
      </button>
    );
  }

  return null;
}

export { BlockRenderer };
