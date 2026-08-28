# Manual Test Questions

A categorized test set to exercise the platform's different paths — general KB questions, transaction questions, and edge cases. Useful for manually clicking through the chat UI (or hitting `POST /chat` directly) after any change to retrieval, tool-calling, or the frontend.

## 1. Exact / near-exact KB matches

Should answer directly, grounded from the knowledge base.

- How do I sell my gold?
- How do I buy gold?
- How does recurring savings work?
- What KYC documents do I need?
- What is the minimum investment amount?

## 2. Paraphrases / synonyms

Tests retrieval quality, not just exact wording.

- How can I exchange my gold for cash?
- Can I liquidate my gold holdings?
- What's the process to cash out?
- What ID proof do you need from me?
- Is there a cap on how much I can invest?

## 3. Transaction questions — should resolve directly, no card list

- Why did my last purchase fail?
- What happened to my most recent order?
- Why was my sell transaction refunded?
- Show me the details of my failed recurring buy

## 4. Transaction questions — genuinely ambiguous, should show cards

- Show me my recent transactions
- What are my past orders?
- List my transaction history

## 5. Out of scope / can't answer — should say so, not guess

- How much gold do I have in my account? *(no balance/holdings tool exists)*
- If I buy and sell gold on the same day, will I make a profit? *(speculative/financial-advice question, no data backs a "yes/no")*
- What's today's gold price? *(no live price feed)*
- What's the weather today? *(fully off-topic)*
- Tell me how to get gold without paying for it *(nonsensical/edge phrasing — good robustness check)*

## 6. Follow-up / context-awareness

Ask in sequence, in the same conversation:

1. "Show me my recent transactions" → cards appear
2. "why did the failed one happen?" → should resolve without re-fetching/re-asking
3. "what about the SELL one" → tests ordinal/descriptive follow-up against the same list

## 7. Authorization boundary

Needs two browser sessions or a logout/login:

- Log in as Alice, ask about transactions, note the IDs shown.
- Log in as Bob, confirm none of Alice's transaction IDs ever appear, even if you try referencing one by guessing an ID pattern.
