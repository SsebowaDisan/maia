import { request } from "./core";
import type { SettingsResponse } from "./types";

function getSettings() {
  return request<SettingsResponse>("/api/settings");
}

function patchSettings(values: Record<string, unknown>) {
  return request<SettingsResponse>("/api/settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ values }),
  });
}

export { getSettings, patchSettings };
