import {
  ChatUIMessage,
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
import { RedemptionOrderSelector } from "./RedemptionOrderSelector";
import { RedemptionTrackingDetail } from "./RedemptionTrackingDetail";
import { TransactionDetail } from "./TransactionDetail";
import { TransactionSelector } from "./TransactionSelector";
import { TransactionsSummary } from "./TransactionsSummary";

interface Props {
  message: ChatUIMessage;
  onSelectTransaction: (id: string) => void;
  onSelectRedemptionOrder: (orderRef: string) => void;
  onRetry: (id: string) => void;
}

export function MessageBubble({ message, onSelectTransaction, onSelectRedemptionOrder, onRetry }: Props) {
  if (message.role === "user") {
    return (
      <div className="message-row user">
        <div className="bubble user-bubble">{message.text}</div>
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
        <div className="message-row assistant">
          <div className="bubble assistant-bubble">{message.text}</div>
        </div>
      );
    }
    return (
      <div className="message-row assistant">
        <div className="bubble assistant-bubble">
          <LoadingIndicator />
        </div>
      </div>
    );
  }

  if (message.status === "error") {
    return (
      <div className="message-row assistant">
        <ErrorBanner message={message.text} onRetry={() => onRetry(message.id)} />
      </div>
    );
  }

  const response = message.response;
  if (!response) return null;

  if (response.type === "TRANSACTION_SELECTION") {
    return (
      <div className="message-row assistant">
        <div className="bubble assistant-bubble">
          <MarkdownText text={response.message} />
        </div>
        <TransactionSelector
          data={response.data as TransactionSelectionData}
          onSelect={onSelectTransaction}
        />
      </div>
    );
  }

  if (response.type === "TRANSACTION_EXPLANATION") {
    return (
      <div className="message-row assistant">
        <TransactionDetail data={response.data as TransactionExplanationData} message={response.message} />
      </div>
    );
  }

  if (response.type === "TRANSACTION_SUMMARY") {
    return (
      <div className="message-row assistant">
        <TransactionsSummary data={response.data as TransactionsSummaryData} message={response.message} />
      </div>
    );
  }

  if (response.type === "REDEMPTION_SELECTION") {
    return (
      <div className="message-row assistant">
        <div className="bubble assistant-bubble">
          <MarkdownText text={response.message} />
        </div>
        <RedemptionOrderSelector data={response.data as RedemptionSelectionData} onSelect={onSelectRedemptionOrder} />
      </div>
    );
  }

  if (response.type === "REDEMPTION_TRACKING") {
    return (
      <div className="message-row assistant">
        <RedemptionTrackingDetail data={response.data as RedemptionTrackingData} message={response.message} />
      </div>
    );
  }

  if (response.type === "ESCALATE") {
    return (
      <div className="message-row assistant">
        <EscalateCard message={response.message} />
      </div>
    );
  }

  if (response.type === "ERROR") {
    return (
      <div className="message-row assistant">
        <ErrorBanner message={response.message} onRetry={() => onRetry(message.id)} />
      </div>
    );
  }

  const grounded = (response.data as TextAnswerData | undefined)?.grounded;
  return (
    <div className="message-row assistant">
      <div className="bubble assistant-bubble">
        <MarkdownText text={response.message} />
        {grounded === false && <div className="grounding-note">Not found in our knowledge base</div>}
      </div>
    </div>
  );
}
