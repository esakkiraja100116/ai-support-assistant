import { RedemptionTrackingData } from "@/lib/types";
import { MarkdownText } from "./MarkdownText";

interface Props {
  data: RedemptionTrackingData;
  message: string;
}

export function RedemptionTrackingDetail({ data, message }: Props) {
  const t = data.tracking;

  return (
    <div className="max-w-[90%] rounded-xl bg-muted/50 p-3.5 ring-1 ring-foreground/10">
      <div className="mb-2.5 text-sm">
        <MarkdownText text={message} />
        {t.stale && (
          <div className="mt-1.5 text-xs text-muted-foreground">
            Showing last known status - may not be fully up to date
          </div>
        )}
      </div>
      <details className="group">
        <summary className="cursor-pointer text-xs text-primary select-none">View tracking history</summary>
        <dl className="mt-2.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-muted-foreground">Order</dt>
          <dd className="truncate font-medium">{t.order_ref}</dd>
          <dt className="text-muted-foreground">Product</dt>
          <dd className="font-medium">
            {t.product_name} ({t.quantity}g)
          </dd>
          <dt className="text-muted-foreground">Status</dt>
          <dd className="font-medium">{t.status}</dd>
          {t.current_location && (
            <>
              <dt className="text-muted-foreground">Current location</dt>
              <dd className="font-medium">{t.current_location}</dd>
            </>
          )}
        </dl>
        {t.history.length > 0 && (
          <ul className="mt-3 flex flex-col gap-1.5 text-sm text-foreground/80">
            {t.history.map((ev, i) => (
              <li key={i}>
                <strong className="font-semibold">{new Date(ev.event_time).toLocaleString()}</strong> — {ev.remarks}{" "}
                ({ev.area})
              </li>
            ))}
          </ul>
        )}
      </details>
    </div>
  );
}
