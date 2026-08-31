"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { ChatSidebarContent } from "@/components/chat/ChatSidebarContent";
import { ChatWindow } from "@/components/ChatWindow";
import { LoginScreen } from "@/components/LoginScreen";
import { DashboardShell } from "@/components/shell/DashboardShell";
import { useAuth } from "@/hooks/useAuth";
import { useConversations } from "@/hooks/useConversations";

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
    }
  }, [ready, session, router]);

  function startNewChat() {
    router.push("/");
  }

  function handleLogout() {
    logout();
    router.replace("/");
  }

  // The URL only gains a ?c= once the first message of a conversation is
  // actually sent (see ChatWindow's onConversationCreated) - not merely on
  // login or when landing on "/", so we never expose an unused conversation
  // id that nothing was ever sent to.
  function handleConversationCreated(id: string) {
    router.replace(`/?c=${id}`);
  }

  if (!ready || (session && session.role === "ADMINISTRATOR")) {
    return <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">Loading...</div>;
  }

  if (!session) {
    return <LoginScreen onLogin={loginAs} />;
  }

  return (
    <DashboardShell
      session={session}
      onLogout={handleLogout}
      sidebarContent={
        <ChatSidebarContent
          conversations={conversations}
          loading={conversationsLoading}
          activeConversationId={conversationId}
          onNewChat={startNewChat}
        />
      }
    >
      <ChatWindow
        session={session}
        conversationId={conversationId}
        onConversationCreated={handleConversationCreated}
        onTurnComplete={refresh}
      />
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
