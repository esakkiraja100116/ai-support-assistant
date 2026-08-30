"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { ChatSidebarContent } from "@/components/chat/ChatSidebarContent";
import { ChatWindow } from "@/components/ChatWindow";
import { LoginScreen } from "@/components/LoginScreen";
import { DashboardShell } from "@/components/shell/DashboardShell";
import { useAuth } from "@/hooks/useAuth";
import { useConversations } from "@/hooks/useConversations";
import { newConversationId } from "@/lib/session";

function HomeInner() {
  const { session, ready, loginAs, logout } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const conversationId = searchParams.get("c");
  const { conversations, loading: conversationsLoading, refresh } = useConversations(session);

  useEffect(() => {
    if (!ready || !session) return;
    if (session.role === "ADMINISTRATOR") {
      router.replace("/admin");
      return;
    }
    if (!conversationId) {
      router.replace(`/?c=${newConversationId()}`);
    }
  }, [ready, session, conversationId, router]);

  function startNewChat() {
    router.push(`/?c=${newConversationId()}`);
  }

  if (!ready || (session && session.role === "ADMINISTRATOR") || (session && !conversationId)) {
    return <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">Loading...</div>;
  }

  if (!session) {
    return <LoginScreen onLogin={loginAs} />;
  }

  return (
    <DashboardShell
      session={session}
      onLogout={logout}
      sidebarContent={
        <ChatSidebarContent
          conversations={conversations}
          loading={conversationsLoading}
          activeConversationId={conversationId}
          onNewChat={startNewChat}
        />
      }
    >
      <ChatWindow session={session} conversationId={conversationId as string} onTurnComplete={refresh} />
    </DashboardShell>
  );
}

export default function Home() {
  return (
    <Suspense fallback={<div className="flex h-screen items-center justify-center text-sm text-muted-foreground">Loading...</div>}>
      <HomeInner />
    </Suspense>
  );
}
