// ACP Client
// Connects to an ACP event stream, maintains an agent registry, and exposes
// send helpers with delivery semantics.

import type {
  ACPActivity,
  ACPCapabilities,
  ACPClientOptions,
  ACPEvent,
  ACPEventMap,
  ACPHandoff,
  ACPMessage,
  ACPRegistryLike,
  ACPReview,
  ACPTransport,
  AgentPresence,
  DeliveryStatus,
  DeliveryReceipt,
  EventType,
} from "./types";
import { envelope } from "./builders";
import { ACPAgentRegistry } from "./registry";

type EventCallback<T = ACPEvent> = (event: T) => void;

function cloneMessageWithStatus(message: ACPMessage, status: DeliveryStatus): ACPMessage {
  return {
    ...message,
    context: {
      ...(message.context ?? {}),
      delivery_status: status,
    },
  };
}

function derivePresenceFromActivity(activity: ACPActivity): AgentPresence {
  const kind = String(activity.activity || "").trim().toLowerCase();
  const detail = String(activity.detail || "").trim() || undefined;
  if (kind === "idle" || kind === "waiting") {
    return {
      availability: "available",
      current_focus: detail,
      last_seen_at: new Date().toISOString(),
    };
  }
  if (kind === "error") {
    return {
      availability: "busy",
      current_focus: detail,
      last_seen_at: new Date().toISOString(),
    };
  }
  return {
    availability: kind === "reviewing" ? "focused" : "busy",
    current_focus: detail,
    active_task_count: 1,
    last_seen_at: new Date().toISOString(),
  };
}

export class ACPClient {
  readonly agentId: string;
  readonly name: string;
  readonly role: string;
  readonly registry: ACPRegistryLike;

  private _runId = "";
  private _listeners: Map<string, Set<EventCallback<any>>> = new Map();
  private _eventSource: EventSource | null = null;
  private _buffer: ACPEvent[] = [];
  private _connected = false;
  private _onError: ((error: Error) => void) | undefined;
  private _onEvent: ((event: ACPEvent) => void) | undefined;
  private _transport: ACPTransport | undefined;

  constructor(options: ACPClientOptions) {
    this.agentId = options.agentId;
    this.name = options.name ?? options.agentId.replace("agent://", "");
    this.role = options.role ?? "agent";
    this.registry = options.registry ?? new ACPAgentRegistry();
    this._onError = options.onError;
    this._onEvent = options.onEvent;
    this._transport = options.transport;

    if (options.streamUrl) {
      this.connect(options.streamUrl);
    }
  }

