"""Optional price tables. Without one, cost is reported as "unpriced" and never guessed."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ModelPrice:
    input_per_mtok: float
    output_per_mtok: float
    cache_read_per_mtok: float | None = None
    cache_write_per_mtok: float | None = None


class PriceTable:
    def __init__(self, data: dict[str, Any] | None):
        self.source = (data or {}).get("source")
        self.as_of = (data or {}).get("as_of")
        self.models: dict[str, ModelPrice] = {}
        for model, row in ((data or {}).get("models") or {}).items():
            self.models[model] = ModelPrice(**row)

    @classmethod
    def load(cls, path: str | Path | None) -> PriceTable:
        if not path:
            return cls(None)
        return cls(yaml.safe_load(Path(path).read_text()))

    def cost(self, model: str, input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0) -> float | None:
        price = self.models.get(model)
        if price is None:
            return None
        cost = input_tokens * price.input_per_mtok / 1e6 + output_tokens * price.output_per_mtok / 1e6
        if cache_read and price.cache_read_per_mtok is not None:
            cost += cache_read * price.cache_read_per_mtok / 1e6
        if cache_write and price.cache_write_per_mtok is not None:
            cost += cache_write * price.cache_write_per_mtok / 1e6
        return cost

    def describe(self) -> dict[str, Any]:
        return {"source": self.source, "as_of": self.as_of, "models": sorted(self.models)}
