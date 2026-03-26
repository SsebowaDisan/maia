// --- @maia/sdk/theatre ------------------------------------------------------
// Live agent visualization. Import from '@maia/sdk/theatre' for React components.

export { Theatre } from "@maia/theatre";
export type { TheatreProps } from "@maia/theatre";

export { TeamThread } from "@maia/theatre";
export type { TeamThreadProps } from "@maia/theatre";

export { ActivityTimeline } from "@maia/theatre";
export type { ActivityTimelineProps } from "@maia/theatre";
export { DiffViewer, DoneStageOverlay, FullscreenViewerOverlay, InteractionSuggestionsPanel } from "@maia/theatre";
export type {
  ActivityPhaseRow,
  AssemblyProgressEvent,
  AssemblyProgressPanelProps,
  BrainReviewEvent,
  BrainReviewPanelProps,
  DiffViewerProps,
  DoneStageOverlayProps,
  FullscreenTimelineItem,
  FullscreenViewerOverlayProps,
  InteractionSuggestion,
  InteractionSuggestionsPanelProps,
  PhaseTimelineProps,
  ResearchTodoListProps,
  RoadmapStep,
  TodoEvent,
} from "@maia/theatre";
export { AssemblyProgressPanel, BrainReviewPanel, PhaseTimeline, ResearchTodoList } from "@maia/theatre";

export { AgentAvatar } from "@maia/theatre";
export type { AgentAvatarProps } from "@maia/theatre";

export { CostBar } from "@maia/theatre";
export type { CostBarProps } from "@maia/theatre";

export { ReplayControls } from "@maia/theatre";
export type { ReplayControlsProps } from "@maia/theatre";

export { DesktopSceneRouter } from "@maia/theatre";
export type { DesktopSceneRouterProps } from "@maia/theatre";

export { TheatreDesktop } from "@maia/theatre";
export type { TheatreDesktopProps } from "@maia/theatre";
export { TheatreDesktopViewer } from "@maia/theatre";
export type { TheatreDesktopViewerProps } from "@maia/theatre";

export {
  ApiScene,
  BrowserScene,
  DefaultScene,
  DocsScene,
  DocumentFallbackScene,
  DocumentPdfScene,
  EmailScene,
  GhostCursor,
  ClickRipple,
  SheetsScene,
  SnapshotScene,
  SystemScene,
  useComputerUseStream,
} from "@maia/theatre";
export type {
  ApiFieldDiff,
  ApiSceneState,
  ApiValidationCheck,
  ClickRippleEntry,
  DocumentHighlight,
  HighlightColor,
  HighlightRegion,
  UseComputerUseStreamOptions,
  ZoomHistoryEntry,
} from "@maia/theatre";
export { parseApiSceneState } from "@maia/theatre";

export { maiaTheme, resolveTheatreTheme } from "@maia/theatre";
export type { TheatreTheme, TheatreThemeOverride } from "@maia/theatre";

export { useACPStream } from "@maia/theatre";
export type { UseACPStreamOptions, ACPStreamState } from "@maia/theatre";

export { useReplay } from "@maia/theatre";
export type { UseReplayOptions, ReplayState } from "@maia/theatre";

export { fromAgentActivityEvent, fromAgentActivityEvents } from "@maia/theatre";
export type { AgentActivityEventLike } from "@maia/theatre";
