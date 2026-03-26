import type { RefObject } from "react";
import { ClickRipple } from "../ClickRipple";
import { GhostCursor } from "../GhostCursor";
import { InteractionOverlay } from "../InteractionOverlay";
import { ThoughtBubble } from "../ThoughtBubble";
import {
  ComparePanel,
  CopyPulse,
  ExecutionRoadmapOverlay,
  FindOverlay,
  ScrollMeter,
  VerifierConflictBadge,
  ZoomBadge,
} from "./browserPanels";
import type { BrowserSceneProps } from "./common";

type OverlayChromeProps = Pick<
  BrowserSceneProps,
  | "activeDetail"
  | "activeEventType"
  | "action"
  | "actionPhase"
  | "actionStatus"
  | "actionTargetLabel"
  | "compareLeft"
  | "compareRight"
  | "compareVerdict"
  | "copyPulseText"
  | "copyPulseVisible"
  | "cursorSource"
  | "cursorX"
  | "cursorY"
  | "dedupedBrowserKeywords"
  | "findMatchCount"
  | "findQuery"
  | "isClickEvent"
  | "scrollDirection"
  | "semanticFindResults"
  | "showFindOverlay"
  | "verifierConflict"
  | "verifierConflictReason"
  | "verifierRecheckRequired"
  | "zoomEscalationRequested"
  | "zoomLevel"
  | "zoomReason"
> & {
  clickRipples: NonNullable<BrowserSceneProps["clickRipples"]>;
  effectiveScrollPercent: number | null;
  handleScrollSelect?: (percent: number) => void;
  pageIndex: number | null;
  roadmapActiveIndex: number;
  roadmapSteps: Array<{ toolId: string; title: string; whyThisStep: string }>;
  roadmapVisible: boolean;
  sceneNarration: string | null;
  showOverlayCursor: boolean;
};

function OverlayChrome(props: OverlayChromeProps) {
  const scrollControls = (
    <ScrollMeter
      scrollPercent={props.effectiveScrollPercent}
      onSelect={props.handleScrollSelect}
    />
  );

  return (
    <>
      {scrollControls}
      <VerifierConflictBadge
        verifierConflict={props.verifierConflict}
        verifierConflictReason={props.verifierConflictReason}
        verifierRecheckRequired={props.verifierRecheckRequired}
        zoomEscalationRequested={props.zoomEscalationRequested}
      />
      <ZoomBadge zoomLevel={props.zoomLevel} zoomReason={props.zoomReason} />
      <ComparePanel
        compareLeft={props.compareLeft}
        compareRight={props.compareRight}
        compareVerdict={props.compareVerdict}
      />
      <InteractionOverlay
        sceneSurface="website"
        activeEventType={props.activeEventType}
        activeDetail={props.activeDetail}
        scrollDirection={props.scrollDirection}
        action={props.action}
        actionPhase={props.actionPhase}
        actionStatus={props.actionStatus}
        actionTargetLabel={props.actionTargetLabel}
      />
      {props.showFindOverlay ? (
        <FindOverlay
          dedupedBrowserKeywords={props.dedupedBrowserKeywords}
          findMatchCount={props.findMatchCount}
          findQuery={props.findQuery}
          semanticFindResults={props.semanticFindResults}
        />
      ) : null}
      <CopyPulse copyPulseText={props.copyPulseText} copyPulseVisible={props.copyPulseVisible} />
      {props.showOverlayCursor ? (
        <>
          <GhostCursor
            cursorX={props.cursorX ?? null}
            cursorY={props.cursorY ?? null}
            isClick={props.isClickEvent ?? false}
            advisory={props.cursorSource === "suggested"}
          />
          <ClickRipple ripples={props.clickRipples} />
        </>
      ) : null}
      <ThoughtBubble text={props.sceneNarration} />
      {props.pageIndex !== null ? (
        <div className="pointer-events-none absolute right-3 bottom-3 rounded-full border border-black/[0.1] bg-white/92 px-2.5 py-1 text-[10px] text-[#4a4f5c]">
          Page {Math.max(1, props.pageIndex)}
        </div>
      ) : null}
      <ExecutionRoadmapOverlay
        roadmapSteps={props.roadmapSteps}
        roadmapActiveIndex={props.roadmapActiveIndex}
        visible={props.roadmapVisible}
      />
    </>
  );
}

