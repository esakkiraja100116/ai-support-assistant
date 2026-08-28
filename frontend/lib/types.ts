export type ChatResponseType =
  | "TEXT_ANSWER"
  | "TRANSACTION_SELECTION"
  | "TRANSACTION_EXPLANATION"
  | "ERROR";

export interface TransactionSummary {
  id: string;
  type: string;
  product: string;
  amount: number;
  status: string;
  created_at: string;
}

export interface TransactionDetail extends TransactionSummary {
  failure_reason: string | null;
  payment_method: string;
  updated_at: string;
}

export interface TextAnswerData {
  grounded: boolean;
  sources: number[];
}

export interface TransactionSelectionData {
  transactions: TransactionSummary[];
}

export interface TransactionExplanationData {
  transaction: TransactionDetail;
}

export interface ErrorData {
  code: string;
  detail: string;
}

export interface ChatResponse {
  type: ChatResponseType;
  message: string;
  data: TextAnswerData | TransactionSelectionData | TransactionExplanationData | ErrorData | null;
}

export interface ChatHistoryEntry {
  role: "user" | "assistant";
  content: string;
}

export interface SeededUser {
  username: string;
  display_name: string;
}

export interface FaqArticle {
  id: number;
  question: string;
  answer: string;
  category: string | null;
}

export interface AuthSession {
  accessToken: string;
  userId: string;
  displayName: string;
  username: string;
}

export type MessageStatus = "pending" | "sent" | "error";

export type RetryAction =
  | { kind: "chat"; message: string }
  | { kind: "explain"; transactionId: string };

export interface ChatUIMessage {
  id: string;
  role: "user" | "assistant";
  status: MessageStatus;
  text: string;
  response?: ChatResponse;
  retry?: RetryAction;
}
