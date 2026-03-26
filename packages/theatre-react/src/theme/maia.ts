import type { TheatreTheme, TheatreThemeOverride } from "./types";

const maiaTheme: TheatreTheme = {
  theatre: {
    shell: "flex flex-col overflow-hidden rounded-[24px] border border-[#e5e7eb] bg-[linear-gradient(180deg,#ffffff_0%,#fbfdff_100%)] shadow-[0_10px_30px_rgba(15,23,42,0.04)]",
    header: "flex items-center justify-between border-b border-[#eaecf0] px-4 py-3",
    title: "text-[13px] font-semibold text-[#111827]",
    statusMeta: "text-[11px] text-[#98a2b3]",
    statusConnected: "bg-[#12b76a]",
    statusDisconnected: "bg-[#d0d5dd]",
    tabsWrap: "flex rounded-full border border-[#e4e7ec] bg-white p-0.5",
    tabBase: "rounded-full px-3 py-1 text-[12px] font-semibold transition-colors",
    tabActive: "bg-[#111827] text-white shadow-sm",
    tabInactive: "text-[#667085] hover:text-[#111827]",
    content: "flex-1 overflow-hidden",
  },
  desktop: {
    shell: "mx-auto mb-3 w-full max-w-[940px] rounded-2xl border border-[#e5e7eb] bg-white p-4 text-[#111827] shadow-[0_16px_36px_-30px_rgba(15,23,42,0.4)]",
    metaRow: "mb-2.5 flex items-center justify-between gap-2 text-[11px] text-[#6b7280]",
    metaLabel: "inline-flex items-center gap-1.5 text-[11px] text-[#4b5563]",
    metaRole: "text-[#9ca3af]",
    controlsWrap: "inline-flex items-center gap-2",
    controlButton: "rounded-full border border-[#d7dbe3] bg-[#f8fafc] px-2.5 py-0.5 text-[10px] text-[#4b5563] transition hover:bg-[#eef2f7]",
    liveChip: "inline-flex items-center gap-1 rounded-full border border-[#d7dbe3] bg-[#f8fafc] px-2 py-0.5 text-[#4b5563]",
    liveDot: "h-1.5 w-1.5 rounded-full bg-[#34c759]",
    statusText: "mb-2.5 text-[12px] font-medium text-[#1f2937]",
    viewportWrap: "mx-auto",
    viewportTheatreWidth: "w-full max-w-[860px]",
    viewportStandardWidth: "w-full max-w-[760px]",
    viewportFullscreenWidth: "w-full",
    viewportPanel: "relative overflow-hidden rounded-2xl bg-[radial-gradient(circle_at_50%_-20%,rgba(121,152,201,0.2),transparent_44%),#0d1117] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)]",
    viewportFrame: "absolute inset-0",
    viewportFrameInlineHeight: "h-[clamp(460px,72vh,760px)]",
    viewportFrameCompactHeight: "h-[clamp(200px,28vh,285px)]",
    viewportFrameFullscreenHeight: "h-[74vh]",
    viewportFrameFocusHeight: "h-[calc(100vh-180px)]",
    stageBadge: "pointer-events-none absolute left-1/2 top-3 z-30 -translate-x-1/2 rounded-full border border-white/15 bg-[#111827] px-3 py-1 text-[10px] font-medium tracking-[0.045em] text-white/80",
    cursor: "pointer-events-none absolute z-20 transition-all duration-500 ease-out text-white drop-shadow-[0_1px_3px_rgba(0,0,0,0.65)]",
    captionWrap: "pointer-events-none absolute inset-x-3 bottom-3 z-30",
    captionCard: "rounded-xl border border-white/12 bg-[#111827] px-3 py-2",
    captionTitle: "truncate text-[13px] font-semibold text-white",
    captionDetail: "mt-0.5 line-clamp-2 text-[11px] text-white/85",
  },
  thread: {
    root: "flex flex-col overflow-y-auto",
    rosterWrap: "sticky top-0 z-10 border-b border-[#eaecf0] bg-white/95 px-4 py-3 backdrop-blur",
    rosterTitle: "mb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-[#98a2b3]",
    rosterChip: "inline-flex items-center gap-2 rounded-full border border-[#eaecf0] bg-[#f8fafc] px-2.5 py-1.5",
    rosterName: "text-[11px] font-medium text-[#344054]",
    rosterMeta: "max-w-[160px] truncate text-[10px] text-[#98a2b3]",
    emptyState: "flex flex-1 items-center justify-center px-6 text-center text-[13px] text-[#98a2b3]",
    sections: "space-y-6 px-4 py-4",
    section: "space-y-2",
    sectionHeader: "flex items-baseline gap-3",
    sectionTitle: "text-[13px] font-semibold text-[#111827]",
    sectionSubtitle: "text-[11px] text-[#98a2b3]",
    threadCard: "space-y-2 rounded-[24px] border border-[#eaecf0] bg-[linear-gradient(180deg,#fcfdff_0%,#f7f9fc_100%)] p-3",
    typing: "flex items-center gap-3 py-2 text-[12px] text-[#667085]",
  },
  bubble: {
    row: "flex gap-3 py-2.5",
    card: "rounded-[20px] border border-[#eaecf0] bg-white/95 px-4 py-3 shadow-[0_1px_0_rgba(17,24,39,0.02)]",
    name: "text-[13px] font-semibold text-[#111827]",
    role: "text-[11px] text-[#667085]",
    badgeBase: "rounded-full px-2 py-0.5 text-[10px] font-medium",
    time: "ml-auto text-[11px] text-[#98a2b3]",
    metaRow: "mt-2 flex flex-wrap items-center gap-2 text-[11px] text-[#667085]",
    metaChip: "inline-flex items-center rounded-full bg-[#f8fafc] px-2 py-0.5",
    ackChip: "inline-flex items-center rounded-full bg-[#fffbeb] px-2 py-0.5 text-[#b54708]",
    replyCard: "mt-2 rounded-[16px] border border-[#eaecf0] bg-[#f8fafc] px-3 py-2 text-[11px] text-[#667085]",
    replyTitle: "font-medium text-[#344054]",
    thinkingCard: "mt-2 rounded-[16px] bg-[#fffaeb] px-3 py-2 text-[12px] italic text-[#b54708]",
    content: "mt-2 whitespace-pre-wrap text-[13px] leading-relaxed text-[#344054]",
    artifactChip: "inline-flex items-center rounded-lg border border-[#eaecf0] bg-[#f8fafc] px-2 py-1 text-[11px] font-medium text-[#475467]",
  },
  activity: {
    root: "overflow-y-auto px-4 py-2",
    emptyState: "py-8 text-center text-[13px] text-[#98a2b3]",
    item: "flex gap-3 py-1.5",
    actor: "text-[12px] font-medium text-[#344054]",
    action: "text-[11px] text-[#98a2b3]",
    time: "text-[10px] text-[#d0d5dd]",
    detail: "mt-0.5 text-[12px] text-[#667085]",
    toolChip: "mt-1 rounded bg-[#f8fafc] px-2 py-1 text-[11px] font-mono text-[#475467]",
    browserChip: "mt-1 flex items-center gap-1.5 rounded bg-[#eff8ff] px-2 py-1 text-[11px] text-[#175cd3]",
    cost: "mt-0.5 inline-block text-[10px] text-[#98a2b3]",
  },
};

function mergeSection<T extends Record<string, string>>(base: T, override?: Partial<T>): T {
  return { ...base, ...(override ?? {}) };
}

export function resolveTheatreTheme(override?: TheatreThemeOverride): TheatreTheme {
  if (!override) {
    return maiaTheme;
  }
  return {
    theatre: mergeSection(maiaTheme.theatre, override.theatre),
    desktop: mergeSection(maiaTheme.desktop, override.desktop),
    thread: mergeSection(maiaTheme.thread, override.thread),
    bubble: mergeSection(maiaTheme.bubble, override.bubble),
    activity: mergeSection(maiaTheme.activity, override.activity),
  };
}

export { maiaTheme };
