# Redemption Tracking — Production Regression Checklist (T1–T12)

Verification script for the 12-row "Minimum Test Matrix" (§14 of the redemption-tracking engineering spec) against the **deployed production chat UI**, after the `get_orders`/redemption-merge refactor. Each row lists the demo user to log in as, the exact message(s) to type, the expected reply, and whether the row is actually observable from the chat UI or needs backend-level verification instead — say so plainly rather than pretending a UI click proves something it can't.

Demo users (seed data, password matches username unless your login flow differs): `alice`, `bob`, `carol`, `dave`, `erin`, `frank`. Do not create real orders to run this — the fixtures below already cover every row.

Run top to bottom in a fresh conversation per row unless a row says "same conversation, next turn."

---

## T1 — No redemptions at all

**User:** `bob`
**Type:** `Where is my order?`
**Expect:** *"You don't have any ongoing redemption orders right now."* No order cards, no tracking API call (bob has zero redemption rows — nothing to accidentally show).

## T2 — Delivered orders only

**User:** `carol`
**Type:** `Where is my order?`
**Expect:** Same "no ongoing redemption orders" reply. Carol's only redemption is `DELIVERED` — must not appear as trackable.

## T3 — Failed/cancelled orders only

**User:** `dave`
**Type:** `Where is my order?`
**Expect:** Same "no ongoing redemption orders" reply. Dave's only redemption is `CANCELLED`.

## T4 — Exactly one ongoing order (auto-select)

**User:** `erin`
**Type:** `Where is my order?`
**Expect:** No selection step — goes straight to a tracking answer for her single `IN_TRANSIT` Gold Bar (AWB `PRO19460780`), current location Pune, no "which order?" prompt.

**Follow-up (same conversation):** `what happened before that?`
**Expect:** Answers from the same tracking history without re-asking which order.

## T5 — Multiple ongoing, ambiguous by product (scoped selector)

**User:** `alice`
**Type:** `Track my gold coin`
**Expect:** A selection prompt listing **exactly 2 orders** — both Gold Coin (one `IN_TRANSIT`, one `ATTEMPTED`). Her Gold Bar orders must NOT appear in this list — the selector is scoped to what was actually asked about, not a dump of all 4 ongoing orders.

**Follow-up:** pick the `IN_TRANSIT` one
**Expect:** Tracking detail for that specific coin order only.

## T6 — Ongoing order with no AWB yet (PROCESSING)

**User:** `alice`
**Type:** `Track my order` → pick **"the one that's still processing"** from the resulting list
**Expect:** *"Your Gold Bar (10.0g) is still being processed and doesn't have tracking information yet."* — or equivalent wording. No AWB shown, and this must not trigger a tracking-API-backed answer (nothing to look up yet).

## T7 — Mixed states on one account (ongoing + delivered + failed)

**User:** `frank`
**Type:** `Where is my order?`
**Expect:** Auto-selects the single ongoing order (Gold Coin, `IN_TRANSIT`, AWB `PRO19460783`) and reports it — his `DELIVERED` and `REJECTED` redemptions must not appear as options or get mixed into the answer.

## T8 — Selected order not owned by the user

**Not directly typeable in the production chat UI.** The chat tool schema never accepts a raw order ID from user text or from the model — the only order references the LLM can pass are ones the *server* just handed back in a selection list for *that* authenticated user, so there is no UI action that hands the model another user's ref to try. This is enforced and covered by automated tests instead:
`backend/tests/test_redemption_edge_case_spec.py::test_row5_resolve_cannot_be_tricked_into_another_users_real_order` and `::test_row6_awb_lookup_never_reveals_another_users_order` — both simulate a tool call/service call naming another real user's order ID directly and assert it falls back to a generic "not found" / safe selection list, never that user's data.
If you want a manual sanity check anyway: log in as `alice`, ask for tracking, note an order ref never appears in the reply text (only product/status/date) — there is nothing in the UI a customer could even copy to attempt this.

