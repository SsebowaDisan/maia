type CollaborationSelectionEvent = {
  kind: "selection";
  runId: string;
  nodeId: string;
  userId: string;
  userLabel: string;
  timestamp: string;
};

type CollaborationCommentEvent = {
  kind: "comment";
  runId: string;
  nodeId: string;
  commentId: string;
  text: string;
  userId: string;
  userLabel: string;
  timestamp: string;
};

type CollaborationEvent = CollaborationSelectionEvent | CollaborationCommentEvent;

type CollaborationTransport = {
  publish: (event: CollaborationEvent) => void;
  subscribe: (listener: (event: CollaborationEvent) => void) => () => void;
  dispose: () => void;
};

type CollaborationTransportFactoryOptions = {
  provider: "local_broadcast" | "liveblocks" | "noop";
  channelId: string;
};

type CreateCollaborationTransportOptions = CollaborationTransportFactoryOptions & {
  liveblocksFactory?: (options: CollaborationTransportFactoryOptions) => CollaborationTransport;
};

function createNoopTransport(): CollaborationTransport {
  return {
    publish: () => {},
    subscribe: () => () => {},
    dispose: () => {},
  };
}

function createLocalBroadcastTransport(channelId: string): CollaborationTransport {
  const listeners = new Set<(event: CollaborationEvent) => void>();
  const hasWindow = typeof window !== "undefined";
  const canUseBroadcast = hasWindow && "BroadcastChannel" in window;
  const channel = canUseBroadcast ? new BroadcastChannel(channelId) : null;

  const emit = (event: CollaborationEvent) => {
    for (const listener of listeners) {
      listener(event);
    }
  };

  if (channel) {
    channel.onmessage = (message) => {
      const payload = message.data as CollaborationEvent | null;
      if (!payload || typeof payload !== "object") {
        return;
      }
      if (payload.runId && payload.runId !== channelId.split(":").pop()) {
        return;
      }
      emit(payload);
    };
  }

  return {
    publish: (event) => {
      emit(event);
      channel?.postMessage(event);
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    dispose: () => {
      listeners.clear();
      channel?.close();
    },
  };
}

function createCollaborationTransport(options: CreateCollaborationTransportOptions): CollaborationTransport {
  if (options.provider === "liveblocks") {
    if (options.liveblocksFactory) {
      return options.liveblocksFactory({
        provider: "liveblocks",
        channelId: options.channelId,
      });
    }
    return createNoopTransport();
  }
  if (options.provider === "local_broadcast") {
    return createLocalBroadcastTransport(options.channelId);
  }
  return createNoopTransport();
}

export { createCollaborationTransport };
export type {
  CollaborationCommentEvent,
  CollaborationEvent,
  CollaborationSelectionEvent,
  CollaborationTransport,
  CollaborationTransportFactoryOptions,
};
