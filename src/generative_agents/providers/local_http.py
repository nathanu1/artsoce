"""Minimal JSON-over-HTTP client for model servers on your own machine (Ollama, LM Studio).

Standard library only, so the zero-cost path needs no extra packages. Proxies from the
environment are ignored by default: a local server must be reached directly even when an
``HTTPS_PROXY``/``HTTP_PROXY`` is set for the internet.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .base import ProviderError


def is_local_url(url: str) -> bool:
    host = urllib.request.urlparse(url).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1", "0.0.0.0") or host.endswith(".local")


class JSONClient:
    def __init__(self, base_url: str, *, timeout_s: float = 300.0, use_env_proxy: bool = False, headers: dict[str, str] | None = None, label: str = "server"):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        self.label = label
        handlers = [] if use_env_proxy else [urllib.request.ProxyHandler({})]
        self._opener = urllib.request.build_opener(*handlers)

    def request(self, method: str, path: str, body: dict[str, Any] | None = None, *, timeout_s: float | None = None) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers=self.headers)
        try:
            with self._opener.open(req, timeout=timeout_s or self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = _error_detail(exc)
            raise ProviderError(
                f"{self.label} {exc.code}: {detail}",
                retryable=exc.code >= 500 or exc.code in (408, 429),
                metadata={"status": exc.code, "path": path},
            ) from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            reason = getattr(exc, "reason", exc)
            raise ProviderError(f"{self.label} not reachable at {self.base_url} ({reason})", retryable=True, metadata={"path": path}) from exc
        try:
            out = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError as exc:
            raise ProviderError(f"{self.label} returned non-JSON from {path}: {raw[:200]!r}", retryable=True) from exc
        if not isinstance(out, dict):
            raise ProviderError(f"{self.label} returned unexpected JSON from {path}", retryable=False)
        return out


def _error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8")
    except Exception:  # pragma: no cover - unreadable body
        return str(exc.reason)
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body[:300] or str(exc.reason)
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)
        if err:
            return str(err)
    return body[:300]


def inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Return ``schema`` with local ``$ref``s to ``$defs`` expanded in place.

    Grammar-constrained decoders in local servers handle plain nested objects more reliably
    than references, and the expanded schema is equivalent.
    """

    defs = schema.get("$defs", {})

    def expand(node: Any, depth: int = 0) -> Any:
        if depth > 32:
            raise ValueError("schema nesting too deep to inline")
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                target = defs[ref.split("/")[-1]]
                merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
                return expand(merged, depth + 1)
            return {k: expand(v, depth + 1) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [expand(v, depth + 1) for v in node]
        return node

    return expand(schema)
