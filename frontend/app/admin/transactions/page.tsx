"use client";

import { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { DataTable } from "@/components/ui/data-table";
import { useAuth } from "@/hooks/useAuth";
import { adminListTransactions } from "@/lib/api";
import { statusBadgeClass } from "@/lib/statusStyles";
import { AdminTransaction } from "@/lib/types";

const columns: ColumnDef<AdminTransaction>[] = [
  { accessorKey: "id", header: "ID" },
  { accessorKey: "display_name", header: "User" },
  { accessorKey: "type", header: "Type" },
  { accessorKey: "product", header: "Product" },
  { accessorKey: "amount", header: "Amount" },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <Badge className={statusBadgeClass(row.original.status)}>{row.original.status}</Badge>
    ),
  },
  { accessorKey: "payment_method", header: "Payment method" },
  {
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => new Date(row.original.created_at).toLocaleString(),
  },
];

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

  const data = useMemo(() => transactions, [transactions]);

  return (
    <div className="flex h-full flex-col px-5 pt-6 pb-6">
      <h1 className="mb-5 shrink-0 text-2xl font-semibold tracking-tight">Transactions</h1>
      {loading && <p className="text-sm text-muted-foreground">Loading...</p>}
      {error && <p className="text-sm text-muted-foreground">{error}</p>}
      {!loading && !error && (
        <DataTable
          columns={columns}
          data={data}
          searchPlaceholder="Search transactions..."
          emptyMessage="No transactions found."
        />
      )}
    </div>
  );
}
