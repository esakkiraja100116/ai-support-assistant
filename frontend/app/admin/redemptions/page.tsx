"use client";

import { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { DataTable } from "@/components/ui/data-table";
import { useAuth } from "@/hooks/useAuth";
import { adminListRedemptionOrders } from "@/lib/api";
import { statusBadgeClass } from "@/lib/statusStyles";
import { AdminRedemptionOrder } from "@/lib/types";

const columns: ColumnDef<AdminRedemptionOrder>[] = [
  { accessorKey: "order_ref", header: "Order ref" },
  { accessorKey: "display_name", header: "User" },
  { accessorKey: "product_name", header: "Product" },
  { accessorKey: "product_type", header: "Type" },
  {
    accessorKey: "quantity",
    header: "Quantity",
    cell: ({ row }) => `${row.original.quantity}g`,
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <Badge className={statusBadgeClass(row.original.status)}>{row.original.status}</Badge>
    ),
  },
  {
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => new Date(row.original.created_at).toLocaleString(),
  },
];

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

  const data = useMemo(() => orders, [orders]);

  return (
    <div className="flex h-full flex-col px-5 pt-6 pb-6">
      <h1 className="mb-5 shrink-0 text-2xl font-semibold tracking-tight">Redemption Orders</h1>
      {loading && <p className="text-sm text-muted-foreground">Loading...</p>}
      {error && <p className="text-sm text-muted-foreground">{error}</p>}
      {!loading && !error && (
        <DataTable
          columns={columns}
          data={data}
          searchPlaceholder="Search redemption orders..."
          emptyMessage="No redemption orders found."
        />
      )}
    </div>
  );
}
