import { create } from "zustand";
import { createJSONStorage, persist, type StateStorage } from "zustand/middleware";

import type { CanvasDocumentRecord } from "../messageBlocks";

type CanvasDocumentState = CanvasDocumentRecord & {
  isDirty: boolean;
};

type PersistedCanvasStoreState = {
  activeDocumentId: string | null;
  documentsById: Record<string, Partial<CanvasDocumentState>>;
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
const CANVAS_DOCUMENTS_STORAGE_KEY = "maia.canvas.documents.v1";
const CANVAS_SENDER_ID = `canvas-${Math.random().toString(36).slice(2)}-${Date.now()}`;
const CANVAS_PERSIST_SOFT_LIMIT_BYTES = 180_000;
const canvasSyncChannel =
  typeof window !== "undefined" && "BroadcastChannel" in window
    ? new BroadcastChannel(CANVAS_SYNC_CHANNEL_NAME)
    : null;

function sanitizeLegacyCanvasStorage() {
  if (typeof window === "undefined") {
    return;
  }
  try {
    const raw = window.localStorage.getItem(CANVAS_DOCUMENTS_STORAGE_KEY);
    if (!raw) {
      return;
    }
    if (raw.length <= CANVAS_PERSIST_SOFT_LIMIT_BYTES) {
      return;
    }
    const parsed = JSON.parse(raw) as { state?: PersistedCanvasStoreState; version?: number };
    const documentEntries = Object.entries(parsed?.state?.documentsById || {});
    const compactedState = {
      state: {
        activeDocumentId: parsed?.state?.activeDocumentId || null,
        documentsById: Object.fromEntries(
          documentEntries.slice(0, 2).map(([id, doc]) => [
            id,
            {
              id,
              title: String((doc as Partial<CanvasDocumentState>)?.title || "").slice(0, 160),
              content: "",
              infoHtml: "",
              userPrompt: String((doc as Partial<CanvasDocumentState>)?.userPrompt || "").slice(0, 400),
              modeVariant: String((doc as Partial<CanvasDocumentState>)?.modeVariant || "").slice(0, 64),
              isDirty: Boolean((doc as Partial<CanvasDocumentState>)?.isDirty),
            },
          ]),
        ),
      },
      version: parsed?.version ?? 0,
    };
    window.localStorage.setItem(CANVAS_DOCUMENTS_STORAGE_KEY, JSON.stringify(compactedState));
  } catch {
    try {
      window.localStorage.removeItem(CANVAS_DOCUMENTS_STORAGE_KEY);
    } catch {
      // Ignore final storage failures.
    }
  }
}

sanitizeLegacyCanvasStorage();

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

function compactPersistedCanvasState(state: CanvasStoreState): PersistedCanvasStoreState {
  const entries = Object.entries(state.documentsById || {});
  const activeId = state.activeDocumentId;
  const prioritized = entries.sort(([aId, aDoc], [bId, bDoc]) => {
    if (aId === activeId) return -1;
    if (bId === activeId) return 1;
    if (aDoc.isDirty && !bDoc.isDirty) return -1;
    if (bDoc.isDirty && !aDoc.isDirty) return 1;
    return bId.localeCompare(aId);
  });

  const limited = prioritized.slice(0, 6);
  const documentsById = Object.fromEntries(
    limited.map(([id, doc]) => [
      id,
      {
        id,
        title: String(doc.title || "").slice(0, 240),
        content: String(doc.content || "").slice(0, 12000),
        infoHtml: String(doc.infoHtml || "").slice(0, 8000),
        userPrompt: String(doc.userPrompt || "").slice(0, 2000),
        modeVariant: String(doc.modeVariant || "").slice(0, 64),
        isDirty: Boolean(doc.isDirty),
      } satisfies Partial<CanvasDocumentState>,
    ]),
  );

  return {
    activeDocumentId: activeId && documentsById[activeId] ? activeId : Object.keys(documentsById)[0] || null,
    documentsById,
  };
}

const safeCanvasStorage: StateStorage = {
  getItem: (name) => {
    if (typeof window === "undefined") {
      return null;
    }
    try {
      const raw = window.localStorage.getItem(name);
      if (name === CANVAS_DOCUMENTS_STORAGE_KEY && raw && raw.length > CANVAS_PERSIST_SOFT_LIMIT_BYTES) {
        sanitizeLegacyCanvasStorage();
        return window.localStorage.getItem(name);
      }
      return raw;
    } catch {
      return null;
    }
  },
  setItem: (name, value) => {
    if (typeof window === "undefined") {
      return;
    }
    try {
      window.localStorage.setItem(name, value);
      return;
    } catch {
      try {
        const parsed = JSON.parse(String(value || "{}")) as { state?: PersistedCanvasStoreState };
        const compactedState = {
          state: {
            activeDocumentId: parsed?.state?.activeDocumentId || null,
            documentsById: Object.fromEntries(
              Object.entries(parsed?.state?.documentsById || {}).slice(0, 3).map(([id, doc]) => [
                id,
                {
                  id,
                  title: String((doc as Partial<CanvasDocumentState>)?.title || "").slice(0, 160),
                  content: "",
                  infoHtml: "",
                  userPrompt: String((doc as Partial<CanvasDocumentState>)?.userPrompt || "").slice(0, 500),
                  modeVariant: String((doc as Partial<CanvasDocumentState>)?.modeVariant || "").slice(0, 64),
                  isDirty: Boolean((doc as Partial<CanvasDocumentState>)?.isDirty),
                },
              ]),
            ),
          },
          version: 0,
        };
        window.localStorage.setItem(name, JSON.stringify(compactedState));
      } catch {
        try {
          window.localStorage.removeItem(name);
        } catch {
          // Ignore final storage failures.
        }
      }
    }
  },
  removeItem: (name) => {
    if (typeof window === "undefined") {
      return;
    }
    try {
      window.localStorage.removeItem(name);
    } catch {
      // Ignore storage failures.
    }
  },
};

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
              infoHtml: String(document.infoHtml ?? current?.infoHtml ?? ""),
              infoPanel:
                document.infoPanel && typeof document.infoPanel === "object" && !Array.isArray(document.infoPanel)
                  ? document.infoPanel
                  : current?.infoPanel,
              userPrompt: String(document.userPrompt ?? current?.userPrompt ?? ""),
              modeVariant: String(document.modeVariant ?? current?.modeVariant ?? ""),
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
      name: CANVAS_DOCUMENTS_STORAGE_KEY,
      storage: createJSONStorage(() => safeCanvasStorage),
      partialize: (state) => ({
        ...compactPersistedCanvasState(state),
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
