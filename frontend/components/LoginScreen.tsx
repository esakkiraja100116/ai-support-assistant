"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { listUsers } from "@/lib/api";
import { SeededUser } from "@/lib/types";
import { ErrorBanner } from "./ErrorBanner";

interface Props {
  onLogin: (username: string) => Promise<void>;
}

export function LoginScreen({ onLogin }: Props) {
  const [users, setUsers] = useState<SeededUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [loggingInAs, setLoggingInAs] = useState<string | null>(null);

  useEffect(() => {
    listUsers()
      .then(setUsers)
      .catch(() => setError("Could not reach the server. Is the backend running?"))
      .finally(() => setLoadingUsers(false));
  }, []);

  async function handleLogin(username: string) {
    setLoggingInAs(username);
    setError(null);
    try {
      await onLogin(username);
    } catch {
      setError("Login failed. Please try again.");
    } finally {
      setLoggingInAs(null);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">Support Assistant</CardTitle>
          <CardDescription>Choose an account to continue</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {loadingUsers && <p className="text-sm text-muted-foreground">Loading accounts...</p>}
          {error && <ErrorBanner message={error} onRetry={() => window.location.reload()} />}

          <div className="flex flex-col gap-2.5">
            {users.map((user) => (
              <Button
                key={user.username}
                variant="outline"
                className="justify-start"
                disabled={loggingInAs !== null}
                onClick={() => handleLogin(user.username)}
              >
                {loggingInAs === user.username ? "Logging in..." : `Log in as ${user.display_name}`}
              </Button>
            ))}
          </div>

          {!loadingUsers && users.length === 0 && !error && (
            <p className="text-sm text-muted-foreground">No seeded accounts found. Run the backend seed script.</p>
          )}

          <Link href="/faq" className="text-center text-xs text-primary hover:underline">
            Browse the knowledge base
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
