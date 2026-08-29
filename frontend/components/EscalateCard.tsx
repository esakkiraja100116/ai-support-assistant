"use client";

import { useState } from "react";

interface Props {
  message: string;
}

export function EscalateCard({ message }: Props) {
  const [requested, setRequested] = useState(false);

  return (
    <div className="escalate-card">
      <p className="escalate-card-message">{message}</p>
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
