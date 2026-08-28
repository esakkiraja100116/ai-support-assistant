"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { ChatWindow } from "@/components/ChatWindow";
import { LoginScreen } from "@/components/LoginScreen";
import { useAuth } from "@/hooks/useAuth";
import { newConversationId } from "@/lib/session";

function HomeInner() {
  const { session, ready, loginAs, logout } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const conversationId = searchParams.get("c");

  useEffect(() => {
    if (ready && session && !conversationId) {
      router.replace(`/?c=${newConversationId()}`);
    }
  }, [ready, session, conversationId, router]);

  function startNewChat() {
    router.push(`/?c=${newConversationId()}`);
  }

  if (!ready || (session && !conversationId)) {
    return <div className="page-loading">Loading...</div>;
  }

  if (!session) {
    return <LoginScreen onLogin={loginAs} />;
  }

  return (
    <ChatWindow
      session={session}
      conversationId={conversationId as string}
      onLogout={logout}
      onNewChat={startNewChat}
    />
  );
}

export default function Home() {
  return (
    <Suspense fallback={<div className="page-loading">Loading...</div>}>
      <HomeInner />
    </Suspense>
  );
}
