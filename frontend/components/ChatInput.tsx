"use client";

import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: Props) {
  const [value, setValue] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  return (
    <form className="flex shrink-0 gap-2 border-t bg-background p-3.5" onSubmit={handleSubmit}>
      <Input
        type="text"
        placeholder="Type a message..."
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={disabled}
        className="h-10 rounded-full px-4"
      />
      <Button type="submit" disabled={disabled || !value.trim()} className="h-10 rounded-full px-5">
        Send
      </Button>
    </form>
  );
}
