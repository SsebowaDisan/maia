import { sanitizeComputerUseText } from "../../utils/userFacingComputerUse";
import { compactValue } from "./helpers";
import type { HighlightRegion } from "./types";

type SceneRecord = Record<string, unknown>;

type OpenedPage = {
  url: string;
  title: string;
  pageIndex: number | null;
  reviewed: boolean;
};

type RoadmapStep = {
  toolId: string;
  title: string;
  whyThisStep: string;
};

type TeamChatSceneVisibilityOptions = {
  activeEventType: string;
  activeSceneData: SceneRecord;
  apiSceneActive: boolean;
  isBrowserScene: boolean;
  isDocsScene: boolean;
  isDocumentScene: boolean;
  isEmailScene: boolean;
  isSheetsScene: boolean;
  isSystemScene: boolean;
  snapshotUrl: string;
};

function looksLikePdfUrl(value: string): boolean {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) {
    return false;
  }
  return (
    normalized.includes(".pdf") ||
    normalized.includes("application/pdf") ||
    normalized.includes("/pdf?")
  );
}

function parsePercent(value: unknown): number | null {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return Math.max(0, Math.min(100, parsed));
}

function buildTargetRegion(
  activeSceneData: SceneRecord,
  actionTarget: SceneRecord,
  actionTargetLabel: string,
): { regionSource: SceneRecord; targetRegion: HighlightRegion | null } {
  const regionSource =
    activeSceneData["target_region"] && typeof activeSceneData["target_region"] === "object"
      ? (activeSceneData["target_region"] as SceneRecord)
      : actionTarget;
  const regionX = parsePercent(regionSource["x"] ?? regionSource["region_x"]);
  const regionY = parsePercent(regionSource["y"] ?? regionSource["region_y"]);
  const regionWidth = parsePercent(regionSource["width"] ?? regionSource["region_width"]);
  const regionHeight = parsePercent(regionSource["height"] ?? regionSource["region_height"]);
  const targetRegion =
    regionX !== null &&
    regionY !== null &&
    regionWidth !== null &&
    regionHeight !== null &&
    regionWidth > 0 &&
    regionHeight > 0
      ? {
          keyword: actionTargetLabel || "target",
          color: "yellow",
          x: regionX,
          y: regionY,
          width: regionWidth,
          height: regionHeight,
        }
      : null;
  return { regionSource, targetRegion };
}

function parseOpenedPages(activeSceneData: SceneRecord): OpenedPage[] {
  if (!Array.isArray(activeSceneData["opened_pages"])) {
    return [];
  }
  return activeSceneData["opened_pages"]
    .map((row) => {
      if (!row || typeof row !== "object") return null;
      const item = row as SceneRecord;
      const url = compactValue(item["url"]);
      if (!url || (!url.startsWith("http://") && !url.startsWith("https://"))) return null;
      const title = compactValue(item["title"]);
      const pageIdx = Number(item["page_index"]);
      const reviewed = Boolean(item["reviewed"]);
      return {
        url,
        title,
        pageIndex: Number.isFinite(pageIdx) && pageIdx >= 1 ? Math.round(pageIdx) : null,
        reviewed,
      };
    })
    .filter((row): row is OpenedPage => Boolean(row))
    .slice(-24);
}

function buildRoadmapSteps(activeSceneData: SceneRecord): RoadmapStep[] {
  if (!Array.isArray(activeSceneData["__roadmap_steps"])) {
    return [];
  }
  return (activeSceneData["__roadmap_steps"] as RoadmapStep[]).map((step) => ({
    toolId: sanitizeComputerUseText(step.toolId),
    title: sanitizeComputerUseText(step.title),
    whyThisStep: sanitizeComputerUseText(step.whyThisStep),
  }));
}

function shouldRenderTeamChatScene({
  activeEventType,
  activeSceneData,
  apiSceneActive,
  isBrowserScene,
  isDocsScene,
  isDocumentScene,
  isEmailScene,
  isSheetsScene,
  isSystemScene,
  snapshotUrl,
}: TeamChatSceneVisibilityOptions): boolean {
  return (
    (activeSceneData?.scene_surface === "team_chat" || activeEventType === "team_chat_message") &&
    !isBrowserScene &&
    !isEmailScene &&
    !isDocumentScene &&
    !isDocsScene &&
    !isSheetsScene &&
    !isSystemScene &&
    !apiSceneActive &&
    !snapshotUrl
  );
}

export {
  buildRoadmapSteps,
  buildTargetRegion,
  looksLikePdfUrl,
  parseOpenedPages,
  parsePercent,
  shouldRenderTeamChatScene,
};
export type { OpenedPage, RoadmapStep };
