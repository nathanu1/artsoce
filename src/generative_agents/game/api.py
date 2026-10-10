"""HTTP interface of a live (or replayed) game session: ``ga play``.

The town page polls ``/api/game/poll`` a few times a second and sends player actions to
``/api/game/action``. Build checks run against the session's last published snapshot. The
research inspector reads the same run through the read-only viewer API mounted at
``/research/api``; nothing it shows is ever sent to residents.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..db import Database
from ..viewer.app import create_app as create_viewer_app
from .session import SPEEDS, GameSession

WEB = Path(__file__).parent / "web"


class ActionIn(BaseModel):
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)


class BuildIn(BaseModel):
    ops: list[dict[str, Any]]


class ControlIn(BaseModel):
    action: str
    speed: str | None = None


def _rle(arr: np.ndarray) -> list[list[int]]:
    flat = arr.reshape(-1).astype(int).tolist()
    out: list[list[int]] = []
    for v in flat:
        if out and out[-1][0] == v:
            out[-1][1] += 1
        else:
            out.append([v, 1])
    return out


def town_info(session: GameSession) -> dict[str, Any]:
    """Who lives in the town and what the game is made of (``/api/game/info``)."""

    sim, game = session.sim, session.game
    content = game.content
    residents = []
    for aid in sim.order:
        ident = sim.identities[aid]
        residents.append(
            {
                "id": aid,
                "name": ident.name,
                "first_name": ident.first_name,
                "age": ident.age,
                "innate": ident.innate,
                "learned": ident.learned,
                "currently": ident.currently,
                "lifestyle": ident.lifestyle,
                "living_area": ident.living_area,
                "loves": game.residents[aid]["loves"],
                "look": content.look(aid).model_dump(),
            }
        )
    manifest_llm = sim.rt.provider.describe() if hasattr(sim.rt.provider, "describe") else {}
    return {
        "run_id": sim.run_id,
        "mode": "replay" if session.replay else sim.cfg.run_mode,
        "label": sim.cfg.run.label,
        "llm": {"kind": sim.cfg.providers.llm.kind, "model": sim.cfg.providers.llm.model, "local": sim.cfg.providers.llm.is_local(), "describe": manifest_llm},
        "embeddings": {"kind": sim.cfg.providers.embeddings.kind, "model": sim.cfg.providers.embeddings.model},
        "builder": game.builder,
        "start": sim.cfg.scenario.start.isoformat(),
        "end": session.end.isoformat(),
        "seconds_per_step": sim.cfg.scenario.seconds_per_step,
        "speeds": list(SPEEDS),
        "residents": residents,
        "content": content.public(),
        "zones": game.zones,
    }


def town_map(session: GameSession) -> dict[str, Any]:
    """The base map, run-length encoded, plus what the front end needs to draw it (``/api/game/map``)."""

    sim, game = session.sim, session.game
    editor, world = game.editor, sim.world
    arenas = sorted({a for a in world.address_tiles if a.count(":") == 2})
    return {
        "world": world.world,
        "width": world.width,
        "height": world.height,
        "legend": {"sector": list(world.legend["sector"]), "arena": list(world.legend["arena"]), "object": list(editor._base_legend)},
        "layers": {
            "collision": _rle(editor._base_collision),
            "sector": _rle(world.sector),
            "arena": _rle(world.arena),
            "object": _rle(editor._base_object),
        },
        "outdoor_arenas": [a for a in arenas if editor.is_outdoor(a)],
        "ground_objects": sorted(editor._ground_size),
        "objects": sorted(a for a in world.address_tiles if a.count(":") == 3 and not any(p.address == a for p in game.store.items())),
    }


def object_info(session: GameSession, address: str) -> dict[str, Any]:
    """What the object card shows about one object (``/api/game/object``)."""

    return {"address": address, "name": address.rsplit(":", 1)[-1], "place": address.split(":")[1:3], "search_theme": session.game.aff.search_theme(address)}


def create_game_app(session: GameSession, *, web_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="Smallville Lab town", docs_url=None, redoc_url=None)
    sim = session.sim
    world = sim.world
    reader = Database(sim.run_dir / "state.sqlite", read_only=True)
    reader_lock = threading.Lock()

    def rows(sql: str, params: tuple = ()) -> list[Any]:
        with reader_lock:
            return reader.query(sql, params)

    info_payload = town_info(session)
    map_payload = town_map(session)

    # ------------------------------------------------------------------ game endpoints
    @app.get("/api/game/info")
    def info() -> dict[str, Any]:
        return info_payload

    @app.get("/api/game/map")
    def map_() -> JSONResponse:
        return JSONResponse(map_payload, headers={"Cache-Control": "max-age=600"})

    @app.get("/api/game/poll")
    def poll(since_step: int = Query(-2), since_feed: int = Query(0)) -> dict[str, Any]:
        return session.poll(since_step, since_feed)

    @app.post("/api/game/action")
    def action(body: ActionIn) -> dict[str, Any]:
        try:
            return session.submit(body.kind, body.payload)
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/game/validate-build")
    def validate_build(body: BuildIn) -> dict[str, Any]:
        try:
            return session.validate_build(body.ops)
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(400, f"bad build request: {exc}") from exc

    @app.post("/api/game/control")
    def control(body: ControlIn) -> dict[str, Any]:
        try:
            return session.control(body.action, body.speed)
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/game/resident/{aid}")
    def resident(aid: str) -> dict[str, Any]:
        if aid not in sim.identities:
            raise HTTPException(404, f"no resident {aid}")
        exchanges = []
        for r in rows(
            "SELECT id, sim_time, kind, json FROM game_events WHERE agent_id=? AND kind IN ('chat','gift','delivered','request','rejected') ORDER BY id DESC LIMIT 30",
            (aid,),
        ):
            d = json.loads(r["json"])
            exchanges.append(
                {"id": r["id"], "time": r["sim_time"], "kind": r["kind"], **{k: d.get(k) for k in ("builder_line", "reply", "mood", "reason", "gift", "loved")}}
            )
        convs = []
        for r in rows("SELECT id, started_at, json FROM conversations WHERE participants LIKE ? ORDER BY started_at DESC LIMIT 6", (f"%{aid}%",)):
            c = json.loads(r["json"])
            convs.append(
                {
                    "id": r["id"],
                    "started_at": c.get("started_at"),
                    "participants": c.get("participants"),
                    "summary": c.get("summary"),
                    "lines": [{"speaker": u.get("speaker_id"), "text": u.get("text")} for u in c.get("utterances", [])],
                }
            )
        return {"id": aid, "exchanges": list(reversed(exchanges)), "conversations": convs}

    @app.get("/api/game/object")
    def object_route(address: str) -> dict[str, Any]:
        if not world.exists(address):
            raise HTTPException(404, "unknown object")
        return object_info(session, address)

    # ------------------------------------------------------------------ research inspector data (read-only)
    app.mount("/research", create_viewer_app(sim.run_dir))

    # ------------------------------------------------------------------ the built interface
    web = web_dir or WEB
    if (web / "index.html").exists():
        if (web / "assets").exists():
            app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str) -> FileResponse:
            target = (web / path).resolve()
            if path and target.is_file() and web.resolve() in target.parents:
                return FileResponse(target)
            return FileResponse(web / "index.html")
    else:

        @app.get("/")
        def missing() -> JSONResponse:
            return JSONResponse(
                {"error": "the town interface is not built; run `npm install && npm run build` in frontend/"},
                status_code=503,
            )

    return app
