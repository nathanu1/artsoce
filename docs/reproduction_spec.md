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
| A-1 | Stable agent ID, name, age, innate traits, learned traits, current status, lifestyle, living area, daily requirement. | p. 5; `scratch.json` fields; `scratch.py:382-414` (identity stable set) | P, C | `schemas.py` `AgentIdentity`; `scenario/importer.py` `persona_spec`; `scenario/loader.py` | `test_scenario.py::test_n25_scenario_loads_all_agents_with_their_own_data` | IDs are slugs (`isabella_rodriguez`); names unchanged. |
| A-2 | Each semicolon-delimited history phrase becomes one initial memory. | p. 5; p. 12; `reverie.py:577-591` | P, C | `scenario/importer.py` `read_history`; `memory/seeds.py` `seed_agent` | `test_scenario.py::test_seeds_are_entered_once_verbatim_and_do_not_feed_the_trigger` | Seeds are tagged `seed=True`, type observation, `origin=seed`, with the import flags in metadata. |
| A-3 | Seed rendering. Code rewrites each phrase into a third-person "inner thought" with an LLM and stores it as a *thought* (`converse.py:239-254`). | `converse.py:239-254`, `v2/whisper_inner_thought_v1.txt` | C | `memory/seeds.py`; `scenario.seed_rendering: verbatim` (default) or `inner_thought_llm` | `test_scenario.py::test_inner_thought_seed_rendering_keeps_the_original` | Default keeps the authored text verbatim (paper p. 5 says phrases are *entered* as memories). The rewrite keeps the original phrase in metadata. |
| A-4 | Loading the base scenario alone is not the intended state; the history CSV must also be loaded exactly once. | `base_the_ville_n25/personas/*/associative_memory/nodes.json` are `{}` | C | `memory/seeds.py` refuses a second seeding of an agent | `test_scenario.py::test_seeds_are_entered_once_verbatim_and_do_not_feed_the_trigger` | |
| A-5 | Party seeded only to Isabella; candidacy only to Sam. | p. 15 (§7.1.1: "known only by their respective originators") | P | `scenario/loader.py` (policy), `scenario/audit.py` (check) | `test_scenario.py::test_candidacy_policy_paper_vs_released_data`, `test_scenario_audit.py` | **Conflict:** the released n25 CSV tells Jennifer Moore that Sam plans to run. Default `candidacy_seed_policy: paper_originator_only` drops that one statement and logs it; `released_csv` keeps it (and the audit flags it). See D-3. |
| A-6 | Party end time 19:00. | p. 7 ("from 5 to 7 p.m. on February 14th") | P, C | `scenarios/smallville_n25/events.yaml` (evaluator-only) | `test_metrics.py::test_attendance_is_physical_and_uses_separate_denominators` | The n25 CSV says only "from 5pm"; Isabella's own `scratch.json` `currently` field says "from 5pm to 7pm", so the 19:00 end is agent-visible to Isabella only. |
| A-7 | Global event metadata (party window, candidacy) is for the engine and evaluator only, never in shared prompts. | prompt §7; p. 7 | E | `scenario/loader.py` keeps `events` out of identities; prompts are built only from agent-owned state (`cognition/context.py`) | `test_engine.py::test_evaluator_ground_truth_never_reaches_a_prompt`, `test_scenario.py::test_events_stay_out_of_agent_data` | Before the first conversation, party text appears only in the originator's prompts. |

### 2B. Memory stream

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| B-1 | Memory = description + creation time + last-access time (simulation time). | p. 8 | P | `schemas.py` `Memory`; `memory/store.py` (SQLite) | `test_retrieval.py::test_store_is_append_only_and_isolated_per_agent` | Extra fields: owner, kind, origin, importance, embedding key, SPO triple, location, conversation, speaker, evidence, depth, plan link. |
| B-2 | Types: observation, reflection, plan; seeds and conversation records tagged. | pp. 8–11; code types event, thought, chat (`associative_memory.py:15-40`) | P, C | `schemas.MemoryKind`, `MemoryOrigin` | `test_retrieval.py::test_kind_mask_excludes_types` | Mapping: code *event* → observation; code *thought* → reflection or plan; code *chat* → statements (`origin=statement`/`own_statement`, with `speaker_id`) plus a conversation summary (`origin=conversation`). |
| B-3 | Originals are retained; summaries and reflections are added, never replacing. | p. 8 ("comprehensive record") | P | append-only store; updates only touch `last_accessed_at` | `test_retrieval.py::test_store_is_append_only_and_isolated_per_agent` | No expiry. Code sets 30-day expirations (`reflect.py:124`) but nothing in the inspected path deletes them. |
| B-4 | A plan or intention is not proof of action; a statement is not world truth. | prompt §3 | E | `MemoryOrigin` distinguishes `direct_observation`, `executed_action`, `statement`, `inference`, `intention`, `system_feedback`, `inner_voice` | `test_metrics.py` (evaluation counts only received memories as exposure evidence) | |

