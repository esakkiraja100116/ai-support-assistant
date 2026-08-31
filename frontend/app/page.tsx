"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ChatSidebarContent } from "@/components/chat/ChatSidebarContent";
import { ChatWindow } from "@/components/ChatWindow";
import { LoginScreen } from "@/components/LoginScreen";
import { DashboardShell } from "@/components/shell/DashboardShell";
import { useAuth } from "@/hooks/useAuth";
import { useConversations } from "@/hooks/useConversations";

// This app is reverse-proxied under esakkiraja.me/ai-assistant-chat-demo/
// rather than served from its own domain (see next.config.js's basePath).
// next/navigation's router.push/replace issues a client-side RSC data fetch
// for same-page URL updates, and that fetch 404s through the proxy - which
// was aborting the very first chat turn (the moment onConversationCreated
// fired router.replace) until a manual page refresh. Plain
// history.replaceState/pushState updates the visible URL without ever going
// through that RSC fetch, so conversationId is tracked as local state here
// (seeded from/kept in sync with the URL) instead of driving everything off
// useSearchParams directly.
function setUrlConversationId(id: string | null, push: boolean): void {
  const url = id ? `${window.location.pathname}?c=${id}` : window.location.pathname;
  if (push) {
    window.history.pushState(null, "", url);
  } else {
    window.history.replaceState(null, "", url);
  }
}

function HomeInner() {
  const { session, ready, loginAs, logout } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [conversationId, setConversationId] = useState<string | null>(() => searchParams.get("c"));
  const { conversations, loading: conversationsLoading, refresh } = useConversations(session);

  // Picks up a conversation id that arrived via real Next.js navigation
  // (a bookmarked/shared link, or the browser back/forward buttons) - our
  // own history.replaceState/pushState writes below never touch this.
  useEffect(() => {
    const urlId = searchParams.get("c");
    if (urlId && urlId !== conversationId) setConversationId(urlId);
  }, [searchParams, conversationId]);

  useEffect(() => {
    if (!ready || !session) return;
    if (session.role === "ADMINISTRATOR") {
      router.replace("/admin");
    }
  }, [ready, session, router]);

  function startNewChat() {
    setConversationId(null);
    setUrlConversationId(null, true);
  }

  function handleLogout() {
    logout();
    setConversationId(null);
    setUrlConversationId(null, false);
  }

  function openConversation(id: string) {
    setConversationId(id);
    setUrlConversationId(id, true);
  }

  // The URL only gains a ?c= once the first message of a conversation is
  // actually sent (see ChatWindow's onConversationCreated) - not merely on
  // login or when landing on "/", so we never expose an unused conversation
  // id that nothing was ever sent to.
  function handleConversationCreated(id: string) {
    setConversationId(id);
    setUrlConversationId(id, false);
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
          onSelectConversation={openConversation}
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
