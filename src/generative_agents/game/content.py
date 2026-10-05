"""Game content: affinity themes, motifs, gifts, catalog, paints, templates, Town Pulse.

Loaded from ``configs/game/*.yaml`` (or another directory) and validated as a whole, so a
typo in a theme id or an unknown template item fails at start-up rather than mid-game.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..config import repo_path


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Theme(_M):
    id: str
    name: str
    color: str
    icon: str
    description: str = ""
    keywords: list[str] = Field(default_factory=list)


class Motif(_M):
    id: str
    name: str
    theme: str
    source: Literal["environment", "social"]
    icon: str


class Gift(_M):
    id: str
    name: str
    theme: str
    icon: str
    cost: int = 1


class CatalogItem(_M):
    id: str
    name: str
    theme: str
    category: Literal["furniture", "decor", "garden", "structure"]
    footprint: tuple[int, int] = (1, 1)
    placement: Literal["indoor", "outdoor", "any"] = "any"
    blocks: bool = False
    cost: dict[str, int] = Field(default_factory=dict)
    unlock: int = 1
    shape: str = "box"

    def size(self, rot: int) -> tuple[int, int]:
        w, h = self.footprint
        return (h, w) if rot % 2 else (w, h)


class Paint(_M):
    id: str
    name: str
    hex: str
    theme: str | None = None


class TemplatePart(_M):
    item: str
    dx: int
    dy: int
    rot: int = 0
    paint: str | None = None


class Template(_M):
    id: str
    name: str
    unlock: int = 1
    parts: list[TemplatePart]


class Zone(_M):
    id: str
    sector: str
    arena: str
    rect: tuple[int, int, int, int]  # x0, y0, x1, y1 inclusive


class PulseLevel(_M):
    level: int
    name: str
    points: int


class GameContent(_M):
    themes: list[Theme]
    outdoor_keywords: list[str] = Field(default_factory=lambda: ["garden", "park"])
    resident_loves: dict[str, list[str]] = Field(default_factory=dict)  # optional overrides by agent id
    motifs: list[Motif]
    gifts: list[Gift]
    items: list[CatalogItem]
    paints: list[Paint]
    templates: list[Template] = Field(default_factory=list)
    levels: list[PulseLevel]
    points: dict[str, int]
    friendship: dict[str, int]
    zones: list[Zone] = Field(default_factory=list)
    ground_objects: list[str] = Field(default_factory=lambda: ["garden"])
    ground_min_tiles: int = 4

    @model_validator(mode="after")
    def _check(self) -> GameContent:
        ids = [t.id for t in self.themes]
        if len(ids) != 6 or len(set(ids)) != 6:
            raise ValueError(f"there must be exactly six distinct affinity themes, got {ids}")
        theme_set = set(ids)
        for group, name in ((self.motifs, "motif"), (self.gifts, "gift"), (self.items, "item"), (self.paints, "paint"), (self.templates, "template")):
            seen = [g.id for g in group]
            if len(seen) != len(set(seen)):
                raise ValueError(f"duplicate {name} ids: {sorted({s for s in seen if seen.count(s) > 1})}")
        for m in self.motifs:
            if m.theme not in theme_set:
                raise ValueError(f"motif {m.id} names unknown theme {m.theme}")
        for t in ids:
            if not any(m.theme == t and m.source == "environment" for m in self.motifs):
                raise ValueError(f"theme {t} has no environmental motif")
            if sum(1 for m in self.motifs if m.theme == t and m.source == "social") != 1:
                raise ValueError(f"theme {t} needs exactly one social motif")
        for aid, loves in self.resident_loves.items():
            if not set(loves) <= theme_set or not 1 <= len(loves) <= 2:
                raise ValueError(f"resident_loves for {aid} must name one or two known themes")
        for g in self.gifts:
            if g.theme not in theme_set:
                raise ValueError(f"gift {g.id} names unknown theme {g.theme}")
        names: set[str] = set()
        for it in self.items:
            if it.theme not in theme_set or not set(it.cost) <= theme_set:
                raise ValueError(f"item {it.id} names an unknown theme")
            if min(it.footprint) < 1 or max(it.footprint) > 4:
                raise ValueError(f"item {it.id} footprint must be 1-4 tiles per side")
            if not 1 <= it.unlock <= 5:
                raise ValueError(f"item {it.id} unlock level must be 1-5")
            if it.name in names:
                raise ValueError(f"item name {it.name!r} is used twice")
            names.add(it.name)
        for p in self.paints:
            if p.theme is not None and p.theme not in theme_set:
                raise ValueError(f"paint {p.id} names unknown theme {p.theme}")
        item_ids = {i.id for i in self.items}
        paint_ids = {p.id for p in self.paints}
        for tpl in self.templates:
            for part in tpl.parts:
                if part.item not in item_ids:
                    raise ValueError(f"template {tpl.id} uses unknown item {part.item}")
                if part.paint is not None and part.paint not in paint_ids:
                    raise ValueError(f"template {tpl.id} uses unknown paint {part.paint}")
        levels = [lv.level for lv in self.levels]
        pts = [lv.points for lv in self.levels]
        if levels != [1, 2, 3, 4, 5] or pts[0] != 0 or pts != sorted(set(pts)):
            raise ValueError("Town Pulse needs levels 1-5 with increasing point thresholds starting at 0")
        return self

    # ------------------------------------------------------------------ lookups
    def theme(self, tid: str) -> Theme:
        return next(t for t in self.themes if t.id == tid)

    def item(self, iid: str) -> CatalogItem:
        for it in self.items:
            if it.id == iid:
                return it
        raise KeyError(f"unknown catalog item {iid!r}")

    def gift(self, gid: str) -> Gift:
        for g in self.gifts:
            if g.id == gid:
                return g
        raise KeyError(f"unknown gift {gid!r}")

    def paint(self, pid: str) -> Paint:
        for p in self.paints:
            if p.id == pid:
                return p
        raise KeyError(f"unknown paint {pid!r}")

    def template(self, tid: str) -> Template:
        for t in self.templates:
            if t.id == tid:
                return t
        raise KeyError(f"unknown template {tid!r}")

    def motifs_for(self, theme: str, source: str) -> list[Motif]:
        return [m for m in self.motifs if m.theme == theme and m.source == source]

    def level_for(self, points: int) -> PulseLevel:
        return [lv for lv in self.levels if lv.points <= points][-1]

    def public(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def load_content(directory: str | Path = "configs/game") -> GameContent:
    d = Path(directory)
    d = d if d.is_absolute() else repo_path(str(d))
    data: dict[str, Any] = {}
    for name in ("affinities.yaml", "motifs.yaml", "catalog.yaml", "pulse.yaml", "town.yaml"):
        part = yaml.safe_load((d / name).read_text()) or {}
        for k, v in part.items():
            key = "themes" if k == "themes" else k
            if key in data:
                raise ValueError(f"{name} repeats the key {key!r}")
            data[key] = v
    return GameContent.model_validate(data)
