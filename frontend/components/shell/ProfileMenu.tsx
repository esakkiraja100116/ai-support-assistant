"use client";

import { useState } from "react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AuthSession } from "@/lib/types";

interface Props {
  session: AuthSession;
  onLogout: () => void;
}

export function ProfileMenu({ session, onLogout }: Props) {
  const [open, setOpen] = useState(false);
  const initial = session.displayName.trim().charAt(0).toUpperCase() || "?";

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        aria-label="Account menu"
        className="rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
      >
        <Avatar>
          <AvatarFallback className="bg-primary text-primary-foreground font-semibold">{initial}</AvatarFallback>
        </Avatar>
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader className="items-center text-center">
            <Avatar className="mb-2 size-16">
              <AvatarFallback className="bg-primary text-primary-foreground text-2xl font-semibold">
                {initial}
              </AvatarFallback>
            </Avatar>
            <DialogTitle className="text-lg">{session.displayName}</DialogTitle>
            <DialogDescription>
              @{session.username} - {session.role === "ADMINISTRATOR" ? "Administrator" : "Customer"}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="sm:justify-center">
            <Button
              variant="outline"
              className="border-destructive/40 text-destructive hover:bg-destructive/10"
              onClick={() => {
                setOpen(false);
                onLogout();
              }}
            >
              Log out
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
