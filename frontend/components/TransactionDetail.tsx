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
    <div className="transaction-detail">
      <div className="transaction-detail-message">
        <MarkdownText text={message} />
      </div>
      <details className="transaction-detail-toggle">
        <summary>View transaction details</summary>
        <dl className="transaction-detail-facts">
          <dt>Transaction</dt>
          <dd>{txn.id}</dd>
          <dt>Type</dt>
          <dd>{txn.type.replace("_", " ")}</dd>
          <dt>Product</dt>
          <dd>{txn.product}</dd>
          <dt>Amount</dt>
          <dd>₹{txn.amount.toLocaleString()}</dd>
          <dt>Status</dt>
          <dd>{txn.status}</dd>
          {txn.failure_reason && (
            <>
              <dt>Reason</dt>
              <dd>{txn.failure_reason}</dd>
            </>
          )}
          <dt>Payment method</dt>
          <dd>{txn.payment_method}</dd>
          <dt>Date</dt>
          <dd>{date}</dd>
        </dl>
      </details>
    </div>
  );
}
