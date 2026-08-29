"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ConversationSummary } from "@/lib/types";

interface Props {
  conversations: ConversationSummary[];
  loading: boolean;
  activeConversationId: string | null;
  onNewChat: () => void;
}

export function ChatSidebarContent({ conversations, loading, activeConversationId, onNewChat }: Props) {
  const router = useRouter();

  return (
    <div className="sidebar-content">
      <button className="new-chat-button" onClick={onNewChat}>
        + New chat
      </button>
      <div className="conversation-list">
        {loading && <p className="muted sidebar-empty">Loading...</p>}
        {!loading && conversations.length === 0 && <p className="muted sidebar-empty">No conversations yet</p>}
        {conversations.map((c) => (
          <button
            key={c.id}
            className={`conversation-list-item${c.id === activeConversationId ? " active" : ""}`}
            onClick={() => router.push(`/?c=${c.id}`)}
          >
            <span className="conversation-list-item-title">{c.title}</span>
            <span className="conversation-list-item-meta">{c.message_count} messages</span>
          </button>
        ))}
      </div>
      <Link href="/faq" className="faq-link sidebar-faq-link">
        Browse the knowledge base
      </Link>
    </div>
  );
}
