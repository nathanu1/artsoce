# Smallville Lab: a Generative Agents reproduction

A runnable, inspectable reproduction of **Generative Agents: Interactive Simulacra of Human
Behavior** (Park et al., UIST 2023, [arXiv:2304.03442v2](https://arxiv.org/abs/2304.03442)),
built against the authors' released code
([joonspk-research/generative_agents](https://github.com/joonspk-research/generative_agents) @
`fe05a71`). Agents remember, retrieve, reflect, plan, react and talk in the original 140 × 100
Smallville map. The paper's two evaluations (matched-history interviews and end-to-end social
measures) and one extension (reflection on/off in independent runs) are implemented with
auditable evidence.

On top of it sits an optional **town game** (`ga play`): a cozy storybook-diorama town in the
browser where you chat with residents, build what they wish for and decorate the town, with every
resident thought coming from a local open-weight model through Ollama or LM Studio at no API cost.
See [Town game](#town-game-on-your-own-computer) and [`docs/game.md`](docs/game.md).

Every setting is tagged as **paper**, **released code**, **engineering choice** or
**extension** in [`docs/reproduction_spec.md`](docs/reproduction_spec.md), which also lists every
deviation.

> **What has actually been validated.** All of it runs offline with a deterministic mock model
> and hash embeddings: 177 Python tests and 25 front-end tests pass, a five-agent and a 25-agent
> two-day simulation complete, and evaluation, interviews, exports, replay, the viewer, a ten-run
> reflection experiment and the town game work on them. **No live model has been called**: no
> API credentials were available, and Ollama could not be installed in the build environment, so
> the local-model adapters were tested against a fake server that follows the documented API.
> Nothing here is evidence about how Claude-driven or open-weight agents behave. Mock runs are
> labeled MOCK everywhere; their outcomes are structural demonstrations, never research results.

## Setup

Python 3.11+. With [uv](https://docs.astral.sh/uv/) (lockfile included):

```bash
uv sync --extra dev --extra viewer          # add --extra anthropic --extra local-embeddings for live runs
source .venv/bin/activate
ga doctor                                    # checks config, scenario, prompts, providers, paper PDF
```

or with pip: `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev,viewer]"`.

Live runs read keys from the environment only (see `.env.example`): `ANTHROPIC_API_KEY` for the
Claude adapter, `OPENAI_API_KEY` for the optional OpenAI adapters. Nothing secret is written to
disk; run directories (`runs/`), caches and downloaded models are git-ignored. The paper PDF is
expected at `docs/2304.03442v2.pdf` (git-ignored; `ga doctor` checks its hash).

## Quick start (offline, about a minute)

```bash
ga run --config configs/offline_pilot_2day.yaml --run-id demo     # 5 agents, 13–15 Feb 2023, MOCK
ga evaluate --run-dir runs/demo                                   # diffusion, relationships, attendance, failures
ga interview --run-dir runs/demo --protocol configs/interviews_reference.yaml
ga serve --run-dir runs/demo                                      # http://127.0.0.1:8000
python examples/walkthrough.py                                    # one conversation → memory → retrieval → reflection → plan
```

A six-hour smoke run takes about five seconds: `ga run --config configs/offline_smoke.yaml`.

## Commands

| Command | What it does |
| --- | --- |
| `ga doctor [--config FILE]` | Validates the config, scenario audit, prompt templates, providers and keys, pricing file, paper PDF hash and disk. |
| `ga run --config FILE [--set key=value] [--max-steps N] [--until ISO] [--interventions FILE] [--actions FILE] [--yes]` | Bounded headless simulation. Live API configs print their limits and need `--yes` (local models do not). `--actions` plays a scripted town-game session. |
| `ga resume --run-dir DIR [--set budget.max_calls=N]` | Continues from the last checkpoint. Calls made after it are re-used from the ledger, not paid twice. |
| `ga replay --run-dir DIR [--out DIR]` | Re-executes a run from its recorded responses with **no model calls** and checks the state is identical. |
| `ga inspect-memory --run-dir DIR --agent ID --query TEXT [--at ISO] [--condition C] [--evidence MEMORY_ID]` | Retrieval with recency/importance/relevance components, "why #1 outranked #2", and reflection evidence trees. |
| `ga interview --run-dir DIR [--protocol FILE] [--snapshot final] [--condition C ...] [--ask TEXT --agent ID]` | Matched-history interviews (Appendix B) under memory masks, on clones of a snapshot. |
| `ga export-blinded --run-dir DIR --name N [--human-responses CSV]` | Blinded rating sheets, rubric and per-agent context for human raters; the key is kept separate. |
| `ga analyze-ratings --run-dir DIR --name N --ratings CSV` | TrueSkill, Kruskal–Wallis, Dunn, Holm (the authors' analysis) plus a labeled Friedman/Wilcoxon addition, on genuine rankings only. |
| `ga judge --run-dir DIR --name N` | Exploratory LLM judge, written to its own file; never reported as believability. |
| `ga evaluate --run-dir DIR` | §7 measures with memory-validated evidence and a Markdown report. |
| `ga experiment --protocol FILE [--measured-run DIR] [--execute] [--yes]` | Reflection extension: plans and projects usage by default; runs only with `--execute`. |
| `ga serve --run-dir DIR [--experiment DIR]` | Local read-only viewer and inspector. |
| `ga play --config FILE` / `--resume DIR` / `--replay DIR` `[--speed S] [--paused] [--open] [--port N]` | The town game (extension): a live town in the browser at http://127.0.0.1:8080, research inspector at `/inspector`. Replays make no model calls. |
| `ga export-demo --run-dir DIR --out DIR` | A recorded town as static files for the front end's demo build: a page that plays the recording (and its research inspector) in any browser, with no server and no model. |
| `ga export --run-dir DIR` | JSONL events, transcripts, retrieval traces and model calls; CSV memories, plans and usage; Markdown run report. |
| `ga prompt-examples --run-dir DIR [DIR ...] [--out DIR]` | One page per prompt template: source, information scope, output schema and the smallest recorded call exactly as sent and received (plus a repaired exchange, when there was one). |
| `ga import-scenario --source CHECKOUT` / `ga audit-scenario` | Rebuild scenario files from the official data (byte-identical) and audit seeds, knowledge scoping, spawn tiles and places. |

## Configurations

| File | Purpose |
| --- | --- |
| `configs/offline_smoke.yaml` | Five agents, one morning, MOCK. Seconds. |
| `configs/offline_pilot_2day.yaml` | Five agents, the full two days, MOCK. About a minute. |
| `configs/live_pilot.yaml` | Five agents, two days, `claude-opus-5-5` (low effort for classification tasks), local embeddings, budget ceilings, price table. |
| `configs/reference_n25.yaml` | All 25 agents, two days, live. Start only after a live pilot has been measured. |
| `configs/interviews_reference.yaml` | Appendix B interviews on the final snapshot, four conditions. |
| `configs/experiment_reflection.yaml` / `_mock.yaml` | Reflection on vs off, five matched seeds per condition (live / offline). |
| `configs/ollama_pilot.yaml` | Three agents, two days, `llama3.1:8b` and `nomic-embed-text` on a local Ollama. No API cost. |
| `configs/experiment_reflection_ollama.yaml` | The reflection extension on a local model. |
| `configs/town_mock.yaml` / `town_ollama.yaml` / `town_n25_ollama.yaml` | The town game: offline MOCK; three residents on Ollama (start here); all 25 residents on Ollama. |
| `configs/game/` | Town game content: six affinity themes, motifs and gifts, catalog, paints and templates, Town Pulse levels, the Town Square, resident looks, a demo action script. |
| `configs/defaults.yaml` | Every setting with its default, for reference. |
| `configs/pricing.yaml` | USD per million tokens from the [published pricing page](https://platform.claude.com/docs/en/about-claude/pricing), fetched 2026-10-05. Without it, cost is reported as "unpriced". |

Any value can be overridden with `--set`, for example
`--set scenario.population="[isabella_rodriguez, maria_lopez, klaus_mueller]"`.

## Going live

1. `uv sync --extra anthropic --extra local-embeddings`, export `ANTHROPIC_API_KEY`, then
   `ga doctor --config configs/live_pilot.yaml` until every line is `ok`.
2. Run a short slice and look at it:
   `ga run --config configs/live_pilot.yaml --set scenario.end=2023-02-13T09:00:00 --run-id live-slice --yes`,
   then `ga serve --run-dir runs/live-slice` and `ga export --run-dir runs/live-slice`.
3. Project the full run from the measured slice:
   `ga experiment --protocol configs/experiment_reflection.yaml --measured-run runs/live-slice`.
   Raise or lower the ceilings in the config accordingly. Budget exhaustion stops the run at the
   last checkpoint with status `budget_exhausted`; `ga resume` continues it.

For reference, the offline 25-agent two-day run made about 33,000 model calls with about 18M
input tokens estimated from the real prompts; live dialogue, thinking and plan lengths will
differ, so measure before you scale. The adapter's structured outputs, effort setting and
optional server-side refusal fallback follow the current Anthropic SDK, but have not been run
against the API from this project.

## Town game on your own computer

```bash
ga play --config configs/town_mock.yaml --open     # offline demo with the MOCK model, no downloads
```

For real resident minds at zero cost, install [Ollama](https://ollama.com/) and pull an
open-weight model (8 GB of RAM minimum for an 8B model, 16 GB comfortable):

```bash
ollama pull llama3.1:8b          # about 4.9 GB; mistral:7b (4.4 GB) or llama3:8b (4.7 GB) also work
ollama pull nomic-embed-text
ga doctor --config configs/town_ollama.yaml
ga play --config configs/town_ollama.yaml --open
```

This is the three-resident vertical slice (Isabella, Maria, Klaus); `configs/town_n25_ollama.yaml`
runs all 25 once the slice works well on your machine. LM Studio and llama.cpp work through the
OpenAI-compatible adapter (`providers.llm.kind: openai_compatible`, `base_url:
http://localhost:1234/v1`). `ga play --resume runs/<id>` continues a town and
`ga play --replay runs/<id>` replays it with no model calls.

In the town you can watch residents follow their own schedules and talk to each other, chat with
them, take on requests they generate from their own goals, give gifts, collect motifs, and build
and decorate (placement checks, snapping, paint, undo and redo, duplication, templates and
affinity feedback) while the Town Pulse grows through five levels. The notebook (N) holds
requests, collections, residents and the town; Look Around (L) lists what is nearby, so the
whole game can be played with the keyboard. The research inspector (`/inspector`) shows
memories, retrieval scores, plans, reflections, information diffusion and the provenance of every
model call; nothing in it is ever sent to residents. Game meters never enter a prompt either.
Design, rules and what each action does to a resident's memory: [`docs/game.md`](docs/game.md).

The front end lives in `frontend/` (React, Tailwind, Three.js). Its built bundle is committed, so
`ga play` needs no Node.js; to change it, `cd frontend && npm ci && npm run dev` (with `ga play`
running) and `npm run build`.

To share a town without a server, record it, build the demo page and export the recording into it
(`python examples/record_demo_town.py` makes the scripted morning used for the published demo):

```bash
cd frontend && npm run build:demo && cd ..
ga export-demo --run-dir runs/<id> --out frontend/dist-demo
python -m http.server -d frontend/dist-demo 8090     # open http://127.0.0.1:8090/demo.html
```

## How it works

```
perceive (square vision, same arena, attention bandwidth, retention)
   → memory stream (SQLite; importance 1–10 at creation; embeddings)
   → retrieve (0.995/hour recency + importance + cosine relevance, min-max normalized, α = 1)
   → reflect (summed importance > 150 → 3 questions → evidence-cited insights → trees)
   → plan (day plan → hour blocks → 5–15 min tasks just in time; replanned on reactions)
   → act (recursive location choice over the agent's own spatial memory → BFS path, one tile per step)
   → react / converse (one focal percept per step; turn-by-turn private dialogue)
```

* **Engine** (`simulation/engine.py`): each 10-second step freezes a snapshot, lets every agent
  perceive and decide against it, resolves conversations, then commits movement. Checkpoints,
  crash-safe resume, replay, budget rollback and snapshots for evaluation live here.
* **Gateway** (`providers/gateway.py`): every model call is validated against a JSON schema,
  repaired at most once, retried on transient errors and recorded in an exact-request ledger.
  Failures are recorded, never papered over with invented output.
* **Evaluation** (`evaluation/`): interviews on per-condition clones, claimed-versus-supported
  diffusion, mutual supported relationship density, physical attendance, failure taxonomy,
  rank statistics and the experiment runner.
* **Viewer** (`viewer/`): FastAPI and a no-build canvas front end. It plays recorded frames
  (pause, step, speed, timeline), and inspects plans, retrieval traces with score components,
  reflection evidence, conversations, social measures, interviews and experiments. It is read-only
  and never calls a model. Map artwork from the original project is not copied; sectors are drawn
  as labeled shapes from the official map layers.

[`docs/walkthrough.md`](docs/walkthrough.md) follows one conversation through memory, retrieval,
reflection and planning with real IDs and scores.
[`docs/experiment_protocol.md`](docs/experiment_protocol.md) is the evaluation and experiment
protocol. [`prompts/examples/`](prompts/examples/README.md) shows, for each of the 21 tasks, the
exact text a model receives and the schema its answer must fill.

## Main differences from the paper and the released code

The full list, with sources, is in the spec (§3 and §6). In short:

* the language and embedding models are configurable (no gpt-3.5-turbo or ada-002 assumption);
  outputs are validated JSON instead of free text;
* retrieval, reflection and seeding follow the paper by default, with the released code's
  different choices (weights 0.5/3/2, positional recency, countdown trigger, LLM-rewritten seeds)
  available as compatibility modes;
* Jennifer Moore's seeded knowledge of Sam's candidacy is dropped by default, because the paper
  says only Sam knew (switchable);
* steps are snapshot-based rather than sequential; opening hours, one-person bathrooms and private
  rooms can be enforced (`constraints.policy: strict-v1`), which the paper did not do;
* agents react to object and ambient events (the paper's burning stove), which the released code
  does not;
* nothing is fabricated when a model call fails: the action, plan or conversation fails visibly.

## Tests

```bash
pytest             # 177 tests, offline, about 30 seconds
ruff check src tests examples
cd frontend && npm ci && npm test && npm run typecheck   # 25 front-end unit tests
```

They cover the mechanisms that could invalidate an experiment: the recency formula and
normalization edge cases, token-budgeted selection and access times; memory isolation and
evaluator-only ground truth never reaching a prompt; the reflection trigger boundary, evidence
validity and malformed output; plan validation, just-in-time decomposition, replanning, midnight
and idempotent completion; private dialogue, reservation and limits; pathfinding, perception and
constraints; the burning stove, occupied bathroom, empty fridge, nearby friend and street fire
scenarios; checkpoint/resume and replay equivalence; interview masks and side effects; toy
examples for diffusion, density and attendance; budgets and failures; the local-model adapters
against a fake Ollama server; the town game's placement rules, memory channels, meters kept out of
prompts, replay and crash resume. Tests prove structure, not believable behavior.

One test checks that `prompts/examples/` matches the current templates. After changing a template,
regenerate the examples (about two minutes):

```bash
rm -rf runs/examples-main runs/examples-compat runs/examples-game
ga run --config configs/offline_pilot_2day.yaml --run-id examples-main
ga evaluate --run-dir runs/examples-main
ga interview --run-dir runs/examples-main --protocol configs/interviews_reference.yaml
ga judge --run-dir runs/examples-main --name appendix_b
ga run --config configs/offline_smoke.yaml --run-id examples-compat \
  --set scenario.seed_rendering=inner_thought_llm --set architecture.post_conversation_inferences=true
ga run --config configs/town_mock.yaml --run-id examples-game --actions configs/game/demo_actions.jsonl \
  --set scenario.start=2023-02-13T10:00:00 --set scenario.end=2023-02-13T11:00:00
rm -r prompts/examples && ga prompt-examples --run-dir runs/examples-main runs/examples-compat runs/examples-game --out prompts/examples
```

## Layout

```
src/generative_agents/   config, schemas, db, prompting, cli
  providers/             gateway, ledger, Anthropic/OpenAI/Ollama/OpenAI-compatible adapters, mock, embeddings, pricing
  memory/                store, retrieval, traces, evidence, masks, seeds
  cognition/             importance, summary, reflection, planning, location, reaction, dialogue
  world/                 map tree, spatial memory, perception, navigation, state, constraints
  simulation/            clock, engine, runtime, budget, state, exports
  scenario/              importer, loader, audit
  evaluation/            interviews, banks, diffusion, relationships, attendance, failures, stats, experiment
  viewer/                FastAPI app and static front end
  game/                  town game extension: content, affinity, placement, action log, live session, API
    web/                 built town front end (generated by frontend/, committed)
frontend/                town front end source: React, Tailwind, Three.js (npm run build)
prompts/                 23 versioned prompt templates (front matter names the source of each)
  examples/              one recorded input/output per template (MOCK outputs; see its README)
scenarios/               imported Smallville data: smallville_n25, pilot3, pilot5
configs/                 example configurations, Appendix B question banks, game/ content
docs/                    reproduction spec, walkthrough, experiment protocol, town game
examples/                walkthrough.py, record_demo_town.py
tests/
```

## Ethics and attribution

These agents are simulated characters. Behavior that looks plausible in Smallville does not
establish validity for real people or populations. The viewer and every report label mock,
replayed and live runs, and no human evaluation is claimed or simulated: human answers and
ratings can only be imported.

Persona text, history statements and map matrices come from the authors' released project
(Apache-2.0, © 2023 Joon Sung Park); prompt wording adapts the released templates. See `NOTICE`
and `third_party/generative_agents/LICENSE`.
