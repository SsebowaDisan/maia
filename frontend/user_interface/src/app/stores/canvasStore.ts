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

export { useCanvasStore };
export type { CanvasDocumentState };
