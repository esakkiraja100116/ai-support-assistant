"""Approximate OpenAI list pricing, in USD per 1,000,000 tokens.

Not fetched from any live API - these are hardcoded published rates for the
two models this app uses. Update them here if your actual/negotiated billing
differs; nothing else in the codebase needs to change.
"""

PRICING_PER_MILLION_TOKENS: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
}


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int = 0) -> float:
    rates = PRICING_PER_MILLION_TOKENS.get(model)
    if not rates:
        return 0.0
    return (prompt_tokens * rates["input"] + completion_tokens * rates["output"]) / 1_000_000
