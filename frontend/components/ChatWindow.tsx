"use client";

import { useChat } from "@/hooks/useChat";
import { AuthSession } from "@/lib/types";
import { ChatInput } from "./ChatInput";
import { MessageList } from "./MessageList";
import { SuggestedQuestions } from "./SuggestedQuestions";

interface Props {
  session: AuthSession;
  conversationId: string | null;
  onConversationCreated: (id: string) => void;
  onTurnComplete?: () => void;
}

export function ChatWindow({ session, conversationId, onConversationCreated, onTurnComplete }: Props) {
  const { messages, sendMessage, selectTransaction, selectRedemptionOrder, retry } = useChat(
    session,
    conversationId,
    onTurnComplete,
    onConversationCreated
  );
  const isBusy = messages.some((m) => m.status === "pending");

  return (
    <div className="flex h-full flex-col bg-background">
      {messages.length === 0 ? (
        <div className="flex flex-1 flex-col justify-center overflow-y-auto">
          <SuggestedQuestions onSelect={sendMessage} />
        </div>
      ) : (
        <MessageList
          messages={messages}
          onSelectTransaction={selectTransaction}
          onSelectRedemptionOrder={selectRedemptionOrder}
          onRetry={retry}
        />
      )}
      <ChatInput onSend={sendMessage} disabled={isBusy} />
    </div>
  );
}
