import { request } from "./core";
import type { SettingsResponse } from "./types";

function getSettings() {
  return request<SettingsResponse>("/api/settings");
}

export { getSettings };
