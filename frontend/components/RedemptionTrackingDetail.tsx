import { RedemptionTrackingData } from "@/lib/types";
import { MarkdownText } from "./MarkdownText";

interface Props {
  data: RedemptionTrackingData;
  message: string;
}

export function RedemptionTrackingDetail({ data, message }: Props) {
  const t = data.tracking;

  return (
    <div className="transaction-detail">
      <div className="transaction-detail-message">
        <MarkdownText text={message} />
        {t.stale && <div className="grounding-note">Showing last known status - may not be fully up to date</div>}
      </div>
      <details className="transaction-detail-toggle">
        <summary>View tracking history</summary>
        <dl className="transaction-detail-facts">
          <dt>Order</dt>
          <dd>{t.order_ref}</dd>
          <dt>Product</dt>
          <dd>{t.product_name}</dd>
          <dt>Status</dt>
          <dd>{t.status}</dd>
          {t.current_location && (
            <>
              <dt>Current location</dt>
              <dd>{t.current_location}</dd>
            </>
          )}
        </dl>
        {t.history.length > 0 && (
          <ul className="tracking-history">
            {t.history.map((ev, i) => (
              <li key={i}>
                <strong>{new Date(ev.event_time).toLocaleString()}</strong> — {ev.remarks} ({ev.area})
              </li>
            ))}
          </ul>
        )}
      </details>
    </div>
  );
}
