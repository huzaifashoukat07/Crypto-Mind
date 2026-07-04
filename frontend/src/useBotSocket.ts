import { useEffect, useRef } from "react";
import { WS_URL } from "./api";
import type { WsEvent } from "./types";

export function useBotSocket(onEvent: (event: WsEvent) => void) {
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    let socket: WebSocket | null = null;
    let closedByEffect = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      socket = new WebSocket(WS_URL);
      socket.onmessage = (msg) => {
        try {
          const event: WsEvent = JSON.parse(msg.data);
          handlerRef.current(event);
        } catch {
          // ignore malformed frames
        }
      };
      socket.onclose = () => {
        if (!closedByEffect) {
          retryTimer = setTimeout(connect, 2000);
        }
      };
    };

    connect();

    return () => {
      closedByEffect = true;
      if (retryTimer) clearTimeout(retryTimer);
      socket?.close();
    };
  }, []);
}
