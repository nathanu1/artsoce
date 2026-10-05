# `reaction@v1`

> Example from run `examples-main` (offline two-day pilot (MOCK)), default architecture settings. Inputs are exactly what the model was sent in that state; outputs show the format only, not model behavior.

* Template: [`prompts/reaction.v1.md`](../reaction.v1.md) · SHA-256 `1e3f7cadce8770009f349ef25efc41d2c9fe5a99d81e1a6570ea7184a7176421`
* Source: Paper §4.3.1 p. 11 (prompt with [Agent's Summary Description], time, status, observation, summary of relevant context, 'Should John react to the observation, and if so, what would be an appropriate reaction?'); wait option from released v2/decide_to_react_v1.txt; talk option from v2/decide_to_talk_v2.txt
* Information scope: The agent's dynamic summary, its own status, one perceived observation and the context summary built from its own memories.
* Output model: `ReactionDecisionOut` · max output tokens 300 · effort low
* Calls in this run: 150 (ok 150; 0 repair attempts)

## Output schema

```json
{
  "additionalProperties": false,
  "properties": {
    "decision": {
      "enum": [
        "continue",
        "react",
        "talk",
        "wait"
      ],
      "type": "string"
    },
    "reason": {
      "type": "string"
    },
    "new_activity": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "duration_minutes": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "required": [
    "decision",
    "reason",
    "new_activity",
    "duration_minutes"
  ],
  "type": "object"
}
```

## Smallest successful call

Ledger call 1726 · scope `examples-main` · sim time 2023-02-13T18:25:10 · agent `wolfgang_schulz` · model `mock-llm-v1` · status `ok` · tokens 634 in / 28 out (estimated)

**System**

```text
You are one component of a research simulation of believable characters, reproducing the generative agents architecture (Park et al., UIST 2023). Use only the information in the request; do not invent facts about the world or other characters. Reply with JSON that matches the requested schema and nothing else.
```

**User**

```text
Name: Wolfgang Schulz
Age: 21
Innate traits: Hardworking, passionate, dedicated
Learned traits: Wolfgang Schulz is a student at Oak Hill College studying chemistry and a student athlete. He is very dedicated to both his academics and his sport.
Currently: Wolfgang Schulz is training for his next competition and studying for his exams. He is also looking for ways to make his studies more efficient.
Lifestyle: Wolfgang Schulz goes to bed around 9pm, awakes up around 5am, eats dinner around 6pm.
Daily plan requirement: Wolfgang Schulz goes for a run at the part in the morning, studies during the day, and exercises at his room at night 
Current Date: Monday February 13
Wolfgang Schulz is Hardworking, passionate, dedicated. Notably: Wolfgang Schulz keeps coming back to mayor; Wolfgang Schulz keeps coming back to election.
Wolfgang Schulz spends the day on the usual routine. Notably: Wolfgang Schulz keeps coming back to mayor; Wolfgang Schulz keeps coming back to election.
Wolfgang Schulz feels steady about recent progress. Notably: Sam Moore said to Wolfgang Schulz: "Hi Wolfgang! Did you hear? I am telling people that I am running for the upcoming local mayor election."; Wolfgang Schulz keeps coming back to mayor.
It is February 13, 2023, 6:25 pm.
Wolfgang Schulz's status: Wolfgang Schulz is have dinner (continuing) at Dorm for Oak Hill College:kitchen:kitchen sink
Observation: Maria Lopez is have dinner (continuing)
Summary of relevant context from Wolfgang Schulz's memory:
Wolfgang Schulz knows Maria Lopez: Maria Lopez said to Wolfgang Schulz: "Hi Wolfgang! Did you hear? Klaus Mueller told me: This is very important -- I have a crush on Maria Lopez.". Maria Lopez is have dinner (continuing).
Should Wolfgang Schulz react to the observation, and if so, what would be an appropriate reaction?

Choose one decision:
- "continue": keep doing the current activity.
- "react": do something else now. Give the new activity and how many minutes it takes.

- "wait": wait until the situation changes. Give how many minutes to wait.

Respond with JSON: {"decision": "continue" | "react" | "talk" | "wait", "reason": "<one sentence>", "new_activity": "<activity or null>", "duration_minutes": <int or null>}
```

**Raw output**

```json
{"decision": "continue", "reason": "Not a good moment to talk.", "new_activity": null, "duration_minutes": null}
```

**Validated output**

```json
{
  "decision": "continue",
  "reason": "Not a good moment to talk.",
  "new_activity": null,
  "duration_minutes": null
}
```

No call for this task needed a repair in this run.