type SnapshotPaneProps = OverlayChromeProps & {
  crossFadeUrl: string;
  handleSnapshotLoad: () => void;
  sceneSnapshotUrl: string;
  snapshotReady: boolean;
  viewportScrollOffsetPx: number;
  onSnapshotError: () => void;
};

function SnapshotPane(props: SnapshotPaneProps) {
  return (
    <div className="relative flex-1 overflow-hidden bg-[#f5f7fb]">
      {!props.snapshotReady && !props.crossFadeUrl ? (
        <div className="absolute inset-0 flex items-center justify-center bg-[#f5f5f7]">
          <div className="space-y-2.5 w-[55%]">
            <div className="h-2 rounded-full bg-black/10 animate-pulse" />
            <div className="h-2 rounded-full bg-black/8 animate-pulse w-[82%]" />
            <div className="h-2 rounded-full bg-black/10 animate-pulse w-[90%]" />
          </div>
        </div>
      ) : null}
      {props.crossFadeUrl && !props.snapshotReady ? (
        <img
          src={props.crossFadeUrl}
          alt=""
          aria-hidden="true"
          className="absolute inset-0 h-full w-full object-contain object-top bg-transparent"
          style={{
            transform: `translate3d(0, ${props.viewportScrollOffsetPx}px, 0)`,
            transition: "transform 220ms ease-out",
          }}
        />
      ) : null}
      <img
        src={props.sceneSnapshotUrl}
        alt="Live browser capture"
        className={`absolute inset-0 h-full w-full object-contain object-top bg-transparent ${props.snapshotReady ? "opacity-100" : "opacity-0"}`}
        style={{
          transition: "opacity 320ms ease-in-out, transform 1100ms cubic-bezier(0.22, 1, 0.36, 1)",
          transform: `translate3d(0, ${props.viewportScrollOffsetPx}px, 0)`,
        }}
        onLoad={props.handleSnapshotLoad}
        onError={props.onSnapshotError}
      />
      <OverlayChrome {...props} />
    </div>
  );
}

type FramePaneProps = OverlayChromeProps & {
  frameRef: RefObject<HTMLIFrameElement | null>;
  frameScale: number;
  frameUrl: string;
  frameViewportRef: RefObject<HTMLDivElement | null>;
  frameVirtualHeight: number;
  handleFrameLoad: () => void;
  proxyLoaded: boolean;
  resolvedPageUrl: string;
  viewportScrollOffsetPx: number;
};