### 2C. Retrieval

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| C-1 | `recency = 0.995 ** hours_since_last_access` (sandbox hours). | p. 9 | P | `memory/retrieval.py` `Retriever.score` | `test_retrieval.py::test_recency_is_elapsed_time_decay`, `::test_recency_uses_fractional_hours_and_clamps_negative` | Hours are fractional; negative gaps clamp to 0. |
| C-2 | Importance = stored integer. | p. 9 | P | same | `test_retrieval.py::test_score_is_sum_of_normalized_components_with_unit_weights` | |
| C-3 | Relevance = cosine(embedding(memory), embedding(query)). | p. 9 | P | `memory/retrieval.py` `cosine_to` | `test_retrieval.py::test_zero_norm_embeddings_give_zero_cosine_and_are_flagged`, `::test_negative_cosine_normalizes_without_nan` | Zero-norm vectors give cosine 0 and are flagged in the trace. |
| C-4 | Min-max normalize each component to [0, 1] over the candidates. | p. 9 | P | `normalize_minmax` | `test_retrieval.py::test_normalization_bounds_and_constant_component` | Constant component → 0.5 for every candidate; same constant as `retrieve.py:99`. |
| C-5 | `score = α_r·r + α_i·i + α_v·v`, all α = 1. | p. 9 | P | `RetrievalWeights` / `Weights` | `test_retrieval.py::test_weights_change_the_ranking` | |
| C-6 | Return the top-ranked memories that fit the context window. | p. 9 | P | prefix of the ranking under `budget_tokens` and `max_items` | `test_retrieval.py::test_prefix_selection_under_token_budget`, `::test_item_cap` | The paper names no universal top-k; budget and count are explicit config (defaults in §5). Code uses `n_count` 30, 50 or 15 per call site. |
| C-7 | Scores for all candidates are computed before any access time changes; only delivered memories are touched. | prompt §3 | E | `Retriever.retrieve(..., commit_access=True)` | `test_retrieval.py::test_access_time_updates_only_delivered_and_after_scoring`, `::test_no_access_update_when_not_committed` | Code updates the selected top-n (`retrieve.py:266-267`). |
| C-8 | Deterministic tie-break: score ↓, last access ↓, creation ↓, ID ↑. | prompt §3 | E | `rank_key` | `test_retrieval.py::test_ties_are_broken_deterministically` | |
| C-9 | Released-code compatibility mode: weights 0.5 / 2 / 3 for recency / importance / relevance times per-agent weights; recency `decay ** position` over candidates sorted by last access ascending; drop `idle` memories. | `retrieve.py:199-268` (`gw = [0.5, 3, 2]` at :244 in the order recency, relevance, importance; positional powers at :145; idle filter at :226) | C | `retrieval.mode: released_code` in `Retriever` | `test_retrieval.py::test_compat_recency_uses_positions_and_favors_oldest_access`, `::test_compat_weights_and_idle_filter` | Positional powers rank the *oldest* access highest (verified in a test). Not equivalent to elapsed-time decay. |
| C-10 | Second retrieval entry point: keyword match on the perceived event's subject, predicate and object, unscored, used for reaction context. | `retrieve.py:16-45`, `associative_memory.py:304-322`; called from `persona.py:221` | C | `memory/retrieval.py` `keyword_lookup` | `test_retrieval.py::test_keyword_lookup_matches_subject_or_object` | Paper mode uses scored retrieval for reaction context with the two §4.3.1 queries (D-14). |
| C-11 | Store retrieval traces: query, filters, raw and normalized components, weights, selected IDs, scores, tokens. Explain why A outranked B. | prompt §3 | E | `memory/trace.py`; `RetrievalResult.explain`; `ga inspect-memory`; viewer Retrieval tab | `test_retrieval.py::test_trace_is_persisted_with_components`, `::test_explain_reports_component_differences`, `test_cli_viewer.py::test_inspect_memory_prints_components_and_explanation` | Traces keep the top 40 candidates and the full counts. |

### 2D. Importance

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| D-1 | LLM integer 1–10 at creation, anchored by mundane vs poignant examples. | p. 9 (prompt quoted) | P | `prompts/importance.v1.md` → `cognition/importance.py` | `test_gateway.py::test_importance_idle_shortcut_and_range` | Output is JSON `{"rating": int}`; range validated. |
| D-2 | Separate anchors for conversations and thoughts. | `v3_ChatGPT/poignancy_chat_v1.txt`, `poignancy_thought_v1.txt` | C | `ANCHORS` by kind, in both the single and the batched template | `test_gateway.py::test_importance_batch_requires_one_rating_per_item` | |
| D-3 | Memories ending "is idle" score 1 without a call. | `perceive.py:15-17` | C | `importance.idle_shortcut` (default on) | `test_gateway.py::test_importance_idle_shortcut_and_range` | Applied identically in every condition. |
| D-4 | Bounded retries; cache only exact repeats; log invalid output. | prompt §3, §11 | E | `providers/gateway.py` | `test_gateway.py` (17 tests) | |
| D-5 | Reflections, plans and seeds are scored the same way but do not feed the perception trigger. | p. 10; `perceive.py:178` (only perceived events decrement the counter) | P, C | `cognition/services.py` `PERCEIVED_ORIGINS` | `test_reflection.py::test_reflections_and_plans_do_not_feed_the_trigger` | Statements heard and system feedback count as perceived. Batching: one call for the statements of one conversation, one for one plan's items, one for an agent's seeds. |

