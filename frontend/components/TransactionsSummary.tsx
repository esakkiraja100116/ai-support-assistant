import { TransactionDetail, TransactionsSummaryData } from "@/lib/types";
import { MarkdownText } from "./MarkdownText";

interface Props {
  data: TransactionsSummaryData;
  message: string;
}

function Facts({ txn }: { txn: TransactionDetail }) {
  const date = new Date(txn.created_at).toLocaleString();
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
      <dt className="text-muted-foreground">Type</dt>
      <dd className="font-medium">{txn.type.replace("_", " ")}</dd>
      <dt className="text-muted-foreground">Product</dt>
      <dd className="font-medium">{txn.product}</dd>
      <dt className="text-muted-foreground">Amount</dt>
      <dd className="font-medium">₹{txn.amount.toLocaleString()}</dd>
      <dt className="text-muted-foreground">Status</dt>
      <dd className="font-medium">{txn.status}</dd>
      {txn.failure_reason && (
        <>
          <dt className="text-muted-foreground">Reason</dt>
          <dd className="font-medium">{txn.failure_reason}</dd>
        </>
      )}
      <dt className="text-muted-foreground">Payment method</dt>
      <dd className="font-medium">{txn.payment_method}</dd>
      <dt className="text-muted-foreground">Date</dt>
      <dd className="font-medium">{date}</dd>
    </dl>
  );
}

export function TransactionsSummary({ data, message }: Props) {
  return (
    <div className="max-w-[90%] rounded-xl bg-muted/50 p-3.5 ring-1 ring-foreground/10">
      <div className="mb-2.5 text-sm">
        <MarkdownText text={message} />
      </div>
      <details className="group">
        <summary className="cursor-pointer text-xs text-primary select-none">
          View {data.transactions.length} transaction{data.transactions.length === 1 ? "" : "s"}
        </summary>
        {data.transactions.map((txn, i) => (
          <div key={txn.id} className={`pt-2.5 mt-2.5 ${i > 0 ? "border-t" : ""}`}>
            <div className="mb-1 text-xs font-semibold text-muted-foreground">{txn.id}</div>
            <Facts txn={txn} />
          </div>
        ))}
      </details>
    </div>
  );
}
