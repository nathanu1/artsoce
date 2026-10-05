"""Convert pydantic output models into strict JSON schemas accepted by structured-output APIs.

Structured outputs require ``additionalProperties: false`` on every object and do not support
numeric or string-length constraints; those are validated client-side by the pydantic model.
"""

from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel

_UNSUPPORTED = {
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "pattern", "minItems", "maxItems", "uniqueItems", "default", "title",
}


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = copy.deepcopy(model.model_json_schema())
    return _strictify(schema)


def _strictify(node: Any) -> Any:
    if isinstance(node, dict):
        out = {k: _strictify(v) for k, v in node.items() if k not in _UNSUPPORTED}
        if out.get("type") == "object" or "properties" in out:
            props = out.get("properties", {})
            out["type"] = "object"
            out["additionalProperties"] = False
            out["required"] = list(props.keys())
        return out
    if isinstance(node, list):
        return [_strictify(v) for v in node]
    return node