### 2E. Reflection

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| E-1 | Trigger when summed importance of newly perceived events **exceeds** 150 (strict `>`). | p. 10 | P | `ReflectionEngine.should_reflect` (`reflection.mode: paper`) | `test_reflection.py::test_trigger_requires_strictly_more_than_threshold` | |
| E-2 | Compat trigger: countdown from `importance_trigger_max` fires at `<= 0`. | `reflect.py:152-168`; n25 `scratch.json` has `importance_trigger_max: 250`; n3 base has 150; class default 150 (`scratch.py:61`) | C | `reflection.mode: released_code` | `test_reflection.py::test_compat_trigger_counts_down_and_uses_access_ordered_window` | |
| E-3 | Question prompt sees the 100 most recent records (or all, if fewer). | p. 10 | P | `ReflectionEngine.recent_records` | `test_reflection.py::test_reflection_stores_evidence_linked_insights_and_resets` | Code uses the last `importance_ele_n` records by last access, excluding idle (`reflect.py:23-34`); available in compat mode. |
| E-4 | Three salient high-level questions. | p. 10; `v3_ChatGPT/generate_focal_pt_v1.txt` | P, C | `prompts/reflection_questions.v1.md` | `test_reflection.py` | |
| E-5 | Each question is a retrieval query; five insights per question citing supplied memories. | p. 10; `v2/insight_and_evidence_v1.txt`; `reflect.py:110-131` | P, C | `prompts/reflection_insights.v1.md` | `test_reflection.py::test_reflection_stores_evidence_linked_insights_and_resets` | Citations use the numbers shown, mapped back to IDs. Evidence for all questions is retrieved before any insight is stored, as in the code. |
| E-6 | Evidence validation: exists, same owner, was supplied in that prompt, no cycles. | prompt §4 | E | `memory/evidence.py` | `test_reflection.py::test_validate_evidence_rejects_foreign_unsupplied_and_missing`, `::test_cycle_detection`, `::test_malformed_insights_are_repaired_or_recorded_without_fabrication` | Code drops parse failures to `{"this is blank": "node_1"}` (`reflect.py:47-53`); we record the failure instead. **Validation is structural:** it cannot tell whether a cited statement supports the claim (see `examples/walkthrough.py`). |
| E-7 | Reflections may cite reflections → trees; depth = 1 + max evidence depth. | p. 10; `associative_memory.py:207-212` | P, C | `Memory.depth`, `evidence_tree` | `test_reflection.py::test_later_reflections_can_cite_earlier_ones_forming_a_tree` | |
| E-8 | Reset the accumulator only after the batch is stored. | prompt §4; `reflect.py:262-264` | E, C | `ReflectionEngine.run` | `test_reflection.py::test_reflection_stores_evidence_linked_insights_and_resets` | Failed batches keep the accumulator, retry after a cooldown (30 sim minutes), and are recorded. |
| E-9 | "Two or three reflections a day" is an outcome, not a quota. | p. 10 | P | not enforced | `test_reflection.py::test_no_quota_is_enforced` | The offline 25-agent run produced 3,615 reflection memories; mock importance ratings are not calibrated. |
| E-10 | Post-conversation "planning thought" and "memo" inferences. | `reflect.py:186-245` | C | `architecture.post_conversation_inferences` (follows fidelity: off in paper mode) | `test_experiment.py::test_no_reflection_disables_every_reflective_path_but_keeps_transcript_summaries` | Counted as reflection-generating and disabled whenever reflection is off (R-2). |

### 2F. Dynamic summary (Appendix A)

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| F-1 | Retrieve and summarize "[name]'s core characteristics", "[name]'s current daily occupation", "[name]'s feeling about his recent progress in life"; concatenate with name, age, traits. | p. 21 | P | `cognition/summary.py` | `test_summary.py::test_summary_uses_three_appendix_a_queries_and_caches` | Pronoun in the third query adapted to the agent ("their"). |
| F-2 | Refresh interval or invalidation policy. | p. 21 ("at regular intervals") | E | `summary.refresh_every_minutes: 180`, `refresh_on_new_day: true` | `test_summary.py::test_refresh_policy_interval_and_new_day` | |
| F-3 | Summaries use only permitted memories; recomputed per evaluation condition. | prompt §8 | E | cache key includes the memory mask; interviews rebuild per condition | `test_summary.py::test_masked_summaries_are_isolated_from_the_full_cache`, `test_interview.py::test_masks_limit_retrieval_and_summary` | Code uses the static identity block (`scratch.py:382`) in most prompts; the paper's cached summary is used here. |

