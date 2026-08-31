export type ChatResponseType =
  | "TEXT_ANSWER"
  | "TRANSACTION_SELECTION"
  | "TRANSACTION_EXPLANATION"
  | "TRANSACTION_SUMMARY"
  | "REDEMPTION_SELECTION"
  | "REDEMPTION_TRACKING"
  | "ORDERS_OVERVIEW"
  | "ESCALATE"
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

export interface TransactionsSummaryData {
  transactions: TransactionDetail[];
}

export interface RedemptionOrderSummary {
  order_ref: string;
  product_name: string;
  product_type: string;
  metal_type: string;
  quantity: number;
  status: string;
  created_at: string;
}

export interface TrackingEvent {
  type: string;
  remarks: string;
  area: string;
  event_time: string;
}

export interface RedemptionTracking {
  order_ref: string;
  product_name: string;
  quantity: number;
  status: string;
  awb_available: boolean;
  current_location: string | null;
  latest_event: TrackingEvent | null;
  history: TrackingEvent[];
  stale: boolean;
}

export interface RedemptionSelectionData {
  orders: RedemptionOrderSummary[];
}

export interface RedemptionTrackingData {
  tracking: RedemptionTracking;
}

export interface OrderCard {
  kind: "transaction" | "redemption";
  transaction: TransactionSummary | null;
  redemption: RedemptionOrderSummary | null;
}

export interface OrdersOverviewData {
  orders: OrderCard[];
}

export interface EscalateData {
  contact_email: string;
}

export interface ErrorData {
  code: string;
  detail: string;
}

export interface ChatResponse {
  type: ChatResponseType;
  message: string;
  data:
    | TextAnswerData
    | TransactionSelectionData
    | TransactionExplanationData
    | TransactionsSummaryData
    | RedemptionSelectionData
    | RedemptionTrackingData
    | OrdersOverviewData
    | EscalateData
    | ErrorData
    | null;
}

export type UserRole = "ADMINISTRATOR" | "USER";

export interface SeededUser {
  username: string;
  display_name: string;
  role: UserRole;
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
  role: UserRole;
}

export interface ConversationSummary {
  id: string;
  title: string;
  total_cost_usd: number;
  models_used: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationWithUser extends ConversationSummary {
  user_id: string;
  username: string;
  display_name: string;
}

export interface PersistedMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  response_type: ChatResponseType | null;
  response_data: ChatResponse["data"] | null;
  model_used: string | null;
  cost_usd: number | null;
  created_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: PersistedMessage[];
}

export interface AdminUser {
  id: string;
  username: string;
  display_name: string;
  role: UserRole;
  transaction_count: number;
  redemption_order_count: number;
  conversation_count: number;
}

export interface AdminTransaction extends TransactionDetail {
  user_id: string;
  username: string;
  display_name: string;
}

export interface AdminRedemptionOrder extends RedemptionOrderSummary {
  user_id: string;
  username: string;
  display_name: string;
}

export interface CostByModel {
  model: string;
  cost_usd: number;
  calls: number;
}

export interface CostByCategory {
  category: string;
  cost_usd: number;
  turns: number;
}

export interface TopConversation {
  conversation_id: string;
  title: string;
  username: string;
  cost_usd: number;
}

export interface AdminCostSummary {
  total_cost_usd: number;
  by_model: CostByModel[];
  by_category: CostByCategory[];
  top_conversations: TopConversation[];
}

export interface FaqArticleCreate {
  question: string;
  answer: string;
  category: string | null;
  tags: string[] | null;
}

export type MessageStatus = "pending" | "sent" | "error";

export type RetryAction =
  | { kind: "chat"; message: string }
  | { kind: "explain"; transactionId: string }
  | { kind: "track"; orderRef: string };

export interface ChatUIMessage {
  id: string;
  role: "user" | "assistant";
  status: MessageStatus;
  text: string;
  response?: ChatResponse;
  retry?: RetryAction;
  // True while text is still growing from SSE deltas - lets MessageBubble
  // render plain text instead of markdown, since partially-streamed markdown
  // (e.g. an unclosed **bold) renders incorrectly if parsed mid-stream.
  streaming?: boolean;
}
