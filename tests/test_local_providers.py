"""Zero-cost local models: the Ollama and OpenAI-compatible adapters, over real HTTP to a stand-in
server that implements the documented endpoints (no Ollama binary is available here)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from fake_ollama import DIGEST, FakeOllama, MockBackedOllama
from generative_agents.cognition.outputs import ReflectionInsightsOut
from generative_agents.config import GAConfig, apply_overrides
from generative_agents.prompting import PromptRegistry
from generative_agents.providers.base import ProviderError, TaskFailed
from generative_agents.providers.embeddings import EmbeddingService
from generative_agents.providers.gateway import GatewaySettings, LLMGateway
from generative_agents.providers.ledger import CallLedger
from generative_agents.providers.local_http import inline_refs
from generative_agents.providers.ollama_provider import OllamaEmbedding, OllamaProvider, ollama_status
from generative_agents.providers.openai_compatible import OpenAICompatibleEmbedding, OpenAICompatibleProvider
from generative_agents.providers.schema import strict_json_schema
from generative_agents.simulation.budget import Budget
from generative_agents.simulation.engine import Simulation
from helpers import sim_config

REG = PromptRegistry()
TRIO = ["isabella_rodriguez", "maria_lopez", "klaus_mueller"]


def variables(task, **values):
    return {k: values.get(k, f"<{k}>") for k in REG.get(task).placeholders()}


def gateway(provider, **settings):
    s = GatewaySettings(model=provider.model, backoff_s=0, zero_cost=True, **settings)
    return LLMGateway(provider, REG, CallLedger(None, scope="r"), Budget(), s, sleep=lambda s: None)


def test_chat_request_follows_the_documented_api_and_records_provenance():
    with FakeOllama() as srv:
        srv.script = [{"content": '{"rating": 4}', "prompt_eval_count": 300, "eval_count": 5}]
        gw = gateway(OllamaProvider("llama3.1:8b", base_url=srv.url, num_ctx=4096, seed=7), temperature=0.6)
        res = gw.run("importance", variables("importance", memory="Isabella is planning a party"), agent_id="isabella_rodriguez")
        body = srv.chats()[0]
    assert res.output.rating == 4
    row = gw.ledger.rows()[0]
    assert body["model"] == "llama3.1:8b" and body["stream"] is False and body["keep_alive"] == "30m"
    assert [m["role"] for m in body["messages"]] == ["system", "user"] and body["messages"][1]["content"] == row["prompt"]
    assert body["options"] == {"num_ctx": 4096, "num_predict": REG.get("importance").max_output_tokens, "temperature": 0.6, "seed": 7}
    assert body["format"]["required"] == ["rating"] and "$ref" not in json.dumps(body["format"])
    assert row["provider"] == "ollama" and row["cost_usd"] == 0.0 and row["status"] == "ok"
    assert (row["input_tokens"], row["output_tokens"], row["tokens_estimated"]) == (300, 5, 0)
    assert json.loads(row["metadata_json"])["digest"] == DIGEST


def test_nested_output_schemas_are_inlined_for_local_decoders():
    schema = strict_json_schema(ReflectionInsightsOut)
    assert "$defs" in schema
    flat = inline_refs(schema)
    assert "$ref" not in json.dumps(flat) and "$defs" not in flat
    assert flat["properties"]["insights"]["items"]["required"] == ["insight", "evidence"]


def test_truncated_output_and_missing_model_fail_visibly():
    with FakeOllama() as srv:
        srv.script = [{"content": '{"rat', "done_reason": "length"}]
        gw = gateway(OllamaProvider("llama3.1:8b", base_url=srv.url))
        with pytest.raises(TaskFailed) as err:
            gw.run("importance", variables("importance"), agent_id="a")
        assert err.value.errors == ["truncated"] and gw.ledger.rows()[0]["status"] == "truncated"

        gw2 = gateway(OllamaProvider("mistral:7b", base_url=srv.url))
        with pytest.raises(ProviderError) as err2:
            gw2.run("importance", variables("importance"), agent_id="a")
        assert not err2.value.retryable and "ollama pull mistral:7b" in str(err2.value)
        assert sum(1 for b in srv.chats() if b["model"] == "mistral:7b") == 1  # a missing model is not retried


def test_prompt_larger_than_the_context_window_is_refused_before_sending():
    with FakeOllama() as srv:
        gw = gateway(OllamaProvider("llama3.1:8b", base_url=srv.url, num_ctx=256))
        with pytest.raises(ProviderError) as err:
            gw.run("importance", variables("importance", agent_summary="word " * 400), agent_id="a")
        assert "num_ctx=256" in str(err.value) and not err.value.retryable
        assert srv.chats() == []


def test_unreachable_server_is_retryable_and_environment_proxies_are_ignored(monkeypatch):
    with pytest.raises(ProviderError) as err:
        OllamaProvider("llama3.1:8b", base_url="http://127.0.0.1:9", timeout_s=2).client.request("GET", "/api/version")
    assert err.value.retryable and "not reachable" in str(err.value)
    for var in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.setenv(var, "http://127.0.0.1:1")  # a proxy that would refuse everything
    with FakeOllama() as srv:
        assert ollama_status(srv.url, ["llama3.1:8b"])["reachable"]


def test_embeddings_batch_check_dimensions_and_probe_before_keying():
    with FakeOllama() as srv:
        emb = OllamaEmbedding("nomic-embed-text", None, base_url=srv.url, batch_size=2)
        svc = EmbeddingService(emb)
        assert svc.model_key == "nomic-embed-text@none:64"  # learned before any vector is keyed
        vecs = svc.embed(["coffee at the cafe", "a quiet library", "the park"])
        embeds = [b for p, b in srv.requests if p == "/api/embed"]
        assert vecs.shape == (3, 64) and [len(b["input"]) for b in embeds] == [1, 2, 1]
        wrong = OllamaEmbedding("nomic-embed-text", 32, base_url=srv.url)
        with pytest.raises(ProviderError, match="fix the config"):
            wrong.embed(["x"])


def test_status_reports_version_digests_and_missing_models():
    with FakeOllama() as srv:
        st = ollama_status(srv.url, ["llama3.1:8b", "nomic-embed-text", "mistral:7b"])
    assert st["reachable"] and st["version"] == "0.12.6"
    assert st["present"]["llama3.1:8b"]["digest"] == DIGEST and st["present"]["nomic-embed-text"] is not None
    assert st["present"]["mistral:7b"] is None
    down = ollama_status("http://127.0.0.1:9", ["llama3.1:8b"], timeout_s=1)
    assert not down["reachable"] and "not reachable" in down["error"]


def test_local_config_is_zero_cost_and_needs_no_key():
    cfg = GAConfig.model_validate(apply_overrides({}, ["providers.llm.kind=ollama", "providers.llm.model=llama3.1:8b"]))
    assert cfg.providers.llm.is_local() and cfg.run_mode == "live"
    remote = GAConfig.model_validate(apply_overrides({}, ["providers.llm.kind=openai_compatible", "providers.llm.base_url=https://api.example.org/v1"]))
    assert not remote.providers.llm.is_local()


def test_a_simulation_runs_over_http_and_replays_without_any_ollama_request(tmp_path):
    with FakeOllama(models=("llama3.1:8b", "nomic-embed-text:latest")) as srv:
        extra = (
            "providers.llm.kind=ollama",
            "providers.llm.model=llama3.1:8b",
            f"providers.llm.base_url={srv.url}",
            "providers.embeddings.kind=ollama",
            "providers.embeddings.model=nomic-embed-text",
            "providers.embeddings.dims=64",
            f"providers.embeddings.base_url={srv.url}",
            "budget.max_calls=5000",
        )
        cfg = sim_config(TRIO, start="2023-02-13T07:00:00", end="2023-02-13T07:20:00", extra=extra)
        a = Simulation(cfg, tmp_path / "a", provider=MockBackedOllama(srv))
        assert a.run() == "completed", a.db.get_meta("stop_detail")
        rows = a.rt.ledger.rows()
        assert rows and {r["provider"] for r in rows} == {"ollama"} and all(r["cost_usd"] == 0.0 for r in rows)
        assert len(srv.chats()) == len(rows)
        manifest = json.loads((tmp_path / "a" / "manifest.json").read_text())
        assert manifest["mode"] == "live" and manifest["llm"]["digest"] == DIGEST
        seen = len(srv.requests)
        r = Simulation(cfg, tmp_path / "replay", replay_from=tmp_path / "a")
        assert r.run() == "completed", r.db.get_meta("stop_detail")
        assert len(srv.requests) == seen  # neither chat nor embed nor tags: no request at all
    tables = ("memories", "plans", "conversations", "agent_state", "spatial_memory", "world_objects", "embeddings")
    assert r.db.content_hash(tables) == a.db.content_hash(tables)


class _OpenAIish(BaseHTTPRequestHandler):
    seen: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).seen.append((self.path, body, self.headers.get("Authorization")))
        if self.path.endswith("/chat/completions"):
            out = {
                "id": "x",
                "model": "lmstudio-community/llama-3.1-8b",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": '{"rating": 3}'}}],
                "usage": {"prompt_tokens": 210, "completion_tokens": 4},
            }
        else:
            out = {"data": [{"index": i, "embedding": [float(i), 1.0, 0.0]} for i, _ in enumerate(body["input"])]}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def test_openai_compatible_server_request_and_reply(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _OpenAIish)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/v1"
    monkeypatch.setenv("LMSTUDIO_KEY", "local-key")
    try:
        gw = gateway(OpenAICompatibleProvider("llama-3.1-8b", base_url=base, api_key_env="LMSTUDIO_KEY", seed=3))
        assert gw.run("importance", variables("importance"), agent_id="a").output.rating == 3
        path, body, auth = _OpenAIish.seen[0]
        assert path == "/v1/chat/completions" and auth == "Bearer local-key"
        assert body["response_format"]["type"] == "json_schema" and body["response_format"]["json_schema"]["strict"] is True
        assert body["seed"] == 3 and body["max_tokens"] == REG.get("importance").max_output_tokens
        row = gw.ledger.rows()[0]
        assert row["served_model"] == "lmstudio-community/llama-3.1-8b" and row["input_tokens"] == 210 and row["cost_usd"] == 0.0
        vecs = OpenAICompatibleEmbedding("nomic-embed", 3, base_url=base).embed(["a", "b"])
        assert vecs.shape == (2, 3)
    finally:
        srv.shutdown()
        srv.server_close()
