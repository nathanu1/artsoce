"""A stand-in Ollama server for tests: real HTTP on 127.0.0.1, documented endpoints only.

No Ollama binary or model is available where these tests run. The server implements
``GET /api/version``, ``GET /api/tags``, ``POST /api/chat`` and ``POST /api/embed`` with the
response fields of Ollama's API reference, and records every request body so tests can check
exactly what the adapter sent. Chat replies come from a scripted queue, or from the offline
mock model when a provider registers the originating request (``MockBackedOllama``).
"""

from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from generative_agents.providers.base import LLMRequest
from generative_agents.providers.embeddings import MockHashEmbedding
from generative_agents.providers.mock import MockLLM
from generative_agents.providers.ollama_provider import OllamaProvider

DIGEST = "sha256:" + "ab" * 32
EMBED_DIGEST = "sha256:" + "cd" * 32


def message_key(system: str, prompt: str) -> str:
    return hashlib.sha256(f"{system}\x00{prompt}".encode()).hexdigest()


class FakeOllama:
    def __init__(self, models: tuple[str, ...] = ("llama3.1:8b", "nomic-embed-text:latest"), embed_dims: int = 64):
        self.models = list(models)
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.script: list[dict[str, Any]] = []  # queued /api/chat replies (dicts merged into a default reply)
        self.backend: dict[str, LLMRequest] = {}  # message_key -> original request (mock-backed replies)
        self.mock = MockLLM(seed=0)
        self.embedder = MockHashEmbedding(dims=embed_dims)
        self.fail_next: list[tuple[int, dict[str, Any]]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # quiet
                pass

            def _send(self, code: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                outer.requests.append((self.path, {}))
                if self.path == "/api/version":
                    return self._send(200, {"version": "0.12.6"})
                if self.path == "/api/tags":
                    return self._send(
                        200,
                        {
                            "models": [
                                {
                                    "name": m,
                                    "model": m,
                                    "modified_at": "2026-10-01T00:00:00Z",
                                    "size": 4_900_000_000,
                                    "digest": EMBED_DIGEST if "embed" in m else DIGEST,
                                    "details": {"format": "gguf", "family": "llama", "parameter_size": "8.0B", "quantization_level": "Q4_K_M"},
                                }
                                for m in outer.models
                            ]
                        },
                    )
                return self._send(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                outer.requests.append((self.path, body))
                if outer.fail_next:
                    code, payload = outer.fail_next.pop(0)
                    return self._send(code, payload)
                if self.path == "/api/chat":
                    if body.get("model") not in outer.models:
                        return self._send(404, {"error": f"model '{body.get('model')}' not found"})
                    return self._send(200, outer.chat_reply(body))
                if self.path == "/api/embed":
                    if body.get("model") not in outer.models and f"{body.get('model')}:latest" not in outer.models:
                        return self._send(404, {"error": f"model '{body.get('model')}' not found"})
                    texts = body["input"] if isinstance(body["input"], list) else [body["input"]]
                    vecs = outer.embedder.embed(texts)
                    return self._send(200, {"model": body["model"], "embeddings": vecs.tolist(), "prompt_eval_count": len(texts)})
                return self._send(404, {"error": "not found"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def chat_reply(self, body: dict[str, Any]) -> dict[str, Any]:
        reply: dict[str, Any] = {
            "model": body["model"],
            "created_at": "2026-10-05T00:00:00Z",
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "done_reason": "stop",
            "total_duration": 1_000_000,
            "load_duration": 10_000,
            "prompt_eval_count": 120,
            "eval_count": 8,
        }
        system, prompt = body["messages"][0]["content"], body["messages"][1]["content"]
        original = self.backend.get(message_key(system, prompt))
        if self.script:
            override = self.script.pop(0)
            reply.update({k: v for k, v in override.items() if k != "message"})
            reply["message"] = {"role": "assistant", "content": override.get("content", "")}
        elif original is not None:
            out = self.mock.complete(original)
            reply["message"]["content"] = out.text
            reply["prompt_eval_count"] = out.input_tokens
            reply["eval_count"] = out.output_tokens
        return reply

    def __enter__(self) -> FakeOllama:
        self.thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.server.shutdown()
        self.server.server_close()

    def chats(self) -> list[dict[str, Any]]:
        return [b for p, b in self.requests if p == "/api/chat"]


class MockBackedOllama(OllamaProvider):
    """The real adapter, talking HTTP to ``FakeOllama``; the server answers with the offline mock."""

    def __init__(self, server: FakeOllama, model: str = "llama3.1:8b", **kw: Any):
        super().__init__(model, base_url=server.url, **kw)
        self.server = server

    def complete(self, request: LLMRequest):
        self.server.backend[message_key(request.system, request.prompt)] = request
        return super().complete(request)
