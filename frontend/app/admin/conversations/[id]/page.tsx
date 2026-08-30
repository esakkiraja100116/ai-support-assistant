"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { MessageList } from "@/components/MessageList";
import { useAuth } from "@/hooks/useAuth";
import { adminGetConversation } from "@/lib/api";
import { persistedToUIMessages } from "@/lib/messageMapping";
import { ChatUIMessage, ConversationDetail } from "@/lib/types";

export default function AdminConversationDetailPage() {
  const { session } = useAuth();
  const params = useParams<{ id: string }>();
  const [conversation, setConversation] = useState<ConversationDetail | null>(null);
  const [messages, setMessages] = useState<ChatUIMessage[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session || !params.id) return;
    adminGetConversation(session.accessToken, params.id)
      .then((detail) => {
        setConversation(detail);
        setMessages(persistedToUIMessages(detail.messages));
      })
      .catch(() => setError("Could not load this conversation."));
  }, [session, params.id]);

  if (error) return <div className="admin-page">{error}</div>;
  if (!conversation) return <div className="admin-page muted">Loading...</div>;

  return (
    <div className="admin-page">
      <h1>{conversation.title}</h1>
      <p className="muted">
        {conversation.message_count} messages - {conversation.models_used || "no model calls"} - $
        {conversation.total_cost_usd.toFixed(4)}
      </p>
      <div className="read-only-transcript">
        <MessageList
          messages={messages}
          onSelectTransaction={() => {}}
          onSelectRedemptionOrder={() => {}}
          onRetry={() => {}}
        />
      </div>
    </div>
  );
}