### 2G. Planning

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| G-1 | Day plan of 5–8 broad chunks from identity, summary and previous-day summary. | p. 11 | P | `prompts/day_plan.v1.md`; `cognition/planning.py` `Planner.ensure_day` | `test_planning.py::test_day_plan_and_hour_blocks_cover_the_day_contiguously` | Code asks for 4–6 items on later days (`plan.py:448-452`). |
| G-2 | Previous-day summary. | p. 11; `plan.py:408-458` (`revise_identity`) | P, C | `Planner.previous_day` | `test_planning.py::test_midnight_boundary_spillover_and_next_day_plan` | Built from the agent's own memories retrieved for the code's two queries. The code's rewrite of the `currently` field is not reproduced. |
| G-3 | Decompose to hourly activities, then 5–15 minute actions. | p. 11 | P | `prompts/hourly_schedule.v1.md`, `prompts/decompose.v1.md` | `test_planning.py::test_tasks_are_decomposed_just_in_time_for_the_current_window` | Code generates the hourly schedule one hour per call with a diversity retry (`plan.py:71-144`); we use one call and validate (D-13). |
| G-4 | Fine-grained decomposition just in time for the near future. | p. 21 | P | the current block is decomposed one window (`planning.jit_window_minutes`, 60) at a time, when the agent reaches it | `test_planning.py::test_tasks_are_decomposed_just_in_time_for_the_current_window` | Windows no longer than one task are used as they are, without a call. |
| G-5 | Sleep blocks are not decomposed. | `plan.py:533-549` | C | `planning.is_sleep` | `test_planning.py::test_sleep_is_not_decomposed`, `::test_sleep_detection` | |
| G-6 | Each entry: location, start, duration, description, status, parent. | p. 11 | P | `schemas.PlanItem`; `PlanStore` | `test_planning.py` | Locations are chosen when the task starts (J-4). |
| G-7 | Validation: 24 h coverage, positive durations, order, no overlap, exact task sums. Raw output and repair trace kept; no fabricated plan. | prompt §5 | E | validators in `Planner` | `test_planning.py::test_invalid_day_plan_is_repaired_once`, `::test_failed_day_plan_leaves_no_plan_and_retries_later` | Code pads a missing remainder with "sleeping" (`plan.py:614`); we repair once with the validator's message, then record the failure. A failed day plan leaves the agent idle and retries after 30 minutes; a failed decomposition falls back to the agent's own hour-level activity and is marked on the task. |
| G-8 | Plans are stored in the memory stream. | p. 11; `plan.py:499-515` (poignancy fixed at 5) | P, C | the day plan and each hour block become plan memories | `test_planning.py::test_day_plan_and_hour_blocks_cover_the_day_contiguously` | Importance comes from the model like other memories (thought anchors), not the fixed 5. |
| G-9 | Completed history preserved; a finished action never re-runs because a tick passed. | prompt §5 | E | `PlanItem.status` transitions | `test_planning.py::test_idempotent_completion` | |

### 2H. Reacting and replanning

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| H-1 | Each step: perceive, store new observations, decide continue or react. | p. 11 | P | `simulation/engine.py` `_agent_step` | `test_behavior.py` | One focal percept per step (agents first, then notable objects and ambient events). |
| H-2 | Context summary from "[observer]'s relationship with [observed]" and "[observed] is [action]". | p. 11 | P | `cognition/reaction.py` `ReactionEngine.context` | `test_behavior.py::test_nearby_friend_conversation_is_private_and_turn_by_turn` | |
| H-3 | Regenerate the plan from the reaction time; keep the past. | p. 11; `plan.py:806-880` | P, C | `Planner.insert` + `_replan_rest` | `test_planning.py::test_insert_supersedes_overlaps_and_replans_rest_of_window` | Overlapping tasks are truncated or superseded, never deleted. |
| H-4 | React to object and ambient events (burning stove, empty fridge, fire on the street). | p. 6 | P, X | `cognition/reaction.py`; object states in `world/state.py` | `test_behavior.py::test_burning_stove_is_noticed_and_put_out`, `::test_empty_fridge_prompts_a_shopping_trip`, `::test_street_fire_seen_by_a_passerby` | **Code reacts only to agent events** (`plan.py:796`). Each lasting object state is considered once while awake. |
| H-5 | Wait when an occupied resource blocks the action. | `plan.py:741-772`, `v2/decide_to_react_v1.txt` | C, E | reaction option `wait`; strict-v1 occupancy refusal → wait | `test_behavior.py::test_occupied_single_person_bathroom_makes_the_agent_wait`, `test_planning.py::test_wait_pauses_the_plan_without_replacing_it` | Waiting pauses the plan instead of replacing it. |
| H-6 | No new conversation while either party sleeps, after 23:00, or within the cooldown. | `plan.py:715-738`; cooldown 800 steps (`plan.py:888,894`) | C | `Simulation._can_talk` | `test_behavior.py::test_nearby_friend_conversation_is_private_and_turn_by_turn` (cooldown), `::test_sleeping_agents_store_what_they_perceive_but_do_not_react` | Cooldown expressed in sim minutes (default 133 ≈ 800 × 10 s). |

