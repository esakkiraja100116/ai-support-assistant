"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, explainTransaction, sendChatMessage } from "@/lib/api";
import { loadChatHistory, saveChatHistory } from "@/lib/session";
import {
  AuthSession,
  ChatHistoryEntry,
  ChatUIMessage,
  TransactionSelectionData,
} from "@/lib/types";

const MAX_HISTORY_TURNS = 10;

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
}

// Assistant turns that showed a transaction list carry the actual records into
// history (not just the human-facing "Which transaction..." text), so a later
// follow-up like "the second one" or "the failed one" can still be resolved
// even after the card list has scrolled out of view.
function toHistory(messages: ChatUIMessage[]): ChatHistoryEntry[] {
  return messages
    .filter((m) => m.status === "sent")
    .slice(-MAX_HISTORY_TURNS)
    .map((m) => {
      if (m.role === "assistant" && m.response?.type === "TRANSACTION_SELECTION") {
        const data = m.response.data as TransactionSelectionData;
        return { role: m.role, content: `${m.text}\n${JSON.stringify(data.transactions)}` };
      }
      return { role: m.role, content: m.text };
    });
}

export function useChat(session: AuthSession | null, conversationId: string | null) {
  const [messages, setMessages] = useState<ChatUIMessage[]>([]);
  const hydratedFor = useRef<string | null>(null);

  useEffect(() => {
    if (!session || !conversationId) {
      setMessages([]);
      hydratedFor.current = null;
      return;
    }
    const key = `${session.userId}:${conversationId}`;
    if (hydratedFor.current !== key) {
      setMessages(loadChatHistory(session.userId, conversationId));
      hydratedFor.current = key;
    }
  }, [session, conversationId]);

  useEffect(() => {
    if (session && conversationId && hydratedFor.current === `${session.userId}:${conversationId}`) {
      saveChatHistory(session.userId, conversationId, messages);
    }
  }, [messages, session, conversationId]);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!session || !conversationId) return;
      const historyBefore = toHistory(messages);
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
        const response = await sendChatMessage(session.accessToken, text, historyBefore, conversationId);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, status: "sent", text: response.message, response } : m
          )
        );
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Something went wrong.";
        setMessages((prev) => (prev.map((m) => (m.id === assistantId ? { ...m, status: "error", text: message } : m))));
      }
    },
    [session, messages, conversationId]
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
        const response = await explainTransaction(session.accessToken, transactionId);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, status: "sent", text: response.message, response } : m
          )
        );
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Something went wrong.";
        setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, status: "error", text: message } : m)));
      }
    },
    [session]
  );

  const retry = useCallback(
    async (messageId: string) => {
      const target = messages.find((m) => m.id === messageId);
      if (!target?.retry) return;
      setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, status: "pending", text: "" } : m)));

      if (target.retry.kind === "chat") {
        if (!session || !conversationId) return;
        const historyBefore = toHistory(messages.filter((m) => m.id !== messageId));
        try {
          const response = await sendChatMessage(
            session.accessToken,
            target.retry.message,
            historyBefore,
            conversationId
          );
          setMessages((prev) =>
            prev.map((m) =>
              m.id === messageId ? { ...m, status: "sent", text: response.message, response } : m
            )
          );
        } catch (err) {
          const message = err instanceof ApiError ? err.message : "Something went wrong.";
          setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, status: "error", text: message } : m)));
        }
      } else {
        if (!session) return;
        try {
          const response = await explainTransaction(session.accessToken, target.retry.transactionId);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === messageId ? { ...m, status: "sent", text: response.message, response } : m
            )
          );
        } catch (err) {
          const message = err instanceof ApiError ? err.message : "Something went wrong.";
          setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, status: "error", text: message } : m)));
        }
      }
    },
    [messages, session, conversationId]
  );

  return { messages, sendMessage, selectTransaction, retry };
}
