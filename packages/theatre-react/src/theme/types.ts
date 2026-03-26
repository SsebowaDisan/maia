export interface TheatreTheme {
  theatre: {
    shell: string;
    header: string;
    title: string;
    statusMeta: string;
    statusConnected: string;
    statusDisconnected: string;
    tabsWrap: string;
    tabBase: string;
    tabActive: string;
    tabInactive: string;
    content: string;
  };
  desktop: {
    shell: string;
    metaRow: string;
    metaLabel: string;
    metaRole: string;
    controlsWrap: string;
    controlButton: string;
    liveChip: string;
    liveDot: string;
    statusText: string;
    viewportWrap: string;
    viewportTheatreWidth: string;
    viewportStandardWidth: string;
    viewportFullscreenWidth: string;
    viewportPanel: string;
    viewportFrame: string;
    viewportFrameInlineHeight: string;
    viewportFrameCompactHeight: string;
    viewportFrameFullscreenHeight: string;
    viewportFrameFocusHeight: string;
    stageBadge: string;
    cursor: string;
    captionWrap: string;
    captionCard: string;
    captionTitle: string;
    captionDetail: string;
  };
  thread: {
    root: string;
    rosterWrap: string;
    rosterTitle: string;
    rosterChip: string;
    rosterName: string;
    rosterMeta: string;
    emptyState: string;
    sections: string;
    section: string;
    sectionHeader: string;
    sectionTitle: string;
    sectionSubtitle: string;
    threadCard: string;
    typing: string;
  };
  bubble: {
    row: string;
    card: string;
    name: string;
    role: string;
    badgeBase: string;
    time: string;
    metaRow: string;
    metaChip: string;
    ackChip: string;
    replyCard: string;
    replyTitle: string;
    thinkingCard: string;
    content: string;
    artifactChip: string;
  };
  activity: {
    root: string;
    emptyState: string;
    item: string;
    actor: string;
    action: string;
    time: string;
    detail: string;
    toolChip: string;
    browserChip: string;
    cost: string;
  };
}

export type TheatreThemeOverride = Partial<{
  [K in keyof TheatreTheme]: Partial<TheatreTheme[K]>;
}>;
