"use client";

import { ArrowLeftRight, DollarSign, FileText, Gift, MessageSquare, Users, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { useAuth } from "@/hooks/useAuth";
import {
  adminGetCosts,
  adminListConversations,
  adminListRedemptionOrders,
  adminListTransactions,
  adminListUsers,
  listFaqArticles,
} from "@/lib/api";

interface DashboardCard {
  label: string;
  value: string;
  href: string;
  icon: LucideIcon;
}

export default function AdminHome() {
  const { session } = useAuth();
  const [cards, setCards] = useState<DashboardCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    Promise.all([
      adminListUsers(session.accessToken),
      adminListTransactions(session.accessToken),
      adminListRedemptionOrders(session.accessToken),
      adminListConversations(session.accessToken),
      adminGetCosts(session.accessToken),
      listFaqArticles(),
    ])
      .then(([users, transactions, redemptions, conversations, costs, faq]) => {
        setCards([
          { label: "Total cost", value: `$${costs.total_cost_usd.toFixed(4)}`, href: "/admin/costs", icon: DollarSign },
          { label: "Users", value: String(users.length), href: "/admin/users", icon: Users },
          { label: "Transactions", value: String(transactions.length), href: "/admin/transactions", icon: ArrowLeftRight },
          { label: "Redemptions", value: String(redemptions.length), href: "/admin/redemptions", icon: Gift },
          { label: "Conversations", value: String(conversations.length), href: "/admin/conversations", icon: MessageSquare },
          { label: "FAQ articles", value: String(faq.length), href: "/admin/faq", icon: FileText },
        ]);
      })
      .catch(() => setError("Could not load dashboard data."));
  }, [session]);

  return (
    <div className="px-5 pt-6 pb-16">
      <h1 className="mb-5 text-2xl font-semibold tracking-tight">Dashboard</h1>
      {error && <p className="text-sm text-muted-foreground">{error}</p>}
      {!error && !cards && <p className="text-sm text-muted-foreground">Loading...</p>}
      {cards && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {cards.map((card) => (
            <Link key={card.href} href={card.href} className="block">
              <Card className="transition-shadow hover:shadow-md hover:ring-primary/30">
                <CardContent className="flex items-center gap-4">
                  <div className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <card.icon className="size-5" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">{card.label}</p>
                    <p className="text-2xl font-semibold tracking-tight">{card.value}</p>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
