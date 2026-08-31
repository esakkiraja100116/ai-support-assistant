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

export function useChat(
  session: AuthSession | null,
  conversationId: string | null,
  onTurnComplete?: () => void,
  onConversationCreated?: (id: string) => void
) {
  const [messages, setMessages] = useState<ChatUIMessage[]>([]);
  const hydratedFor = useRef<string | null>(null);
  // Holds an id generated locally for the very first message of a brand-new
  // chat, before the "c=" query param (and thus the conversationId prop)
  // catches up to it.
  const pendingConversationId = useRef<string | null>(null);

  useEffect(() => {
    if (!session || !conversationId) {
      setMessages([]);
      hydratedFor.current = null;
      pendingConversationId.current = null;
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

  // Resolves the id to send this turn to. If the caller hasn't put an id in
  // the URL yet (a fresh "New chat"), generate one now, mark it as already
  // hydrated (there's nothing to fetch for a conversation that doesn't exist
  // yet), and let the caller update the URL - without clobbering the
  // optimistic messages we're about to add once that URL update flows back
  // down as a conversationId prop change.
  const resolveConversationId = useCallback(() => {
    if (conversationId) return conversationId;
    if (!session) return null;
    if (!pendingConversationId.current) {
      const id = newId();
      pendingConversationId.current = id;
      hydratedFor.current = `${session.userId}:${id}`;
      onConversationCreated?.(id);
    }
    return pendingConversationId.current;
  }, [session, conversationId, onConversationCreated]);

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
      if (!session) return;
      const activeId = resolveConversationId();
      if (!activeId) return;
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

      await streamChatMessage(session.accessToken, text, activeId, makeCallbacks(assistantId));
    },
    [session, resolveConversationId, makeCallbacks]
  );

  const selectTransaction = useCallback(
    async (transactionId: string) => {
      if (!session) return;
      const activeId = resolveConversationId();
      const assistantId = newId();
      const placeholder: ChatUIMessage = {
        id: assistantId,
        role: "assistant",
        status: "pending",
        text: "",
        retry: { kind: "explain", transactionId },
      };
      setMessages((prev) => [...prev, placeholder]);

      await streamExplainTransaction(session.accessToken, transactionId, activeId, makeCallbacks(assistantId));
    },
    [session, resolveConversationId, makeCallbacks]
  );

  const selectRedemptionOrder = useCallback(
    async (orderRef: string) => {
      if (!session) return;
      const activeId = resolveConversationId();
      const assistantId = newId();
      const placeholder: ChatUIMessage = {
        id: assistantId,
        role: "assistant",
        status: "pending",
        text: "",
        retry: { kind: "track", orderRef },
      };
      setMessages((prev) => [...prev, placeholder]);

      await streamTrackRedemptionOrder(session.accessToken, orderRef, activeId, makeCallbacks(assistantId));
    },
    [session, resolveConversationId, makeCallbacks]
  );

  const retry = useCallback(
    async (messageId: string) => {
      const target = messages.find((m) => m.id === messageId);
      if (!target?.retry || !session) return;
      setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, status: "pending", text: "" } : m)));

      if (target.retry.kind === "chat") {
        const activeId = resolveConversationId();
        if (!activeId) return;
        await streamChatMessage(session.accessToken, target.retry.message, activeId, makeCallbacks(messageId));
      } else if (target.retry.kind === "explain") {
        await streamExplainTransaction(
          session.accessToken,
          target.retry.transactionId,
          resolveConversationId(),
          makeCallbacks(messageId)
        );
      } else {
        await streamTrackRedemptionOrder(
          session.accessToken,
          target.retry.orderRef,
          resolveConversationId(),
          makeCallbacks(messageId)
        );
      }
    },
    [messages, session, resolveConversationId, makeCallbacks]
  );

  return { messages, sendMessage, selectTransaction, selectRedemptionOrder, retry };
}
