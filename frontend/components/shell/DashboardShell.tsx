"use client";

import { ReactNode, useState } from "react";
import { AuthSession } from "@/lib/types";
import { ProfileMenu } from "./ProfileMenu";
import { Sidebar } from "./Sidebar";

interface Props {
  session: AuthSession;
  onLogout: () => void;
  sidebarContent: ReactNode;
  children: ReactNode;
}

export function DashboardShell({ session, onLogout, sidebarContent, children }: Props) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="dashboard-shell">
      <header className="dashboard-navbar">
        <button
          className="sidebar-toggle"
          aria-label="Toggle menu"
          onClick={() => setSidebarOpen((v) => !v)}
        >
          <span />
          <span />
          <span />
        </button>
        <span className="dashboard-navbar-title">Support Assistant</span>
        <ProfileMenu session={session} onLogout={onLogout} />
      </header>
      <div className="dashboard-body">
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)}>
          {sidebarContent}
        </Sidebar>
        <main className="dashboard-main">{children}</main>
      </div>
    </div>
  );
}
