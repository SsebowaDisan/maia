/**
 * Skin types — connector-branded visual wrapping for Theatre surfaces.
 */

export type SkinPalette = {
  /** CSS class for the outer shell gradient. */
  shellGradient: string;
  /** Card background. */
  cardBg: string;
  /** Card border. */
  cardBorder: string;
  /** Primary text color. */
  textPrimary: string;
  /** Secondary text color. */
  textSecondary: string;
  /** Accent background. */
  accentBg: string;
  /** Accent text color. */
  accentText: string;
};

export type SkinDescriptor = {
  /** Brand name shown in the header (e.g., "Gmail", "Slack"). */
  brand: string;
  /** What Theatre shows as the context label (e.g., "Mail", "Channel"). */
  theatreLabel: string;
  /** What the primary object is called (e.g., "Thread", "Message"). */
  objectLabel: string;
  /** Present-tense verb for what's happening (e.g., "Composing email"). */
  actionVerb: string;
};

export type ConnectorSkin = {
  palette: SkinPalette;
  descriptor: SkinDescriptor;
};