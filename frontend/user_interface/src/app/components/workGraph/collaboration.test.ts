import { describe, expect, it, vi } from "vitest";

import { createCollaborationTransport } from "./collaboration";

describe("work graph collaboration transport", () => {
  it("publishes selection and comment events through local transport", () => {
    const transport = createCollaborationTransport({
      provider: "local_broadcast",
      channelId: "work-graph:run-1",
    });
    const listener = vi.fn();
    const unsubscribe = transport.subscribe(listener);

    transport.publish({
      kind: "selection",
      runId: "run-1",
      nodeId: "node.research",
      userId: "u1",
      userLabel: "Alice",
      timestamp: "2026-03-07T00:00:00Z",
    });
    transport.publish({
      kind: "comment",
      runId: "run-1",
      nodeId: "node.research",
      commentId: "c1",
      text: "Verify source quality.",
      userId: "u1",
      userLabel: "Alice",
      timestamp: "2026-03-07T00:00:01Z",
    });

    unsubscribe();
    transport.dispose();

    expect(listener).toHaveBeenCalledTimes(2);
    expect(listener.mock.calls[0][0].kind).toBe("selection");
    expect(listener.mock.calls[1][0].kind).toBe("comment");
  });

  it("uses provider abstraction for liveblocks when factory is supplied", () => {
    const publish = vi.fn();
    const subscribe = vi.fn(() => () => {});
    const dispose = vi.fn();
    const transport = createCollaborationTransport({
      provider: "liveblocks",
      channelId: "work-graph:run-2",
      liveblocksFactory: () => ({
        publish,
        subscribe,
        dispose,
      }),
    });

    transport.publish({
      kind: "selection",
      runId: "run-2",
      nodeId: "node.plan",
      userId: "u2",
      userLabel: "Bob",
      timestamp: "2026-03-07T00:10:00Z",
    });

    expect(publish).toHaveBeenCalledTimes(1);
  });
});
