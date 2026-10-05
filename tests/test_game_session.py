"""The live game session (background engine thread) and its HTTP interface."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from generative_agents.game.api import create_game_app
from generative_agents.game.session import GameSession
from generative_agents.providers.base import ProviderError
from generative_agents.providers.embeddings import MockHashEmbedding
from generative_agents.providers.mock import MockLLM
from generative_agents.simulation.engine import save_config
from helpers import sim_config

TRIO = ["isabella_rodriguez", "maria_lopez", "klaus_mueller"]


def town_cfg(start="2023-02-13T10:00:00", end="2023-02-13T10:30:00", extra=()):
    return sim_config(TRIO, start=start, end=end, extra=("game.enabled=true", "game.auto_requests=false", *extra))


def wait_for(cond, timeout=60.0, every=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        out = cond()
        if out:
            return out
        time.sleep(every)
    raise AssertionError("condition not met in time")


class FlakyLLM:
    """The mock, but the first ``fail`` calls raise a non-retryable provider error."""

    name = "flaky"

    def __init__(self, fail: int):
        self.inner = MockLLM(seed=5)
        self.fail = fail

    def describe(self):
        return {"provider": "flaky"}

    def complete(self, request):
        if self.fail > 0:
            self.fail -= 1
            raise ProviderError("ollama not reachable at http://localhost:11434", retryable=False)
        return self.inner.complete(request)


def make_session(tmp_path, name="town", cfg=None, **kw):
    cfg = cfg or town_cfg()
    run_dir = tmp_path / name
    run_dir.mkdir(parents=True, exist_ok=True)
    save_config(cfg, run_dir)
    kw.setdefault("provider", MockLLM(seed=5))
    kw.setdefault("embedding_provider", MockHashEmbedding(128))
    return GameSession(cfg, run_dir, **kw)


def feed_kinds(session, kind):
    return [e for e in session.poll(-2, 0)["feed"] if e["kind"] == kind]


def test_live_session_steps_applies_actions_and_pauses(tmp_path):
    s = make_session(tmp_path, speed="max")
    s.start()
    try:
        wait_for(lambda: s.poll()["frames"])
        ack = s.submit("chat", {"agent": "klaus_mueller", "text": "Hi Klaus! Busy day?"})
        assert ack["seq"] == 1
        chat = wait_for(lambda: feed_kinds(s, "chat") or feed_kinds(s, "rejected"))
        assert chat[0]["action_seq"] == 1
        s.control("pause")
        wait_for(lambda: s.poll()["status"] == "paused")
        step = s.poll()["clock"]["step"]
        s.submit("search", {"address": "the Ville:Oak Hill College:library:bookshelf"})
        wait_for(lambda: feed_kinds(s, "motif"))
        assert s.poll()["clock"]["step"] == step  # applied while paused, without stepping
        s.control("speed", "max")
        s.control("resume")
        wait_for(lambda: s.poll()["status"] == "finished", timeout=120)
    finally:
        s.stop()
    lines = (tmp_path / "town" / "actions.jsonl").read_text().splitlines()
    assert [json.loads(x)["kind"] for x in lines] == ["chat", "search"]
    manifest = json.loads((tmp_path / "town" / "manifest.json").read_text())
    assert manifest["status"] == "completed" and manifest["game"]["actions"] == 2


def test_a_session_resumes_from_disk_and_replays_without_calls(tmp_path):
    cfg = town_cfg(end="2023-02-13T10:20:00")
    s = make_session(tmp_path, cfg=cfg, speed="max", paused=True)
    s.start()
    wait_for(lambda: s.poll()["status"] == "paused")
    s.submit("ask_request", {"agent": "isabella_rodriguez"})
    wait_for(lambda: feed_kinds(s, "request") or feed_kinds(s, "rejected"))
    s.control("resume")
    wait_for(lambda: (s.poll()["clock"] or {}).get("step", 0) > 40)
    s.stop()
    stopped_at = json.loads((tmp_path / "town" / "manifest.json").read_text())["next_step"]
    assert stopped_at > 40
    again = GameSession(cfg, tmp_path / "town", provider=MockLLM(seed=5), embedding_provider=MockHashEmbedding(128), speed="max")
    again.start()
    wait_for(lambda: again.poll()["status"] == "finished", timeout=120)
    again.stop()
    rp = GameSession(cfg, tmp_path / "replay", replay_from=tmp_path / "town", speed="max")
    rp.start()
    try:
        wait_for(lambda: rp.poll()["status"] == "finished", timeout=120)
        with pytest.raises(PermissionError):
            rp.submit("chat", {"agent": "klaus_mueller", "text": "hello"})
        assert rp.poll()["replay"] and rp.poll()["ledger"]["calls"] == 0 or rp.sim.rt.budget.usage.calls == 0
        assert feed_kinds(rp, "request")  # the recorded request happens again, from the recording
    finally:
        rp.stop()


def test_a_model_failure_stops_at_the_checkpoint_and_retry_continues(tmp_path):
    flaky = FlakyLLM(fail=1)
    s = make_session(tmp_path, provider=flaky, speed="max")
    s.start()
    try:
        failed = wait_for(lambda: s.poll()["error"])
        assert "not reachable" in failed and s.poll()["status"] == "provider_failure"
        epoch = s.poll()["epoch"]
        s.control("retry")
        wait_for(lambda: s.poll()["status"] == "finished", timeout=120)
        assert s.poll()["epoch"] == epoch and s.poll()["error"] is None
    finally:
        s.stop()


def test_http_interface(tmp_path):
    s = make_session(tmp_path, speed="max", paused=True)
    s.start()
    client = TestClient(create_game_app(s))
    try:
        wait_for(lambda: s.poll()["status"] == "paused")
        info = client.get("/api/game/info").json()
        assert info["mode"] == "mock" and [r["id"] for r in info["residents"]] == TRIO
        assert len(info["content"]["themes"]) == 6 and info["residents"][2]["look"]["accessory"] == "glasses"
        m = client.get("/api/game/map").json()
        assert m["width"] == 140 and "Town Square" in m["legend"]["sector"] and m["outdoor_arenas"]
        poll = client.get("/api/game/poll").json()
        assert poll["status"] == "paused" and poll["game"]["pulse"]["level"] == 1 and set(poll["schedules"]) == set(TRIO)
        plaza = [t for t in s.sim.world.walkable_tiles_for("the Ville:Town Square:plaza")][20]
        ok = client.post("/api/game/validate-build", json={"ops": [{"op": "place", "catalog_id": "bench", "x": plaza[0], "y": plaza[1]}]}).json()
        bad = client.post("/api/game/validate-build", json={"ops": [{"op": "place", "catalog_id": "armchair", "x": plaza[0], "y": plaza[1]}]}).json()
        assert ok["ok"] and not bad["ok"] and "belongs indoors" in bad["verdicts"][0]["reasons"]
        assert client.post("/api/game/action", json={"kind": "dance", "payload": {}}).status_code == 400
        ack = client.post("/api/game/action", json={"kind": "chat", "payload": {"agent": "isabella_rodriguez", "text": "Hello!"}}).json()
        assert ack["seq"] == 1
        wait_for(lambda: feed_kinds(s, "chat") or feed_kinds(s, "rejected"))
        res = client.get("/api/game/resident/isabella_rodriguez").json()
        assert res["id"] == "isabella_rodriguez"
        assert client.get("/api/game/resident/nobody").status_code == 404
        obj = client.get("/api/game/object", params={"address": "the Ville:Oak Hill College:library:bookshelf"}).json()
        assert obj["search_theme"] == "lore"
        assert client.post("/api/game/control", json={"action": "speed", "speed": "warp"}).status_code == 400
        assert client.post("/api/game/control", json={"action": "resume"}).json()["paused"] is False
        assert client.get("/research/api/run").json()["run_id"] == "town"  # the read-only research API
    finally:
        s.stop()