### 2I. Dialogue

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| I-1 | Turn-by-turn; each utterance conditioned on the speaker's summarized memory about the partner and memories retrieved for the last utterance, plus the transcript so far. | pp. 11–12 | P | `cognition/dialogue.py` | `test_behavior.py::test_nearby_friend_conversation_is_private_and_turn_by_turn` | |
| I-2 | Either speaker may end the conversation. | p. 12; `converse.py:139-176` | P, C | `{"utterance", "end_conversation"}` output | `test_behavior.py::test_dialogue_ends_when_a_speaker_ends_it` | |
| I-3 | Cap of 8 rounds (16 utterances). | `converse.py:130` | C | `dialogue.max_utterances: 16` | `test_behavior.py::test_dialogue_stops_at_the_utterance_cap` | |
| I-4 | Duration `ceil((chars / 8) / 30)` minutes; both parties reserved. | `plan.py:290`, `plan.py:870-880` | C | `conversation_minutes`; one conversation per agent per step | `test_behavior.py::test_conversation_duration_rule` | |
| I-5 | Partner learns what was said, never the speaker's private memory. | p. 12 | P | statements stored with `origin=statement`, `speaker_id` | `test_behavior.py::test_nearby_friend_conversation_is_private_and_turn_by_turn` | Bystanders perceive only "A is chatting with B". |
| I-6 | No fabricated utterance on failure. | `run_gpt_prompt.py:2891-2895` returns "..." | E | conversation aborted and logged | `test_behavior.py::test_failed_turn_aborts_without_inventing_lines` | |
| I-7 | Observational transcript summary for each participant. | `v3_ChatGPT/summarize_conversation_v1.txt` | C | memory with `origin=conversation` | `test_experiment.py::test_no_reflection_disables_every_reflective_path_but_keeps_transcript_summaries` | Kept in the reflection-off condition (observational, not inferential). |

### 2J. World, perception, navigation

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| J-1 | Tree world → sector → arena → object. | p. 12; Fig. 2; `maze.py:19-205` | P, C | `world/hierarchy.py` | `test_world.py::test_world_tree_matches_released_matrices` | |
| J-2 | Private, possibly stale subgraph per agent; initial knowledge from the official `spatial_memory.json`. | p. 12 | P, C | `world/spatial.py` | `test_world.py::test_spatial_memory_grows_only_from_what_is_seen` | Every tile in the vision square is learned, as in the code (no line of sight). |
| J-3 | Perception: square of `vision_r` tiles; events only in the agent's current arena (outdoor tiles form one arena); nearest `att_bandwidth`; skip triples seen in the last `retention` events. n25 values 8 / 8 / 8. | p. 12; `maze.py:249-325`; `perceive.py:44-104, 122-125` | P, C | `world/perception.py`; retention in the engine | `test_world.py::test_perception_square_same_arena_bandwidth_and_self`, `::test_agents_on_the_street_see_each_other` | An object spanning several tiles is perceived once at its nearest tile. |
| J-4 | Recursive destination choice over the known tree, preferring the current area; validated. | pp. 12–13 | P | `cognition/location.py` | `test_behavior.py::test_private_room_is_refused_and_the_agent_chooses_again`, `::test_single_call_location_strategy_and_block_reuse` | A level with one known option is taken without a call; `location.strategy: single_call` is an engineering alternative. Invalid answers get one repair; then the action fails visibly. |
| J-5 | Real pathfinding; one tile per step; no teleporting. | p. 13; `path_finder.py:96-178`; `execute.py:147-154` | P, C | `world/navigation.py` (4-neighbour BFS, cached fields) | `test_world.py::test_bfs_path_is_shortest_contiguous_and_walkable`, `::test_nearest_prefers_free_tiles_and_is_deterministic` | Target tile = nearest reachable tile of the address, preferring unoccupied tiles (code samples up to four random tiles). |
| J-6 | LLM proposes object state; engine applies it only at a reached target. | p. 13 | P, E | `Simulation._ground`, `_commit_moves`; `world/state.py` | `test_world.py::test_object_state_overlay_lasting_and_release`, `test_behavior.py::test_burning_stove_is_noticed_and_put_out` | In-use states overlay the object while the agent is there; lasting conditions (intervention or `lasting_state` from grounding) persist. The prompt shows the condition the agent last saw, never the true state. |
| J-7 | Occupancy, ownership and opening hours from scenario data. | p. 17 (one-person bathroom, stores close ~5 pm) | E | `world/constraints.py`, policy `strict-v1` or `none` | `test_world.py::test_strict_v1_constraints`, `test_behavior.py::test_occupied_single_person_bathroom_makes_the_agent_wait`, `::test_without_constraints_the_bathroom_is_entered` | The paper did not enforce these; enforcement is an adaptation, identical across conditions. Refusals become `system_feedback` memories. |
| J-8 | The released map: 140 × 100 tiles, 32 px, from the official matrices. | `matrix/maze_meta_info.json` | C | `scenario/importer.py` `build_map` | `test_world.py::test_world_tree_matches_released_matrices`, `test_scenario_audit.py::test_reimport_reproduces_committed_scenario_files` | Re-importing the official checkout reproduces the committed files byte for byte. |

