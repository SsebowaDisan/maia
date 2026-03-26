/**
 * useConversationStream — React hook that filters ACP events for conversations.
 * Only tracks message, review, and capabilities events (ignores activity/tool events).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { ACPEvent, ACPCapabilities } from "@maia/acp";

export interface UseConversationStreamOptions {
  url: string | null;
  recordedEvents?: ACPEvent[];
  onEvent?: (event: ACPEvent) => void;
}

export interface ConversationStreamState {
  messages: ACPEvent[];
  reviews: ACPEvent[];
  agents: Map<string, ACPCapabilities>;
  typingAgent: string | null;
  connected: boolean;
}

export function useConversationStream(options: UseConversationStreamOptions): ConversationStreamState {
  const { url, recordedEvents, onEvent } = options;
  const [messages, setMessages] = useState<ACPEvent[]>([]);
  const [reviews, setReviews] = useState<ACPEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [typingAgent, setTypingAgent] = useState<string | null>(null);
  const agentsRef = useRef<Map<string, ACPCapabilities>>(new Map());
  const sourceRef = useRef<EventSource | null>(null);
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleEvent = useCallback(
    (event: ACPEvent) => {
      if (event.event_type === "message") {
        setMessages((prev) => [...prev, event]);
        // Clear typing indicator when a message arrives from the typing agent
        setTypingAgent(null);
      } else if (event.event_type === "review") {
        setReviews((prev) => [...prev, event]);
      } else if (event.event_type === "capabilities") {
        const caps = event.payload as unknown as ACPCapabilities;
        agentsRef.current.set(caps.agent_id, caps);
      } else if (event.event_type === "event") {
        // Activity events — use them to show typing indicator
        const act = event.payload as Record<string, unknown>;
        if (act.activity === "thinking" || act.activity === "writing" || act.activity === "reviewing") {
          const agentId = (act.agent_id as string) ?? event.agent_id;
          setTypingAgent(agentId);
          // Auto-clear typing after 10s
          if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
          typingTimerRef.current = setTimeout(() => setTypingAgent(null), 10000);
        }
      }
      onEvent?.(event);
    },
    [onEvent],
  );

  // Live mode — connect to SSE
  useEffect(() => {
    if (!url) return;

    const es = new EventSource(url);
    sourceRef.current = es;

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    es.onmessage = (evt) => {
      try {
        const parsed = JSON.parse(evt.data);
        if (parsed.acp_version) handleEvent(parsed as ACPEvent);
      } catch {
        // ignore non-ACP events
      }
    };

    return () => {
      es.close();
      sourceRef.current = null;
      setConnected(false);
    };
  }, [url, handleEvent]);

  // Replay mode — process pre-recorded events
  useEffect(() => {
    if (!recordedEvents || url) return;
    setConnected(true);
    for (const event of recordedEvents) {
      handleEvent(event);
    }
  }, [recordedEvents, url, handleEvent]);

  return {
    messages,
    reviews,
    agents: agentsRef.current,
    typingAgent,
    connected,
  };
}