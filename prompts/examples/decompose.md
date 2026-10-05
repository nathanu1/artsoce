# `decompose@v1`

> Example from run `examples-main` (offline two-day pilot (MOCK)), default architecture settings. Inputs are exactly what the model was sent in that state; outputs show the format only, not model behavior.

* Template: [`prompts/decompose.v1.md`](../decompose.v1.md) · SHA-256 `44df7e8c35ec67a51a8010c569d861dcdd80359396df810f7c747ed6e203cdd4`
* Source: Paper §4.3 p. 11 ('recursively decompose this again into 5–15 minute chunks'); Appendix A p. 21 (just-in-time); released v2/task_decomp_v3.txt
* Information scope: The agent's identity, dynamic summary and the hour-level plan around the activity.
* Output model: `DecomposeOut` · max output tokens 900 · effort low
* Calls in this run: 156 (ok 156; 0 repair attempts)

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

Ledger call 122 · scope `examples-main` · sim time 2023-02-13T06:00:00 · agent `sam_moore` · model `mock-llm-v1` · status `ok` · tokens 582 in / 93 out (estimated)

**System**

```text
You are one component of a research simulation of believable characters, reproducing the generative agents architecture (Park et al., UIST 2023). Use only the information in the request; do not invent facts about the world or other characters. Reply with JSON that matches the requested schema and nothing else.
```

**User**

```text
Name: Sam Moore
Age: 65
Innate traits: wise, resourceful, humorous
Learned traits: Sam Moore is a retired navy officer who loves to share stories from his time in the military. He is always full of interesting stories and advice.
Currently: Sam Moore lives with his wife of 40 years, Jennifer Moore, and spends his free time tending the park and is an avid reader. Sam is planning on running for local mayor in the upcoming election and he is telling is neighbors about it
Lifestyle: Sam Moore goes to bed around 9pm, awakes up around 5am, eats dinner around 5pm.
Daily plan requirement: Sam Moore likes to talk a walk around Johnson Park, and sit at Hobbs cafe reading.
Current Date: Monday February 13
Sam Moore is wise, resourceful, humorous. Notably: Sam Moore is sleeping; bed is being slept in.
Sam Moore spends the day on the usual routine. Notably: You are telling people that you are running for the upcoming local mayor election; You are thinking of running in the upcoming local mayor election.
Sam Moore feels steady about recent progress. Notably: You are telling people that you are running for the upcoming local mayor election; You are thinking of running in the upcoming local mayor election.

Today is Monday February 13. Sam's schedule around this time:
00:00–05:00 sleeping
05:00–06:00 wake up and complete the morning routine
06:00–08:00 have breakfast
08:00–12:00 go about the daily routine (likes to talk a walk around Johnson Park, and sit at Hobbs cafe reading)
12:00–13:00 have lunch at Hobbs Cafe
13:00–18:00 go about the daily routine (likes to talk a walk around Johnson Park, and sit at Hobbs cafe reading)
18:00–20:00 have dinner
20:00–21:00 relax and wind down
21:00–21:30 go to bed
21:30–24:00 sleeping

Decompose "have breakfast" from 06:00 to 07:00 (60 minutes) into smaller actions of 5 to 15 minutes each, in order. Durations must add up to exactly 60 minutes.

Respond with JSON: {"tasks": [{"start": "HH:MM", "duration_minutes": <int>, "activity": "<what Sam is doing>"}, ...]}
```

**Raw output**

```json
{"tasks": [{"start": "06:00", "duration_minutes": 15, "activity": "have breakfast (getting started)"}, {"start": "06:15", "duration_minutes": 15, "activity": "have breakfast (continuing)"}, {"start": "06:30", "duration_minutes": 15, "activity": "have breakfast (making progress)"}, {"start": "06:45", "duration_minutes": 15, "activity": "have breakfast (wrapping up)"}]}
```

**Validated output**

```json
{
  "tasks": [
    {
      "start": "06:00",
      "duration_minutes": 15,
      "activity": "have breakfast (getting started)"
    },
    {
      "start": "06:15",
      "duration_minutes": 15,
      "activity": "have breakfast (continuing)"
    },
    {
      "start": "06:30",
      "duration_minutes": 15,
      "activity": "have breakfast (making progress)"
    },
    {
      "start": "06:45",
      "duration_minutes": 15,
      "activity": "have breakfast (wrapping up)"
    }
  ]
}
```

No call for this task needed a repair in this run.
