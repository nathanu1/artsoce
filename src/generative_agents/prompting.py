"""Versioned prompt templates (prompts/*.md) with front matter and ``{{placeholders}}``.

Each template states its source (paper page or released template) and its information scope,
so a reader can check that a prompt only sees what its agent may know. The template's SHA-256
enters every cache key and the run manifest.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from .cognition.outputs import OUTPUT_MODELS
from .config import REPO_ROOT

PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

SYSTEM_ROLE = (
    "You are one component of a research simulation of believable characters, reproducing "
    "the generative agents architecture (Park et al., UIST 2023). Use only the information in "
    "the request; do not invent facts about the world or other characters. Reply with JSON that "
    "matches the requested schema and nothing else."
)


@dataclass
class PromptTemplate:
    id: str
    version: int
    output_model: type[BaseModel]
    source: str
    scope: str
    system: str
    user: str
    max_output_tokens: int
    effort: str | None
    path: Path
    sha256: str

    @property
    def template_id(self) -> str:
        return f"{self.id}@v{self.version}"

    def placeholders(self) -> set[str]:
        return set(PLACEHOLDER.findall(self.system)) | set(PLACEHOLDER.findall(self.user))

    def render(self, variables: dict[str, Any]) -> tuple[str, str]:
        missing = self.placeholders() - set(variables) - {"system_role"}
        if missing:
            raise KeyError(f"template {self.template_id} missing variables: {sorted(missing)}")

        def sub(match: re.Match[str]) -> str:
            name = match.group(1)
            if name == "system_role":
                return SYSTEM_ROLE
            value = variables[name]
            return value if isinstance(value, str) else str(value)

        system = PLACEHOLDER.sub(sub, self.system).strip()
        user = PLACEHOLDER.sub(sub, self.user).strip()
        return system, user


def _parse(path: Path) -> PromptTemplate:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path} has no front matter")
    _, front, body = text.split("---", 2)
    meta = yaml.safe_load(front)
    sections = re.split(r"^### (system|user)\s*$", body, flags=re.MULTILINE)
    parts: dict[str, str] = {}
    for i in range(1, len(sections), 2):
        parts[sections[i]] = sections[i + 1].strip("\n")
    if "user" not in parts:
        raise ValueError(f"{path} has no ### user section")
    out_name = meta["output"]
    if out_name not in OUTPUT_MODELS:
        raise ValueError(f"{path}: unknown output model {out_name}")
    return PromptTemplate(
        id=meta["id"],
        version=int(meta["version"]),
        output_model=OUTPUT_MODELS[out_name],
        source=meta.get("source", ""),
        scope=meta.get("scope", ""),
        system=parts.get("system", "{{system_role}}"),
        user=parts["user"],
        max_output_tokens=int(meta.get("max_output_tokens", 512)),
        effort=meta.get("effort"),
        path=path,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


class PromptRegistry:
    def __init__(self, directory: str | Path | None = None):
        self.directory = Path(directory) if directory else REPO_ROOT / "prompts"
        self._templates: dict[str, PromptTemplate] = {}
        for path in sorted(self.directory.glob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            tpl = _parse(path)
            existing = self._templates.get(tpl.id)
            if existing is None or tpl.version > existing.version:
                self._templates[tpl.id] = tpl

    def get(self, task: str) -> PromptTemplate:
        try:
            return self._templates[task]
        except KeyError as exc:
            raise KeyError(f"no prompt template for task {task!r}") from exc

    def tasks(self) -> list[str]:
        return sorted(self._templates)

    def manifest(self) -> dict[str, dict[str, Any]]:
        return {
            t.id: {"version": t.version, "sha256": t.sha256, "source": t.source, "file": t.path.name}
            for t in sorted(self._templates.values(), key=lambda t: t.id)
        }
