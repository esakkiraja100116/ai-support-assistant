"use client";

import { useCallback, useEffect, useState } from "react";
import { login as apiLogin } from "@/lib/api";
import { clearAuth, loadAuth, saveAuth } from "@/lib/session";
import { AuthSession } from "@/lib/types";

export function useAuth() {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setSession(loadAuth());
    setReady(true);
  }, []);

  const loginAs = useCallback(async (username: string) => {
    const result = await apiLogin(username);
    const next: AuthSession = {
      accessToken: result.access_token,
      userId: result.user_id,
      displayName: result.display_name,
      username,
      role: result.role as AuthSession["role"],
    };
    saveAuth(next);
    setSession(next);
  }, []);

  const logout = useCallback(() => {
    clearAuth();
    setSession(null);
  }, []);

  return { session, ready, loginAs, logout };
}
