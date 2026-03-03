import { createMindmapShare } from "../../api/client";

type MindmapSharePayload = {
  version: 1;
  conversationId?: string;
  map: Record<string, unknown>;
};

const PARAM_KEY = "mindmap_share";
const PARAM_SHARE_ID = "mindmap_share_id";

function toBase64Url(raw: string): string {
  const bytes = new TextEncoder().encode(raw);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function fromBase64Url(raw: string): string {
  const normalized = raw.replace(/-/g, "+").replace(/_/g, "/");
  const padding = normalized.length % 4 === 0 ? "" : "=".repeat(4 - (normalized.length % 4));
  const binary = atob(normalized + padding);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

async function buildMindmapShareLink(params: {
  map: Record<string, unknown>;
  conversationId?: string | null;
  title?: string;
}): Promise<string> {
  const url = new URL(window.location.href);
  const conversationId = String(params.conversationId || "").trim();
  if (conversationId) {
    try {
      const shared = await createMindmapShare(conversationId, {
        map: params.map,
        title: params.title,
      });
      url.searchParams.delete(PARAM_KEY);
      url.searchParams.set(PARAM_SHARE_ID, shared.share_id);
      return url.toString();
    } catch {
      // Fallback to inline payload when share API is unavailable.
    }
  }

  const payload: MindmapSharePayload = {
    version: 1,
    conversationId: conversationId || undefined,
    map: params.map,
  };
  url.searchParams.delete(PARAM_SHARE_ID);
  url.searchParams.set(PARAM_KEY, toBase64Url(JSON.stringify(payload)));
  return url.toString();
}

function readMindmapShareFromUrl(search: string = window.location.search): {
  map?: Record<string, unknown>;
  conversationId?: string;
  shareId?: string;
} | null {
  const params = new URLSearchParams(search);
  const shareId = String(params.get(PARAM_SHARE_ID) || "").trim();
  if (shareId) {
    return {
      shareId,
    };
  }
  const encoded = params.get(PARAM_KEY);
  if (!encoded) {
    return null;
  }
  try {
    const parsed = JSON.parse(fromBase64Url(encoded)) as MindmapSharePayload;
    if (!parsed || Number(parsed.version) !== 1 || !parsed.map || typeof parsed.map !== "object") {
      return null;
    }
    return {
      map: parsed.map,
      conversationId: parsed.conversationId,
    };
  } catch {
    return null;
  }
}

function clearMindmapShareInUrl(): void {
  const url = new URL(window.location.href);
  const hasInline = url.searchParams.has(PARAM_KEY);
  const hasSharedId = url.searchParams.has(PARAM_SHARE_ID);
  if (!hasInline && !hasSharedId) {
    return;
  }
  url.searchParams.delete(PARAM_KEY);
  url.searchParams.delete(PARAM_SHARE_ID);
  window.history.replaceState({}, "", url.toString());
}

export {
  buildMindmapShareLink,
  clearMindmapShareInUrl,
  readMindmapShareFromUrl,
};
