"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/admin", label: "Dashboard" },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/transactions", label: "Transactions" },
  { href: "/admin/redemptions", label: "Redemptions" },
  { href: "/admin/conversations", label: "Conversations" },
  { href: "/admin/costs", label: "Costs" },
  { href: "/admin/faq", label: "FAQ Articles" },
];

export function AdminSidebarContent() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-1 p-3.5">
      {LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className={cn(
            "rounded-md px-2.5 py-2 text-sm hover:bg-accent",
            (link.href === "/admin" ? pathname === link.href : pathname?.startsWith(link.href)) &&
              "bg-accent font-medium text-primary"
          )}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
