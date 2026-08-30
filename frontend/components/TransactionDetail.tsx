import { TransactionExplanationData } from "@/lib/types";
import { MarkdownText } from "./MarkdownText";

interface Props {
  data: TransactionExplanationData;
  message: string;
}

export function TransactionDetail({ data, message }: Props) {
  const txn = data.transaction;
  const date = new Date(txn.created_at).toLocaleString();

  return (
    <div className="max-w-[90%] rounded-xl bg-muted/50 p-3.5 ring-1 ring-foreground/10">
      <div className="mb-2.5 text-sm">
        <MarkdownText text={message} />
      </div>
      <details className="group">
        <summary className="cursor-pointer text-xs text-primary select-none">View transaction details</summary>
        <dl className="mt-2.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-muted-foreground">Transaction</dt>
          <dd className="font-medium">{txn.id}</dd>
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
      </details>
    </div>
  );
}
