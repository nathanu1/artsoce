# Reproduction specification and fidelity map

This document maps every behavior this project implements to its source: a page of the paper, a
verified file in the released code, or an explicit decision of ours. It was written before the
main implementation and is updated as modules land. Section 9 tracks status.

**Bottom line.** This is a *documented reproduction with adaptations*, not an exact numerical
replication. The original model (gpt-3.5-turbo with `text-davinci-002/003` helpers) and embedding
model (`text-embedding-ada-002`) are not used. Prompt formatting changes to validated JSON. The
pilot population is a subset. Tick, constraint and observation policies are stated choices.

## 0. Sources

| Source | Identity | How it was used |
| --- | --- | --- |
| Paper | Park et al., *Generative Agents: Interactive Simulacra of Human Behavior*, UIST '23, arXiv:2304.03442**v2** (6 Aug 2023), 22 pages. Local copy `docs/2304.03442v2.pdf`, SHA-256 `1b31e77fb24d25d7598f2c49e955d12a28b95a6dabad34acdac40f44bfb7a139`. | All 22 pages read: extracted text plus visual inspection of Figures 2, 3, 4, 5, 6, 7, 8 and 9, the retrieval formula and Appendices A and B. The PDF is git-ignored; `ga doctor` checks its hash. |
| Released code | `joonspk-research/generative_agents` at commit `fe05a71d3e4ed7d10bf68aa4eda6dd995ec070f4` (the commit named in the build prompt), Apache-2.0, © 2023 Joon Sung Park. | Read: `reverie/backend_server/{reverie.py, maze.py, path_finder.py}`, `persona/{persona.py, cognitive_modules/*, memory_structures/*}`, `persona/prompt_template/{run_gpt_prompt.py, gpt_structure.py}` and the `v1/`, `v2/`, `v3_ChatGPT/`, `safety/` templates they load. Scenario data: `environment/frontend_server/storage/base_the_ville_n25/` and `base_the_ville_isabella_maria_klaus/` (`reverie/meta.json`, every persona's `scratch.json`, `spatial_memory.json`, `associative_memory/`, `environment/0.json`), `static_dirs/assets/the_ville/{agent_history_init_n25.csv, agent_history_init_n3.csv, matrix/**}`. |
| Game art | Tilesets and sprites credited in the official README to PixyMoon, LimeZu and ぴぽ. | **Not copied.** Their license is separate from the code's. The viewer draws labeled simple shapes laid out from the official sector matrix. |

Reused data (persona text, history CSVs, map matrices) and prompt wording adapted from the
released templates are covered by the Apache-2.0 license; see `NOTICE` and
`third_party/generative_agents/LICENSE`.

### Fidelity classes used throughout

| Tag | Class | Meaning |
| --- | --- | --- |
| **P** | Paper-reported | Stated in the paper; page cited. |
| **C** | Released-code behavior | Verified in the released code; file and line cited (paths relative to `reverie/backend_server/` unless noted). |
| **E** | Our engineering choice | Not specified by either source, or deliberately changed; kept identical across experimental conditions. |
| **X** | Experimental extension | Goes beyond the paper (new analyses, the reflection experiment, extra probes). |

Every run manifest records the active value and class of each setting in section 5.

## 1. Reading map (page numbers refer to the supplied PDF)

| Paper location | What it specifies here |
| --- | --- |
| §3.1, p. 5 | One-paragraph authored identity per agent; each semicolon-delimited phrase becomes an initial memory. |
| §3.1.1, p. 5 | Agents output a natural-language action each step; emoji rendering (not reproduced, see D-12). |
| §3.1.2, p. 6 | User persona interviews; "inner voice" directives. |
| §3.2, p. 6 | Smallville affordances; object states (bed occupied, empty refrigerator); users rewrite object status (`<Isabella's apartment: kitchen: stove> is burning`); burning stove and leaking shower reactions. |
| §3.3–3.4, pp. 6–7 | Day in the life; information diffusion; relationship memory; coordination (party 5–7 pm on 14 Feb, five agents arrive). |
| §4, p. 8; Fig. 5 | Perceive → memory stream → retrieve → act; plan and reflect feed back into the stream. |
| §4.1, pp. 8–9; Fig. 6 | Memory objects (description, creation time, last-access time); recency 0.995 per sandbox hour since last retrieval; LLM importance 1–10 at creation; cosine relevance; min-max normalization to [0, 1]; all α = 1; top-ranked memories that fit the context window. |
| §4.2, pp. 9–10; Fig. 7 | Reflection when summed importance of latest perceived events exceeds 150; 100 most recent records → 3 questions → retrieval per question → 5 insights citing evidence; reflections recurse into trees. |
| §4.3, pp. 10–11 | Plan entries have location, start time, duration; day plan of 5–8 chunks from summary plus previous-day summary; recursive decomposition to hour then 5–15 minute chunks; plans are stored in the memory stream. |
| §4.3.1, p. 11 | Each step: perceive, store, decide continue vs react; context summary from two queries; regenerate the plan from the reaction time. |
| §4.3.2, pp. 11–12 | Dialogue conditioned on each speaker's memory about the other; turn by turn until one ends it. |
| §5, p. 12 | Server JSON state; agents receive everything inside a preset visual range. |
| §5.1, pp. 12–13 | World tree; private, possibly stale subgraphs; initial knowledge of living quarters, workplace and commonly visited stores; recursive location prompt preferring the current area; path algorithms; LLM-proposed object state. |
| §6, pp. 13–15; Fig. 8 | Interviews in five categories; end of two game days; four memory conditions plus crowdworkers on the same history; 100 evaluators; TrueSkill, Kruskal–Wallis, Dunn, Holm; results and failure examples. |
| §7, pp. 15–17; Fig. 9 | Diffusion questions; affirmative answers verified against memory; "Do you know of <name>?" at start and end; mutual-knowledge density; attendance; reported numbers; boundary errors. |
| §8, pp. 17–18 | Cost (thousands of dollars, multiple days), short horizon, model biases, ethics (disclosure, logging). |
| App. A, p. 21 | Cached summary from three retrievals plus name, age and traits; just-in-time decomposition; sequential execution (1 s real ≈ 1 min game). |
| App. B, pp. 21–22 | The 25 interview questions; placeholder rules (random interacted-with agents; most-frequent interaction partners). |

## 2. Requirements map

Columns: **Req** (ID), **Behavior**, **Source**, **Class**, **Implementation**, **Tests**, **Deviation or note**.
Implementation paths are relative to `src/generative_agents/`; tests to `tests/`.

### 2A. Agents and seeding

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| A-1 | Stable agent ID, name, age, innate traits, learned traits, current status, lifestyle, living area, daily requirement. | p. 5; `scratch.json` fields; `scratch.py:382-414` (identity stable set) | P, C | `schemas.py` `AgentIdentity`; `scenario/importer.py` | `test_scenario_import.py` | IDs are slugs (`isabella_rodriguez`); names unchanged. |
| A-2 | Each semicolon-delimited history phrase becomes one initial memory. | p. 5; p. 12; `reverie.py:577-591` | P, C | `scenario/importer.py` `split_seed_statements` | `test_scenario_import.py::test_seed_split_*` | Seeds are tagged `seed=True`, type observation, with the original statement retained. |
| A-3 | Seed rendering. Code rewrites each phrase into a third-person "inner thought" with an LLM and stores it as a *thought* (`converse.py:239-254`). | `converse.py:239-254`, `v2/whisper_inner_thought_v1.txt` | C | `memory/seeds.py`, `seed_rendering: verbatim` (default) or `inner_thought_llm` | `test_seeds.py` | Default keeps the authored text verbatim (paper p. 5 says phrases are *entered* as memories). The code path is available and labeled. |
| A-4 | Loading the base scenario alone is not the intended state; the history CSV must also be loaded exactly once. | `base_the_ville_n25/personas/*/associative_memory/nodes.json` are `{}` | C | `scenario/importer.py` refuses double import (seed hash ledger) | `test_scenario_import.py::test_no_duplicate_seeds` | |
| A-5 | Party seeded only to Isabella; candidacy only to Sam. | p. 15 (§7.1.1: "known only by their respective originators") | P | `scenario/audit.py` | `test_scenario_audit.py` | **Conflict:** the released n25 CSV tells Jennifer Moore that Sam plans to run. Default `candidacy_seed_policy: paper_originator_only` drops that one clause and records it; `released_csv` keeps it. See D-3. |
| A-6 | Party end time 19:00. | p. 7 ("from 5 to 7 p.m. on February 14th") | P, C | `scenarios/smallville_n25/events.yaml` (evaluator-only) | `test_scenario_audit.py` | The n25 CSV says only "from 5pm"; Isabella's own `scratch.json` `currently` field says "from 5pm to 7pm", so the 19:00 end is agent-visible to Isabella only. |
| A-7 | Global event metadata (party window, candidacy) is for the engine and evaluator only, never in shared prompts. | spec §7; p. 7 | E | `scenario/loader.py` keeps `events` out of agent context; `cognition/context.py` builds prompts only from agent-owned state | `test_isolation.py` | |

### 2B. Memory stream

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| B-1 | Memory = description + creation time + last-access time (simulation time). | p. 8 | P | `schemas.py` `Memory`; `memory/store.py` (SQLite) | `test_memory_store.py` | Extra fields: owner, type, importance, embedding metadata, source event or conversation, location, SPO triple, evidence, plan links. |
| B-2 | Types: observation, reflection, plan; seeds and conversation records tagged. | pp. 8–11; code types event, thought, chat (`associative_memory.py:15-40`) | P, C | `schemas.MemoryKind`, `MemoryOrigin` | `test_memory_store.py` | Mapping: code *event* → observation; code *thought* → reflection or plan (code also stores seeds and daily plans as thoughts); code *chat* → conversation record. Statements heard are observations with `origin=statement` and a `speaker_id`. |
| B-3 | Originals are retained; summaries and reflections are added, never replacing. | p. 8 ("comprehensive record") | P | append-only store; updates only touch `last_accessed_at` | `test_memory_store.py::test_append_only` | No expiry. Code sets 30-day expirations (`reflect.py:124`) but nothing in the inspected path deletes them. |
| B-4 | A plan or intention is not proof of action; a statement is not world truth. | spec §3 | E | `MemoryOrigin` distinguishes `direct_observation`, `statement`, `inference`, `intention`, `executed_action` | `test_provenance.py` | |

### 2C. Retrieval

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| C-1 | `recency = 0.995 ** hours_since_last_access` (sandbox hours). | p. 9 | P | `memory/retrieval.py` `paper_scores` | `test_retrieval.py::test_recency_*` | Hours are fractional; negative gaps clamp to 0. |
| C-2 | Importance = stored integer. | p. 9 | P | same | same | |
| C-3 | Relevance = cosine(embedding(memory), embedding(query)). | p. 9 | P | `memory/retrieval.py` `cosine_matrix` | `test_retrieval.py::test_cosine_*` | Zero-norm vectors give cosine 0 and are flagged in the trace. |
| C-4 | Min-max normalize each component to [0, 1] over the candidates. | p. 9 | P | `normalize_minmax` | `test_retrieval.py::test_normalization_*` | Constant component → 0.5 for every candidate; same constant as `retrieve.py:99`. |
| C-5 | `score = α_r·r + α_i·i + α_v·v`, all α = 1. | p. 9 | P | `RetrievalWeights` | `test_retrieval.py::test_weights_*` | |
| C-6 | Return the top-ranked memories that fit the context window. | p. 9 | P | prefix of the ranking under `budget_tokens` and `max_items` | `test_retrieval.py::test_budget_*` | The paper names no universal top-k. Budget and count are explicit config (defaults in §5). Code uses `n_count` 30, 50 or 15 per call site. |
| C-7 | Scores for all candidates are computed before any access time changes; only delivered memories are touched. | spec §3 | E | `Retriever.retrieve(..., commit_access=True)` | `test_retrieval.py::test_access_update_only_delivered` | Code updates the selected top-n (`retrieve.py:266-267`). |
| C-8 | Deterministic tie-break: score ↓, last access ↓, creation ↓, ID ↑. | spec §3 | E | `rank_candidates` | `test_retrieval.py::test_ties_deterministic` | |
| C-9 | Released-code compatibility mode: weights 0.5 / 2 / 3 for recency / importance / relevance times per-agent weights; recency `decay ** position` over candidates sorted by last access ascending; drop `idle` memories. | `retrieve.py:199-268` (`gw = [0.5, 3, 2]` at :244 in the order recency, relevance, importance; positional powers at :145; idle filter at :226) | C | `memory/retrieval.py` `compat_scores` | `test_retrieval.py::test_compat_*` | Positional powers rank the *oldest* access highest (verified in a test). Not equivalent to elapsed-time decay. |
| C-10 | Second retrieval entry point: keyword match on the perceived event's subject, predicate and object, unscored, used for reaction context. | `retrieve.py:16-45`, `associative_memory.py:304-322`; called from `persona.py:221` | C | `memory/retrieval.py` `keyword_lookup` (compat only) | `test_retrieval.py::test_keyword_lookup` | Paper mode uses scored retrieval for reaction context with the two §4.3.1 queries. |
| C-11 | Store retrieval traces: query, filters, raw and normalized components, weights, selected IDs, scores, tokens. Explain why A outranked B. | spec §3 | E | `memory/trace.py`; `ga inspect-memory` | `test_retrieval.py::test_trace_*`, `test_cli.py` | |

### 2D. Importance

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| D-1 | LLM integer 1–10 at creation, anchored by mundane vs poignant examples. | p. 9 (prompt quoted) | P | `prompts/importance.v1.md` → `cognition/importance.py` | `test_importance.py` | Output is JSON `{"rating": int}`; range validated. |
| D-2 | Separate anchors for conversations and thoughts. | `v3_ChatGPT/poignancy_chat_v1.txt`, `poignancy_thought_v1.txt` | C | `kind`-specific anchor text in the same template | `test_importance.py` | |
| D-3 | Memories ending "is idle" score 1 without a call. | `perceive.py:15-17` | C | `importance.idle_shortcut` (default on) | `test_importance.py::test_idle_shortcut` | Applied identically in every condition. |
| D-4 | Bounded retries; cache only exact repeats; log invalid output. | spec §3 | E | `providers/gateway.py` | `test_gateway.py` | |
| D-5 | Reflections and plans are scored the same way but do not feed the perception trigger. | p. 10; `perceive.py:178` (only perceived events decrement the counter) | P, C | `cognition/reflection.py` trigger accounting | `test_reflection.py::test_reflections_do_not_feed_trigger` | |

### 2E. Reflection

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| E-1 | Trigger when summed importance of newly perceived events **exceeds** 150 (strict `>`). | p. 10 | P | `ReflectionTrigger(mode="paper", threshold=150)` | `test_reflection.py::test_trigger_boundary` | |
| E-2 | Compat trigger: countdown from `importance_trigger_max` fires at `<= 0`. | `reflect.py:152-168`; n25 `scratch.json` has `importance_trigger_max: 250`; n3 base has 150; class default 150 (`scratch.py:61`) | C | `ReflectionTrigger(mode="released_code")` | `test_reflection.py::test_compat_trigger` | |
| E-3 | Question prompt sees the 100 most recent records (or all, if fewer). | p. 10 | P | `reflection.recent_records(n=100)` | `test_reflection.py::test_recent_window` | Code uses the last `importance_ele_n` records by last access, excluding idle (`reflect.py:23-34`); available in compat mode. |
| E-4 | Three salient high-level questions. | p. 10; `v3_ChatGPT/generate_focal_pt_v1.txt` | P, C | `prompts/reflection_questions.v1.md` | `test_reflection.py` | |
| E-5 | Each question is a retrieval query; five insights per question citing supplied memory IDs. | p. 10; `v2/insight_and_evidence_v1.txt`; `reflect.py:110-131` | P, C | `prompts/reflection_insights.v1.md` | `test_reflection.py::test_insights_cite_supplied` | Citations use short handles mapped back to IDs. |
| E-6 | Evidence validation: exists, same owner, was supplied in that prompt, no cycles. | spec §4 | E | `memory/evidence.py` | `test_evidence.py` | Code drops parse failures to `{"this is blank": "node_1"}` (`reflect.py:47-53`); we record the failure instead. |
| E-7 | Reflections may cite reflections → trees; depth = 1 + max evidence depth. | p. 10; `associative_memory.py:207-212` | P, C | `Memory.depth` | `test_evidence.py::test_depth` | |
| E-8 | Reset the accumulator only after the batch is stored. | spec §4; `reflect.py:262-264` | E, C | `ReflectionEngine.run` | `test_reflection.py::test_reset_after_success` | Failed batches keep the accumulator, retry after a cooldown, and are recorded. |
| E-9 | "Two or three reflections a day" is an outcome, not a quota. | p. 10 | P | not enforced | `test_reflection.py::test_no_quota` | Test fixtures may lower the threshold and say so. |
| E-10 | Post-conversation "planning thought" and "memo" inferences. | `reflect.py:186-245` | C | `dialogue.post_conversation_inferences` (compat only) | `test_dialogue.py` | Off in paper mode. Counted as reflection-generating and disabled in the reflection-off experiment (R-2). |

### 2F. Dynamic summary (Appendix A)

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| F-1 | Retrieve and summarize "[name]'s core characteristics", "[name]'s current daily occupation", "[name]'s feeling about his recent progress in life"; concatenate with name, age, traits. | p. 21 | P | `cognition/summary.py` | `test_summary.py` | Pronoun in the third query adapted to the agent ("their"). |
| F-2 | Refresh interval or invalidation policy. | p. 21 ("at regular intervals") | E | `summary.refresh: {every_sim_minutes: 180, on_new_day: true}` | `test_summary.py::test_refresh_policy` | |
| F-3 | Summaries use only permitted memories; recomputed per evaluation condition. | spec §4, §8 | E | cache key includes the memory mask | `test_ablation.py::test_summary_cache_isolation` | Code uses the static identity block (`scratch.py:382`) in most prompts; the paper's cached summary is used here. |

### 2G. Planning

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| G-1 | Day plan of 5–8 broad chunks from identity, summary and previous-day summary. | p. 11 | P | `prompts/day_plan.v1.md`; `cognition/planning.py` | `test_planning.py` | Code asks for 4–6 items on later days (`plan.py:448-452`). |
| G-2 | Previous-day summary. | p. 11; `plan.py:408-458` (`revise_identity`) | P, C | `planning.previous_day_summary` | `test_planning.py` | Built from the agent's own retrieved memories. |
| G-3 | Decompose to hourly activities, then 5–15 minute actions. | p. 11 | P | `prompts/hourly_schedule.v1.md`, `prompts/decompose.v1.md` | `test_planning.py::test_hierarchy_links` | Code generates the hourly schedule one hour per call with a diversity retry (`plan.py:71-144`); we use one call and validate. |
| G-4 | Fine-grained decomposition just in time for the near future. | p. 21 | P | decompose current block and the block 60 minutes ahead | `test_planning.py::test_jit_window` | Same window as `plan.py:556-595`. |
| G-5 | Sleep blocks are not decomposed. | `plan.py:533-549` | C | `planning.should_decompose` | `test_planning.py` | |
| G-6 | Each entry: location, start, duration, description, status, parent. | p. 11 | P | `schemas.PlanItem` | `test_planning.py` | Locations are resolved recursively when the entry starts (J-4). |
| G-7 | Validation: 24 h coverage, positive durations, order, no overlap, midnight. Raw output and repair trace kept; no fabricated plan. | spec §5 | E | `planning.validate_schedule` | `test_planning.py::test_validation_*` | Code pads a missing remainder with "sleeping" (`plan.py:614`); we repair once with the validator's message, then record failure. |
| G-8 | Plans are stored in the memory stream. | p. 11; `plan.py:499-515` (poignancy fixed at 5) | P, C | day and hour plans become plan memories | `test_planning.py::test_plans_in_stream` | Importance comes from the LLM like other memories (D-5), not the fixed 5. |
| G-9 | Completed history preserved; a finished action never re-runs because a tick passed. | spec §5 | E | `PlanItem.status` transitions | `test_planning.py::test_idempotent_completion` | |

### 2H. Reacting and replanning

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| H-1 | Each step: perceive, store new observations, decide continue or react. | p. 11 | P | `simulation/engine.py` | `test_engine.py` | |
| H-2 | Context summary from "What is [observer]'s relationship with [observed]?" and "[observed] is [action]". | p. 11 | P | `cognition/context.py` `interaction_context` | `test_reaction.py` | |
| H-3 | Regenerate the plan from the reaction time; keep the past. | p. 11; `plan.py:806-880` | P, C | `planning.replan_from` | `test_planning.py::test_replan_preserves_history` | |
| H-4 | React to object events (burning stove, leaking shower, empty fridge). | p. 6 | P | `cognition/reaction.py` handles agent and object events | `test_reaction.py::test_burning_stove` etc. | **Code reacts only to agent events** (`plan.py:796`). |
| H-5 | Wait when an occupied resource blocks the action. | `plan.py:741-772`, `v2/decide_to_react_v1.txt` | C | reaction option `wait` | `test_reaction.py::test_occupied_bathroom` | |
| H-6 | No new conversation while either party sleeps, after 23:00, or within the cooldown. | `plan.py:715-738`; cooldown 800 steps (`plan.py:888,894`) | C | `ConversationPolicy` | `test_dialogue.py::test_policy_*` | Cooldown expressed in sim minutes (default 133 ≈ 800 × 10 s). |

### 2I. Dialogue

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| I-1 | Turn-by-turn; each utterance conditioned on the speaker's summarized memory about the partner, the intended reaction, and the transcript so far. | pp. 11–12 | P | `cognition/dialogue.py` | `test_dialogue.py::test_private_context` | |
| I-2 | Either speaker may end the conversation. | p. 12; `converse.py:139-176` | P, C | `{"utterance", "end_conversation"}` output | `test_dialogue.py::test_end` | |
| I-3 | Cap of 8 rounds (16 utterances). | `converse.py:130` | C | `dialogue.max_utterances: 16` | `test_dialogue.py::test_max_turns` | |
| I-4 | Duration `ceil((chars / 8) / 30)` minutes; both parties reserved. | `plan.py:290`, `plan.py:870-880` | C | `dialogue.duration_minutes` | `test_dialogue.py::test_reservation` | |
| I-5 | Partner learns what was said, never the speaker's private memory. | p. 12 | P | statements stored with `origin=statement`, `speaker_id` | `test_isolation.py::test_dialogue_private_memory` | |
| I-6 | No fabricated utterance on failure. | `run_gpt_prompt.py:2891-2895` returns "..." | E | conversation aborted and logged | `test_dialogue.py::test_failure_not_fabricated` | |
| I-7 | Observational transcript summary for each participant. | `v3_ChatGPT/summarize_conversation_v1.txt` | C | `conversation_summary` memory, `origin=direct_observation` | `test_dialogue.py` | Kept in the reflection-off condition (observational, not inferential). |

### 2J. World, perception, navigation

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| J-1 | Tree world → sector → arena → object. | p. 12; Fig. 2; `maze.py:19-205` | P, C | `world/hierarchy.py` | `test_world.py` | |
| J-2 | Private, possibly stale subgraph per agent; initial knowledge from the official `spatial_memory.json`. | p. 12 | P, C | `world/spatial_memory.py` | `test_world.py::test_private_subgraph` | |
| J-3 | Perception: square of `vision_r` tiles; events only in the agent's current arena; nearest `att_bandwidth`; skip triples seen in the last `retention` events. n25 values 8 / 8 / 8. | p. 12; `maze.py:286-325`; `perceive.py:44-104, 122-125` | P, C | `world/perception.py` | `test_perception.py` | |
| J-4 | Recursive destination choice over the known tree, preferring the current area; validated. | pp. 12–13 | P | `cognition/location.py` | `test_location.py` | Invalid answers get one repair; then the action fails visibly. |
| J-5 | Real pathfinding; one tile per step; no teleporting. | p. 13; `path_finder.py:96-178`; `execute.py:147-154` | P, C | `world/navigation.py` (4-neighbour BFS) | `test_navigation.py` | |
| J-6 | LLM proposes object state; engine applies it only at a valid, reached target. | p. 13 | P, E | `world/execution.py` | `test_execution.py` | Rejections are logged and perceived by the agent. |
| J-7 | Occupancy, ownership, capacity and opening hours from scenario data. | p. 17 (one-person bathroom, stores close ~5 pm) | E | `world/constraints.py`, policy `strict-v1` or `none` | `test_constraints.py` | The paper did not enforce these; enforcement is an adaptation, identical across conditions. |
| J-8 | The released map: 140 × 100 tiles, 32 px, from the official matrices. | `matrix/maze_meta_info.json` | C | `scenario/maze_import.py` | `test_scenario_import.py::test_maze_dimensions` | |

### 2K. Clock, ordering, persistence

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| K-1 | 10 simulated seconds per step; start Mon 13 Feb 2023 00:00:00. | `base_the_ville_n25/reverie/meta.json` | C | `simulation/clock.py` | `test_clock.py` | Paper prompt examples pair "February 13" with Wednesday (pp. 10–11); 13 Feb 2023 is a Monday, and the code computes weekdays from the date (`scratch.py:413`). We do the same. |
| K-2 | Snapshot → decide → resolve → commit, recorded agent order. | spec §6 | E | `simulation/engine.py` | `test_engine.py::test_order_independence` | Code updates agents sequentially in dict order and mutates partners mid-step (`reverie.py:373-385`, `plan.py:845-880`). |
| K-3 | Long unchanged actions avoid model calls. | spec §6 | E | decisions only on action end, new perception, or reaction | `test_engine.py::test_no_calls_while_sleeping` | Documented in the manifest as `observation_policy`. |
| K-4 | Checkpoint and resume without duplicating actions or memories; exact replay from stored responses. | spec §6, §11 | E | `simulation/checkpoint.py`, `providers/replay.py` | `test_checkpoint.py`, `test_replay.py` | |

### 2L. User interactions

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| L-1 | Interview an agent as an outside visitor, read-only. | p. 6; `converse.py:257-280` | P, C | `evaluation/interview.py` on a clone | `test_interview.py::test_no_side_effects` | Code's "analysis" mode still updates access times (`retrieve.py:266`); ours runs on a discarded clone. |
| L-2 | Inner-voice directive to one agent, logged as an intervention. | p. 6; `converse.py:283-296` | P, C | `simulation/interventions.py` `inner_voice` | `test_interventions.py` | |
| L-3 | Change one object's state. | p. 6 | P | `interventions.set_object_state` | `test_interventions.py` | |
| L-4 | Visitors cannot mutate state. | spec §5 | E | clone isolation | `test_interview.py` | |

### 2M. Controlled evaluation (§6, Appendix B)

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| M-1 | Run the full architecture two days, freeze, then interview isolated copies under four memory conditions. | pp. 13–14 | P | `evaluation/ablation.py` | `test_ablation.py` | |
| M-2 | Masks: full; no reflection; observations only; no memory stream. Static identity identical across conditions. | p. 13 | P | `memory/masks.py` | `test_ablation.py::test_masks_*` | Seeds count as observations. |
| M-3 | 25 verbatim questions, five per category; placeholders: random interacted-with agents (memory), most frequent partners (reflections). | pp. 21–22 | P | `evaluation/question_bank.py`, `configs/questions/appendix_b_reference.yaml`, `..._adapted.yaml` | `test_question_bank.py` | Reference bank keeps the original "she". |
| M-4 | Explicit interview clock; "today" resolves against simulation time. | spec §8 | E | `InterviewSpec.reference_time` | `test_interview.py::test_today_resolution` | |
| M-5 | Blinded randomized export; genuine human ratings import only. | pp. 13–14 | P, E | `evaluation/export.py`, `evaluation/human.py` | `test_export.py` | No human condition is ever simulated. |
| M-6 | TrueSkill, Kruskal–Wallis, Dunn, Holm. | p. 14 | P | `evaluation/stats.py` | `test_stats.py` | |
| M-7 | Friedman with paired Wilcoxon + Holm. | spec §8 | X | `evaluation/stats.py` | `test_stats.py` | Labeled as our addition. |
| M-8 | Optional LLM judge, exploratory only. | spec §8 | X | `evaluation/judge.py` | `test_export.py` | Never reported as believability. |

### 2N. End-to-end evaluation (§7)

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| N-1 | Ask everyone "Did you know there is a Valentine's Day party?" and "Do you know who is running for mayor?"; verify affirmative answers against memory. | p. 15 | P | `evaluation/diffusion.py` | `test_diffusion.py` | Claimed vs supported reported separately; transmission time, sender, receiver, conversation, details. |
| N-2 | "Do you know of <name>?" at start and end; edge iff both know; `η = 2|E| / (|V|(|V|−1))`. | pp. 15–16 | P | `evaluation/relationships.py` | `test_relationships.py` | `n < 2` → undefined (null). Affirmatives validated against seeds or interaction records. |
| N-3 | Count agents who actually showed up. | p. 16 | P | `evaluation/attendance.py` (engine positions in the window) | `test_attendance.py` | Exposure, invitation, intention, scheduled and arrival are separate variables; host excluded from the invited denominator. |
| N-4 | Failure categories with examples. | pp. 15–17 | P, E | `evaluation/failures.py` | `test_failures.py` | Categories from spec §9. |
| N-5 | Probes run on clones and never seed the town. | spec §9 | E | clone-based probes | `test_interview.py::test_no_side_effects` | |

### 2O. Providers, cost, provenance

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| O-1 | Central gateway: bounded retries, timeouts, validation, usage accounting, exact-request cache keys, record and replay. | spec §11 | E | `providers/gateway.py` | `test_gateway.py` | Cache keys include prompt, template version, model, settings, schema, agent and run. |
| O-2 | No cross-replicate reuse of stochastic samples. | spec §11 | E | cache scope = run ID for generation; global for embeddings | `test_gateway.py::test_cache_scope` | |
| O-3 | Budgets: calls, input and output tokens, runtime, optional cost; exhaustion checkpoints instead of fabricating. | spec §11 | E | `simulation/budget.py` | `test_budget.py` | Cost stays "unpriced" unless a price table is configured. |
| O-4 | Anthropic adapter; deterministic mock; optional OpenAI adapter; embeddings backends with recorded model and dimensions. | spec §2 | E | `providers/{anthropic_provider, mock, openai_provider, embeddings}.py` | `test_providers.py` | Mock embeddings are test fixtures only. |
| O-5 | Run manifest. | spec §11 | E | `simulation/manifest.py` | `test_manifest.py` | |

### 2R. Reflection extension

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| R-1 | Full architecture vs reflection disabled *throughout* independent simulations from identical authored worlds. | spec §10 | X | `evaluation/experiment.py`, `configs/experiment_reflection*.yaml` | `test_experiment.py` | |
| R-2 | Disable every reflection-generating path (trigger, questions, insights, post-conversation inferences); keep observational transcript summaries. | spec §10 | X | `ArchitectureFlags.reflection=False` | `test_experiment.py::test_no_reflection_paths` | |
| R-3 | Primary outcomes: supported event recall; attendance among invited guests. Report exposure, invitations, unsupported claims, calls, tokens, cost, runtime; include failed and truncated runs. | spec §10 | X | `evaluation/experiment.py` | `test_experiment.py` | Run is the unit of analysis. |

## 3. Paper vs released code: verified differences

| Item | Paper | Released code (verified) | Our default | Compat option |
| --- | --- | --- | --- | --- |
| Retrieval weights | α = 1, 1, 1 (p. 9) | `new_retrieve` multiplies recency 0.5, relevance 3, importance 2 by per-agent weights (`retrieve.py:244-249`); n25 agents have weights 1, 1, 1 | Paper | `retrieval.mode: released_code` |
| Recency | 0.995 per sandbox hour since last access (p. 9) | `decay ** i` for positions `i = 1..n` of nodes sorted by `last_accessed` ascending (`retrieve.py:145`, `:224-228`), so the oldest-accessed node gets the largest raw value. Decay 0.995 in all n25 files; class default 0.99 (`scratch.py:60`); the n3 base mixes 0.995 (Isabella) and 0.99 (Maria, Klaus) | Paper | yes |
| Candidate set | All memories | Events and thoughts whose embedding key lacks "idle" (`retrieve.py:224-226`); chats excluded | All memories | yes |
| Retrieval entry points | One scoring function | `new_retrieve` for reflection, conversation, interviews, identity revision; keyword `retrieve` for per-step reaction context | Scored retrieval everywhere | keyword lookup available |
| Reflection input | 100 most recent records (p. 10) | last `importance_ele_n` records by last access, idle excluded (`reflect.py:23-34`) | Paper | yes |
| Reflection trigger | Summed importance > 150 (p. 10) | Countdown from `importance_trigger_max` fires at `<= 0`, then resets (`reflect.py:152-168`); n25 files set 250, n3 base 150 | Paper (> 150) | yes |
| Seed memories | Phrases entered as memories (p. 5) | LLM rewrites each phrase, stored as a thought (`converse.py:239-254`) | Verbatim, typed as observation | `seed_rendering: inner_thought_llm` |
| Object-event reactions | Burning stove, leaking shower (p. 6) | Only agent events can trigger a reaction (`plan.py:796`) | Agent and object events | — |
| Conversation inferences | Not described | Planning thought + memo after each chat (`reflect.py:186-245`) | Off | on in compat |
| Failure handling | Not described | Fail-safe outputs, e.g. "..." utterance (`run_gpt_prompt.py:2893`), "error" strings (`gpt_structure.py:88-169`) | Record failure; never fabricate | — |
| Interview side effects | Not described | "analysis" mode is stateless for memory but updates access times through `new_retrieve` | Clone, then discard | — |
| Update order | Not described | Sequential per agent; a conversation edits the partner mid-step (`reverie.py:373-385`) | Snapshot / decide / commit | — |
| Weekday | Prompt examples pair Feb 13 with Wednesday (pp. 10–11) | `strftime('%A')` gives Monday | Computed from date | — |

## 4. Scenario fidelity (verified data audit)

* `base_the_ville_n25/reverie/meta.json`: start `February 13, 2023, 00:00:00`, `sec_per_step: 10`,
  25 personas, maze `the_ville`.
* All 25 n25 `scratch.json` files share: `vision_r 8`, `att_bandwidth 8`, `retention 8`,
  `recency_w = relevance_w = importance_w = 1`, `recency_decay 0.995`,
  `importance_trigger_max 250`. Associative memories are empty; the history CSV supplies seeds.
* Party knowledge: only Isabella (CSV seed "planning a Valentine's Day party at *Hobbs Cafe on
  February 14th from 5pm*"; `scratch.json` `currently` "from 5pm to 7pm").
* Candidacy knowledge: Sam (CSV and `currently`) **and Jennifer Moore** (CSV: "You know Sam Moore,
  your husband, is planning on running for the local mayor election ..."). Seven agents are seeded
  as *curious* about the election without knowing a candidate (Latoya, Giorgio, John, Tom, Yuriko,
  Adam, Carmen); that is not candidacy knowledge.
* Maria's authored crush on Klaus is preserved (CSV, both n3 and n25).
* `base_the_ville_isabella_maria_klaus` (official starter): 3 personas, `importance_trigger_max 150`,
  and its own n3 history CSV, which differs from the n25 statements for the same people.
* Initial positions come from `environment/0.json`.
* Map: 140 × 100 tiles; sectors, arenas, objects and collisions from `matrix/**`.

## 5. Settings registry (defaults)

| Setting | Default | Class | Source |
| --- | --- | --- | --- |
| `retrieval.mode` | `paper` | P | p. 9 |
| `retrieval.weights` | 1 / 1 / 1 | P | p. 9 |
| `retrieval.decay_per_hour` | 0.995 | P | p. 9 |
| `retrieval.equal_component_value` | 0.5 | C | `retrieve.py:99` |
| `retrieval.budget_tokens` / `max_items` | 1200 tokens / 30 items, per call site overrides | E | code uses 30, 50, 15 |
| `importance.idle_shortcut` | true | C | `perceive.py:15-17` |
| `reflection.mode` / `threshold` | `paper` / 150, strict `>` | P | p. 10 |
| `reflection.recent_records` | 100 | P | p. 10 |
| `reflection.questions` / `insights_per_question` | 3 / 5 | P | p. 10 |
| `summary.refresh` | every 180 sim minutes and each new day | E | p. 21 says "regular intervals" |
| `planning.day_chunks` | 5–8 | P | p. 11 |
| `planning.task_minutes` | 5–15 | P | p. 11 |
| `planning.jit_window_minutes` | 60 | C | `plan.py:556-595` |
| `perception.vision_r` / `att_bandwidth` / `retention` | 8 / 8 / 8 (n25) | C | n25 `scratch.json` |
| `dialogue.max_utterances` | 16 | C | `converse.py:130` |
| `dialogue.cooldown_minutes` | 133 | C | 800 steps × 10 s (`plan.py:888`) |
| `dialogue.post_conversation_inferences` | false (paper) / true (compat) | C | `reflect.py:186-245` |
| `clock.seconds_per_step` | 10 | C | `meta.json` |
| `constraints.policy` | `strict-v1` | E | p. 17 motivates it |
| `seed_rendering` | `verbatim` | P, E | p. 5 |
| `candidacy_seed_policy` | `paper_originator_only` | P | p. 15 |

## 6. Deviations and adaptations

* **D-1 Model.** Configurable provider and model; nothing is the original gpt-3.5-turbo or
  text-davinci stack. Exact model IDs and served models are recorded per call.
* **D-2 Embeddings.** No `text-embedding-ada-002` assumption. Backends: OpenAI API, local
  sentence-transformers, or `mock-hash-256` test fixtures (lexical hashing, not semantic).
* **D-3 Candidacy seed.** Jennifer Moore's clause removed under the default policy (A-5).
* **D-4 Structured outputs.** Every task returns JSON validated against a schema. Prompt meaning and
  information scope follow the paper and released templates; wording is versioned in `prompts/`.
* **D-5 Batched calls.** Location choice may combine sector and arena in one call; action grounding
  combines event triple and object-state proposal; statements heard in one conversation are scored
  in one batched importance call. Each batch keeps per-item validation.
* **D-6 Ordering.** Snapshot / decide / commit instead of sequential mutation (K-2).
* **D-7 Constraints.** Opening hours, capacity and ownership enforced under `strict-v1` (J-7).
* **D-8 Population.** Pilot runs use documented subsets (`scenarios/pilot3`, `scenarios/pilot5`).
* **D-9 Tick.** Reference 10 s; coarser pilot ticks are labeled in the manifest.
* **D-10 Viewer.** Simple shapes instead of the original art.
* **D-11 Interviews.** Clones instead of the live process; matched-history design as in the paper.
* **D-12 Emoji.** The emoji rendering of actions (p. 5) is not reproduced; the viewer shows text.
* **D-13 Hourly schedule.** One validated call instead of 24 per-hour calls with diversity retries.
* **D-14 Reaction context.** Scored retrieval with the two §4.3.1 queries replaces the keyword
  lookup in paper mode; the keyword lookup is available in compat mode.

## 7. What is out of reach

* Human believability rankings: export and import exist; no human study was run, and no human
  condition is simulated.
* Exact numbers in §6.5 and §7.1.2 are comparison references, not test targets.
* Hosted models are not bit-reproducible; exact replay needs the stored responses and state.

## 8. Ethics and interpretation

Agents are simulated characters. Plausible behavior here does not establish validity for real
people or populations (p. 17). Every interaction is logged with inputs and outputs (p. 18), and the
viewer labels mocked, replayed and live runs.

## 9. Status

Updated as milestones land; see the README for the current state of each module and test.
