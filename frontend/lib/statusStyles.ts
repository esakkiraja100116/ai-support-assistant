// Shared status -> Tailwind color mapping for both transaction and
// redemption-order status pills, matching the original hand-written CSS's
// palette (which already lined up with Tailwind's default color scale).
const SUCCESS = new Set(["SUCCESS", "DELIVERED"]);
const FAILURE = new Set(["FAILED", "ATTEMPTED", "REJECTED", "CANCELLED"]);
const REFUNDED = new Set(["REFUNDED"]);
// Everything else (PENDING, PROCESSING, ORDER_CONFIRMED, PACKED, SHIPPED,
// IN_TRANSIT, OUT_FOR_DELIVERY, ...) falls through to the "in progress" style.

export function statusBadgeClass(status: string): string {
  if (SUCCESS.has(status)) return "bg-green-100 text-green-700 hover:bg-green-100";
  if (FAILURE.has(status)) return "bg-red-100 text-red-700 hover:bg-red-100";
  if (REFUNDED.has(status)) return "bg-indigo-100 text-indigo-700 hover:bg-indigo-100";
  return "bg-yellow-100 text-yellow-800 hover:bg-yellow-100";
}
