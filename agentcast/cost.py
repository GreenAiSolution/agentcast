"""Rough cost estimates. Prices are USD per million tokens and are
deliberately conservative *estimates* — subscription plans (Claude Pro/Max,
ChatGPT Plus) do not bill per token, and provider prices change. The
renderer always labels the number as an estimate."""
from __future__ import annotations

# (input, output, cache_read, cache_write) per 1M tokens
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-fable-5":      (10.0, 50.0, 1.00, 12.5),
    "claude-mythos-5":     (10.0, 50.0, 1.00, 12.5),
    "claude-opus-5":       (5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-8":     (5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-7":     (5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-6":     (5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-5":     (5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-1":     (15.0, 75.0, 1.50, 18.75),
    "claude-opus-4":       (15.0, 75.0, 1.50, 18.75),
    "claude-sonnet-5":     (2.0, 10.0, 0.20, 2.50),
    "claude-sonnet-4-6":   (3.0, 15.0, 0.30, 3.75),
    "claude-sonnet-4-5":   (3.0, 15.0, 0.30, 3.75),
    "claude-sonnet-4":     (3.0, 15.0, 0.30, 3.75),
    "claude-haiku-4-5":    (1.0, 5.0, 0.10, 1.25),
    "claude-3-5-haiku":    (0.8, 4.0, 0.08, 1.00),
    # OpenAI (Codex). Approximate list prices.
    "gpt-5":               (1.25, 10.0, 0.125, 1.25),
    "gpt-5-codex":         (1.25, 10.0, 0.125, 1.25),
    "gpt-5-mini":          (0.25, 2.0, 0.025, 0.25),
    "gpt-4.1":             (2.0, 8.0, 0.50, 2.0),
    "o3":                  (2.0, 8.0, 0.50, 2.0),
    "o4-mini":             (1.1, 4.4, 0.275, 1.1),
}
DEFAULT = (5.0, 25.0, 0.50, 6.25)


def price_for(model: str) -> tuple[float, float, float, float]:
    m = (model or "").lower()
    # longest matching prefix wins
    best = ""
    for k in PRICES:
        if m.startswith(k) and len(k) > len(best):
            best = k
    return PRICES[best] if best else DEFAULT


def estimate(usage: dict[str, int], model: str) -> float:
    i, o, cr, cw = price_for(model)
    return (usage.get("input", 0) * i
            + usage.get("output", 0) * o
            + usage.get("cache_read", 0) * cr
            + usage.get("cache_write", 0) * cw) / 1_000_000