function FramePane(props: FramePaneProps) {
  return (
    <div ref={props.frameViewportRef} className="relative flex-1 overflow-hidden bg-[#f5f7fb]">
      {!props.proxyLoaded ? (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-[#f5f5f7]">
          <div className="space-y-2.5 w-[52%]">
            <div className="h-2 rounded-full bg-black/10 animate-pulse" />
            <div className="h-2 rounded-full bg-black/8 animate-pulse w-[80%]" />
            <div className="h-2 rounded-full bg-black/10 animate-pulse w-[88%]" />
          </div>
        </div>
      ) : null}
      <iframe
        ref={props.frameRef}
        src={props.frameUrl || props.resolvedPageUrl}
        title="Live website preview"
        className="absolute left-0 top-0 border-0"
        style={{
          width: "1366px",
          height: `${props.frameVirtualHeight}px`,
          transform: `translate3d(0, ${props.viewportScrollOffsetPx}px, 0) scale(${props.frameScale})`,
          transformOrigin: "top left",
          transition: "transform 1100ms cubic-bezier(0.22, 1, 0.36, 1)",
        }}
        sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
        referrerPolicy="no-referrer-when-downgrade"
        onLoad={props.handleFrameLoad}
      />
      <OverlayChrome {...props} />
    </div>
  );
}

type FallbackPaneProps = OverlayChromeProps & {
  activeTitle: string;
  sceneSnapshotUrl: string;
  sceneText: string;
  onFallbackSnapshotError: () => void;
  snapshotReady: boolean;
  viewportScrollOffsetPx: number;
};

function FallbackPane(props: FallbackPaneProps) {
  return (
    <div className="relative flex-1 space-y-3 p-4">
      <InteractionOverlay
        sceneSurface="website"
        activeEventType={props.activeEventType}
        activeDetail={props.activeDetail}
        scrollDirection={props.scrollDirection}
        action={props.action}
        actionPhase={props.actionPhase}
        actionStatus={props.actionStatus}
        actionTargetLabel={props.actionTargetLabel}
      />
      <p className="text-[13px] font-semibold text-[#1d1d1f]">{props.activeTitle || "Browser scene"}</p>
      <p className="text-[12px] text-[#4a4f5c]">
        {props.sceneText || props.activeDetail || "Inspecting page content and extracting evidence..."}
      </p>
      <div className="relative overflow-hidden rounded-xl border border-black/[0.08] bg-white px-3 py-3">
        <div
          className="space-y-2 transition-transform duration-200 ease-out"
          style={{
            transform: `translate3d(0, ${props.viewportScrollOffsetPx}px, 0)`,
            transition: "transform 1100ms cubic-bezier(0.22, 1, 0.36, 1)",
          }}
        >
          <div className="h-2 w-[92%] rounded-full bg-black/12" />
          <div className="h-2 w-[84%] rounded-full bg-black/8" />
          <div className="h-2 w-[88%] rounded-full bg-black/12" />
          <div className="h-2 w-[63%] rounded-full bg-black/8" />
          <div className="h-2 w-[76%] rounded-full bg-black/10" />
          <div className="h-2 w-[68%] rounded-full bg-black/8" />
        </div>
      </div>
      {props.showFindOverlay ? (
        <div className="rounded-lg border border-black/[0.08] bg-white px-2.5 py-2 text-[11px] text-[#1d1d1f]">
          <p className="font-semibold">
            Find: {props.findQuery || props.dedupedBrowserKeywords.slice(0, 2).join(" ")}
          </p>
          {props.dedupedBrowserKeywords.length ? (
            <p className="mt-0.5 text-[#4a4f5c]">Terms: {props.dedupedBrowserKeywords.slice(0, 5).join(", ")}</p>
          ) : null}
        </div>
      ) : null}
      {props.copyPulseVisible ? (
        <div className="rounded-lg border border-black/[0.08] bg-white px-2.5 py-1.5 text-[11px] text-[#1d1d1f]">
          Copied: {props.copyPulseText}
        </div>
      ) : null}
      <ScrollMeter scrollPercent={props.effectiveScrollPercent} onSelect={props.handleScrollSelect} />
      {props.sceneSnapshotUrl && props.snapshotReady ? (
        <img
          src={props.sceneSnapshotUrl}
          alt="Browser capture"
          className="absolute bottom-3 right-3 h-24 w-36 rounded-lg border border-black/[0.08] object-contain bg-[#f5f7fb]"
          onError={props.onFallbackSnapshotError}
        />
      ) : null}
      {props.showOverlayCursor ? (
        <>
          <GhostCursor
            cursorX={props.cursorX ?? null}
            cursorY={props.cursorY ?? null}
            isClick={props.isClickEvent ?? false}
            advisory={props.cursorSource === "suggested"}
          />
          <ClickRipple ripples={props.clickRipples} />
        </>
      ) : null}
      <ExecutionRoadmapOverlay
        roadmapSteps={props.roadmapSteps}
        roadmapActiveIndex={props.roadmapActiveIndex}
        visible={props.roadmapVisible}
      />
    </div>
  );
}

export { FallbackPane, FramePane, SnapshotPane };
