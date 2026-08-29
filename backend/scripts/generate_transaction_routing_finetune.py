"""Builds a supervised fine-tuning dataset (OpenAI chat fine-tuning JSONL) for
the intent-routing decision made at the top of `orchestrator._chat_turn` -
i.e. "does this message warrant get_recent_transactions / search_knowledge_base
/ request_human_agent, or is it genuine small talk?" - the exact decision
point where three real routing bugs were found via manual testing:

1. Aggregate/count questions over transactions ("how many were successful?")
   got wrongly declined as an unsupported "portfolio balance"-style question,
   even though get_recent_transactions returns everything needed to answer it.
2. General platform-pricing questions phrased as "why/where/what factors"
   ("why does the gold price change every day?") got wrongly treated as
   out-of-scope small talk instead of routed to search_knowledge_base.
3. (Included as a *correct* negative example, not a bug) genuine capability
   gaps - current total holdings/portfolio value/account balance - are
   correctly declined, since the app has no live pricing data for that.

Five 7-turn scenarios, each turn labeled with the CORRECT routing decision
(not what the app currently, sometimes incorrectly, does) - grounded in
Alice's real seeded transactions (backend/scripts/seed.py's TXN_TEMPLATES:
3 SUCCESS, 2 FAILED, 1 PENDING, 1 REFUNDED; 3 BUY, 2 SELL, 2 RECURRING_BUY),
so the conversation content is internally consistent, not just plausible-sounding.

This is a small (35-example) starter set - well over OpenAI's 10-example
minimum for a fine-tuning job, but still small for teaching a genuinely
robust routing distinction; treat it as a first pass to validate the
approach, not a finished training set.

Run from the `backend/` directory:
    python -m scripts.generate_transaction_routing_finetune
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import prompts  # noqa: E402
from app.services.tools_schema import ALL_TOOLS  # noqa: E402

DISPLAY_NAME = "Alice Nguyen"
OUTPUT_PATH = Path(__file__).resolve().parent / "fixtures" / "transaction_routing_finetune.jsonl"

# Each scenario is a list of turns: (user_text, target, history_text)
#   target is either ("tool", tool_name) or ("content", text)
#   history_text is the human-facing text that would appear in conversation
#   history for later turns - for a tool-routed turn this is NOT part of the
#   training target itself (the router never re-sees its own tool call, only
#   the resulting reply text, exactly like orchestrator.chat_turn's history).

SCENARIOS: list[list[tuple[str, tuple[str, str], str]]] = [
    # A: mirrors the real bug conversation - ordinal reference, then a count/
    # aggregate question that was wrongly declined, then a status check.
    [
        ("How is the price of gold set on your platform?", ("tool", "search_knowledge_base"),
         "In India, most retail gold platforms benchmark their live rate off the MCX (Multi Commodity Exchange of India), since that's where domestic gold futures actually trade and get price-discovered."),
        ("show me the transaction list", ("tool", "get_recent_transactions"),
         "Here are your recent transactions:"),
        ("why my last transaction was failed ?", ("tool", "get_recent_transactions"),
         "Hi Alice! Your most recent transaction (a recurring purchase of GOLD22) failed due to insufficient funds in your linked account."),
        ("How about my first transation ?", ("tool", "get_recent_transactions"),
         "Your earliest transaction was a BUY of GOLD24 for 5000, which failed because the payment gateway declined the card used."),
        ("Total how many success transaction ?", ("tool", "get_recent_transactions"),
         "You have 3 successful transactions out of your 7 recent ones."),
        ("Is there any pending transaction ?", ("tool", "get_recent_transactions"),
         "Yes, one BUY of GOLD22 for 3200 is currently PENDING."),
        ("Thanks, that's everything I needed.", ("content", "You're welcome, Alice! Feel free to reach out anytime you have another question about buying or selling gold."), ""),
    ],
    # B: more aggregate/count variations over the same real data, plus a
    # sum-style aggregate ("total amount spent") - all answerable once the
    # list is fetched, so all route to get_recent_transactions.
    [
        ("What's my last purchase status?", ("tool", "get_recent_transactions"),
         "Your most recent purchase (a recurring GOLD22 buy) is marked FAILED."),
        ("Why did it fail?", ("tool", "get_recent_transactions"),
         "It failed due to insufficient funds in your linked account."),
        ("How many of my transactions failed?", ("tool", "get_recent_transactions"),
         "2 of your 7 recent transactions failed."),
        ("What about successful ones, how many?", ("tool", "get_recent_transactions"),
         "3 of your 7 recent transactions were successful."),
        ("Show me only the failed ones", ("tool", "get_recent_transactions"),
         "Here are your 2 failed transactions: a GOLD24 buy for 5000, and a GOLD22 recurring buy for 1000."),
        ("What's the total amount from my successful buys?", ("tool", "get_recent_transactions"),
         "Your successful BUY/RECURRING_BUY transactions total 3500 (2500 + 1000)."),
        ("Great, thanks for the help!", ("content", "Anytime, Alice! Let me know if anything else comes up."), ""),
    ],
    # C: general platform-pricing questions phrased as "why/where/what
    # factors" - the exact phrasing pattern that got wrongly treated as
    # out-of-scope small talk instead of routed to the knowledge base.
    [
        ("How is the gold rate determined in the market?", ("tool", "search_knowledge_base"),
         "In India, most retail gold platforms benchmark their live rate off the MCX (Multi Commodity Exchange of India), since that's where domestic gold futures actually trade and get price-discovered."),
        ("Where do you get your live gold rates from?", ("tool", "search_knowledge_base"),
         "Our live rate is benchmarked off the MCX (Multi Commodity Exchange of India)."),
        ("Why does the gold price change every day?", ("tool", "search_knowledge_base"),
         "Because it tracks the MCX, where gold futures trade and get repriced continuously."),
        ("What factors affect today's gold price?", ("tool", "search_knowledge_base"),
         "The rate follows MCX gold futures pricing."),
        ("Is your rate the same as the international market?", ("tool", "search_knowledge_base"),
         "It's benchmarked to the domestic MCX rate rather than directly to international spot prices."),
        ("How often do you update the gold rate?", ("tool", "search_knowledge_base"),
         "I don't have specifics on the update frequency in our knowledge base - I can confirm it's benchmarked off the MCX, though."),
        ("Got it, thanks!", ("content", "You're welcome, Alice! Let me know if you have any other questions."), ""),
    ],
    # D: explicit escalation mid-flow, then the customer changes their mind
    # and keeps asking legitimate follow-ups (routing must not get "stuck" on
    # the escalation branch for later, unrelated turns).
    [
        ("Show me my recent transactions", ("tool", "get_recent_transactions"),
         "Here are your recent transactions:"),
        ("Why did my last one fail?", ("tool", "get_recent_transactions"),
         "It failed due to insufficient funds in your linked account."),
        ("This isn't making sense to me, I need a real person", ("tool", "request_human_agent"),
         "I'd be happy to connect you with a human support agent who can help further."),
        ("Actually wait, can you just tell me why the pending one hasn't gone through?", ("tool", "get_recent_transactions"),
         "Your PENDING transaction (a GOLD22 buy for 3200) is still being processed and hasn't completed yet."),
        ("What about the one before that?", ("tool", "get_recent_transactions"),
         "The transaction before that was a successful RECURRING_BUY of GOLD24 for 1000."),
        ("Do you support international wire transfers?", ("tool", "search_knowledge_base"),
         "I don't have information on international wire transfers in our knowledge base."),
        ("Thanks for your help!", ("content", "You're welcome, Alice! Reach out anytime."), ""),
    ],
    # E: contrasts genuine capability gaps (correctly declined - no tool call)
    # against superficially similar but answerable aggregate questions, so
    # fine-tuning doesn't overcorrect into calling a tool for everything.
    [
        ("How much gold do I currently own in total?", ("content", "I'm not able to show your total gold holdings or portfolio value, Alice - that's not something this system tracks. I can help with your recent transactions or general questions instead."), ""),
        ("Ok, then show me my recent transactions instead", ("tool", "get_recent_transactions"),
         "Here are your recent transactions:"),
        ("How many of these were buys?", ("tool", "get_recent_transactions"),
         "3 of your 7 recent transactions were BUY orders."),
        ("And how many were sells?", ("tool", "get_recent_transactions"),
         "2 of your 7 recent transactions were SELL orders."),
        ("What's my account balance?", ("content", "I'm not able to show your account balance, Alice - that's not something this system tracks. I can help with your recent transactions or general questions instead."), ""),
        ("Fine. Just show me the failed ones then.", ("tool", "get_recent_transactions"),
         "Here are your 2 failed transactions: a GOLD24 buy for 5000, and a GOLD22 recurring buy for 1000."),
        ("Alright, that's all, thank you.", ("content", "You're welcome, Alice! Have a great day."), ""),
    ],
]


def _tool_call_message(tool_name: str) -> dict:
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": tool_name, "arguments": "{}"},
            }
        ],
    }


def build_examples() -> list[dict]:
    system_prompt = prompts.render("system_prompt.j2", display_name=DISPLAY_NAME)
    examples = []

    for scenario in SCENARIOS:
        history: list[dict] = [{"role": "system", "content": system_prompt}]
        for user_text, target, history_text in scenario:
            turn_messages = history + [{"role": "user", "content": user_text}]
            kind, value = target
            target_message = _tool_call_message(value) if kind == "tool" else {"role": "assistant", "content": value}

            examples.append({"messages": turn_messages + [target_message], "tools": ALL_TOOLS})

            # Advance history with the human-facing text for the *next* turn,
            # never with the raw tool call itself - matching how the real app
            # only ever persists/replays final reply text as history.
            history.append({"role": "user", "content": user_text})
            history.append({"role": "assistant", "content": history_text or value})

    return examples


def main() -> None:
    examples = build_examples()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        for example in examples:
            f.write(json.dumps(example) + "\n")
    print(f"Wrote {len(examples)} examples ({len(SCENARIOS)} scenarios) to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
