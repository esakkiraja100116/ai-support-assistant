"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
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

  if (error) return <div className="mx-auto max-w-4xl px-5 pt-6 pb-16 text-sm text-muted-foreground">{error}</div>;
  if (!summary)
    return <div className="mx-auto max-w-4xl px-5 pt-6 pb-16 text-sm text-muted-foreground">Loading...</div>;

  return (
    <div className="mx-auto max-w-4xl px-5 pt-6 pb-16">
      <h1 className="mb-1.5 text-2xl font-semibold tracking-tight">Costs</h1>
      <p className="mb-6 text-2xl font-bold">${summary.total_cost_usd.toFixed(4)} total spent</p>

      <h2 className="mb-2.5 text-base font-semibold">By model</h2>
      <Card className="mb-6 overflow-x-auto py-0">
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Model</TableHead>
                <TableHead>Cost (USD)</TableHead>
                <TableHead>Calls</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {summary.by_model.map((row) => (
                <TableRow key={row.model}>
                  <TableCell>{row.model}</TableCell>
                  <TableCell>{row.cost_usd.toFixed(4)}</TableCell>
                  <TableCell>{row.calls}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <h2 className="mb-2.5 text-base font-semibold">By query category</h2>
      <Card className="mb-6 overflow-x-auto py-0">
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Category</TableHead>
                <TableHead>Cost (USD)</TableHead>
                <TableHead>Turns</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {summary.by_category.map((row) => (
                <TableRow key={row.category}>
                  <TableCell>{row.category}</TableCell>
                  <TableCell>{row.cost_usd.toFixed(4)}</TableCell>
                  <TableCell>{row.turns}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <h2 className="mb-2.5 text-base font-semibold">Top conversations by cost</h2>
      <Card className="overflow-x-auto py-0">
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Conversation</TableHead>
                <TableHead>User</TableHead>
                <TableHead>Cost (USD)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {summary.top_conversations.map((row) => (
                <TableRow key={row.conversation_id}>
                  <TableCell>
                    <Link href={`/admin/conversations/${row.conversation_id}`} className="text-primary hover:underline">
                      {row.title}
                    </Link>
                  </TableCell>
                  <TableCell>{row.username}</TableCell>
                  <TableCell>{row.cost_usd.toFixed(4)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
