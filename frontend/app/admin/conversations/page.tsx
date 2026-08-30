"use client";

import { ColumnDef } from "@tanstack/react-table";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { DataTable } from "@/components/ui/data-table";
import { useAuth } from "@/hooks/useAuth";
import { adminListConversations } from "@/lib/api";
import { ConversationWithUser } from "@/lib/types";

const columns: ColumnDef<ConversationWithUser>[] = [
  {
    accessorKey: "title",
    header: "Title",
    cell: ({ row }) => (
      <Link href={`/admin/conversations/${row.original.id}`} className="text-primary hover:underline">
        {row.original.title}
      </Link>
    ),
  },
  { accessorKey: "display_name", header: "User" },
  { accessorKey: "message_count", header: "Messages" },
  {
    accessorKey: "models_used",
    header: "Model(s) used",
    cell: ({ row }) => row.original.models_used || "-",
  },
  {
    accessorKey: "total_cost_usd",
    header: "Cost (USD)",
    cell: ({ row }) => row.original.total_cost_usd.toFixed(4),
  },
  {
    accessorKey: "updated_at",
    header: "Updated",
    cell: ({ row }) => new Date(row.original.updated_at).toLocaleString(),
  },
];

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

  const data = useMemo(() => conversations, [conversations]);

  return (
    <div className="flex h-full flex-col px-5 pt-6 pb-6">
      <h1 className="mb-5 shrink-0 text-2xl font-semibold tracking-tight">Conversations</h1>
      {loading && <p className="text-sm text-muted-foreground">Loading...</p>}
      {error && <p className="text-sm text-muted-foreground">{error}</p>}
      {!loading && !error && (
        <DataTable
          columns={columns}
          data={data}
          searchPlaceholder="Search conversations..."
          emptyMessage="No conversations found."
        />
      )}
    </div>
  );
}
