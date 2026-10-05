"""Deterministic affinity scoring (no model calls).

Residents, activities, places and items are mapped onto the six themes by whole-word keyword
matches. This is game bookkeeping for the player; none of it enters a resident's prompt.
"""

from __future__ import annotations

import re
from typing import Any

from .content import GameContent

_WORD = re.compile(r"[a-z]+")


class Affinity:
    def __init__(self, content: GameContent):
        self.content = content
        self.order = [t.id for t in content.themes]
        self._kw = {t.id: {k.lower() for k in t.keywords} for t in content.themes}

    def scores(self, text: str) -> dict[str, float]:
        out = dict.fromkeys(self.order, 0.0)
        for w in _WORD.findall(text.lower()):
            for t in self.order:
                if w in self._kw[t]:
                    out[t] += 1.0
        return out

    def top(self, scores: dict[str, float], default: str | None = None) -> str | None:
        best = max(self.order, key=lambda t: (scores.get(t, 0.0), -self.order.index(t)))
        return best if scores.get(best, 0.0) > 0 else default

    def classify(self, text: str, default: str | None = None) -> str | None:
        return self.top(self.scores(text), default)

    def place_scores(self, address: str) -> dict[str, float]:
        """``world:sector:arena[:object]``: object words count 3, room words 2, building words 1."""

        parts = address.split(":")[1:]
        out = dict.fromkeys(self.order, 0.0)
        for weight, part in zip((1.0, 2.0, 3.0), parts, strict=False):
            for t, v in self.scores(part).items():
                out[t] += weight * v
        return out

    def search_theme(self, address: str) -> str | None:
        """What searching an object can turn up: object words count 3, room words 2.

        Building names are left out here (a family's bathroom is not a community place).
        """

        parts = address.split(":")[2:]
        out = dict.fromkeys(self.order, 0.0)
        for weight, part in zip((2.0, 3.0), parts, strict=False):
            for t, v in self.scores(part).items():
                out[t] += weight * v
        return self.top(out)

    def resident(self, identity: Any) -> dict[str, Any]:
        # Traits, background and current pursuits; the lifestyle line (bed and meal times)
        # describes routines, not interests.
        text = " ".join(str(getattr(identity, f, "") or "") for f in ("innate", "learned", "currently"))
        scores = self.scores(text)
        override = self.content.resident_loves.get(identity.id)
        if override:
            loves = list(override)
        else:
            ranked = sorted((t for t in self.order if scores[t] > 0), key=lambda t: (-scores[t], self.order.index(t)))
            loves = ranked[:2]
        return {"scores": scores, "loves": loves}

    @staticmethod
    def reaction(loves: list[str], theme: str) -> str:
        return "loved" if theme in loves else "fine"
