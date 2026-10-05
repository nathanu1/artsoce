"""Local, read-only viewer and inspector (prompt §12).

``ga serve --run-dir DIR`` serves a single-page app that plays back recorded frames and
inspects memories, retrieval traces, reflections, plans and conversations. It never writes
to the run and never calls a model; what it shows is for the researcher only and is never
fed back into agent prompts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .data import RunData

STATIC = Path(__file__).parent / "static"


def create_app(run_dir: Path, experiment_dir: Path | None = None) -> FastAPI:
    data = RunData(run_dir)
    app = FastAPI(title="Smallville Lab viewer", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    def guard(fn, *a: Any, **kw: Any) -> Any:
        try:
            return fn(*a, **kw)
        except KeyError as exc:
            raise HTTPException(404, f"not found: {exc}") from exc

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/run")
    def run() -> dict[str, Any]:
        info = data.run_info()
        info["has_evaluation"] = (data.run_dir / "exports" / "evaluation" / "summary.json").exists()
        info["has_experiment"] = experiment_dir is not None
        return info

    @app.get("/api/map")
    def map_() -> JSONResponse:
        return JSONResponse(data.map_payload(), headers={"Cache-Control": "max-age=3600"})

    @app.get("/api/frames")
    def frames(start: int = Query(-1), end: int = Query(...)) -> dict[str, Any]:
        if end - start > 20000:
            raise HTTPException(400, "request at most 20000 steps at a time")
        return data.frames(start, end)

    @app.get("/api/timeline")
    def timeline(day: str | None = None) -> dict[str, Any]:
        return data.timeline(day)

    @app.get("/api/agent/{aid}")
    def agent(aid: str, step: int | None = None) -> dict[str, Any]:
        return guard(data.agent, aid, step)

    @app.get("/api/agent/{aid}/memories")
    def memories(aid: str, kind: str | None = None, q: str | None = None, limit: int = 60, before: str | None = None) -> list[dict[str, Any]]:
        return data.memories(aid, kind=kind, text=q, limit=min(limit, 500), before=before)

    @app.get("/api/agent/{aid}/traces")
    def traces(aid: str, limit: int = 40, before: str | None = None) -> list[dict[str, Any]]:
        return data.traces(aid, min(limit, 200), before)

    @app.get("/api/agent/{aid}/reflections")
    def reflections(aid: str) -> list[dict[str, Any]]:
        return data.reflections(aid)

    @app.get("/api/trace/{tid}")
    def trace(tid: str) -> dict[str, Any]:
        return guard(data.trace, tid)

    @app.get("/api/evidence/{mid}")
    def evidence(mid: str) -> dict[str, Any]:
        return data.evidence(mid)

    @app.get("/api/conversations")
    def conversations(agent: str | None = None) -> list[dict[str, Any]]:
        return data.conversations(agent)

    @app.get("/api/conversation/{cid}")
    def conversation(cid: str) -> dict[str, Any]:
        return guard(data.conversation, cid)

    @app.get("/api/events")
    def events(type: str | None = None, agent: str | None = None, limit: int = 200, after: int = 0) -> list[dict[str, Any]]:
        return data.events(type, agent, min(limit, 2000), after)

    @app.get("/api/evaluation")
    def evaluation() -> Any:
        return data.evaluation() or {}

    @app.get("/api/interviews")
    def interviews() -> dict[str, Any]:
        return data.interviews()

    @app.get("/api/experiment")
    def experiment() -> Any:
        if experiment_dir is None:
            return {}
        out: dict[str, Any] = {"dir": str(experiment_dir)}
        for name in ("summary.json",):
            p = experiment_dir / name
            if p.exists():
                out["summary"] = json.loads(p.read_text())
        p = experiment_dir / "runs.csv"
        if p.exists():
            import csv

            out["runs"] = list(csv.DictReader(p.open()))
        return out

    return app
