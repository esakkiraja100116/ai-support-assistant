"use client";

import { ReactNode } from "react";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";

interface Props {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

export function Sidebar({ open, onClose, children }: Props) {
  return (
    <>
      {/* Desktop: always-visible static sidebar. */}
      <aside className="hidden md:flex md:w-64 md:shrink-0 md:flex-col md:border-r md:bg-muted/30">
        {children}
      </aside>

      {/* Mobile: off-canvas drawer, built on shadcn's Sheet (Radix/base-ui
          Dialog) instead of the old hand-rolled transform/backdrop CSS -
          gets a focus trap and escape-to-close for free. */}
      <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
        <SheetContent side="left" className="w-72 p-0 md:hidden">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <div className="flex h-full flex-col" onClick={onClose}>
            {children}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