### 2K. Clock, ordering, persistence

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| K-1 | 10 simulated seconds per step; start Mon 13 Feb 2023 00:00:00. | `base_the_ville_n25/reverie/meta.json` | C | `simulation/clock.py` | `test_planning.py::test_midnight_boundary_spillover_and_next_day_plan`, `test_interview.py::test_today_resolves_against_the_interview_clock` | Paper prompt examples pair "February 13" with Wednesday (pp. 10–11); 13 Feb 2023 is a Monday, and the code computes weekdays from the date (`scratch.py:413`). We do the same. |
| K-2 | Snapshot → decide → resolve → commit, recorded agent order. | prompt §6 | E | `simulation/engine.py` | `test_engine.py::test_perception_uses_the_start_of_step_snapshot` | Code updates agents sequentially in dict order and mutates partners mid-step (`reverie.py:373-385`, `plan.py:845-880`). |
| K-3 | Long unchanged actions avoid model calls. | prompt §6 | E | decisions only on task end, new perception, or a reaction | `test_engine.py::test_no_model_calls_while_nothing_changes` | |
| K-4 | Checkpoint and resume without duplicating actions or memories; exact replay from stored responses. | prompt §6, §11 | E | `simulation/engine.py` (checkpoints, rollback, `replay_from`); `providers/ledger.py` | `test_engine.py::test_resume_after_crash_matches_an_uninterrupted_run_without_paying_twice`, `::test_replay_reproduces_the_run_without_any_model_call`, `::test_replay_that_diverges_stops_instead_of_calling_a_model`, `test_cli_viewer.py::test_replay_command_matches_without_model_calls` | Resume re-uses ledgered calls of rolled-back steps. |

### 2L. User interactions

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| L-1 | Interview an agent as an outside visitor, read-only. | p. 6; `converse.py:257-280` | P, C | `evaluation/interview.py` on a clone; `ga interview --ask` | `test_interview.py::test_interviews_leave_the_snapshot_and_access_times_untouched` | Code's "analysis" mode still updates access times (`retrieve.py:266`); ours runs on a discarded clone. |
| L-2 | Inner-voice directive to one agent, logged as an intervention. | p. 6; `converse.py:283-296` | P, C | `Simulation.schedule_intervention` / `_apply_interventions` (`kind: inner_voice`) | `test_behavior.py::test_inner_voice_intervention_is_stored_and_logged` | Stored as an observation with `origin=inner_voice`. |
| L-3 | Change one object's state. | p. 6 | P | `kind: object_state` (and `ambient`, `end_ambient`) interventions | `test_behavior.py::test_burning_stove_is_noticed_and_put_out` | |
| L-4 | Visitors cannot mutate state. | prompt §5 | E | clone isolation; read-only viewer | `test_interview.py`, `test_cli_viewer.py::test_viewer_api_is_read_only` | |

### 2M. Controlled evaluation (§6, Appendix B)

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| M-1 | Run the full architecture two days, freeze, then interview isolated copies under four memory conditions. | pp. 13–14 | P | snapshots in `simulation/engine.py`; `evaluation/interview.py` | `test_interview.py::test_run_interviews_writes_responses_and_refuses_a_human_condition` | Run configs end one minute into 15 Feb so "today" has a plan at the final snapshot. |
| M-2 | Masks: full; no reflection; observations only; no memory stream. Static identity identical across conditions. | p. 13 | P | `memory/masks.py` | `test_interview.py::test_masks_limit_retrieval_and_summary` | Seeds count as observations. |
| M-3 | 25 verbatim questions, five per category; placeholders: random interacted-with agents (memory), most frequent partners (reflections). | pp. 21–22 | P | `evaluation/question_bank.py`, `configs/questions/appendix_b_reference.yaml`, `appendix_b_adapted.yaml` | `test_question_bank.py` | Reference bank keeps the original "she"; selections and ties are recorded. |
| M-4 | Explicit interview clock; "today" resolves against simulation time. | prompt §8 | E | `InterviewSpec.reference_time` | `test_interview.py::test_today_resolves_against_the_interview_clock` | |
| M-5 | Blinded randomized export; genuine human responses and ratings import only. | pp. 13–14 | P, E | `evaluation/export.py`, `evaluation/human.py` | `test_export.py` | No human condition is ever simulated. |
| M-6 | TrueSkill, Kruskal–Wallis, Dunn, Holm. | p. 14 | P | `evaluation/stats.py` | `test_stats.py` | Computed only from imported rankings. |
| M-7 | Friedman with paired Wilcoxon + Holm. | prompt §8 | X | `evaluation/stats.py` | `test_stats.py::test_analysis_needs_genuine_data_and_labels_our_addition` | Labeled as our addition. |
| M-8 | Optional LLM judge, exploratory only. | prompt §8 | X | `evaluation/judge.py`; `ga judge` | `test_export.py::test_llm_judge_is_labeled_exploratory` | Never reported as believability. |

