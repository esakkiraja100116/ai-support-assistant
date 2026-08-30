"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
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

  if (error) return <div className="mx-auto max-w-4xl px-5 pt-6 pb-16 text-sm text-muted-foreground">{error}</div>;
  if (!conversation)
    return <div className="mx-auto max-w-4xl px-5 pt-6 pb-16 text-sm text-muted-foreground">Loading...</div>;

  return (
    <div className="mx-auto max-w-4xl px-5 pt-6 pb-16">
      <h1 className="mb-1.5 text-2xl font-semibold tracking-tight">{conversation.title}</h1>
      <p className="mb-4 text-sm text-muted-foreground">
        {conversation.message_count} messages - {conversation.models_used || "no model calls"} - $
        {conversation.total_cost_usd.toFixed(4)}
      </p>
      <Card className="[&_button]:pointer-events-none [&_button]:cursor-default">
        <MessageList
          messages={messages}
          onSelectTransaction={() => {}}
          onSelectRedemptionOrder={() => {}}
          onRetry={() => {}}
          className="max-h-[70vh] flex-none"
        />
      </Card>
    </div>
  );
}
