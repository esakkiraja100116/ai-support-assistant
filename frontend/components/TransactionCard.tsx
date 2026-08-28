import { TransactionSummary } from "@/lib/types";

interface Props {
  transaction: TransactionSummary;
  onSelect: (id: string) => void;
  disabled?: boolean;
}

const STATUS_CLASS: Record<string, string> = {
  SUCCESS: "status-success",
  FAILED: "status-failed",
  PENDING: "status-pending",
  REFUNDED: "status-refunded",
};

export function TransactionCard({ transaction, onSelect, disabled }: Props) {
  const date = new Date(transaction.created_at).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <button
      className="transaction-card"
      onClick={() => onSelect(transaction.id)}
      disabled={disabled}
    >
      <div className="transaction-card-row">
        <span className="transaction-type">{transaction.type.replace("_", " ")}</span>
        <span className={`transaction-status ${STATUS_CLASS[transaction.status] || ""}`}>
          {transaction.status}
        </span>
      </div>
      <div className="transaction-card-row">
        <span>{transaction.product}</span>
        <span className="transaction-amount">₹{transaction.amount.toLocaleString()}</span>
      </div>
      <div className="transaction-date">{date}</div>
    </button>
  );
}
