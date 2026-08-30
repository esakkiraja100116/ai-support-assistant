# Admin Dashboard

A role-gated area at `/admin` (redirects to `/` for anyone whose session isn't `ADMINISTRATOR` — checked client-side in `app/admin/layout.tsx`, with the server independently enforcing the same rule on every `/admin/*` API call via `get_current_admin`, so the client check is a UX convenience, not the actual security boundary).

## Tech stack

Rebuilt on Tailwind CSS v4 + [shadcn/ui](https://ui.shadcn.com/) (`base-nova` style), replacing an earlier hand-written CSS version. Concretely:

- **Tables** — `@tanstack/react-table` via a shared `components/ui/data-table.tsx`, giving every list page free-text search and column sorting with no per-page code.
- **Navigation shell** — `components/shell/DashboardShell.tsx` (shared with the customer chat UI): a sticky top bar, a static sidebar on desktop, and a `Sheet`-based (Radix/base-ui `Dialog` under the hood) off-canvas drawer on mobile — real focus trap and escape-to-close, not hand-rolled CSS transforms.
- **Profile menu** — a centered `Dialog` (not a dropdown) showing the admin's name, username, and role, with a log-out button. (This was a `DropdownMenu` originally; it's a `Dialog` now after a real runtime bug — `DropdownMenuLabel` renders base-ui's `Menu.GroupLabel`, which throws unless wrapped in a `Menu.Group`, which it wasn't — see the git history on `components/shell/ProfileMenu.tsx`.)
- **Status pills** — `components/ui/badge.tsx` driven by a single shared `lib/statusStyles.ts` mapping, reused identically for transaction statuses and redemption order statuses.

## Pages

| Route | Shows | Notes |
|---|---|---|
| `/admin` | — | Immediately redirects to `/admin/users`; not a real page. |
| `/admin/users` | Every seeded user, with per-user transaction/redemption-order/conversation counts. | The one endpoint that's intentionally unscoped by ownership (`GET /admin/users`) — guarded by `get_current_admin` instead. |
| `/admin/transactions` | Every user's buy/sell/recurring-buy transactions. | Same unscoped-by-design pattern as above. |
| `/admin/redemptions` | Every user's physical gold redemption/delivery orders, with status badges. | Added alongside the redemption order tracking chat feature — see the root README's "Redis caching" section and `docs/chat-tool-calling-flow.md`'s redemption path for how these rows get tracked in chat. |
| `/admin/conversations` | Every conversation across every user, with message count, model(s) used, and cost. | Links through to a read-only transcript view. |
| `/admin/conversations/[id]` | The full message transcript for one conversation. | Reuses the exact same `MessageBubble`/`MessageList` components the live chat UI uses, in a non-interactive mode (card clicks are inert — `pointer-events-none` on buttons inside this view) — so an admin sees precisely what the customer saw, including rendered transaction/redemption cards, not a plain-text log. |
| `/admin/costs` | Total spend, broken down by model, by query category (general / transaction / redemption / escalation / error / other), and the top 10 conversations by cost. | Sourced from the same per-message `cost_usd`/`model_used` columns that OpenTelemetry spans are also enriched with (see the root README's "Observability" section) — the dashboard and the traces describe the same underlying calls, just two different views of them. |
| `/admin/faq` | Every knowledge-base article, with a delete action. | Deleting an article removes its embedding too — the assistant immediately loses the ability to retrieve it. |
| `/admin/faq/new` | A form to add a new FAQ article. | The new article's embedding is generated immediately on submit (same `text-embedding-3-small` call the seed script uses), so it's retrievable right away — no separate re-indexing step. |

## What's deliberately *not* here

- No way to edit a transaction or redemption order's status from the admin UI — those are treated as data owned by upstream systems (the platform's own trading engine, the courier's tracking feed), not something an admin manually edits through this support tool.
- No pagination on any list page yet — fine at the current seed-data scale (a handful of users, a few dozen rows per table), would need addressing before this held real production volume.
- No live-updating cost/conversation counts — every page fetches once on load; refreshing the page is currently the only way to see new activity.
