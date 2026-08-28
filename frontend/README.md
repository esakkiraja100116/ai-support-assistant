# Frontend

Next.js (App Router, TypeScript) chat UI for the support assistant.

## Setup

```bash
cd frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_BASE_URL, defaults to http://localhost:8000
```

## Run

```bash
npm run dev
```

Open http://localhost:3000. The backend must be running and seeded (see [../backend/README.md](../backend/README.md)) for the login picker to show any accounts.

## Architecture

- **No client-side routing library or global state manager** — one route (`app/page.tsx`), two view states (logged out → `LoginScreen`, logged in → `ChatWindow`), and two small hooks (`useAuth`, `useChat`) covering all state. This app doesn't have enough independent screens or server-cache endpoints to justify more.
- **Auth** (`hooks/useAuth.ts`): "login" is picking one of the seeded users (`GET /auth/users`) and exchanging it for a JWT (`POST /auth/login`, no password). The token and display name are kept in `sessionStorage` — tab-scoped, cleared on close, never sent anywhere except the `Authorization` header of API calls.
- **Conversation id lives in the URL**, not in component state: `app/page.tsx` mints a `?c=<uuid>` on first load after login and again whenever "New chat" is pressed. This makes a conversation a real address — refreshing the tab keeps you in the same thread, and a `New chat` click is just a navigation to a fresh id, nothing more.
- **Chat state** (`hooks/useChat.ts`): messages are held in React state and mirrored into `sessionStorage`, keyed by **both** the logged-in user id and the conversation id (`chat:{userId}:{conversationId}`). Keying by user id too — not just the id in the URL — matters: if a different account logs in on the same browser and lands on the same `?c=` URL, they must not see the previous account's messages, and this keying guarantees that without any extra bookkeeping.
- **The frontend never parses assistant text to decide what to render.** Every backend response carries a `type` (`TEXT_ANSWER` / `TRANSACTION_SELECTION` / `TRANSACTION_EXPLANATION` / `ERROR`) and a typed `data` payload; `MessageBubble.tsx` switches on `type` alone. The `message` string is always just prose to display, never something the UI has to interpret.
- **Context carried across turns despite a stateless backend**: `useChat`'s `toHistory()` builds the `history` array sent with each request from the last 10 *sent* messages. For an assistant turn that showed a transaction list, it embeds the actual transaction records (not just the human-facing "Which transaction..." text) into that history entry, so a later follow-up like "the second one" still has the list to resolve against even though the backend itself keeps no session state.
- **Retry**: each assistant message carries enough to redo its own request (`retry: {kind: "chat", message} | {kind: "explain", transactionId}`), so `ErrorBanner`'s retry button can resubmit the exact failed request without the user retyping anything.

## Key files

- `hooks/useChat.ts` — message state, history construction, send/retry/select-transaction.
- `lib/api.ts` — the only module that calls `fetch`; every network error becomes a typed `ApiError`.
- `lib/session.ts` — all `sessionStorage` reads/writes, in one place.
- `components/MessageBubble.tsx` — the `type` → UI switch described above.
