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
            "relevant to a general product, policy, or how-to question. The customer's "
            "own message is always used verbatim as the search text."
        ),
        "parameters": {"type": "object", "properties": {}},
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

ANSWER_FROM_KB = {
    "type": "function",
    "function": {
        "name": "answer_from_kb",
        "description": (
            "Call this if one or more of the provided articles let you answer the question "
            "through reasonable inference from what's stated - not just exact wording. A "
            "support agent would make these connections naturally, so you should too:\n"
            "- if an article discloses everything it charges/includes, that also answers "
            "whether anything is hidden or extra (disclosure implies nothing left out)\n"
            "- if an article names the specific options/products offered, that also answers "
            "'how many are there?' (count what's listed)\n"
            "- if an article uses one term (e.g. '24K'), that also answers a question using "
            "its common synonym (e.g. 'carat')\n"
            "Only call insufficient_kb_info when the articles genuinely lack the needed "
            "information - not merely because the wording differs. Write the answer using "
            "ONLY the content of the article(s) you cite - never invent a fact, reason, or "
            "number that isn't there."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "answer": {
                    "type": "string",
                    "description": "The final answer for the customer, based only on the cited article(s).",
                },
                "source_article_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "ids of the article(s) actually used to answer.",
                },
            },
            "required": ["answer", "source_article_ids"],
        },
    },
}

INSUFFICIENT_KB_INFO = {
    "type": "function",
    "function": {
        "name": "insufficient_kb_info",
        "description": (
            "Call this only for a genuine mismatch - the articles truly lack the information "
            "needed, not merely different wording. If an article's content would let you "
            "answer through reasonable inference (see answer_from_kb), prefer that instead. "
            "Don't guess or answer from general knowledge here."
        ),
        "parameters": {"type": "object", "properties": {}},
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
    "- specifically THEIR OWN current total gold holdings, portfolio balance, or account net "
    "worth (e.g. 'how much gold do I have', 'what's my balance') - this system does not track "
    "that, so say so plainly and briefly explain what you can help with instead (their recent "
    "transactions, or general support questions). This does NOT apply to questions about what "
    "the platform offers in general (e.g. 'how many gold purity options are there', 'what "
    "products do you offer') - those are catalog/policy questions and must go through "
    "search_knowledge_base like any other general question. Never guess or estimate a number "
    "that wasn't returned by a tool. "
    "\n\n"
    "If the question is unrelated to this platform entirely, politely say you can only help "
    "with buying/selling gold and account support here. "
    "For greetings or small talk only, reply briefly and invite a support question. "
    "Never invent information that isn't present in tool results."
)
