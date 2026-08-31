import { RedemptionOrderSummary } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { statusBadgeClass } from "@/lib/statusStyles";

interface Props {
  order: RedemptionOrderSummary;
  onSelect: (orderRef: string) => void;
  disabled?: boolean;
}

export function RedemptionOrderCard({ order, onSelect, disabled }: Props) {
  const date = new Date(order.created_at).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <button
      onClick={() => onSelect(order.order_ref)}
      disabled={disabled}
      className="flex flex-col gap-2 rounded-xl bg-card p-3 text-left text-sm text-card-foreground ring-1 ring-foreground/10 transition-colors hover:border-primary hover:shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
    >
      <div className="flex items-center justify-between">
        <span className="font-semibold">REDEMPTION</span>
        <Badge className={statusBadgeClass(order.status)}>{order.status}</Badge>
      </div>
      <div className="flex items-center justify-between">
        <span className="capitalize">
          {order.product_name} ({order.product_type})
        </span>
        <span className="font-semibold">{order.quantity}g</span>
      </div>
      <div className="text-muted-foreground">{date}</div>
    </button>
  );
}