  connect(streamUrl: string): void {
    if (this._eventSource) {
      this._eventSource.close();
    }

    this._eventSource = new EventSource(streamUrl);

    this._eventSource.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.acp_version) {
          this._handleEvent(data as ACPEvent);
        }
      } catch {
        // Ignore non-ACP events here. Generic wrapping belongs in stream helpers.
      }
    };

    this._eventSource.onerror = () => {
      this._connected = false;
      this._onError?.(new Error("ACP stream disconnected"));
    };

    this._eventSource.onopen = () => {
      this._connected = true;
    };
  }

  disconnect(): void {
    this._eventSource?.close();
    this._eventSource = null;
    this._connected = false;
  }

  get connected(): boolean {
    return this._connected;
  }

  on<K extends keyof ACPEventMap>(
    eventType: K,
    callback: EventCallback<ACPEventMap[K]>,
  ): () => void {
    if (!this._listeners.has(eventType)) {
      this._listeners.set(eventType, new Set());
    }
    this._listeners.get(eventType)!.add(callback);
    return () => {
      this._listeners.get(eventType)?.delete(callback);
    };
  }

  off<K extends keyof ACPEventMap>(
    eventType: K,
    callback: EventCallback<ACPEventMap[K]>,
  ): void {
    this._listeners.get(eventType)?.delete(callback);
  }

  private _handleEvent(event: ACPEvent): void {
    this._buffer.push(event);
    this._runId = event.run_id;

    if (event.event_type === "capabilities") {
      this.registry.upsertCapabilities(event.payload as ACPCapabilities);
    } else if (event.event_type === "event") {
      const payload = event.payload as ACPActivity;
      if (payload.agent_id) {
        this.registry.updatePresence(payload.agent_id, derivePresenceFromActivity(payload));
      }
    }

    const specific = this._listeners.get(event.event_type);
    if (specific) {
      for (const cb of specific) {
        try {
          cb(event);
        } catch (err) {
          this._onError?.(err instanceof Error ? err : new Error(String(err)));
        }
      }
    }

    const wildcard = this._listeners.get("*");
    if (wildcard) {
      for (const cb of wildcard) {
        try {
          cb(event);
        } catch (err) {
          this._onError?.(err instanceof Error ? err : new Error(String(err)));
        }
      }
    }

    this._onEvent?.(event);
  }

  private _emitTyped<T>(eventType: EventType, payload: T, parentEventId?: string): ACPEvent<T> {
    return envelope(this.agentId, this._runId, eventType, payload, parentEventId);
  }

  emitMessage(msg: ACPMessage): ACPEvent<ACPMessage> {
    return this._emitTyped("message", msg);
  }

  emitHandoff(ho: ACPHandoff): ACPEvent<ACPHandoff> {
    return this._emitTyped("handoff", ho);
  }

  emitReview(rev: ACPReview): ACPEvent<ACPReview> {
    return this._emitTyped("review", rev);
  }

  emitActivity(act: ACPActivity): ACPEvent<ACPActivity> {
    return this._emitTyped("event", act);
  }

  emitCapabilities(caps: ACPCapabilities): ACPEvent<ACPCapabilities> {
    this.registry.upsertCapabilities(caps);
    return this._emitTyped("capabilities", caps);
  }

  private async _deliver<T>(
    event: ACPEvent<T>,
    recipient?: string,
    timeoutMs?: number,
  ): Promise<DeliveryReceipt> {
    if (!this._transport) {
      return { status: "queued", recipient };
    }
    try {
      return await this._transport.deliver(event, { recipient, timeoutMs });
    } catch (error) {
      return {
        status: "failed",
        recipient,
        error: String((error as { message?: string } | undefined)?.message || error || "Delivery failed"),
      };
    }
  }

  async sendMessage(
    msg: ACPMessage,
    options?: { timeoutMs?: number },
  ): Promise<ACPEvent<ACPMessage>> {
    const resolvedRecipient =
      this.registry.resolveRecipient({
        to: msg.to,
        intent: msg.intent,
        excludeAgentId: this.agentId,
      })?.agent_id ?? msg.to;

    const queuedMessage = cloneMessageWithStatus(
      {
        ...msg,
        to: resolvedRecipient,
      },
      "queued",
    );
    const event = this.emitMessage(queuedMessage);
    const receipt = await this._deliver(event, resolvedRecipient, options?.timeoutMs);
    return {
      ...event,
      payload: cloneMessageWithStatus(event.payload, receipt.status),
    };
  }

  async sendHandoff(
    handoff: ACPHandoff,
    options?: { timeoutMs?: number },
  ): Promise<ACPEvent<ACPHandoff>> {
    const resolvedRecipient =
      this.registry.resolveRecipient({
        to: handoff.to,
        intent: "handoff",
        excludeAgentId: this.agentId,
      })?.agent_id ?? handoff.to;
    const event = this.emitHandoff({
      ...handoff,
      to: resolvedRecipient,
      status: handoff.status ?? "proposed",
    });
    const receipt = await this._deliver(event, resolvedRecipient, options?.timeoutMs);
    return {
      ...event,
      payload: {
        ...event.payload,
        status: receipt.status === "failed" ? "rejected" : event.payload.status,
        declined_reason: receipt.error ?? event.payload.declined_reason,
      },
    };
  }

  async sendReview(
    review: ACPReview,
    options?: { recipient?: string; timeoutMs?: number },
  ): Promise<ACPEvent<ACPReview>> {
    const recipient = options?.recipient ?? review.author;
    const event = this.emitReview(review);
    await this._deliver(event, recipient, options?.timeoutMs);
    return event;
  }

  get events(): readonly ACPEvent[] {
    return this._buffer;
  }

  get runId(): string {
    return this._runId;
  }

  clearBuffer(): void {
    this._buffer = [];
  }

  messages(): ACPEvent<ACPMessage>[] {
    return this._buffer
      .filter((e): e is ACPEvent<ACPMessage> => e.event_type === "message")
      .sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
  }

  threads(): Map<string, ACPEvent<ACPMessage>[]> {
    const threads = new Map<string, ACPEvent<ACPMessage>[]>();
    for (const msg of this.messages()) {
      const threadId = (msg.payload as ACPMessage).context?.thread_id ?? "default";
      if (!threads.has(threadId)) {
        threads.set(threadId, []);
      }
      threads.get(threadId)!.push(msg);
    }
    return threads;
  }

  totalCost(): { tokens: number; usd: number } {
    let tokens = 0;
    let usd = 0;
    for (const event of this._buffer) {
      if (event.event_type === "event") {
        const act = event.payload as ACPActivity;
        if (act.cost) {
          tokens += act.cost.tokens_used ?? 0;
          usd += act.cost.cost_usd ?? 0;
        }
      }
    }
    return { tokens, usd };
  }

  listAgents(): ACPCapabilities[] {
    return this.registry.listAgents();
  }

  listAvailableAgents(intent?: ACPMessage["intent"]): ACPCapabilities[] {
    return this.registry.listAvailableAgents(intent);
  }
}
