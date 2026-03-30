type TextMessageBlock = {
  type: "text";
  text: string;
};

type MarkdownMessageBlock = {
  type: "markdown";
  markdown: string;
};

type MathMessageBlock = {
  type: "math";
  latex: string;
  display?: boolean;
};

type CodeMessageBlock = {
  type: "code";
  language: string;
  code: string;
};

type ImageMessageBlock = {
  type: "image";
  src: string;
  alt?: string;
};

type TableMessageBlock = {
  type: "table";
  columns: string[];
  rows: string[][];
};

type NoticeMessageBlock = {
  type: "notice";
  level: "info" | "warning" | "error";
  text: string;
};

type ChartMessageBlock = {
  type: "chart";
  plot: Record<string, unknown>;
};

type WidgetMessageBlock = {
  type: "widget";
  widget: {
    kind: string;
    props: Record<string, unknown>;
  };
};

type DocumentActionMessageBlock = {
  type: "document_action";
  action: {
    kind: string;
    title: string;
    documentId: string;
  };
};

type MessageBlock =
  | TextMessageBlock
  | MarkdownMessageBlock
  | MathMessageBlock
  | CodeMessageBlock
  | ImageMessageBlock
  | TableMessageBlock
  | NoticeMessageBlock
  | ChartMessageBlock
  | WidgetMessageBlock
  | DocumentActionMessageBlock;

type CanvasDocumentRecord = {
  id: string;
  title: string;
  content: string;
  infoHtml?: string;
  infoPanel?: Record<string, unknown>;
  userPrompt?: string;
  modeVariant?: string;
};

function readString(value: unknown): string {
  return String(value ?? "").trim();
}

function readRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function readStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => readString(item))
    .filter((item) => item.length > 0);
}

function fallbackAssistantBlocks(assistantText: string): MessageBlock[] {
  const markdown = String(assistantText || "").trim();
  return markdown ? [{ type: "markdown", markdown }] : [];
}

function normalizeCanvasDocuments(raw: unknown): CanvasDocumentRecord[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .map((entry) => {
      const record = readRecord(entry);
      const id = readString(record.id);
      const title = readString(record.title);
      if (!id || !title) {
        return null;
      }
      return {
        id,
        title,
        content: String(record.content ?? ""),
        ...(readString(record.info_html ?? record.infoHtml)
          ? { infoHtml: readString(record.info_html ?? record.infoHtml) }
          : {}),
        ...(record.info_panel && typeof record.info_panel === "object" && !Array.isArray(record.info_panel)
          ? { infoPanel: record.info_panel as Record<string, unknown> }
          : record.infoPanel && typeof record.infoPanel === "object" && !Array.isArray(record.infoPanel)
            ? { infoPanel: record.infoPanel as Record<string, unknown> }
            : {}),
        ...(readString(record.user_prompt ?? record.userPrompt)
          ? { userPrompt: readString(record.user_prompt ?? record.userPrompt) }
          : {}),
        ...(readString(record.mode_variant ?? record.modeVariant)
          ? { modeVariant: readString(record.mode_variant ?? record.modeVariant) }
          : {}),
      } satisfies CanvasDocumentRecord;
    })
    .filter((entry): entry is CanvasDocumentRecord => Boolean(entry));
}

