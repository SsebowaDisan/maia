export type { SkinPalette, SkinDescriptor, ConnectorSkin } from "./types";
export { ConnectorSkin as ConnectorSkinComponent } from "./ConnectorSkin";
export type { ConnectorSkinProps } from "./ConnectorSkin";
export {
  getConnectorSkin,
  hasConnectorSkin,
  getSkinnedConnectorIds,
  SKIN_PALETTES,
  SKIN_DESCRIPTORS,
  DEFAULT_PALETTE,
  DEFAULT_DESCRIPTOR,
} from "./palettes";