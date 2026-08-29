"use client";

import { useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";
import { AdminSidebarContent } from "@/components/admin/AdminSidebarContent";
import { DashboardShell } from "@/components/shell/DashboardShell";
import { useAuth } from "@/hooks/useAuth";

export default function AdminLayout({ children }: { children: ReactNode }) {
  const { session, ready, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!ready) return;
    if (!session || session.role !== "ADMINISTRATOR") {
      router.replace("/");
    }
  }, [ready, session, router]);

  if (!ready || !session || session.role !== "ADMINISTRATOR") {
    return <div className="page-loading">Loading...</div>;
  }

  return (
    <DashboardShell session={session} onLogout={logout} sidebarContent={<AdminSidebarContent />}>
      {children}
    </DashboardShell>
  );
}
