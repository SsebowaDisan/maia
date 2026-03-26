// --- @maia/theatre ----------------------------------------------------------
// Live agent visualization SDK
//
// Quick start:
//   import { Theatre } from '@maia/theatre';
//   <Theatre streamUrl="/acp/events" />

export { Theatre } from "./components/Theatre";
export type { TheatreProps } from "./components/Theatre";

export { TeamThread } from "./components/TeamThread";
export type { TeamThreadProps } from "./components/TeamThread";

export { ActivityTimeline } from "./components/ActivityTimeline";
export type { ActivityTimelineProps } from "./components/ActivityTimeline";
export { AssemblyProgressPanel } from "./components/AssemblyProgressPanel";
export type { AssemblyProgressEvent, AssemblyProgressPanelProps } from "./components/AssemblyProgressPanel";
export { BrainReviewPanel } from "./components/BrainReviewPanel";
export type { BrainReviewEvent, BrainReviewPanelProps } from "./components/BrainReviewPanel";
export { DiffViewer } from "./components/DiffViewer";
export type { DiffViewerProps } from "./components/DiffViewer";
export { DoneStageOverlay } from "./components/DoneStageOverlay";
export type { DoneStageOverlayProps } from "./components/DoneStageOverlay";
export { FullscreenViewerOverlay } from "./components/FullscreenViewerOverlay";
export type {
  FullscreenTimelineItem,
  FullscreenViewerOverlayProps,
} from "./components/FullscreenViewerOverlay";
export { InteractionSuggestionsPanel } from "./components/InteractionSuggestionsPanel";
export type {
  InteractionSuggestion,
  InteractionSuggestionsPanelProps,
} from "./components/InteractionSuggestionsPanel";
export { PhaseTimeline } from "./components/PhaseTimeline";
export type { ActivityPhaseRow, PhaseTimelineProps } from "./components/PhaseTimeline";
export { ResearchTodoList } from "./components/ResearchTodoList";
export type { ResearchTodoListProps, RoadmapStep, TodoEvent } from "./components/ResearchTodoList";

export { MessageBubble } from "./components/MessageBubble";
export type { MessageBubbleProps } from "./components/MessageBubble";

export { AgentAvatar } from "./components/AgentAvatar";
export type { AgentAvatarProps } from "./components/AgentAvatar";

export { CostBar } from "./components/CostBar";
export type { CostBarProps } from "./components/CostBar";

export { ReplayControls } from "./components/ReplayControls";
export type { ReplayControlsProps } from "./components/ReplayControls";

export { DesktopSceneRouter } from "./components/DesktopSceneRouter";
export type { DesktopSceneRouterProps } from "./components/DesktopSceneRouter";

export { TheatreDesktop } from "./components/TheatreDesktop";
export type { TheatreDesktopProps } from "./components/TheatreDesktop";
export { TheatreDesktopViewer } from "./components/TheatreDesktopViewer";
export type { TheatreDesktopViewerProps } from "./components/TheatreDesktopViewer";

export { EmailScene } from "./desktop-scenes/EmailScene";
export { DocsScene } from "./desktop-scenes/DocsScene";
export { SheetsScene } from "./desktop-scenes/SheetsScene";
export { BrowserScene } from "./desktop-scenes/BrowserScene";
export { ApiScene } from "./desktop-scenes/ApiScene";
export { DocumentFallbackScene, DocumentPdfScene } from "./desktop-scenes/DocumentScenes";
export { SnapshotScene } from "./desktop-scenes/SnapshotScene";
export { DefaultScene, SystemScene } from "./desktop-scenes/SystemFallbackScenes";
export { parseApiSceneState } from "./desktop-scenes/api/api_scene_state";
export type {
  ApiFieldDiff,
  ApiSceneState,
  ApiValidationCheck,
} from "./desktop-scenes/api/api_scene_state";
export { useComputerUseStream } from "./desktop-scenes/useComputerUseStream";
export type { UseComputerUseStreamOptions } from "./desktop-scenes/useComputerUseStream";
export { GhostCursor } from "./desktop-scenes/GhostCursor";
export { ClickRipple } from "./desktop-scenes/ClickRipple";
export type {
  ClickRippleEntry,
  DocumentHighlight,
  HighlightColor,
  HighlightRegion,
  ZoomHistoryEntry,
} from "./desktop-scenes/types";

export { maiaTheme, resolveTheatreTheme } from "./theme";
export type { TheatreTheme, TheatreThemeOverride } from "./theme";

export { useACPStream } from "./hooks/useACPStream";
export type { UseACPStreamOptions, ACPStreamState } from "./hooks/useACPStream";

export { useReplay } from "./hooks/useReplay";
export type { UseReplayOptions, ReplayState } from "./hooks/useReplay";

export { SurfaceRenderer } from "./surfaces/SurfaceRenderer";
export type { SurfaceRendererProps } from "./surfaces/SurfaceRenderer";
export type { SurfaceType, SurfaceState } from "./surfaces/types";

export { fromAgentActivityEvent, fromAgentActivityEvents } from "./adapters/fromAgentActivityEvent";
export type { AgentActivityEventLike } from "./adapters/fromAgentActivityEvent";

export { ConnectorSkinComponent as ConnectorSkin } from "./skins";
export type { ConnectorSkinProps, SkinPalette, SkinDescriptor } from "./skins";
export { getConnectorSkin, hasConnectorSkin, getSkinnedConnectorIds } from "./skins";
