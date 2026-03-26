import type { ApiSceneState } from "../api_scene_state";
import type { SkinProps } from "./skinTypes";
import { getDescriptor, getPalette, resolveSkinVariant } from "./skinPalettes";
import type { SkinVariant } from "./skinPalettes";

import { ChatSkin } from "./ChatSkin";
import { CloudSkin } from "./CloudSkin";
import { CommerceSkin } from "./CommerceSkin";
import { CrmSkin } from "./CrmSkin";
import { DatabaseSkin } from "./DatabaseSkin";
import { DesignSkin } from "./DesignSkin";
import { DocumentSkin } from "./DocumentSkin";
import { EmailSkin } from "./EmailSkin";
import { MarketingSkin } from "./MarketingSkin";
import { ProjectSkin } from "./ProjectSkin";
import { SchedulingSkin } from "./SchedulingSkin";
import { SheetSkin } from "./SheetSkin";
import { SocialSkin } from "./SocialSkin";
import { SupportSkin } from "./SupportSkin";

// ── Scene family → skin component ────────────────────────────────────────────
const FAMILY_SKINS: Record<string, React.ComponentType<SkinProps>> = {
  email: EmailSkin,
  chat: ChatSkin,
  sheet: SheetSkin,
  crm: CrmSkin,
  support: SupportSkin,
  commerce: CommerceSkin,
  database: DatabaseSkin,
  document: DocumentSkin,
  social: SocialSkin,
  marketing: MarketingSkin,
  cloud: CloudSkin,
  scheduling: SchedulingSkin,
  design: DesignSkin,
  api: ProjectSkin,          // project management / developer tools use project skin
};

// ── Brand overrides — some brands get a specific skin regardless of family ───
const BRAND_SKIN_OVERRIDES: Record<string, React.ComponentType<SkinProps>> = {
  gmail: EmailSkin,
  outlook: EmailSkin,
  slack: ChatSkin,
  discord: ChatSkin,
  microsoft_teams: ChatSkin,
  twilio: ChatSkin,
  sheets: SheetSkin,
  excel: SheetSkin,
  airtable: SheetSkin,
  salesforce: CrmSkin,
  hubspot: CrmSkin,
  zendesk: SupportSkin,
  intercom: SupportSkin,
  stripe: CommerceSkin,
  shopify: CommerceSkin,
  sap: CommerceSkin,
  quickbooks: CommerceSkin,
  xero: CommerceSkin,
  postgresql: DatabaseSkin,
  supabase: DatabaseSkin,
  bigquery: DatabaseSkin,
  pinecone: DatabaseSkin,
  notion: DocumentSkin,
  confluence: DocumentSkin,
  dropbox: DocumentSkin,
  box: DocumentSkin,
  docusign: DocumentSkin,
  twitter: SocialSkin,
  linkedin: SocialSkin,
  youtube: SocialSkin,
  spotify: SocialSkin,
  mailchimp: MarketingSkin,
  webflow: MarketingSkin,
  aws: CloudSkin,
  cloudflare: CloudSkin,
  vercel: CloudSkin,
  calendly: SchedulingSkin,
  google_calendar: SchedulingSkin,
  figma: DesignSkin,
  github: ProjectSkin,
  linear: ProjectSkin,
  jira: ProjectSkin,
  asana: ProjectSkin,
  monday: ProjectSkin,
  trello: ProjectSkin,
  openai: ProjectSkin,
};

type SkinResolution = {
  Skin: React.ComponentType<SkinProps>;
  variant: SkinVariant;
  props: SkinProps;
} | null;

/**
 * Resolve the correct skin component + props for a given API scene state.
 * Returns null if no variant can be resolved (falls back to GenericApiScene).
 */
function resolveSkin(state: ApiSceneState, activeTitle: string): SkinResolution {
  const variant = resolveSkinVariant(state.brandSlug, state.sceneFamily);
  if (!variant) return null;

  const palette = getPalette(variant);
  const descriptor = getDescriptor(variant);

  // Determine skin component: brand override first, then scene family, then ProjectSkin fallback
  const slug = (state.brandSlug || "").trim().toLowerCase();
  const family = (state.sceneFamily || "").trim().toLowerCase();
  const Skin =
    BRAND_SKIN_OVERRIDES[slug] ||
    BRAND_SKIN_OVERRIDES[variant] ||
    FAMILY_SKINS[family] ||
    ProjectSkin;

  return {
    Skin,
    variant,
    props: { state, palette, descriptor, activeTitle },
  };
}

export { resolveSkin };
export type { SkinResolution };
