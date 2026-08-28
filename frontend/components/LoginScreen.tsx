"use client";

import { useEffect, useState } from "react";
import { listUsers } from "@/lib/api";
import { SeededUser } from "@/lib/types";

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
    <div className="login-screen">
      <div className="login-card">
        <h1>Support Assistant</h1>
        <p className="subtitle">Choose an account to continue</p>

        {loadingUsers && <p className="muted">Loading accounts...</p>}
        {error && (
          <div className="error-banner">
            <span>{error}</span>
            <button onClick={() => window.location.reload()}>Retry</button>
          </div>
        )}

        <div className="user-list">
          {users.map((user) => (
            <button
              key={user.username}
              className="user-button"
              disabled={loggingInAs !== null}
              onClick={() => handleLogin(user.username)}
            >
              {loggingInAs === user.username ? "Logging in..." : `Log in as ${user.display_name}`}
            </button>
          ))}
        </div>

        {!loadingUsers && users.length === 0 && !error && (
          <p className="muted">No seeded accounts found. Run the backend seed script.</p>
        )}
      </div>
    </div>
  );
}
