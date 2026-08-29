"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { adminListConversations } from "@/lib/api";
import { ConversationWithUser } from "@/lib/types";

export default function AdminConversationsPage() {
  const { session } = useAuth();
  const [conversations, setConversations] = useState<ConversationWithUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    adminListConversations(session.accessToken)
      .then(setConversations)
      .catch(() => setError("Could not load conversations."))
      .finally(() => setLoading(false));
  }, [session]);

  return (
    <div className="admin-page">
      <h1>Conversations</h1>
      {loading && <p className="muted">Loading...</p>}
      {error && <p className="muted">{error}</p>}
      {!loading && !error && (
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>User</th>
                <th>Messages</th>
                <th>Model(s) used</th>
                <th>Cost (USD)</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {conversations.map((c) => (
                <tr key={c.id}>
                  <td>
                    <Link href={`/admin/conversations/${c.id}`}>{c.title}</Link>
                  </td>
                  <td>{c.display_name}</td>
                  <td>{c.message_count}</td>
                  <td>{c.models_used || "-"}</td>
                  <td>{c.total_cost_usd.toFixed(4)}</td>
                  <td>{new Date(c.updated_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
