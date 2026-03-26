export type ClickRippleEntry = {
  id: string;
  x: number;
  y: number;
  type: "click" | "hover";
};

export type HighlightColor = "yellow" | "green";

export type HighlightRegion = {
  keyword: string;
  color: HighlightColor;
  x: number;
  y: number;
  width: number;
  height: number;
};

export type DocumentHighlight = {
  word: string;
  snippet: string;
  color: HighlightColor;
};

export type ZoomHistoryEntry = {
  eventRef: string;
  eventType: string;
  eventIndex: number | null;
  timestamp: string;
  action: "zoom_in" | "zoom_out" | "zoom_reset" | "zoom_to_region";
  sceneSurface: string;
  sceneRef: string;
  graphNodeId: string;
  zoomLevel: number | null;
  zoomReason: string;
  zoomPolicyTriggers: string[];
};
