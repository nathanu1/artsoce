# Evaluation and experiment protocol

Three studies use the same simulation. Run them in this order; each step has a stopping rule.

## 0. Before any live run

1. `ga doctor --config configs/live_pilot.yaml` reports no `FAIL`.
2. Run a one-morning live slice and read it (`ga serve`, `ga export`): look for invalid outputs
   (`model_calls.jsonl`, status `invalid`), action failures and refusals in `events.jsonl`.
3. Project the full runs from the slice:
   `ga experiment --protocol configs/experiment_reflection.yaml --measured-run runs/<slice>`.
   Write the projection and the configured ceilings down before scaling up. A slice
   underestimates evening and conversation-heavy hours; leave a margin.

Stop if more than a few percent of calls are invalid after repair, or if refusals cluster on one
task: fix the prompt version (a new template version changes every request hash, so earlier
recordings are not silently reused).

## 1. Matched-history interviews (paper §6, Appendix B)

**Design.** One full-architecture run of the population for two simulated days. Its final
snapshot is taken one simulated minute into 15 February, after every agent has made that day's
plan, so "today" in the plan questions has an answer. Each of the four conditions answers on
its own clone of that snapshot:

| Condition | Observations | Plans | Reflections |
| --- | --- | --- | --- |
| `full_architecture` | yes | yes | yes |
| `no_reflection` | yes | yes | no |
| `observations_only` | yes | no | no |
| `no_memory_stream` | no | no | no |

Masks apply before retrieval and before the dynamic summary is rebuilt; the static identity
block is identical in every condition. Retrieval does not update access times, so questions are
independent. The allowed observations and plans still come from the full architecture's
trajectory (as in the paper), which makes the ablation conservative.

**Questions.** `configs/questions/appendix_b_reference.yaml`: the 25 questions with the paper's
wording. Memory questions 1 and 5 name two agents the subject talked with, sampled with a
recorded seed; reflection questions 2–4 name the most frequent conversation partner (ties
recorded). "Kane Martinez" is the non-existent person.

```bash
ga interview --run-dir runs/<run> --protocol configs/interviews_reference.yaml
```

**Human condition and ratings.** The paper's crowdworker answers (one author per agent, written
after watching that agent's replay) are not generated. To include them, collect a CSV with
`agent_id,question_id,answer,author_id` and export:

```bash
ga export-blinded --run-dir runs/<run> --name appendix_b --human-responses answers.csv --seed 7
```

Raters get `rating_form.csv`, `rating_items.csv`, `rubric.md` and `context/`; keep
`blinding_key.json` private. Each rater ranks every item's answers best to worst (`C>A>E>B>D`).

```bash
ga analyze-ratings --run-dir runs/<run> --name appendix_b --ratings ratings.csv
```

reports the authors' analysis (TrueSkill from the rankings; Kruskal–Wallis on the raw ranks;
Dunn post-hoc with Holm adjustment) and, labeled as ours, a Friedman test over complete rankings
with paired Wilcoxon follow-ups. Rater IDs and items are kept, so the repeated-measures structure
is preserved. TrueSkill's sigma is a rating uncertainty, not a subject-level spread.

`ga judge` adds an exploratory LLM rating per answer in a separate file. It is never a
substitute for human believability judgments.

Paper reference (not a target): TrueSkill μ 29.89 full, 26.88 no reflection, 25.64 observations
only, 22.95 crowdworkers, 21.21 no memory.

## 2. End-to-end measures (paper §7)

```bash
ga evaluate --run-dir runs/<run>
```

Probes run on clones of the `initial` snapshot (right after seeding) and the `final` snapshot.

* **Information diffusion.** Every agent is asked "Did you know there is a Valentine's Day
  party?" and "Do you know who is running for mayor?". An automated classifier labels whether the
  answer claims knowledge (the paper labeled by hand). A claim counts as supported only if the
  agent's memory holds received evidence: a seed, a statement heard from someone, an inner-voice
  directive or a direct observation. Claimed, supported, newly informed (originator excluded),
  claimed-without-support and evidence-but-denied are reported separately, with every
  transmission from the transcripts (time, sender, receiver, conversation, details said).
* **Relationships.** "Do you know of <name>?" for every ordered pair at both snapshots. An
  undirected edge needs both agents to claim and to be supported by a seed or an interaction
  record; having only seen someone is reported separately. Density `2|E| / (n(n−1))`, undefined
  for `n < 2`.
* **Coordination.** Physical presence in Hobbs Cafe for at least 10 minutes between 17:00 and
  19:00 on 14 February, from the recorded positions. Rates are reported among invited, exposed,
  accepting and scheduling guests, with the host excluded from every denominator.
* **Failures.** Missed exposure, retrieval failure despite stored evidence, unsupported
  embellishment, ungrounded inference, stale location knowledge, invalid action/location
  (including positions that strict-v1 would refuse when constraints were off), forgotten
  commitment, schedule conflict, and a text heuristic for overly formal or agreeable dialogue,
  each with examples in `failures.json`.

Paper reference (not a target): candidacy 1/25 → 8/25; party 1/25 → 13/25; 5 of 12 invited
guests attended; density 0.167 → 0.74; 6 of 453 relationship answers hallucinated.

## 3. Extension: reflection and coordination

**Question.** With memory and planning on, how does reflection affect supported recall of the
seeded events and the conversion of invitations into attendance?

**Design.** Independent two-day simulations of the five-agent pilot from the same authored world.
`full` and `no_reflection` differ only in `architecture.reflection`; turning it off disables the
trigger, questions and insights and the released code's post-conversation inferences, while
observational conversation summaries remain. Five seeds per condition, matched across conditions
(`configs/experiment_reflection.yaml`). A hosted model does not reproduce identical samples, so
the matching is of the initial world, not of the randomness.

**Outcomes, fixed in advance.** Primary: share of agents with supported recall of the party and
of the candidacy at the end; attendance rate among invited guests. Secondary, for
interpretation: exposure and invitation counts, unsupported claims, calls, tokens, cost (when
priced) and runtime.

**Analysis.** The run is the unit: never agents or memories within one town. Per condition:
mean, standard deviation, median and range; the difference between conditions with a bootstrap
95% interval and an exact permutation test. With five runs per condition these are exploratory.
Failed and budget-truncated runs stay in the table with their reason.

```bash
ga experiment --protocol configs/experiment_reflection.yaml --measured-run runs/<slice>   # plan + projection
ga experiment --protocol configs/experiment_reflection.yaml --execute --yes                # the batch
ga serve --run-dir runs/experiments/reflection_live_pilot/full-s101 --experiment runs/experiments/reflection_live_pilot
```

The offline version (`configs/experiment_reflection_mock.yaml`) runs the same pipeline with the
mock model; its numbers say nothing about reflection. Do not change the reflection threshold or
the outcome definitions after seeing results; a retrieval-weight or context-budget sweep is a
separate, later study.
