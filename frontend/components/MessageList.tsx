import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { ChatUIMessage } from "@/lib/types";
import { EmptyState } from "./EmptyState";
import { MessageBubble } from "./MessageBubble";

interface Props {
  messages: ChatUIMessage[];
  onSelectTransaction: (id: string) => void;
  onSelectRedemptionOrder: (orderRef: string) => void;
  onRetry: (id: string) => void;
  // Defaults to filling its flex parent (the normal chat window case).
  // Passed as e.g. "max-h-[70vh]" for the read-only admin transcript view,
  // which isn't inside a flex-1 layout - this replaces the old
  // `.read-only-transcript .message-list` descendant CSS override.
  className?: string;
}

export function MessageList({
  messages,
  onSelectTransaction,
  onSelectRedemptionOrder,
  onRetry,
  className,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const containerClass = cn("flex-1 min-h-0 overflow-y-auto p-4 flex flex-col gap-3.5", className);

  if (messages.length === 0) {
    return (
      <div className={containerClass}>
        <EmptyState message='Ask a support question, e.g. "How do I sell my gold?" or "Show me my recent transactions."' />
      </div>
    );
  }

  return (
    <div className={containerClass}>
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