## T9 — Upstream tracking timeout, valid cache available

**Not observable from the chat UI in production** — there's no way to force the real tracking dependency to time out on demand from the browser. Covered by `test_row8_stale_cache_used_and_flagged_when_upstream_fails`, which populates the cache, then forces the upstream call to raise a timeout, and asserts the response still succeeds with `stale: true` and the last-known location.
If you need to sanity-check this in production specifically: ask an ongoing-order tracking question twice in quick succession (e.g. `erin`, "where is my order?" twice) — the second call should return noticeably faster (cache hit) and identical content; that's as close as the UI gets to proving the cache path without a way to inject a fault.

## T10 — Upstream tracking timeout, no cache available

**Not observable from the chat UI in production**, same reason as T9 — requires forcing the upstream call to fail, which the browser can't do. There isn't yet a dedicated automated test isolating "timeout with zero cache" as distinct from T9's "timeout with stale cache" — this is a real gap, not a documented pass. Track it as a follow-up if a stronger guarantee here is wanted.

## T11 — Duplicate/repeated identical request (no duplicate upstream call)

**Partially observable, not provable, from the UI alone.** Ask the same tracking question twice back-to-back (e.g. `erin`, "Where is my order?" then immediately "where's my order?" again) and confirm both answers are identical and the second reply feels effectively instant — consistent with a cache hit rather than a fresh upstream round trip. To actually *prove* no duplicate upstream/DB call happened, you need backend visibility: check application logs or the `support_tracking_cache_total{result=hit}` / `support_tracking_api_latency_seconds` metrics (if wired to your observability stack) for the relevant window, or watch `tracking_service` logs directly on the server. A passing UI vibe check is not a substitute for that instrumentation.

## T12 — Order status changes between listing and tracking (race)

**User:** `erin`
1. Type `Where is my order?` — she has exactly one ongoing order (`IN_TRANSIT`); note the reply.
2. Have someone (or a script) flip that order's status to `DELIVERED` directly in the DB while the conversation is still open, simulating a courier webhook landing mid-conversation. Not doable from the chat UI itself — needs DB/admin access in the same window.
3. In the same conversation, type `track it again` or repeat the original question.

**Expect:** The reply now reports **DELIVERED** — never a generic "couldn't find that order" (which would wrongly imply the order never existed). A subsequent `Where is my order?` in the same conversation then correctly reports "no ongoing orders" — proving the ongoing-orders cache was invalidated by the status-change discovery, not left stale.

This exact flow is also covered end-to-end by `test_row11_order_delivered_between_listing_and_track_click`, and was additionally live-verified this session via a real 3-turn `erin` conversation (track → status flipped mid-script → re-track reports DELIVERED → follow-up listing shows zero ongoing orders).

---

## Summary

| Row | Verifiable live in prod chat UI | Status |
|---|---|---|
| T1 | Yes | Verified |
| T2 | Yes | Verified |
| T3 | Yes | Verified |
| T4 | Yes | Verified |
| T5 | Yes | Verified |
| T6 | Yes | Verified |
| T7 | Yes | Verified |
| T8 | No — enforced server-side, not reachable via UI input | Covered by automated tests |
| T9 | No — requires forcing an upstream fault | Covered by automated tests |
| T10 | No — requires forcing an upstream fault | **Gap** — no dedicated automated test for "timeout + zero cache" specifically |
| T11 | Partial — UI can suggest but not prove | Needs log/metric confirmation for a hard guarantee |
| T12 | Yes (with DB-level status flip mid-conversation) | Verified |

"Verified" above reflects live testing performed against the local dev environment with the current unified `get_orders` code during this session; before signing off on production specifically, re-run the "Yes" rows through the actual deployed Vercel/production URL with the demo accounts, since local verification does not guarantee production config (env vars, Redis instance, migration state) matches.
