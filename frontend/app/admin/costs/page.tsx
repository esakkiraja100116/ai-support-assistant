"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { adminGetCosts } from "@/lib/api";
import { AdminCostSummary } from "@/lib/types";

export default function AdminCostsPage() {
  const { session } = useAuth();
  const [summary, setSummary] = useState<AdminCostSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    adminGetCosts(session.accessToken)
      .then(setSummary)
      .catch(() => setError("Could not load cost data."));
  }, [session]);

  if (error) return <div className="admin-page">{error}</div>;
  if (!summary) return <div className="admin-page muted">Loading...</div>;

  return (
    <div className="admin-page">
      <h1>Costs</h1>
      <p className="cost-total">${summary.total_cost_usd.toFixed(4)} total spent</p>

      <h2>By model</h2>
      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Model</th>
              <th>Cost (USD)</th>
              <th>Calls</th>
            </tr>
          </thead>
          <tbody>
            {summary.by_model.map((row) => (
              <tr key={row.model}>
                <td>{row.model}</td>
                <td>{row.cost_usd.toFixed(4)}</td>
                <td>{row.calls}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>By query category</h2>
      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Category</th>
              <th>Cost (USD)</th>
              <th>Turns</th>
            </tr>
          </thead>
          <tbody>
            {summary.by_category.map((row) => (
              <tr key={row.category}>
                <td>{row.category}</td>
                <td>{row.cost_usd.toFixed(4)}</td>
                <td>{row.turns}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Top conversations by cost</h2>
      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Conversation</th>
              <th>User</th>
              <th>Cost (USD)</th>
            </tr>
          </thead>
          <tbody>
            {summary.top_conversations.map((row) => (
              <tr key={row.conversation_id}>
                <td>
                  <Link href={`/admin/conversations/${row.conversation_id}`}>{row.title}</Link>
                </td>
                <td>{row.username}</td>
                <td>{row.cost_usd.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
