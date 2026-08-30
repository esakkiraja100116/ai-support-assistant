"use client";

import { Menu } from "lucide-react";
import { ReactNode, useState } from "react";
import { Button } from "@/components/ui/button";
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
    <div className="flex h-screen flex-col">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b bg-background px-4">
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          aria-label="Toggle menu"
          onClick={() => setSidebarOpen((v) => !v)}
        >
          <Menu className="size-5" />
        </Button>
        <span className="flex-1 text-sm font-semibold">Support Assistant</span>
        <ProfileMenu session={session} onLogout={onLogout} />
      </header>
      <div className="flex min-h-0 flex-1">
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)}>
          {sidebarContent}
        </Sidebar>
        <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
