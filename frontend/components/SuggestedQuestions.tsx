interface Props {
  onSelect: (question: string) => void;
}

const SUGGESTIONS = [
  { label: "How do I sell my gold?", hint: "Product & policy help" },
  { label: "Show me my recent transactions", hint: "Buy / sell history" },
  { label: "Where is my latest order?", hint: "Track a delivery" },
  { label: "Why did my last transaction fail?", hint: "Explain one transaction" },
  { label: "List all my orders", hint: "Transactions + deliveries" },
  { label: "What KYC documents do I need?", hint: "Account & verification" },
];

export function SuggestedQuestions({ onSelect }: Props) {
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-3 px-4 py-6">
      <div className="text-center text-sm text-muted-foreground">
        Ask a support question, or try one of these:
      </div>
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s.label}
            onClick={() => onSelect(s.label)}
            className="flex flex-col gap-1 rounded-xl bg-card p-3 text-left text-sm text-card-foreground ring-1 ring-foreground/10 transition-colors hover:border-primary hover:shadow-sm"
          >
            <span className="font-medium">{s.label}</span>
            <span className="text-xs text-muted-foreground">{s.hint}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
