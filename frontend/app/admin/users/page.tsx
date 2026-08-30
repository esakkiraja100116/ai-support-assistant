"use client";

import { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { DataTable } from "@/components/ui/data-table";
import { useAuth } from "@/hooks/useAuth";
import { adminListUsers } from "@/lib/api";
import { AdminUser } from "@/lib/types";

const columns: ColumnDef<AdminUser>[] = [
  { accessorKey: "username", header: "Username" },
  { accessorKey: "display_name", header: "Display name" },
  {
    accessorKey: "role",
    header: "Role",
    cell: ({ row }) => (
      <Badge variant={row.original.role === "ADMINISTRATOR" ? "default" : "outline"}>
        {row.original.role}
      </Badge>
    ),
  },
  { accessorKey: "transaction_count", header: "Transactions" },
  { accessorKey: "redemption_order_count", header: "Redemptions" },
  { accessorKey: "conversation_count", header: "Conversations" },
];

export default function AdminUsersPage() {
  const { session } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    adminListUsers(session.accessToken)
      .then(setUsers)
      .catch(() => setError("Could not load users."))
      .finally(() => setLoading(false));
  }, [session]);

  const data = useMemo(() => users, [users]);

  return (
    <div className="flex h-full flex-col px-5 pt-6 pb-6">
      <h1 className="mb-5 shrink-0 text-2xl font-semibold tracking-tight">Users</h1>
      {loading && <p className="text-sm text-muted-foreground">Loading...</p>}
      {error && <p className="text-sm text-muted-foreground">{error}</p>}
      {!loading && !error && (
        <DataTable columns={columns} data={data} searchPlaceholder="Search users..." emptyMessage="No users found." />
      )}
    </div>
  );
}
