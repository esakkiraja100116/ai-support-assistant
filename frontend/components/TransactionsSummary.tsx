import { TransactionDetail, TransactionsSummaryData } from "@/lib/types";
import { MarkdownText } from "./MarkdownText";

interface Props {
  data: TransactionsSummaryData;
  message: string;
}

function Facts({ txn }: { txn: TransactionDetail }) {
  const date = new Date(txn.created_at).toLocaleString();
  return (
    <dl className="transaction-detail-facts">
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
  );
}

export function TransactionsSummary({ data, message }: Props) {
  return (
    <div className="transaction-detail">
      <div className="transaction-detail-message">
        <MarkdownText text={message} />
      </div>
      <details className="transaction-detail-toggle">
        <summary>View {data.transactions.length} transaction{data.transactions.length === 1 ? "" : "s"}</summary>
        {data.transactions.map((txn) => (
          <div key={txn.id} className="transactions-summary-item">
            <div className="transactions-summary-item-id">{txn.id}</div>
            <Facts txn={txn} />
          </div>
        ))}
      </details>
    </div>
  );
}
