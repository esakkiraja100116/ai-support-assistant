"use client";

import { useCallback, useEffect, useState } from "react";
import { listConversations } from "@/lib/api";
import { AuthSession, ConversationSummary } from "@/lib/types";

export function useConversations(session: AuthSession | null) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!session) return;
    try {
      const result = await listConversations(session.accessToken);
      setConversations(result);
    } catch {
      // Sidebar list is a convenience, not the source of truth for any
      // individual conversation - silently keep the previous list on failure.
    } finally {
      setLoading(false);
    }
  }, [session]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { conversations, loading, refresh };
}
