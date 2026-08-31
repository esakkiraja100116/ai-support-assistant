"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ConversationSummary } from "@/lib/types";

interface Props {
  conversations: ConversationSummary[];
  loading: boolean;
  activeConversationId: string | null;
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
}

export function ChatSidebarContent({
  conversations,
  loading,
  activeConversationId,
  onNewChat,
  onSelectConversation,
}: Props) {
  return (
    <div className="flex h-full flex-col gap-3 p-3.5">
      <Button variant="outline" className="justify-start" onClick={onNewChat}>
        + New chat
      </Button>
      <div className="flex-1 overflow-y-auto flex flex-col gap-1">
        {loading && <p className="px-2.5 py-2 text-sm text-muted-foreground">Loading...</p>}
        {!loading && conversations.length === 0 && (
          <p className="px-2.5 py-2 text-sm text-muted-foreground">No conversations yet</p>
        )}
        {conversations.map((c) => (
          <button
            key={c.id}
            className={cn(
              "flex flex-col gap-0.5 rounded-md px-2.5 py-2 text-left hover:bg-accent",
              c.id === activeConversationId && "bg-accent"
            )}
            onClick={() => onSelectConversation(c.id)}
          >
            <span className="truncate text-sm text-foreground">{c.title}</span>
            <span className="text-xs text-muted-foreground">{c.message_count} messages</span>
          </button>
        ))}
      </div>
      <Link href="/faq" prefetch={false} className="text-center text-xs text-primary hover:underline">
        Browse the knowledge base
      </Link>
    </div>
  );
}
