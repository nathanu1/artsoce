"""Convert the official Smallville data into this project's scenario files (spec A-1 … A-6, J-8).

Sources (joonspk-research/generative_agents @ fe05a71):

* ``environment/frontend_server/static_dirs/assets/the_ville/matrix/**``  → ``map/the_ville.json``
* ``environment/frontend_server/storage/base_the_ville_n25/**``           → ``agents/*.yaml``
* ``static_dirs/assets/the_ville/agent_history_init_n25.csv``             → per-agent ``seeds``
* ``storage/base_the_ville_isabella_maria_klaus`` + ``agent_history_init_n3.csv`` → ``pilot3``

Seeds are split on ";" exactly like ``reverie.py:577-591``. Nothing is rewritten here; seed
policies (e.g. the candidacy clause in Jennifer Moore's history) are applied when a scenario
is loaded, so both the paper policy and the released data stay available and auditable.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import yaml

SOURCE_COMMIT = "fe05a71d3e4ed7d10bf68aa4eda6dd995ec070f4"
WORLD = "the Ville"

PARTY_PATTERNS = [r"valentine", r"\bparty\b"]
CANDIDACY_PATTERNS = [r"running for", r"run(ning)? in the upcoming", r"running in the upcoming", r"planning on running", r"thinking of running"]


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _read_layer(path: Path) -> list[str]:
    rows = list(csv.reader(path.open()))
    return [v.strip() for r in rows for v in r]


def _blocks(path: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    if not path.exists() or path.stat().st_size == 0:
        return out
    for r in csv.reader(path.open()):
        if r:
            out[r[0].strip()] = [x.strip() for x in r]
    return out


def _rle(values: list[int]) -> list[list[int]]:
    out: list[list[int]] = []
    for v in values:
        if out and out[-1][0] == v:
            out[-1][1] += 1
        else:
            out.append([v, 1])
    return out


def build_map(matrix_dir: Path) -> dict[str, Any]:
    meta = json.loads((matrix_dir / "maze_meta_info.json").read_text())
    w, h = int(meta["maze_width"]), int(meta["maze_height"])
    sb = _blocks(matrix_dir / "special_blocks/sector_blocks.csv")
    ab = _blocks(matrix_dir / "special_blocks/arena_blocks.csv")
    gob = _blocks(matrix_dir / "special_blocks/game_object_blocks.csv")
    slb = _blocks(matrix_dir / "special_blocks/spawning_location_blocks.csv")
    col = _read_layer(matrix_dir / "maze/collision_maze.csv")
    sec = _read_layer(matrix_dir / "maze/sector_maze.csv")
    are = _read_layer(matrix_dir / "maze/arena_maze.csv")
    gom = _read_layer(matrix_dir / "maze/game_object_maze.csv")
    spm = _read_layer(matrix_dir / "maze/spawning_location_maze.csv")
    assert len(col) == w * h, "collision layer size mismatch"

    sector_names: list[str] = [""]
    arena_names: list[str] = [""]
    object_names: list[str] = [""]
    spawn_names: list[str] = [""]
    idx_cache: dict[tuple[str, str], int] = {}

    def index(table: list[str], kind: str, name: str) -> int:
        key = (kind, name)
        if key not in idx_cache:
            table.append(name)
            idx_cache[key] = len(table) - 1
        return idx_cache[key]

    sec_l, are_l, obj_l, spawn_l = [], [], [], []
    for i in range(w * h):
        s_name = sb.get(sec[i], [""])[-1] if sec[i] != "0" else ""
        a_name = ab.get(are[i], [""])[-1] if are[i] != "0" else ""
        o_name = gob.get(gom[i], [""])[-1] if gom[i] != "0" else ""
        sp_name = slb.get(spm[i], [""])[-1] if spm[i] != "0" else ""
        sec_l.append(index(sector_names, "s", s_name) if s_name else 0)
        are_l.append(index(arena_names, "a", a_name) if a_name else 0)
        obj_l.append(index(object_names, "o", o_name) if o_name else 0)
        spawn_l.append(index(spawn_names, "p", sp_name) if sp_name else 0)
    return {
        "world": WORLD,
        "width": w,
        "height": h,
        "tile_px": int(meta.get("sq_tile_size", 32)),
        "source": {
            "repo": "joonspk-research/generative_agents",
            "commit": SOURCE_COMMIT,
            "dir": "environment/frontend_server/static_dirs/assets/the_ville/matrix",
        },
        "legend": {"sector": sector_names, "arena": arena_names, "object": object_names, "spawn": spawn_names},
        "layers": {
            "collision": _rle([0 if v == "0" else 1 for v in col]),
            "sector": _rle(sec_l),
            "arena": _rle(are_l),
            "object": _rle(obj_l),
            "spawn": _rle(spawn_l),
        },
    }


def read_history(csv_path: Path) -> dict[str, list[str]]:
    rows = list(csv.reader(csv_path.open()))
    out: dict[str, list[str]] = {}
    for row in rows[1:]:
        if not row:
            continue
        statements = [s.strip() for s in row[1].split(";")]
        out[row[0].strip()] = [s for s in statements if s]
    return out


def _flags(text: str) -> list[str]:
    """Flag statements that carry seeded event knowledge (sentence-level, conservative)."""

    flags = []
    if any(re.search(p, text, re.I) for p in PARTY_PATTERNS):
        flags.append("party_knowledge")
    for sentence in re.split(r"(?<=[.!?;])\s+", text):
        names_sam = re.search(r"\bsam\b", sentence, re.I)
        running = re.search(r"\brunning\b|\brun in\b|candida", sentence, re.I)
        own = re.search(r"\byou are (thinking of |planning on )?running|that you are running", sentence, re.I)
        if (names_sam and running) or own:
            flags.append("candidacy_knowledge")
            break
    return flags


def persona_spec(persona_dir: Path, seeds: list[str], tile: list[int] | None) -> dict[str, Any]:
    scratch = json.loads((persona_dir / "bootstrap_memory/scratch.json").read_text())
    spatial = json.loads((persona_dir / "bootstrap_memory/spatial_memory.json").read_text())
    name = scratch["name"]
    return {
        "id": slug(name),
        "identity": {
            "name": name,
            "first_name": scratch["first_name"],
            "last_name": scratch["last_name"],
            "age": scratch["age"],
            "innate": scratch["innate"],
            "learned": scratch["learned"],
            "currently": scratch["currently"],
            "lifestyle": scratch["lifestyle"],
            "living_area": scratch["living_area"],
            "daily_plan_req": scratch.get("daily_plan_req") or "",
        },
        "identity_flags": sorted({f for k in ("learned", "currently") for f in _flags(scratch[k] or "")}),
        "perception": {
            "vision_r": scratch["vision_r"],
            "att_bandwidth": scratch["att_bandwidth"],
            "retention": scratch["retention"],
        },
        "released_code": {
            "recency_w": scratch["recency_w"],
            "relevance_w": scratch["relevance_w"],
            "importance_w": scratch["importance_w"],
            "recency_decay": scratch["recency_decay"],
            "importance_trigger_max": scratch["importance_trigger_max"],
        },
        "initial_tile": tile,
        "seeds": [{"text": s, "flags": _flags(s)} for s in seeds],
        "spatial_memory": spatial,
    }


def import_official(src_root: Path, out_root: Path) -> dict[str, Any]:
    fs = src_root / "environment/frontend_server"
    matrix = fs / "static_dirs/assets/the_ville/matrix"
    n25_dir = out_root / "smallville_n25"
    (n25_dir / "agents").mkdir(parents=True, exist_ok=True)
    (n25_dir / "map").mkdir(parents=True, exist_ok=True)
    the_map = build_map(matrix)
    (n25_dir / "map/the_ville.json").write_text(json.dumps(the_map, separators=(",", ":")))

    audit: dict[str, Any] = {"source_commit": SOURCE_COMMIT, "scenarios": {}}
    for scen_name, base, history in (
        ("smallville_n25", "base_the_ville_n25", "agent_history_init_n25.csv"),
        ("pilot3", "base_the_ville_isabella_maria_klaus", "agent_history_init_n3.csv"),
    ):
        base_dir = fs / "storage" / base
        meta = json.loads((base_dir / "reverie/meta.json").read_text())
        env0 = json.loads((base_dir / "environment/0.json").read_text())
        hist = read_history(fs / "static_dirs/assets/the_ville" / history)
        target = out_root / scen_name
        (target / "agents").mkdir(parents=True, exist_ok=True)
        agent_ids = []
        scen_audit: dict[str, Any] = {"party_knowledge": [], "candidacy_knowledge": [], "seed_counts": {}}
        for name in meta["persona_names"]:
            tile = [env0[name]["x"], env0[name]["y"]] if name in env0 else None
            spec = persona_spec(base_dir / "personas" / name, hist.get(name, []), tile)
            assoc = json.loads((base_dir / "personas" / name / "bootstrap_memory/associative_memory/nodes.json").read_text())
            spec["base_memories_in_source"] = len(assoc)
            (target / "agents" / f"{spec['id']}.yaml").write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=120))
            agent_ids.append(spec["id"])
            scen_audit["seed_counts"][spec["id"]] = len(spec["seeds"])
            for kind in ("party_knowledge", "candidacy_knowledge"):
                where = [f"seed {i}" for i, s in enumerate(spec["seeds"]) if kind in s["flags"]]
                if kind in spec["identity_flags"]:
                    where.append("identity")
                if where:
                    scen_audit[kind].append({"agent": spec["id"], "where": where})
        scenario = {
            "name": scen_name,
            "description": f"Imported from {base} and {history}",
            "source": {
                "repo": "joonspk-research/generative_agents",
                "commit": SOURCE_COMMIT,
                "base": f"environment/frontend_server/storage/{base}",
                "history": f"environment/frontend_server/static_dirs/assets/the_ville/{history}",
            },
            "start": "2023-02-13T00:00:00",
            "seconds_per_step": meta["sec_per_step"],
            "map": "../smallville_n25/map/the_ville.json" if scen_name != "smallville_n25" else "map/the_ville.json",
            "agents": agent_ids,
            "agents_dir": "agents",
            "events": "../smallville_n25/events.yaml" if scen_name != "smallville_n25" else "events.yaml",
            "constraints": "../smallville_n25/constraints.yaml" if scen_name != "smallville_n25" else "constraints.yaml",
            "familiar_public_areas": "from each agent's official spatial_memory.json",
        }
        (target / "scenario.yaml").write_text(yaml.safe_dump(scenario, sort_keys=False, allow_unicode=True))
        audit["scenarios"][scen_name] = scen_audit
    (out_root / "import_audit.json").write_text(json.dumps(audit, indent=2))
    return audit
