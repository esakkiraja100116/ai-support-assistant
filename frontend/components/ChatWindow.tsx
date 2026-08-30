"use client";

import { useChat } from "@/hooks/useChat";
import { AuthSession } from "@/lib/types";
import { ChatInput } from "./ChatInput";
import { MessageList } from "./MessageList";

interface Props {
  session: AuthSession;
  conversationId: string;
  onTurnComplete?: () => void;
}

export function ChatWindow({ session, conversationId, onTurnComplete }: Props) {
  const { messages, sendMessage, selectTransaction, selectRedemptionOrder, retry } = useChat(
    session,
    conversationId,
    onTurnComplete
  );
  const isBusy = messages.some((m) => m.status === "pending");

  return (
    <div className="chat-window">
      <MessageList
        messages={messages}
        onSelectTransaction={selectTransaction}
        onSelectRedemptionOrder={selectRedemptionOrder}
        onRetry={retry}
      />
      <ChatInput onSend={sendMessage} disabled={isBusy} />
    </div>
  );
}
