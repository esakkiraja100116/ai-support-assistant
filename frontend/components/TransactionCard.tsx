import { TransactionSummary } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { statusBadgeClass } from "@/lib/statusStyles";

interface Props {
  transaction: TransactionSummary;
  onSelect: (id: string) => void;
  disabled?: boolean;
}

export function TransactionCard({ transaction, onSelect, disabled }: Props) {
  const date = new Date(transaction.created_at).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <button
      onClick={() => onSelect(transaction.id)}
      disabled={disabled}
      className="flex flex-col gap-2 rounded-xl bg-card p-3 text-left text-sm text-card-foreground ring-1 ring-foreground/10 transition-colors hover:border-primary hover:shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
    >
      <div className="flex items-center justify-between">
        <span className="font-semibold">{transaction.type.replace("_", " ")}</span>
        <Badge className={statusBadgeClass(transaction.status)}>{transaction.status}</Badge>
      </div>
      <div className="flex items-center justify-between">
        <span>{transaction.product}</span>
        <span className="font-semibold">₹{transaction.amount.toLocaleString()}</span>
      </div>
      <div className="text-muted-foreground">{date}</div>
    </button>
  );
}
