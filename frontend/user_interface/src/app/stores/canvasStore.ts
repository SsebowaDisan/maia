import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { CanvasDocumentRecord } from "../messageBlocks";

type CanvasDocumentState = CanvasDocumentRecord & {
  isDirty: boolean;
};

type CanvasStoreState = {
  activeDocumentId: string | null;
  documentsById: Record<string, CanvasDocumentState>;
  isOpen: boolean;
  closePanel: () => void;
  openDocument: (documentId: string) => void;
  upsertDocuments: (documents: CanvasDocumentRecord[]) => void;
  updateDocumentContent: (documentId: string, content: string) => void;
  markDocumentSaved: (documentId: string, content?: string) => void;
};

type CanvasSyncMessage =
  | {
      senderId: string;
      type: "open";
      documentId: string;
    }
  | {
      senderId: string;
      type: "content";
      documentId: string;
      content: string;
      title?: string;
    }
  | {
      senderId: string;
      type: "saved";
      documentId: string;
      content?: string;
    };
type CanvasSyncStorageMessage = CanvasSyncMessage & {
  ts?: number;
};

const CANVAS_SYNC_CHANNEL_NAME = "maia.canvas.sync.v1";
const CANVAS_SYNC_STORAGE_KEY = "maia.canvas.sync.storage.v1";
const CANVAS_SENDER_ID = `canvas-${Math.random().toString(36).slice(2)}-${Date.now()}`;
const canvasSyncChannel =
  typeof window !== "undefined" && "BroadcastChannel" in window
    ? new BroadcastChannel(CANVAS_SYNC_CHANNEL_NAME)
    : null;

function postCanvasSync(message: Omit<CanvasSyncMessage, "senderId">) {
  const payload = {
    ...message,
    senderId: CANVAS_SENDER_ID,
  } satisfies CanvasSyncStorageMessage;

  if (canvasSyncChannel) {
    canvasSyncChannel.postMessage(payload);
    return;
  }

  if (typeof window === "undefined") {
    return;
  }
  try {
    const wirePayload: CanvasSyncStorageMessage = {
      ...payload,
      ts: Date.now(),
    };
    window.localStorage.setItem(CANVAS_SYNC_STORAGE_KEY, JSON.stringify(wirePayload));
    window.localStorage.removeItem(CANVAS_SYNC_STORAGE_KEY);
  } catch {
    // Ignore storage errors (private mode / quota) and continue local-only.
  }
}

function applyCanvasSyncMessage(payload: CanvasSyncMessage) {
  if (!payload || payload.senderId === CANVAS_SENDER_ID) {
    return;
  }
  useCanvasStore.setState((state) => {
    if (!payload.documentId) {
      return state;
    }
    const existing = state.documentsById[payload.documentId];
    if (!existing && payload.type !== "open") {
      return state;
    }

    if (payload.type === "open") {
      if (!state.documentsById[payload.documentId]) {
        return state;
      }
      return {
        ...state,
        activeDocumentId: payload.documentId,
        isOpen: true,
      };
    }

    if (payload.type === "content" && existing) {
      return {
        ...state,
        documentsById: {
          ...state.documentsById,
          [payload.documentId]: {
            ...existing,
            title: payload.title || existing.title,
            content: String(payload.content || ""),
            isDirty: true,
          },
        },
      };
    }

    if (payload.type === "saved" && existing) {
      const hasContent = typeof payload.content === "string";
      return {
        ...state,
        documentsById: {
          ...state.documentsById,
          [payload.documentId]: {
            ...existing,
            content: hasContent ? String(payload.content) : existing.content,
            isDirty: false,
          },
        },
      };
    }

    return state;
  });
}

const useCanvasStore = create<CanvasStoreState>()(
  persist(
    (set) => ({
      activeDocumentId: null,
      documentsById: {},
      isOpen: false,
      closePanel: () =>
        set({
          isOpen: false,
        }),
      openDocument: (documentId) =>
        set((state) => {
          if (!documentId || !state.documentsById[documentId]) {
            return state;
          }
          postCanvasSync({
            type: "open",
            documentId,
          });
          return {
            activeDocumentId: documentId,
            isOpen: true,
          };
        }),
      upsertDocuments: (documents) =>
        set((state) => {
          if (!Array.isArray(documents) || documents.length <= 0) {
            return state;
          }
          const documentsById = { ...state.documentsById };
          for (const document of documents) {
            const id = String(document.id || "").trim();
            const title = String(document.title || "").trim();
            if (!id || !title) {
              continue;
            }
            const current = documentsById[id];
            documentsById[id] = {
              id,
              title,
              content:
                current && current.isDirty
                  ? current.content
                  : String(document.content ?? current?.content ?? ""),
              isDirty: current?.isDirty || false,
            };
          }
          return {
            documentsById,
          };
        }),
      updateDocumentContent: (documentId, content) =>
        set((state) => {
          const current = state.documentsById[documentId];
          if (!current) {
            return state;
          }
          postCanvasSync({
            type: "content",
            documentId,
            content,
            title: current.title,
          });
          return {
            documentsById: {
              ...state.documentsById,
              [documentId]: {
                ...current,
                content,
                isDirty: true,
              },
            },
          };
        }),
      markDocumentSaved: (documentId, content) =>
        set((state) => {
          const current = state.documentsById[documentId];
          if (!current) {
            return state;
          }
          const hasContent = typeof content === "string";
          postCanvasSync({
            type: "saved",
            documentId,
            content: hasContent ? content : undefined,
          });
          return {
            documentsById: {
              ...state.documentsById,
              [documentId]: {
                ...current,
                content: hasContent ? content : current.content,
                isDirty: false,
              },
            },
          };
        }),
    }),
    {
      name: "maia.canvas.documents.v1",
      partialize: (state) => ({
        activeDocumentId: state.activeDocumentId,
        documentsById: state.documentsById,
      }),
    },
  ),
);

if (canvasSyncChannel) {
  canvasSyncChannel.onmessage = (event: MessageEvent<CanvasSyncMessage>) => {
    applyCanvasSyncMessage(event.data);
  };
} else if (typeof window !== "undefined") {
  window.addEventListener("storage", (event: StorageEvent) => {
    if (event.key !== CANVAS_SYNC_STORAGE_KEY || !event.newValue) {
      return;
    }
    try {
      const payload = JSON.parse(event.newValue) as CanvasSyncStorageMessage;
      applyCanvasSyncMessage(payload);
    } catch {
      // Ignore malformed sync payloads.
    }
  });
}

export { useCanvasStore };
export type { CanvasDocumentState };
