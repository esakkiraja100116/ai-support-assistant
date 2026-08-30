"""OpenAI tool/function schemas exposed to the chat model.

Deliberately, `get_recent_transactions` and `get_ongoing_redemptions` take no
user-identifying parameter. The authenticated user is always bound
server-side from the JWT, so the model can never supply, guess, or be
prompt-injected into supplying a user id for either tool.
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

RESPOND_DIRECTLY = {
    "type": "function",
    "function": {
        "name": "respond_directly",
        "description": (
            "Call this ONLY for a true greeting with no support content at all (e.g. 'hi', "
            "'hello', 'good morning') or pure small talk (e.g. 'thank you', 'how are you'). "
            "Do NOT call this for any question about the platform's products, policies, fees, "
            "pricing, or how-to topics - even if phrased casually or referencing general market "
            "pricing/timing - those must go through search_knowledge_base instead. Do NOT call "
            "this for any question about the customer's own transactions or orders, including "
            "counts/aggregates over them (e.g. 'how many succeeded') - those must go through "
            "get_recent_transactions instead. Do NOT call this for a question about shipment/"
            "delivery tracking of a physical redemption order (e.g. 'where is my order', 'track "
            "my gold coin') - those must go through get_ongoing_redemptions instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reply": {
                    "type": "string",
                    "description": "The direct reply to the customer, addressing them by name.",
                }
            },
            "required": ["reply"],
        },
    },
}

REQUEST_HUMAN_AGENT = {
    "type": "function",
    "function": {
        "name": "request_human_agent",
        "description": (
            "Call this ONLY when the customer explicitly asks to speak with a human/real agent, "
            "asks to be connected to support staff, or clearly expresses that the assistant "
            "isn't helping them (e.g. 'this isn't helping', 'I need a human', 'connect me to "
            "someone', 'your bot is useless') - regardless of whether their underlying question "
            "could otherwise be answered. This bypasses normal routing entirely.\n\n"
            "Never call this just because you are unsure what the customer means or which other "
            "tool applies, or because a question is ambiguous or references something unclear "
            "('that', 'it', 'the status') - uncertainty is not a request for a human. In that "
            "case, use the conversation history to resolve what they're referring to and call "
            "search_knowledge_base or get_recent_transactions instead, whichever fits."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "trigger": {
                    "type": "string",
                    "enum": ["explicit_request", "frustration_expressed"],
                    "description": (
                        "'explicit_request' if the customer directly asked for a human/real agent or "
                        "support staff. 'frustration_expressed' if they said this isn't helping/working "
                        "or similar. If neither genuinely applies - you're just unsure what they mean, "
                        "or a reference is ambiguous - do NOT call this tool: resolve the ambiguity from "
                        "conversation history instead and call search_knowledge_base or "
                        "get_recent_transactions, whichever fits."
                    ),
                },
            },
            "required": ["trigger"],
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

GET_ONGOING_REDEMPTIONS = {
    "type": "function",
    "function": {
        "name": "get_ongoing_redemptions",
        "description": (
            "Fetch the authenticated customer's own ongoing (not yet delivered, not "
            "failed/cancelled) physical gold redemption/delivery orders - coins or bars being "
            "shipped to them. Use this for shipment/delivery tracking questions like 'where is "
            "my order', 'track my gold coin', 'has my bar shipped yet', 'what is my AWB status'. "
            "This is separate from get_recent_transactions, which covers BUY/SELL/RECURRING_BUY "
            "activity, not physical delivery/shipment status."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

RESOLVE_REDEMPTION_ORDER = {
    "type": "function",
    "function": {
        "name": "resolve_redemption_order",
        "description": (
            "Call this once you can tell, from the customer's message, which single ongoing "
            "redemption order they mean, from the list you were given. Only call this when "
            "confident - do not guess."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_ref": {
                    "type": "string",
                    "description": "order_ref of the matching order, from the provided list.",
                },
            },
            "required": ["order_ref"],
        },
    },
}

NO_SINGLE_REDEMPTION_MATCH = {
    "type": "function",
    "function": {
        "name": "no_single_redemption_match",
        "description": (
            "Call this when you do NOT have enough information to identify exactly one order "
            "from the list you were given. Never describe, list, or summarize the orders "
            "yourself - the app renders them separately."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

RESOLVE_TRANSACTIONS = {
    "type": "function",
    "function": {
        "name": "resolve_transactions",
        "description": (
            "Call this once you can tell, from the customer's message, which specific "
            "transaction(s) - one or more - they mean, from the list you were given. Works for "
            "a single transaction ('my last purchase', 'the one that failed') or several ('my "
            "last 3 transactions', 'the failed ones', 'my recent sells'). "
            "\n\n"
            "When interpreting recency or status language, use the actual status field: 'paid', "
            "'completed', or 'successful' means status=SUCCESS - a PENDING or FAILED transaction "
            "has NOT been paid, so don't pick one of those for a 'how much did I pay' style "
            "question even if it happens to be more recent by date. "
            "\n\n"
            "Only call this when you are confident about which transaction(s) match - do not guess."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "transaction_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "ids of the matching transaction(s), from the provided list.",
                },
            },
            "required": ["transaction_ids"],
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

ALL_TOOLS = [
    SEARCH_KNOWLEDGE_BASE,
    GET_RECENT_TRANSACTIONS,
    GET_ONGOING_REDEMPTIONS,
    REQUEST_HUMAN_AGENT,
    RESPOND_DIRECTLY,
]

# --- Streaming variants -----------------------------------------------------
# Used only by the streaming orchestrator path (orchestrator.chat_turn_stream).
# These are judgment/routing-only versions of RESPOND_DIRECTLY/ANSWER_FROM_KB
# with the answer-text field removed, since in the streaming flow the actual
# reply text comes from a separate, later streamed plain-content call - never
# from a tool-call argument. Kept fully separate from the non-streaming
# RESPOND_DIRECTLY/ANSWER_FROM_KB above (which existing tests, eval scripts,
# and the non-streaming /chat endpoint still use unmodified) rather than
# changing those in place, to avoid any risk to the already-working path.

RESPOND_DIRECTLY_ROUTE = {
    "type": "function",
    "function": {
        "name": "respond_directly",
        "description": RESPOND_DIRECTLY["function"]["description"],
        "parameters": {"type": "object", "properties": {}},
    },
}

ANSWER_FROM_KB_JUDGE = {
    "type": "function",
    "function": {
        "name": "answer_from_kb",
        "description": ANSWER_FROM_KB["function"]["description"],
        "parameters": {
            "type": "object",
            "properties": {
                "source_article_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "ids of the article(s) that actually answer the question.",
                },
            },
            "required": ["source_article_ids"],
        },
    },
}

ALL_TOOLS_STREAM = [
    SEARCH_KNOWLEDGE_BASE,
    GET_RECENT_TRANSACTIONS,
    GET_ONGOING_REDEMPTIONS,
    REQUEST_HUMAN_AGENT,
    RESPOND_DIRECTLY_ROUTE,
]

# The system prompt (and every other prompt this app sends) lives in
# app/prompts/*.j2, rendered via app/services/prompts.py - see that module's
# docstring for why (shared framing via {% include %}, easier to read/edit
# than string concatenation).
