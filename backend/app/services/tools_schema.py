"""OpenAI tool/function schemas exposed to the chat model.

Deliberately, `get_recent_transactions` takes no user-identifying parameter.
The authenticated user is always bound server-side from the JWT, so the
model can never supply, guess, or be prompt-injected into supplying a
user id for this tool.
"""

SEARCH_KNOWLEDGE_BASE = {
    "type": "function",
    "function": {
        "name": "search_knowledge_base",
        "description": (
            "Search the approved customer support knowledge base for information "
            "relevant to a general product, policy, or how-to question."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The customer's question, rephrased as a search query if helpful.",
                },
            },
            "required": ["query"],
        },
    },
}

GET_RECENT_TRANSACTIONS = {
    "type": "function",
    "function": {
        "name": "get_recent_transactions",
        "description": (
            "Fetch a list of the authenticated customer's own recent BUY/SELL/RECURRING_BUY "
            "transaction records (each with a status, amount, and date). Use this only when "
            "the customer is asking about specific past orders or activity, e.g. 'show my "
            "recent transactions', 'why did my purchase fail', 'what happened to my last order'. "
            "Do NOT use this for questions about current total holdings, portfolio value, or "
            "account balance - this tool has no such data, it only returns a transaction history list."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

RESOLVE_TRANSACTION = {
    "type": "function",
    "function": {
        "name": "resolve_transaction",
        "description": (
            "Call this once you can tell, from the customer's message, exactly which single "
            "transaction (from the list you were given) they mean - e.g. by recency ('my last "
            "purchase', 'most recent'), status ('the one that failed'), product, amount, or "
            "position in the list. Only call this when you are confident about a single match."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "transaction_id": {
                    "type": "string",
                    "description": "The id of the single matching transaction from the provided list.",
                },
            },
            "required": ["transaction_id"],
        },
    },
}

NO_SINGLE_MATCH = {
    "type": "function",
    "function": {
        "name": "no_single_match",
        "description": (
            "Call this when you do NOT have enough information to identify exactly one "
            "transaction from the list you were given. Never describe, list, or summarize "
            "the transactions yourself - the app renders them separately."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "enum": ["list_requested", "ambiguous"],
                    "description": (
                        "'list_requested' if the customer explicitly asked to see their "
                        "transactions/orders/activity in general. 'ambiguous' if they described "
                        "a specific transaction but more than one could match, or it's unclear."
                    ),
                },
            },
            "required": ["reason"],
        },
    },
}

ALL_TOOLS = [SEARCH_KNOWLEDGE_BASE, GET_RECENT_TRANSACTIONS]

SYSTEM_PROMPT = (
    "You are a customer support assistant for a platform where customers buy and sell gold. "
    "You can only help with: (1) general product/policy/how-to questions about this platform, "
    "and (2) looking up the customer's own past transaction records. "
    "\n\n"
    "For any general product, policy, or how-to question, call search_knowledge_base rather "
    "than answering from general knowledge. "
    "For a question about a specific past order, purchase, sale, or transaction activity, call "
    "get_recent_transactions. "
    "\n\n"
    "Do not call a tool speculatively. If the customer asks something neither tool can answer "
    "- for example their current total gold holdings, portfolio balance, or account net worth, "
    "which this system does not track - say so plainly and briefly explain what you can help "
    "with instead (their recent transactions, or general support questions). Never guess or "
    "estimate a number that wasn't returned by a tool. "
    "\n\n"
    "If the question is unrelated to this platform entirely, politely say you can only help "
    "with buying/selling gold and account support here. "
    "For greetings or small talk only, reply briefly and invite a support question. "
    "Never invent information that isn't present in tool results."
)
