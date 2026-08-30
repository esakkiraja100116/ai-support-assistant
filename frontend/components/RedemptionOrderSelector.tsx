import { RedemptionSelectionData } from "@/lib/types";
import { EmptyState } from "./EmptyState";
import { RedemptionOrderCard } from "./RedemptionOrderCard";

interface Props {
  data: RedemptionSelectionData;
  onSelect: (orderRef: string) => void;
  disabled?: boolean;
}

export function RedemptionOrderSelector({ data, onSelect, disabled }: Props) {
  if (data.orders.length === 0) {
    return <EmptyState message="No ongoing redemption orders found." />;
  }

  return (
    <div className="grid w-full grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
      {data.orders.map((order) => (
        <RedemptionOrderCard key={order.order_ref} order={order} onSelect={onSelect} disabled={disabled} />
      ))}
    </div>
  );
}
