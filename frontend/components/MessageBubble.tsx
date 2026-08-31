import {
  ChatUIMessage,
  OrdersOverviewData,
  RedemptionSelectionData,
  RedemptionTrackingData,
  TextAnswerData,
  TransactionExplanationData,
  TransactionSelectionData,
  TransactionsSummaryData,
} from "@/lib/types";
import { EscalateCard } from "./EscalateCard";
import { ErrorBanner } from "./ErrorBanner";
import { LoadingIndicator } from "./LoadingIndicator";
import { MarkdownText } from "./MarkdownText";
import { RedemptionOrderCard } from "./RedemptionOrderCard";
import { RedemptionOrderSelector } from "./RedemptionOrderSelector";
import { RedemptionTrackingDetail } from "./RedemptionTrackingDetail";
import { TransactionCard } from "./TransactionCard";
import { TransactionDetail } from "./TransactionDetail";
import { TransactionSelector } from "./TransactionSelector";
import { TransactionsSummary } from "./TransactionsSummary";

interface Props {
  message: ChatUIMessage;
  onSelectTransaction: (id: string) => void;
  onSelectRedemptionOrder: (orderRef: string) => void;
  onRetry: (id: string) => void;
}

const BUBBLE = "max-w-[85%] sm:max-w-[75%] rounded-2xl px-3.5 py-2.5 text-sm leading-snug whitespace-pre-wrap";

export function MessageBubble({ message, onSelectTransaction, onSelectRedemptionOrder, onRetry }: Props) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className={`${BUBBLE} rounded-br-sm bg-primary text-primary-foreground`}>{message.text}</div>
      </div>
    );
  }

  if (message.status === "pending") {
    // While streaming, text grows delta-by-delta ("Hi" -> "Hi Alice" -> ...) -
    // rendered as plain text, not markdown: a partially-streamed markup like
    // an unclosed "**bold" renders incorrectly if parsed before it closes.
    // Once the turn finalizes (status becomes "sent"), the branches below
    // render the same text through MarkdownText.
    if (message.streaming && message.text) {
      return (
        <div className="flex flex-col items-start gap-2">
          <div className={`${BUBBLE} rounded-bl-sm bg-muted text-foreground`}>{message.text}</div>
        </div>
      );
    }
    return (
      <div className="flex flex-col items-start gap-2">
        <div className={`${BUBBLE} rounded-bl-sm bg-muted text-foreground`}>
          <LoadingIndicator />
        </div>
      </div>
    );
  }

  if (message.status === "error") {
    return (
      <div className="flex flex-col items-start gap-2">
        <ErrorBanner message={message.text} onRetry={() => onRetry(message.id)} />
      </div>
    );
  }

  const response = message.response;
  if (!response) return null;

  if (response.type === "TRANSACTION_SELECTION") {
    return (
      <div className="flex flex-col items-start gap-2">
        <div className={`${BUBBLE} rounded-bl-sm bg-muted text-foreground`}>
          <MarkdownText text={response.message} />
        </div>
        <TransactionSelector data={response.data as TransactionSelectionData} onSelect={onSelectTransaction} />
      </div>
    );
  }

  if (response.type === "TRANSACTION_EXPLANATION") {
    return (
      <div className="flex flex-col items-start gap-2">
        <TransactionDetail data={response.data as TransactionExplanationData} message={response.message} />
      </div>
    );
  }

  if (response.type === "TRANSACTION_SUMMARY") {
    return (
      <div className="flex flex-col items-start gap-2">
        <TransactionsSummary data={response.data as TransactionsSummaryData} message={response.message} />
      </div>
    );
  }

  if (response.type === "REDEMPTION_SELECTION") {
    return (
      <div className="flex flex-col items-start gap-2">
        <div className={`${BUBBLE} rounded-bl-sm bg-muted text-foreground`}>
          <MarkdownText text={response.message} />
        </div>
        <RedemptionOrderSelector data={response.data as RedemptionSelectionData} onSelect={onSelectRedemptionOrder} />
      </div>
    );
  }

  if (response.type === "REDEMPTION_TRACKING") {
    return (
      <div className="flex flex-col items-start gap-2">
        <RedemptionTrackingDetail data={response.data as RedemptionTrackingData} message={response.message} />
      </div>
    );
  }

  if (response.type === "ORDERS_OVERVIEW") {
    const data = response.data as OrdersOverviewData;
    return (
      <div className="flex flex-col items-start gap-2">
        <div className={`${BUBBLE} rounded-bl-sm bg-muted text-foreground`}>
          <MarkdownText text={response.message} />
        </div>
        <div className="grid w-full grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {data.orders.map((card) =>
            card.kind === "transaction" && card.transaction ? (
              <TransactionCard key={card.transaction.id} transaction={card.transaction} onSelect={onSelectTransaction} />
            ) : card.redemption ? (
              <RedemptionOrderCard
                key={card.redemption.order_ref}
                order={card.redemption}
                onSelect={onSelectRedemptionOrder}
              />
            ) : null
          )}
        </div>
      </div>
    );
  }

  if (response.type === "ESCALATE") {
    return (
      <div className="flex flex-col items-start gap-2">
        <EscalateCard message={response.message} />
      </div>
    );
  }

  if (response.type === "ERROR") {
    return (
      <div className="flex flex-col items-start gap-2">
        <ErrorBanner message={response.message} onRetry={() => onRetry(message.id)} />
      </div>
    );
  }

  const grounded = (response.data as TextAnswerData | undefined)?.grounded;
  return (
    <div className="flex flex-col items-start gap-2">
      <div className={`${BUBBLE} rounded-bl-sm bg-muted text-foreground`}>
        <MarkdownText text={response.message} />
        {grounded === false && <div className="mt-1.5 text-xs text-muted-foreground">Not found in our knowledge base</div>}
      </div>
    </div>
  );
}
