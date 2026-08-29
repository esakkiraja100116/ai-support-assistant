import { AuthSession } from "./types";

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

export function newConversationId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
}
