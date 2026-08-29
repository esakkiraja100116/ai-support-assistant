import {
  ChatUIMessage,
  TextAnswerData,
  TransactionExplanationData,
  TransactionSelectionData,
  TransactionsSummaryData,
} from "@/lib/types";
import { ErrorBanner } from "./ErrorBanner";
import { LoadingIndicator } from "./LoadingIndicator";
import { TransactionDetail } from "./TransactionDetail";
import { TransactionSelector } from "./TransactionSelector";
import { TransactionsSummary } from "./TransactionsSummary";

interface Props {
  message: ChatUIMessage;
  onSelectTransaction: (id: string) => void;
  onRetry: (id: string) => void;
}

export function MessageBubble({ message, onSelectTransaction, onRetry }: Props) {
  if (message.role === "user") {
    return (
      <div className="message-row user">
        <div className="bubble user-bubble">{message.text}</div>
      </div>
    );
  }

  if (message.status === "pending") {
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
        <div className="bubble assistant-bubble">{response.message}</div>
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
        {response.message}
        {grounded === false && <div className="grounding-note">Not found in our knowledge base</div>}
      </div>
    </div>
  );
}
