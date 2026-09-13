"""Token usage and cost calculation; unknown usage is never guessed."""

import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    model: str | None = None
    provider: str | None = None

    @classmethod
    def no_model(cls) -> "TokenUsage":
        return cls(0, 0, 0, 0, 0, None, None)

    def to_dict(self) -> dict:
        return asdict(self)


def estimate_cost(usage: TokenUsage, pricing_path: Path) -> Decimal | None:
    if not usage.model or usage.input_tokens is None or usage.output_tokens is None:
        return None
    try:
        models = json.loads(pricing_path.read_text())["models"]
        price = models.get(usage.model)
    except (OSError, KeyError, json.JSONDecodeError):
        return None
    if not price:
        return None
    return (
        Decimal(usage.input_tokens) * Decimal(str(price["input_per_million"]))
        + Decimal(usage.output_tokens) * Decimal(str(price["output_per_million"]))
    ) / Decimal(1_000_000)
