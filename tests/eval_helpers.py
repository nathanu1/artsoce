"""Toy runs for evaluation tests: a hand-built state database and snapshot."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from generative_agents.schemas import AgentIdentity, Conversation, MemoryKind, MemoryOrigin, Utterance
from helpers import ISABELLA, KLAUS, make_stack

MARIA = AgentIdentity(
    id="maria_lopez",
    name="Maria Lopez",
    first_name="Maria",
    last_name="Lopez",
    age=21,
    innate="energetic, enthusiastic, inquisitive",
    learned="Maria Lopez is a student at Oak Hill College studying physics.",
    currently="Maria Lopez is working on a physics degree.",
    lifestyle="Maria Lopez goes to bed around 2am, awakes up around 9am.",
    living_area="the Ville:Dorm for Oak Hill College:Maria Lopez's room",
)
T0 = datetime(2023, 2, 13, 0, 0)
IDS = {a.id: a for a in (ISABELLA, KLAUS, MARIA)}


def toy_run(provider=None, overrides=None):
    """Isabella knows (seed); Klaus heard it from her; Maria knows nothing about the party."""

    cfg, db, rt, svc = make_stack(provider, overrides, identities=IDS)
    for i, ident in enumerate(IDS.values()):
        db.execute("INSERT INTO agents(id, name, order_index, identity_json) VALUES(?,?,?,?)", (ident.id, ident.name, i, ident.model_dump_json()))
    svc.remember(
        ISABELLA,
        "You are planning a Valentine's Day party at Hobbs Cafe on February 14th from 5pm",
        MemoryKind.OBSERVATION,
        MemoryOrigin.SEED,
        T0,
        importance=8,
        seed=True,
        metadata={"flags": ["party_knowledge"]},
    )
    svc.remember(KLAUS, "You know Maria Lopez from the dorm", MemoryKind.OBSERVATION, MemoryOrigin.SEED, T0, importance=4, seed=True, metadata={"flags": []})
    svc.remember(MARIA, "You know Klaus Mueller from the dorm", MemoryKind.OBSERVATION, MemoryOrigin.SEED, T0, importance=4, seed=True, metadata={"flags": []})
    t = T0 + timedelta(hours=10)
    conv = Conversation(
        id="c00001",
        participants=[ISABELLA.id, KLAUS.id],
        initiator_id=ISABELLA.id,
        started_at=t,
        utterances=[
            Utterance(speaker_id=ISABELLA.id, text="I'm hosting a Valentine's Day party at Hobbs Cafe on February 14th at 5pm. You should come!", sim_time=t),
            Utterance(speaker_id=KLAUS.id, text="That sounds great, I'd love to come!", sim_time=t),
        ],
        status="completed",
        summary="This is a conversation about a Valentine's Day party.",
    )
    db.execute(
        "INSERT INTO conversations(id, started_at, status, participants, json) VALUES(?,?,?,?,?)",
        (conv.id, t.isoformat(), conv.status, ",".join(conv.participants), conv.model_dump_json()),
    )
    for u in conv.utterances:
        for owner, other in ((ISABELLA, KLAUS), (KLAUS, ISABELLA)):
            speaker = IDS[u.speaker_id]
            listener = other if speaker.id == owner.id else owner
            origin = MemoryOrigin.OWN_STATEMENT if u.speaker_id == owner.id else MemoryOrigin.STATEMENT
            svc.remember(
                owner,
                f'{speaker.name} said to {listener.name}: "{u.text}"',
                MemoryKind.OBSERVATION,
                origin,
                t,
                importance=6,
                conversation_id=conv.id,
                speaker_id=u.speaker_id,
            )
    svc.remember(KLAUS, "Klaus Mueller is curious about the party", MemoryKind.REFLECTION, MemoryOrigin.INFERENCE, t + timedelta(minutes=5), importance=5)
    svc.remember(KLAUS, "This is Klaus Mueller's plan for Monday February 13: study at the library.", MemoryKind.PLAN, MemoryOrigin.INTENTION, T0, importance=5)
    db.set_meta("run_id", "toy")
    db.set_meta("sim_time", (T0 + timedelta(hours=12)).isoformat())
    db.commit()
    return cfg, db, rt, svc


def snapshot(db, path, name="final", sim_time=None):
    copy = db.clone(path)
    copy.set_meta("snapshot", {"name": name, "run_id": "toy", "step": 0, "sim_time": (sim_time or T0 + timedelta(hours=12)).isoformat()})
    copy.commit()
    copy.close()
    return path


def put_json(db, sql, params):
    db.execute(sql, params)


def frames(db, rows):
    """rows: list of (step, sim_time, keyframe, {agent: [x, y]})."""

    for step, t, key, agents in rows:
        payload = {"key": key, "agents": {a: [x, y, "", "plan", None, None] for a, (x, y) in agents.items()}, "objects": None}
        db.execute("INSERT INTO frames(step, sim_time, json) VALUES(?,?,?)", (step, t.isoformat(), json.dumps(payload)))
    db.commit()
