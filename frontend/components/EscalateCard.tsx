"use client";

import { useState } from "react";
import { MarkdownText } from "./MarkdownText";

interface Props {
  message: string;
}

export function EscalateCard({ message }: Props) {
  const [requested, setRequested] = useState(false);

  return (
    <div className="escalate-card">
      <div className="escalate-card-message">
        <MarkdownText text={message} />
      </div>
      {requested ? (
        <p className="escalate-card-confirmation">
          ✓ Request received — our support team will call you shortly.
        </p>
      ) : (
        <button className="escalate-card-button" onClick={() => setRequested(true)}>
          Talk to a human agent
        </button>
      )}
    </div>
  );
}