### 2N. End-to-end evaluation (§7)

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| N-1 | Ask everyone "Did you know there is a Valentine's Day party?" and "Do you know who is running for mayor?"; verify affirmative answers against memory. | p. 15 | P | `evaluation/diffusion.py` | `test_metrics.py::test_awareness_separates_supported_claims_from_hallucination_and_retrieval_failure`, `::test_transmissions_record_sender_receiver_and_details` | Claimed vs supported reported separately; the answer label comes from an automated classifier (the paper labeled by hand). |
| N-2 | "Do you know of <name>?" at start and end; edge iff both know; `η = 2|E| / (|V|(|V|−1))`. | pp. 15–16 | P | `evaluation/relationships.py` | `test_metrics.py::test_density_convention_and_mutual_supported_edges`, `::test_relationship_probe_validates_answers_against_memory` | `n < 2` → undefined (null). Affirmatives validated against seeds or interaction records; "seen only" reported separately. |
| N-3 | Count agents who actually showed up. | p. 16 | P | `evaluation/attendance.py` (recorded positions in the window) | `test_metrics.py::test_attendance_is_physical_and_uses_separate_denominators` | Exposure, invitation, intention, scheduled and arrival are separate variables; host excluded from guest denominators; presence ≥ 10 minutes by default. |
| N-4 | Failure categories with examples. | pp. 15–17 | P, E | `evaluation/failures.py` | `test_metrics.py::test_failure_taxonomy_categories_and_examples` | Nine categories from prompt §9; the formal/agreeable category is a text heuristic. |
| N-5 | Probes run on clones and never seed the town. | prompt §9 | E | clone-based probes | `test_interview.py::test_interviews_leave_the_snapshot_and_access_times_untouched` | |

### 2O. Providers, cost, provenance

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| O-1 | Central gateway: bounded retries, timeouts, validation, usage accounting, exact-request cache keys, record and replay. | prompt §11 | E | `providers/gateway.py`, `providers/ledger.py` | `test_gateway.py` | Cache keys include prompt, template version and hash, model, settings, schema and agent; the run ID scopes them. |
| O-2 | No cross-replicate reuse of stochastic samples. | prompt §11 | E | cache scope = run ID for generation; global for pure embeddings | `test_gateway.py::test_cache_scope_isolates_independent_runs` | |
| O-3 | Budgets: calls, input and output tokens, runtime, optional cost; exhaustion checkpoints instead of fabricating. | prompt §11 | E | `simulation/budget.py`; engine rollback | `test_gateway.py::test_budget_ceiling_stops_before_the_call`, `test_engine.py::test_budget_exhaustion_rolls_back_and_resume_finishes` | Cost stays "unpriced" unless a price table is configured (`configs/pricing.yaml`, from the published price page). |
| O-4 | Anthropic adapter; deterministic mock; optional OpenAI adapter; embeddings backends with recorded model and dimensions. | prompt §2 | E | `providers/{anthropic_provider, mock, openai_provider, embeddings}.py` | `test_gateway.py::test_mock_provider_is_deterministic` | Mock embeddings are test fixtures only. **The live adapters have not been exercised against the real APIs** (no credentials). |
| O-5 | Run manifest. | prompt §11 | E | `Simulation.write_manifest` | `test_engine.py::test_manifest_labels_mock_runs` | |

### 2R. Reflection extension

| Req | Behavior | Source | Class | Implementation | Tests | Deviation or note |
| --- | --- | --- | --- | --- | --- | --- |
| R-1 | Full architecture vs reflection disabled *throughout* independent simulations from identical authored worlds. | prompt §10 | X | `evaluation/experiment.py`, `configs/experiment_reflection*.yaml` | `test_experiment.py::test_protocol_matches_seeds_and_plans_without_calling_models`, `::test_execute_reports_every_run_and_missing_outcomes` | |
| R-2 | Disable every reflection-generating path (trigger, questions, insights, post-conversation inferences); keep observational transcript summaries. | prompt §10 | X | `architecture.reflection: false` | `test_experiment.py::test_no_reflection_disables_every_reflective_path_but_keeps_transcript_summaries` | |
| R-3 | Primary outcomes: supported event recall; attendance among invited guests. Report exposure, invitations, unsupported claims, calls, tokens, cost, runtime; include failed and truncated runs. | prompt §10 | X | `evaluation/experiment.py` | `test_experiment.py::test_run_level_summary_statistics` | Run is the unit of analysis; bootstrap interval and exact permutation test are exploratory. |

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
* **D-5 Batched calls.** Action grounding returns the event triple, the in-use object state and an
  optional lasting condition in one call; the statements of one conversation, the items of one plan
  and an agent's seeds are each scored in one batched importance call. Each batch keeps per-item
  validation. Location choice stays recursive (one call per level with more than one option).
