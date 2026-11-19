import { useEffect, useRef, useState } from "react";
import type { LogEntry } from "@/types/api";

interface ServerEventPayload {
  type?: string;
  data?: unknown;
}

export function useServerEvents(onLogEvent: (entry: LogEntry) => void): {
  connected: boolean;
  reconnect: () => void;
} {
  const [connected, setConnected] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const onLogRef = useRef(onLogEvent);
  onLogRef.current = onLogEvent;

  useEffect(() => {
    if (typeof EventSource === "undefined") {
      return;
    }

    const es = new EventSource("/api/events");

    es.onopen = () => {
      setConnected(true);
    };

    es.onmessage = (event) => {
      setConnected(true);
      if (!event.data) return;
      try {
        const parsed = JSON.parse(event.data) as ServerEventPayload;
        if (parsed.type === "log" && parsed.data && typeof parsed.data === "object") {
          onLogRef.current(parsed.data as LogEntry);
        }
      } catch {
        // Ignore keep-alive comments or malformed chunks
      }
    };

    es.onerror = () => {
      setConnected(false);
    };

    return () => {
      setConnected(false);
      es.close();
    };
  }, [epoch]);

  return {
    connected,
    reconnect: () => setEpoch((prev) => prev + 1),
  };
}
