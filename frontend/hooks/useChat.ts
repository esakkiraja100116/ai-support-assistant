"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, explainTransaction, getConversation, sendChatMessage } from "@/lib/api";
import { persistedToUIMessages } from "@/lib/messageMapping";
import { AuthSession, ChatUIMessage } from "@/lib/types";

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

      try {
        const response = await sendChatMessage(session.accessToken, text, conversationId);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, status: "sent", text: response.message, response } : m
          )
        );
        onTurnComplete?.();
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Something went wrong.";
        setMessages((prev) => (prev.map((m) => (m.id === assistantId ? { ...m, status: "error", text: message } : m))));
      }
    },
    [session, conversationId, onTurnComplete]
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

      try {
        const response = await explainTransaction(session.accessToken, transactionId, conversationId);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, status: "sent", text: response.message, response } : m
          )
        );
        onTurnComplete?.();
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Something went wrong.";
        setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, status: "error", text: message } : m)));
      }
    },
    [session, conversationId, onTurnComplete]
  );

  const retry = useCallback(
    async (messageId: string) => {
      const target = messages.find((m) => m.id === messageId);
      if (!target?.retry) return;
      setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, status: "pending", text: "" } : m)));

      if (target.retry.kind === "chat") {
        if (!session || !conversationId) return;
        try {
          const response = await sendChatMessage(session.accessToken, target.retry.message, conversationId);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === messageId ? { ...m, status: "sent", text: response.message, response } : m
            )
          );
          onTurnComplete?.();
        } catch (err) {
          const message = err instanceof ApiError ? err.message : "Something went wrong.";
          setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, status: "error", text: message } : m)));
        }
      } else {
        if (!session) return;
        try {
          const response = await explainTransaction(session.accessToken, target.retry.transactionId, conversationId);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === messageId ? { ...m, status: "sent", text: response.message, response } : m
            )
          );
          onTurnComplete?.();
        } catch (err) {
          const message = err instanceof ApiError ? err.message : "Something went wrong.";
          setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, status: "error", text: message } : m)));
        }
      }
    },
    [messages, session, conversationId, onTurnComplete]
  );

  return { messages, sendMessage, selectTransaction, retry };
}
