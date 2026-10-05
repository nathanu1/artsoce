"""Builders for offline service stacks used across tests."""

from __future__ import annotations

from datetime import datetime

from generative_agents.config import GAConfig, apply_overrides
from generative_agents.db import Database
from generative_agents.memory.store import MemoryStore
from generative_agents.providers.embeddings import MockHashEmbedding
from generative_agents.providers.mock import MockLLM
from generative_agents.schemas import AgentIdentity
from generative_agents.simulation.runtime import build_runtime, make_services

ISABELLA = AgentIdentity(
    id="isabella_rodriguez",
    name="Isabella Rodriguez",
    first_name="Isabella",
    last_name="Rodriguez",
    age=34,
    innate="friendly, outgoing, hospitable",
    learned="Isabella Rodriguez is a cafe owner of Hobbs Cafe who loves to make people feel welcome.",
    currently="Isabella Rodriguez is planning on having a Valentine's Day party at Hobbs Cafe.",
    lifestyle="Isabella Rodriguez goes to bed around 11pm, awakes up around 6am.",
    living_area="the Ville:Isabella Rodriguez's apartment:main room",
    daily_plan_req="Isabella Rodriguez opens Hobbs Cafe at 8am everyday.",
)
KLAUS = AgentIdentity(
    id="klaus_mueller",
    name="Klaus Mueller",
    first_name="Klaus",
    last_name="Mueller",
    age=20,
    innate="kind, inquisitive, passionate",
    learned="Klaus Mueller is a student at Oak Hill College studying sociology.",
    currently="Klaus Mueller is writing a research paper on the effects of gentrification.",
    lifestyle="Klaus Mueller goes to bed around 11pm, awakes up around 7am, eats dinner around 5pm.",
    living_area="the Ville:Dorm for Oak Hill College:Klaus Mueller's room",
    daily_plan_req="Klaus Mueller goes to the library at Oak Hill College early in the morning.",
)


def make_stack(provider=None, overrides: list[str] | None = None, identities=None, db=None):
    cfg = GAConfig.model_validate(apply_overrides({}, overrides))
    db = db or Database(None)
    store = MemoryStore(db)
    rt = build_runtime(
        cfg,
        store=store,
        ledger_path=None,
        scope="test-run",
        provider=provider or MockLLM(seed=3),
        embedding_provider=MockHashEmbedding(128),
        sleep=lambda s: None,
    )
    ids = identities or {ISABELLA.id: ISABELLA, KLAUS.id: KLAUS}
    svc = make_services(cfg, db, rt, ids)
    return cfg, db, rt, svc


T = datetime(2023, 2, 13, 9, 0)


# ---------------------------------------------------------------------- simulation helpers
class CountingLLM:
    """Wraps a provider and counts real (non-ledger) calls."""

    def __init__(self, inner):
        self.inner = inner
        self.name = getattr(inner, "name", "counting")
        self.calls = []

    def describe(self):
        return self.inner.describe()

    def complete(self, request):
        self.calls.append(request)
        return self.inner.complete(request)


def sim_config(population, *, start="2023-02-13T09:00:00", end="2023-02-13T12:00:00", extra=()):
    pop = "[" + ", ".join(population) + "]"
    return GAConfig.model_validate(
        apply_overrides(
            {},
            [
                "scenario.path=scenarios/pilot5/scenario.yaml",
                f"scenario.population={pop}",
                f"scenario.start={start}",
                f"scenario.end={end}",
                "output.checkpoint_every_steps=30",
                *extra,
            ],
        )
    )


def make_sim(tmp_path, population, *, provider=None, name="run", **kw):
    from generative_agents.simulation.engine import Simulation

    cfg = sim_config(population, **kw)
    return Simulation(cfg, tmp_path / name, provider=provider or MockLLM(seed=5), embedding_provider=MockHashEmbedding(128))


def place(sim, agent_id, tile):
    sim.svc.states.get(agent_id).tile = tuple(tile)
