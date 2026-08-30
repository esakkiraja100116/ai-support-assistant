import { RedemptionOrderSummary } from "@/lib/types";

interface Props {
  order: RedemptionOrderSummary;
  onSelect: (orderRef: string) => void;
  disabled?: boolean;
}

const STATUS_CLASS: Record<string, string> = {
  PROCESSING: "status-pending",
  ORDER_CONFIRMED: "status-pending",
  PACKED: "status-pending",
  SHIPPED: "status-pending",
  IN_TRANSIT: "status-pending",
  OUT_FOR_DELIVERY: "status-pending",
  ATTEMPTED: "status-failed",
};

export function RedemptionOrderCard({ order, onSelect, disabled }: Props) {
  const date = new Date(order.created_at).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <button className="transaction-card" onClick={() => onSelect(order.order_ref)} disabled={disabled}>
      <div className="transaction-card-row">
        <span className="transaction-type">{order.product_type}</span>
        <span className={`transaction-status ${STATUS_CLASS[order.status] || ""}`}>{order.status}</span>
      </div>
      <div className="transaction-card-row">
        <span>{order.product_name}</span>
        <span className="transaction-amount">{order.quantity}g</span>
      </div>
      <div className="transaction-date">{date}</div>
    </button>
  );
}
