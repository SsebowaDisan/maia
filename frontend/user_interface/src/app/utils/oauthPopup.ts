type OAuthPopupResult =
  | { success: true }
  | { success: false; error: string };

type OAuthCompletePayload = {
  type?: string;
  success?: boolean;
  error?: string;
};

const DEFAULT_WIDTH = 560;
const DEFAULT_HEIGHT = 720;
const OAUTH_POPUP_TIMEOUT_MS = 120000;

function buildPopupFeatures(width: number, height: number): string {
  const left = Math.max(0, Math.round(window.screenX + (window.outerWidth - width) / 2));
  const top = Math.max(0, Math.round(window.screenY + (window.outerHeight - height) / 2));
  return [
    "popup=yes",
    "toolbar=no",
    "location=yes",
    "status=no",
    "menubar=no",
    "scrollbars=yes",
    "resizable=yes",
    `width=${width}`,
    `height=${height}`,
    `left=${left}`,
    `top=${top}`,
  ].join(",");
}

export function openOAuthPopup(
  authUrl: string,
  options?: { width?: number; height?: number; timeoutMs?: number },
): Promise<OAuthPopupResult> {
  const width = options?.width || DEFAULT_WIDTH;
  const height = options?.height || DEFAULT_HEIGHT;
  const timeoutMs = options?.timeoutMs || OAUTH_POPUP_TIMEOUT_MS;
  const name = `maia-oauth-${Date.now()}`;
  const popup = window.open(authUrl, name, buildPopupFeatures(width, height));

  if (!popup) {
    return Promise.resolve({
      success: false,
      error: "Popup blocked by browser settings.",
    });
  }

  popup.focus();

  return new Promise<OAuthPopupResult>((resolve) => {
    let settled = false;
    const complete = (result: OAuthPopupResult) => {
      if (settled) {
        return;
      }
      settled = true;
      window.removeEventListener("message", onMessage);
      window.clearInterval(closeCheckTimer);
      window.clearTimeout(timeoutHandle);
      try {
        if (!popup.closed) {
          popup.close();
        }
      } catch {
        // noop
      }
      resolve(result);
    };

    const onMessage = (event: MessageEvent<OAuthCompletePayload>) => {
      if (event.source !== popup) {
        return;
      }
      const payload = event.data || {};
      if (payload.type !== "oauth_complete") {
        return;
      }
      if (payload.success) {
        complete({ success: true });
        return;
      }
      complete({
        success: false,
        error: payload.error || "OAuth flow did not complete successfully.",
      });
    };

    const closeCheckTimer = window.setInterval(() => {
      try {
        if (popup.closed) {
          complete({
            success: false,
            error: "OAuth window was closed before completion.",
          });
        }
      } catch {
        complete({
          success: false,
          error: "Could not monitor OAuth popup state.",
        });
      }
    }, 400);

    const timeoutHandle = window.setTimeout(() => {
      complete({
        success: false,
        error: "OAuth flow timed out. Please try again.",
      });
    }, timeoutMs);

    window.addEventListener("message", onMessage);
  });
}

