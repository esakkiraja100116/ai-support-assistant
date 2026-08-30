"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { adminListRedemptionOrders } from "@/lib/api";
import { AdminRedemptionOrder } from "@/lib/types";

export default function AdminRedemptionsPage() {
  const { session } = useAuth();
  const [orders, setOrders] = useState<AdminRedemptionOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    adminListRedemptionOrders(session.accessToken)
      .then(setOrders)
      .catch(() => setError("Could not load redemption orders."))
      .finally(() => setLoading(false));
  }, [session]);

  return (
    <div className="admin-page">
      <h1>Redemption Orders</h1>
      {loading && <p className="muted">Loading...</p>}
      {error && <p className="muted">{error}</p>}
      {!loading && !error && (
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Order ref</th>
                <th>User</th>
                <th>Product</th>
                <th>Type</th>
                <th>Quantity</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.order_ref}>
                  <td>{o.order_ref}</td>
                  <td>{o.display_name}</td>
                  <td>{o.product_name}</td>
                  <td>{o.product_type}</td>
                  <td>{o.quantity}g</td>
                  <td>{o.status}</td>
                  <td>{new Date(o.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
