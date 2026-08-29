"use client";

import { ReactNode } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

export function Sidebar({ open, onClose, children }: Props) {
  return (
    <>
      {open && <div className="dashboard-sidebar-backdrop" onClick={onClose} />}
      <aside className={`dashboard-sidebar${open ? " open" : ""}`}>{children}</aside>
    </>
  );
}
