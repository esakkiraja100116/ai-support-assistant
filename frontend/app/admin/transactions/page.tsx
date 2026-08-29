"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { adminListTransactions } from "@/lib/api";
import { AdminTransaction } from "@/lib/types";

export default function AdminTransactionsPage() {
  const { session } = useAuth();
  const [transactions, setTransactions] = useState<AdminTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    adminListTransactions(session.accessToken)
      .then(setTransactions)
      .catch(() => setError("Could not load transactions."))
      .finally(() => setLoading(false));
  }, [session]);

  return (
    <div className="admin-page">
      <h1>Transactions</h1>
      {loading && <p className="muted">Loading...</p>}
      {error && <p className="muted">{error}</p>}
      {!loading && !error && (
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>User</th>
                <th>Type</th>
                <th>Product</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Payment method</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((t) => (
                <tr key={t.id}>
                  <td>{t.id}</td>
                  <td>{t.display_name}</td>
                  <td>{t.type}</td>
                  <td>{t.product}</td>
                  <td>{t.amount}</td>
                  <td>{t.status}</td>
                  <td>{t.payment_method}</td>
                  <td>{new Date(t.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
