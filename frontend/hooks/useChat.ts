"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  getConversation,
  streamChatMessage,
  streamExplainTransaction,
  streamTrackRedemptionOrder,
} from "@/lib/api";
import { persistedToUIMessages } from "@/lib/messageMapping";
import { AuthSession, ChatResponse, ChatUIMessage } from "@/lib/types";

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
}

export function useChat(session: AuthSession | null, conversationId: string | null, onTurnComplete?: () => void) {
  const [messages, setMessages] = useState<ChatUIMessage[]>([]);
  const hydratedFor = useRef<string | null>(null);

  useEffect(() => {
    if (!session || !conversationId) {
      setMessages([]);
      hydratedFor.current = null;
      return;
    }
    const key = `${session.userId}:${conversationId}`;
    if (hydratedFor.current === key) return;
    hydratedFor.current = key;

    getConversation(session.accessToken, conversationId)
      .then((detail) => setMessages(persistedToUIMessages(detail.messages)))
      // A 404 just means this conversation id hasn't had its first turn sent
      // yet (a brand-new "New chat") - treat any hydration failure the same
      // way, as an empty conversation, rather than surfacing an error state.
      .catch(() => setMessages([]));
  }, [session, conversationId]);

  // Each SSE "delta" event carries the full text-so-far, accumulated on the
  // backend (not an incremental piece) - render it directly, no client-side
  // concatenation. Produces the same visible typewriter effect ("Hi" ->
  // "Hi Alice" -> "Hi Alice!" -> ...) for both the chat and
  // transaction-explain streams.
  const appendDelta = useCallback((id: string, textSoFar: string) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, text: textSoFar, streaming: true } : m)));
  }, []);

  const finalizeMessage = useCallback((id: string, response: ChatResponse) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === id ? { ...m, status: "sent", text: response.message, response, streaming: false } : m
      )
    );
  }, []);

  const failMessage = useCallback((id: string, message: string) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, status: "error", text: message, streaming: false } : m)));
  }, []);

  // Once "done" (or an error) lands for a message, that turn is over - any
  // further delta somehow arriving after it (a stray late event) must not
  // overwrite the already-finalized text, which is what caused the visible
  // flicker right after a response completed.
  const makeCallbacks = useCallback(
    (id: string) => {
      let finished = false;
      return {
        onDelta: (delta: string) => {
          if (!finished) appendDelta(id, delta);
        },
        onDone: (response: ChatResponse) => {
          if (finished) return;
          finished = true;
          finalizeMessage(id, response);
          onTurnComplete?.();
        },
        onError: (message: string) => {
          if (finished) return;
          finished = true;
          failMessage(id, message);
        },
      };
    },
    [appendDelta, finalizeMessage, failMessage, onTurnComplete]
  );

  const sendMessage = useCallback(
    async (text: string) => {
      if (!session || !conversationId) return;
      const userMessage: ChatUIMessage = { id: newId(), role: "user", status: "sent", text };
      const assistantId = newId();
      const assistantPlaceholder: ChatUIMessage = {
        id: assistantId,
        role: "assistant",
        status: "pending",
        text: "",
        retry: { kind: "chat", message: text },
      };
      setMessages((prev) => [...prev, userMessage, assistantPlaceholder]);

      await streamChatMessage(session.accessToken, text, conversationId, makeCallbacks(assistantId));
    },
    [session, conversationId, makeCallbacks]
  );

  const selectTransaction = useCallback(
    async (transactionId: string) => {
      if (!session) return;
      const assistantId = newId();
      const placeholder: ChatUIMessage = {
        id: assistantId,
        role: "assistant",
        status: "pending",
        text: "",
        retry: { kind: "explain", transactionId },
      };
      setMessages((prev) => [...prev, placeholder]);

      await streamExplainTransaction(session.accessToken, transactionId, conversationId, makeCallbacks(assistantId));
    },
    [session, conversationId, makeCallbacks]
  );

  const selectRedemptionOrder = useCallback(
    async (orderRef: string) => {
      if (!session) return;
      const assistantId = newId();
      const placeholder: ChatUIMessage = {
        id: assistantId,
        role: "assistant",
        status: "pending",
        text: "",
        retry: { kind: "track", orderRef },
      };
      setMessages((prev) => [...prev, placeholder]);

      await streamTrackRedemptionOrder(session.accessToken, orderRef, conversationId, makeCallbacks(assistantId));
    },
    [session, conversationId, makeCallbacks]
  );

  const retry = useCallback(
    async (messageId: string) => {
      const target = messages.find((m) => m.id === messageId);
      if (!target?.retry || !session) return;
      setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, status: "pending", text: "" } : m)));

      if (target.retry.kind === "chat") {
        if (!conversationId) return;
        await streamChatMessage(session.accessToken, target.retry.message, conversationId, makeCallbacks(messageId));
      } else if (target.retry.kind === "explain") {
        await streamExplainTransaction(
          session.accessToken,
          target.retry.transactionId,
          conversationId,
          makeCallbacks(messageId)
        );
      } else {
        await streamTrackRedemptionOrder(session.accessToken, target.retry.orderRef, conversationId, makeCallbacks(messageId));
      }
    },
    [messages, session, conversationId, makeCallbacks]
  );

  return { messages, sendMessage, selectTransaction, selectRedemptionOrder, retry };
}