function normalizeMessageBlocks(raw: unknown, assistantText = ""): MessageBlock[] {
  if (!Array.isArray(raw)) {
    return fallbackAssistantBlocks(assistantText);
  }

  const normalized = raw
    .map((entry) => {
      const record = readRecord(entry);
      const type = readString(record.type).toLowerCase();
      if (type === "text") {
        return {
          type: "text",
          text: String(record.text ?? ""),
        } satisfies TextMessageBlock;
      }
      if (type === "markdown") {
        const markdown = String(record.markdown ?? record.text ?? "");
        if (!markdown.trim()) {
          return null;
        }
        return {
          type: "markdown",
          markdown,
        } satisfies MarkdownMessageBlock;
      }
      if (type === "math") {
        const latex = String(record.latex ?? "");
        if (!latex.trim()) {
          return null;
        }
        return {
          type: "math",
          latex,
          display: Boolean(record.display),
        } satisfies MathMessageBlock;
      }
      if (type === "code") {
        return {
          type: "code",
          language: readString(record.language),
          code: String(record.code ?? ""),
        } satisfies CodeMessageBlock;
      }
      if (type === "image") {
        const src = readString(record.src);
        if (!src) {
          return null;
        }
        const alt = readString(record.alt);
        return {
          type: "image",
          src,
          alt: alt || undefined,
        } satisfies ImageMessageBlock;
      }
      if (type === "table") {
        const rows = Array.isArray(record.rows)
          ? (record.rows as unknown[]).map((row) => readStringList(row))
          : [];
        return {
          type: "table",
          columns: readStringList(record.columns),
          rows,
        } satisfies TableMessageBlock;
      }
      if (type === "notice") {
        const level = readString(record.level).toLowerCase();
        return {
          type: "notice",
          level:
            level === "warning" || level === "error" || level === "info"
              ? level
              : "info",
          text: String(record.text ?? ""),
        } satisfies NoticeMessageBlock;
      }
      if (type === "chart") {
        const nestedChart =
          record.chart && typeof record.chart === "object" && !Array.isArray(record.chart)
            ? (record.chart as Record<string, unknown>)
            : null;
        const plotCandidate = nestedChart || record;
        const plot: Record<string, unknown> = {
          ...plotCandidate,
          kind:
            String(plotCandidate.kind || "").trim().toLowerCase() === "chart"
              ? "chart"
              : "chart",
        };
        delete plot.type;
        delete plot.chart;
        return {
          type: "chart",
          plot,
        } satisfies ChartMessageBlock;
      }
      if (type === "widget") {
        const widget = readRecord(record.widget);
        const kind = readString(widget.kind);
        if (!kind) {
          return null;
        }
        return {
          type: "widget",
          widget: {
            kind,
            props: readRecord(widget.props),
          },
        } satisfies WidgetMessageBlock;
      }
      if (type === "scorecard") {
        const metrics = Array.isArray(record.metrics) ? record.metrics : [];
        return {
          type: "widget",
          widget: {
            kind: "scorecard",
            props: {
              title: String(record.title || ""),
              subtitle: String(record.subtitle || ""),
              metrics,
            },
          },
        } satisfies WidgetMessageBlock;
      }
      if (type === "sortable_table") {
        const rows = Array.isArray(record.rows) ? record.rows : [];
        return {
          type: "widget",
          widget: {
            kind: "sortable_table",
            props: {
              title: String(record.title || ""),
              columns: readStringList(record.columns),
              rows,
            },
          },
        } satisfies WidgetMessageBlock;
      }
      if (type === "document_action") {
        const action = readRecord(record.action);
        const documentId = readString(action.documentId);
        const title = readString(action.title);
        const kind = readString(action.kind);
        if (!documentId || !kind) {
          return null;
        }
        return {
          type: "document_action",
          action: {
            kind,
            title,
            documentId,
          },
        } satisfies DocumentActionMessageBlock;
      }
      return null;
    })
    .filter((entry): entry is MessageBlock => Boolean(entry));

  return normalized.length > 0 ? normalized : fallbackAssistantBlocks(assistantText);
}

export type {
  CanvasDocumentRecord,
  ChartMessageBlock,
  CodeMessageBlock,
  DocumentActionMessageBlock,
  ImageMessageBlock,
  MarkdownMessageBlock,
  MathMessageBlock,
  MessageBlock,
  NoticeMessageBlock,
  TableMessageBlock,
  TextMessageBlock,
  WidgetMessageBlock,
};
export {
  fallbackAssistantBlocks,
  normalizeCanvasDocuments,
  normalizeMessageBlocks,
};
