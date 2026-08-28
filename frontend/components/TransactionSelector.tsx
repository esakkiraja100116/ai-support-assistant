import { TransactionSelectionData } from "@/lib/types";
import { EmptyState } from "./EmptyState";
import { TransactionCard } from "./TransactionCard";

interface Props {
  data: TransactionSelectionData;
  onSelect: (id: string) => void;
  disabled?: boolean;
}

export function TransactionSelector({ data, onSelect, disabled }: Props) {
  if (data.transactions.length === 0) {
    return <EmptyState message="No recent transactions found." />;
  }

  return (
    <div className="transaction-grid">
      {data.transactions.map((txn) => (
        <TransactionCard key={txn.id} transaction={txn} onSelect={onSelect} disabled={disabled} />
      ))}
    </div>
  );
}
