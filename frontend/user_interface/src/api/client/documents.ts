import { request } from "./core";

type UpdateCanvasDocumentPayload = {
  title?: string;
  content: string;
};

type CanvasDocumentResponse = {
  id: string;
  title: string;
  content: string;
  date_updated?: string | null;
};

type ListCanvasDocumentsOptions = {
  limit?: number;
};

type ListCanvasDocumentsResponse =
  | CanvasDocumentResponse[]
  | {
      documents?: CanvasDocumentResponse[];
      items?: CanvasDocumentResponse[];
    };

function listDocuments(options?: ListCanvasDocumentsOptions) {
  const query = new URLSearchParams();
  if (typeof options?.limit === "number" && Number.isFinite(options.limit) && options.limit > 0) {
    query.set("limit", String(Math.round(options.limit)));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<ListCanvasDocumentsResponse>(`/api/documents${suffix}`).then((payload) => {
    if (Array.isArray(payload)) {
      return payload;
    }
    if (Array.isArray(payload?.documents)) {
      return payload.documents;
    }
    if (Array.isArray(payload?.items)) {
      return payload.items;
    }
    return [];
  });
}

function updateCanvasDocument(documentId: string, payload: UpdateCanvasDocumentPayload) {
  return request<CanvasDocumentResponse>(`/api/documents/${encodeURIComponent(documentId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: payload.title ?? null,
      content: payload.content,
    }),
  });
}

export { listDocuments, updateCanvasDocument };
export type {
  CanvasDocumentResponse,
  ListCanvasDocumentsOptions,
  UpdateCanvasDocumentPayload,
};
