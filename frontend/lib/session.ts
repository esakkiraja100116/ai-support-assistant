import { AuthSession, ChatUIMessage } from "./types";

const AUTH_KEY = "support_assistant:auth";

export function loadAuth(): AuthSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(AUTH_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthSession;
  } catch {
    return null;
  }
}

export function saveAuth(session: AuthSession): void {
  window.sessionStorage.setItem(AUTH_KEY, JSON.stringify(session));
}

export function clearAuth(): void {
  window.sessionStorage.removeItem(AUTH_KEY);
}

// Keyed by both userId and conversationId: the conversation id lives in the
// URL, so if a different user ends up on the same URL (e.g. shared browser),
// they must not see the previous user's chat history for that id.
function chatKey(userId: string, conversationId: string): string {
  return `support_assistant:chat:${userId}:${conversationId}`;
}

export function loadChatHistory(userId: string, conversationId: string): ChatUIMessage[] {
  if (typeof window === "undefined") return [];
  const raw = window.sessionStorage.getItem(chatKey(userId, conversationId));
  if (!raw) return [];
  try {
    return JSON.parse(raw) as ChatUIMessage[];
  } catch {
    return [];
  }
}

export function saveChatHistory(userId: string, conversationId: string, messages: ChatUIMessage[]): void {
  window.sessionStorage.setItem(chatKey(userId, conversationId), JSON.stringify(messages));
}

export function newConversationId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
}
