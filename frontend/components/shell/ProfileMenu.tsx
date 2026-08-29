"use client";

import { useState } from "react";
import { AuthSession } from "@/lib/types";

interface Props {
  session: AuthSession;
  onLogout: () => void;
}

export function ProfileMenu({ session, onLogout }: Props) {
  const [open, setOpen] = useState(false);
  const initial = session.displayName.trim().charAt(0).toUpperCase() || "?";

  return (
    <div className="profile-menu">
      <button className="profile-menu-avatar" onClick={() => setOpen((v) => !v)} aria-label="Account menu">
        {initial}
      </button>
      {open && (
        <>
          <div className="profile-menu-backdrop" onClick={() => setOpen(false)} />
          <div className="profile-menu-dropdown">
            <div className="profile-menu-name">{session.displayName}</div>
            <div className="profile-menu-role">
              {session.role === "ADMINISTRATOR" ? "Administrator" : "Customer"}
            </div>
            <button className="text-button" onClick={onLogout}>
              Log out
            </button>
          </div>
        </>
      )}
    </div>
  );
}
