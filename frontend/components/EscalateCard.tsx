"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { MarkdownText } from "./MarkdownText";

interface Props {
  message: string;
}

export function EscalateCard({ message }: Props) {
  const [requested, setRequested] = useState(false);

  return (
    <Card className="max-w-[90%] border-amber-200 bg-amber-50/60 py-4">
      <CardContent className="flex flex-col gap-2.5">
        <MarkdownText text={message} />
        {requested ? (
          <p className="text-sm font-semibold text-green-700">
            ✓ Request received — our support team will call you shortly.
          </p>
        ) : (
          <Button
            className="w-fit rounded-full bg-amber-500 text-white hover:bg-amber-600"
            onClick={() => setRequested(true)}
          >
            Talk to a human agent
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