* **D-6 Ordering.** Snapshot / decide / commit instead of sequential mutation (K-2).
* **D-7 Constraints.** Opening hours, capacity and ownership enforced under `strict-v1` (J-7).
* **D-8 Population.** Pilot runs use documented subsets (`scenarios/pilot3`, `scenarios/pilot5`).
* **D-9 Tick and targets.** Reference 10 s. Destination tiles are the nearest reachable tile of the
  chosen address, preferring free tiles; agents may share tiles while walking, as in the code.
* **D-10 Viewer.** Simple shapes instead of the original art.
* **D-11 Interviews.** Clones instead of the live process; matched-history design as in the paper.
* **D-12 Emoji.** The emoji rendering of actions (p. 5) is not reproduced; the viewer shows text.
* **D-13 Hourly schedule.** One validated call instead of 24 per-hour calls with diversity retries.
* **D-14 Reaction context.** Scored retrieval with the two §4.3.1 queries replaces the keyword
  lookup in paper mode; the keyword lookup is available in compat mode.
* **D-15 Focal percept and sleep.** One percept per step is considered for a reaction (agents
  first). Sleeping agents still perceive and store, but make no reaction decisions; notable object
  states are considered once when awake. Talk is offered only when the conversation policy allows.
* **D-16 Lasting object conditions.** Object states distinguish an in-use overlay (cleared when the
  agent leaves, like the code's per-cycle reset) from lasting conditions set by interventions or
  reported by grounding (`lasting_state`, our addition to the grounding output).
* **D-17 Snapshots for evaluation.** Probes at the "start" use a snapshot taken right after seeding
  (before any plan); "end" probes use the snapshot one simulated minute into 15 Feb.
* **D-18 Automated labels.** Awareness and "know of" answers are labeled by a classifier prompt
  (`awareness`), where the paper's authors labeled by hand; every label keeps the answer text.
* **D-19 Not reproduced.** The code's rewrite of each agent's `currently` field at day start
  (`revise_identity`), emoji pronunciatio, and the code's `<random>`/`<waiting>` address tokens.

## 7. What is out of reach

* Human believability rankings: export and import exist; no human study was run, and no human
  condition is simulated.
* Exact numbers in §6.5 and §7.1.2 are comparison references, not test targets.
* Hosted models are not bit-reproducible; exact replay needs the stored responses and state.
* No live model was called while building this project (no credentials were available). The
  Anthropic and OpenAI adapters follow current SDK documentation but are unvalidated against the
  real APIs; the first live run should be a short, bounded slice (README).

## 8. Ethics and interpretation

Agents are simulated characters. Plausible behavior here does not establish validity for real
people or populations (p. 17). Every interaction is logged with inputs and outputs (p. 18), and the
viewer labels mocked, replayed and live runs.

## 9. Status

All seven milestones are implemented. What was actually run:

| Check | Result |
| --- | --- |
| Test suite (`pytest`) | 145 tests pass offline (retrieval, gateway, reflection, summaries, planning, world, behavior scenarios, engine resume/replay/budget, scenario audit, interviews, metrics, statistics, exports, experiment runner, CLI and viewer API). |
| Scenario import | Re-importing the official checkout at `fe05a71` reproduces the committed scenario files byte for byte; the n25 audit is clean under the paper policy (party: Isabella only; candidacy: Sam only). |
| Offline five-agent, two-day run (`configs/offline_pilot_2day.yaml`) | Completes in about a minute; evaluation, interviews (500 answers), blinded export and the viewer were exercised on it. MOCK. |
| Offline 25-agent, two-day run | Completed in 6.6 minutes: 32,970 mock calls, about 17.9M estimated input tokens (real prompts, chars/4), 19,291 memories, 228 conversations, 3,615 reflection memories, about 0.5 GB on disk with snapshots. Evaluation took 44 s. MOCK: these numbers describe the pipeline's load, not agent behavior. |
| Replay | A recorded run replays to an identical state with zero model calls; a replay with a changed setting stops as diverged instead of calling a model. |
| Resume | A run crashed mid-way and resumed reaches the same state as an uninterrupted run, paying for no call twice. |
| Live API | **Not run.** No credentials were available. |

Known limitations: the mock model is a crude fixture (its dialogue and reflections are mechanical);
reflection evidence is validated structurally, not semantically (E-6); importance from the mock is
uncalibrated, so reflection frequency in mock runs says nothing about the paper's two or three a day.
