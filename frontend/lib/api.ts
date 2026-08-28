import { ChatHistoryEntry, ChatResponse, FaqArticle, SeededUser } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
  } catch {
    throw new ApiError(0, "Could not reach the server. Check your connection and try again.");
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // ignore body parse errors, use default detail
    }
    throw new ApiError(response.status, detail);
  }

  return response.json() as Promise<T>;
}

export function listUsers(): Promise<SeededUser[]> {
  return request<SeededUser[]>("/auth/users");
}

export function login(username: string): Promise<{ access_token: string; user_id: string; display_name: string }> {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username }),
  });
}

export function sendChatMessage(
  token: string,
  message: string,
  history: ChatHistoryEntry[],
  conversationId: string
): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ message, history, conversation_id: conversationId }),
  });
}

export function explainTransaction(token: string, transactionId: string): Promise<ChatResponse> {
  return request<ChatResponse>(`/transactions/${transactionId}/explain`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function listFaqArticles(): Promise<FaqArticle[]> {
  return request<FaqArticle[]>("/faq");
}
