import { useEffect, useRef } from "react";
import { ChatUIMessage } from "@/lib/types";
import { EmptyState } from "./EmptyState";
import { MessageBubble } from "./MessageBubble";

interface Props {
  messages: ChatUIMessage[];
  onSelectTransaction: (id: string) => void;
  onSelectRedemptionOrder: (orderRef: string) => void;
  onRetry: (id: string) => void;
}

export function MessageList({ messages, onSelectTransaction, onSelectRedemptionOrder, onRetry }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="message-list">
        <EmptyState message='Ask a support question, e.g. "How do I sell my gold?" or "Show me my recent transactions."' />
      </div>
    );
  }

  return (
    <div className="message-list">
      {messages.map((message) => (
        <MessageBubble
          key={message.id}
          message={message}
          onSelectTransaction={onSelectTransaction}
          onSelectRedemptionOrder={onSelectRedemptionOrder}
          onRetry={onRetry}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
