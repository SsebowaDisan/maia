type SurfaceType =
  | "system"
  | "browser"
  | "email"
  | "document"
  | "snapshot"
  | "chat"
  | "generic";

interface SurfaceState {
  type: SurfaceType;
  title?: string;
  detail?: string;
  url?: string;
  html?: string;
  text?: string;
}

export type { SurfaceType, SurfaceState };
