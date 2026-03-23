import type { ApiSceneState } from "../api_scene_state";

type SkinPalette = {
  shellGradient: string;
  cardBg: string;
  cardBorder: string;
  textPrimary: string;
  textSecondary: string;
  accentBg: string;
  accentText: string;
};

type SkinDescriptor = {
  brand: string;
  theatreLabel: string;
  objectLabel: string;
  actionVerb: string;
  icon?: string;
};

type SkinProps = {
  state: ApiSceneState;
  palette: SkinPalette;
  descriptor: SkinDescriptor;
  activeTitle: string;
};

type SceneFamily =
  | "email" | "chat" | "sheet" | "crm" | "support" | "commerce"
  | "database" | "document" | "social" | "marketing" | "cloud"
  | "scheduling" | "design" | "api";

export type { SceneFamily, SkinDescriptor, SkinPalette, SkinProps };
