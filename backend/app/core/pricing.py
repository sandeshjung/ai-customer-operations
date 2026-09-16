# Approximate Groq pricing in USD per 1M tokens (input, output). Groq changes
# these periodically — verify against https://groq.com/pricing before relying
# on this for anything beyond a rough efficiency signal in the admin console.
MODEL_PRICING_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "llama-3.1-8b-instant": (0.05, 0.08),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-70b-versatile": (0.59, 0.79),
    "gemma2-9b-it": (0.20, 0.20),
}


def estimate_cost_usd(
    model: str | None, input_tokens: int, output_tokens: int
) -> float | None:
    """Returns None (rather than 0) when the model isn't in the pricing
    table, so callers can distinguish "free" from "unknown"."""
    if model is None:
        return None
    pricing = MODEL_PRICING_PER_MILLION_TOKENS.get(model)
    if pricing is None:
        return None
    input_price, output_price = pricing
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000
