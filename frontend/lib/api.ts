import { fetchEventSource } from "@microsoft/fetch-event-source";
import {
  AdminCostSummary,
  AdminTransaction,
  AdminUser,
  ChatResponse,
  ConversationDetail,
  ConversationSummary,
  ConversationWithUser,
  FaqArticle,
  FaqArticleCreate,
  SeededUser,
} from "./types";

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

export function login(
  username: string
): Promise<{ access_token: string; user_id: string; display_name: string; role: string }> {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username }),
  });
}

export interface StreamCallbacks {
  onDelta: (text: string) => void;
  onDone: (response: ChatResponse) => void;
  onError: (message: string) => void;
}

async function streamPost(path: string, body: object, token: string, callbacks: StreamCallbacks): Promise<void> {
  try {
    await fetchEventSource(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
      openWhenHidden: true,
      async onopen(response) {
        if (!response.ok) {
          let detail = `Request failed (${response.status})`;
          try {
            detail = (await response.json()).detail || detail;
          } catch {
            // ignore body parse errors, use default detail
          }
          throw new ApiError(response.status, detail);
        }
      },
      onmessage(ev) {
        if (ev.event === "delta") {
          callbacks.onDelta((JSON.parse(ev.data) as { text: string }).text);
        } else if (ev.event === "done") {
          callbacks.onDone(JSON.parse(ev.data) as ChatResponse);
        }
      },
      onerror(err) {
        callbacks.onError(err instanceof Error ? err.message : "Something went wrong.");
        throw err; // stop fetchEventSource's built-in retry - this is a one-shot turn, not a live feed
      },
    });
  } catch (err) {
    if (!(err instanceof Error)) {
      callbacks.onError("Something went wrong.");
    }
    // onerror above already reported Error/ApiError instances via callbacks.onError
  }
}

export function streamChatMessage(
  token: string,
  message: string,
  conversationId: string,
  callbacks: StreamCallbacks
): Promise<void> {
  return streamPost("/chat/stream", { message, conversation_id: conversationId }, token, callbacks);
}

export function streamExplainTransaction(
  token: string,
  transactionId: string,
  conversationId: string | null,
  callbacks: StreamCallbacks
): Promise<void> {
  return streamPost(`/transactions/${transactionId}/explain/stream`, { conversation_id: conversationId }, token, callbacks);
}

export function listFaqArticles(): Promise<FaqArticle[]> {
  return request<FaqArticle[]>("/faq");
}

export function listConversations(token: string): Promise<ConversationSummary[]> {
  return request<ConversationSummary[]>("/conversations", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getConversation(token: string, conversationId: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/conversations/${conversationId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function adminListUsers(token: string): Promise<AdminUser[]> {
  return request<AdminUser[]>("/admin/users", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function adminListTransactions(token: string): Promise<AdminTransaction[]> {
  return request<AdminTransaction[]>("/admin/transactions", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function adminListConversations(token: string): Promise<ConversationWithUser[]> {
  return request<ConversationWithUser[]>("/admin/conversations", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function adminGetConversation(token: string, conversationId: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/admin/conversations/${conversationId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function adminGetCosts(token: string): Promise<AdminCostSummary> {
  return request<AdminCostSummary>("/admin/costs", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function adminCreateFaqArticle(token: string, payload: FaqArticleCreate): Promise<FaqArticle> {
  return request<FaqArticle>("/admin/faq", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
}

export async function adminDeleteFaqArticle(token: string, articleId: number): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/admin/faq/${articleId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new ApiError(0, "Could not reach the server. Check your connection and try again.");
  }
  if (!response.ok) {
    throw new ApiError(response.status, `Request failed (${response.status})`);
  }
}
