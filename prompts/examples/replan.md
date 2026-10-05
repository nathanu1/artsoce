# `replan@v1`

> Example from run `examples-main` (offline two-day pilot (MOCK)), default architecture settings. Inputs are exactly what the model was sent in that state; outputs show the format only, not model behavior.

* Template: [`prompts/replan.v1.md`](../replan.v1.md) · SHA-256 `3b98254d43f4c950153f00c7db3ddd2285295d4cd040d66405a4bb445fd3cd08`
* Source: Paper §4.3.1 p. 11 ('We then regenerate the agent's existing plan starting from the time when the reaction takes place'); released v2/new_decomp_schedule_v1.txt
* Information scope: The agent's own schedule, the inserted action and the time; nothing about other agents beyond the inserted action's text.
* Output model: `DecomposeOut` · max output tokens 900 · effort low
* Calls in this run: 56 (ok 56; 0 repair attempts)

## Output schema

```json
{
  "$defs": {
    "TaskOut": {
      "additionalProperties": false,
      "properties": {
        "start": {
          "type": "string"
        },
        "duration_minutes": {
          "type": "integer"
        },
        "activity": {
          "type": "string"
        }
      },
      "required": [
        "start",
        "duration_minutes",
        "activity"
      ],
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "tasks": {
      "items": {
        "$ref": "#/$defs/TaskOut"
      },
      "type": "array"
    }
  },
  "required": [
    "tasks"
  ],
  "type": "object"
}
```

## Smallest successful call

Ledger call 1658 · scope `examples-main` · sim time 2023-02-13T18:21:00 · agent `wolfgang_schulz` · model `mock-llm-v1` · status `ok` · tokens 543 in / 68 out (estimated)

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

Here was Wolfgang's originally planned schedule from 18:18 to 19:00:
18:18 (14 min) have dinner (continuing)
18:32 (14 min) have dinner (making progress)
18:46 (14 min) have dinner (wrapping up)

At February 13, 2023, 6:21 pm, Wolfgang started something unplanned: "chatting with Maria Lopez" for 4 minutes, until 18:25.

Write Wolfgang's revised schedule from 18:25 to 19:00 (35 minutes). Keep what still makes sense from the original plan. Each action lasts 5 to 15 minutes and the durations add up to exactly 35 minutes.

Respond with JSON: {"tasks": [{"start": "HH:MM", "duration_minutes": <int>, "activity": "<what>"}, ...]}
```

**Raw output**

```json
{"tasks": [{"start": "18:25", "duration_minutes": 12, "activity": "have dinner (continuing)"}, {"start": "18:37", "duration_minutes": 12, "activity": "have dinner (making progress)"}, {"start": "18:49", "duration_minutes": 11, "activity": "have dinner (wrapping up)"}]}
```

**Validated output**

```json
{
  "tasks": [
    {
      "start": "18:25",
      "duration_minutes": 12,
      "activity": "have dinner (continuing)"
    },
    {
      "start": "18:37",
      "duration_minutes": 12,
      "activity": "have dinner (making progress)"
    },
    {
      "start": "18:49",
      "duration_minutes": 11,
      "activity": "have dinner (wrapping up)"
    }
  ]
}
```

No call for this task needed a repair in this run.
