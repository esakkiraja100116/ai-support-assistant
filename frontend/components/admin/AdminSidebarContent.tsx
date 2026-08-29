"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/admin/users", label: "Users" },
  { href: "/admin/transactions", label: "Transactions" },
  { href: "/admin/conversations", label: "Conversations" },
  { href: "/admin/costs", label: "Costs" },
  { href: "/admin/faq/new", label: "Add FAQ Article" },
];

export function AdminSidebarContent() {
  const pathname = usePathname();

  return (
    <div className="sidebar-content">
      <nav className="admin-nav">
        {LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`admin-nav-link${pathname?.startsWith(link.href) ? " active" : ""}`}
          >
            {link.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
