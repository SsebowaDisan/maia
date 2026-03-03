type MindmapSharePayload = {
  version: 1;
  conversationId?: string;
  map: Record<string, unknown>;
};

const PARAM_KEY = "mindmap_share";

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

function buildMindmapShareLink(params: {
  map: Record<string, unknown>;
  conversationId?: string | null;
}): string {
  const payload: MindmapSharePayload = {
    version: 1,
    conversationId: params.conversationId || undefined,
    map: params.map,
  };
  const url = new URL(window.location.href);
  url.searchParams.set(PARAM_KEY, toBase64Url(JSON.stringify(payload)));
  return url.toString();
}

function readMindmapShareFromUrl(search: string = window.location.search): {
  map: Record<string, unknown>;
  conversationId?: string;
} | null {
  const params = new URLSearchParams(search);
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
  if (!url.searchParams.has(PARAM_KEY)) {
    return;
  }
  url.searchParams.delete(PARAM_KEY);
  window.history.replaceState({}, "", url.toString());
}

export {
  buildMindmapShareLink,
  clearMindmapShareInUrl,
  readMindmapShareFromUrl,
};

