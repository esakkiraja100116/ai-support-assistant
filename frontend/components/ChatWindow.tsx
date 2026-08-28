"use client";

import Link from "next/link";
import { useChat } from "@/hooks/useChat";
import { AuthSession } from "@/lib/types";
import { ChatInput } from "./ChatInput";
import { MessageList } from "./MessageList";

interface Props {
  session: AuthSession;
  conversationId: string;
  onLogout: () => void;
  onNewChat: () => void;
}

export function ChatWindow({ session, conversationId, onLogout, onNewChat }: Props) {
  const { messages, sendMessage, selectTransaction, retry } = useChat(session, conversationId);
  const isBusy = messages.some((m) => m.status === "pending");

  return (
    <div className="chat-window">
      <header className="chat-header">
        <span>Signed in as {session.displayName}</span>
        <div className="header-actions">
          <Link href="/faq" className="text-button">
            FAQ
          </Link>
          <button className="text-button" onClick={onNewChat}>
            New chat
          </button>
          <button className="text-button" onClick={onLogout}>
            Log out
          </button>
        </div>
      </header>

      <MessageList messages={messages} onSelectTransaction={selectTransaction} onRetry={retry} />

      <ChatInput onSend={sendMessage} disabled={isBusy} />
    </div>
  );
}
