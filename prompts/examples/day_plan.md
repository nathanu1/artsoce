# `day_plan@v1`

> Example from run `examples-main` (offline two-day pilot (MOCK)), default architecture settings. Inputs are exactly what the model was sent in that state; outputs show the format only, not model behavior.

* Template: [`prompts/day_plan.v1.md`](../day_plan.v1.md) · SHA-256 `a1584ce4ae0700d899b53527ab2058771c3dbe8f1108e4c3676e182aa95104e7`
* Source: Paper §4.3 p. 11 (Eddy Lin prompt: name, age, traits, summary, previous day, 'Here is Eddy's plan today in broad strokes'); released v2/daily_planning_v6.txt (lifestyle and daily requirement fields)
* Information scope: The agent's authored identity, its dynamic summary (own memories only), its own previous-day summary.
* Output model: `DayPlanOut` · max output tokens 700 · effort medium
* Calls in this run: 15 (ok 15; 0 repair attempts)

## Output schema

```json
{
  "$defs": {
    "DayPlanItem": {
      "additionalProperties": false,
      "properties": {
        "time": {
          "type": "string"
        },
        "activity": {
          "type": "string"
        }
      },
      "required": [
        "time",
        "activity"
      ],
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "wake_up_time": {
      "type": "string"
    },
    "items": {
      "items": {
        "$ref": "#/$defs/DayPlanItem"
      },
      "type": "array"
    }
  },
  "required": [
    "wake_up_time",
    "items"
  ],
  "type": "object"
}
```

## Smallest successful call

Ledger call 19 · scope `examples-main` · sim time 2023-02-13T00:00:00 · agent `maria_lopez` · model `mock-llm-v1` · status `ok` · tokens 440 in / 121 out (estimated)

**System**

```text
You are one component of a research simulation of believable characters, reproducing the generative agents architecture (Park et al., UIST 2023). Use only the information in the request; do not invent facts about the world or other characters. Reply with JSON that matches the requested schema and nothing else.
```

**User**

```text
Name: Maria Lopez (age: 21)
Innate traits: energetic, enthusiastic, inquisitive
Maria Lopez is a student at Oak Hill College studying physics and a part time Twitch game streamer who loves to connect with people and explore new ideas.
Maria Lopez is working on her physics degree and streaming games on Twitch to make some extra money. She visits Hobbs Cafe for studying and eating just about everyday.
Maria Lopez is energetic, enthusiastic, inquisitive. Notably: You and Wolfgang Schulz are classmates and dormmates; This is very important -- you have a secret crush on Klaus Mueller.
Maria Lopez spends the day on the usual routine. Notably: This is very important -- you have a secret crush on Klaus Mueller; For planning, you frequent Hobbs Cafe for studying.
Maria Lopez feels steady about recent progress. Notably: This is very important -- you have a secret crush on Klaus Mueller; For planning, you frequent Hobbs Cafe for studying.
Lifestyle: Maria Lopez goes to bed around midnight, awakes up around 10am, eats dinner around 7pm.
Daily routine: Maria Lopez spends at least 6 hours a day Twitch streaming or gaming.

Today is Monday February 13. Here is Maria's plan today in broad strokes, as 5 to 8 items, each with the time of day (e.g., "wake up and complete the morning routine at 8:00 am").

Respond with JSON: {"wake_up_time": "HH:MM", "items": [{"time": "HH:MM", "activity": "<what>"}, ...]} in chronological order, 24-hour times.
```

**Raw output**

```json
{"wake_up_time": "10:00", "items": [{"time": "10:00", "activity": "wake up and complete the morning routine"}, {"time": "11:00", "activity": "have breakfast"}, {"time": "12:00", "activity": "have lunch at Hobbs Cafe"}, {"time": "13:00", "activity": "go about the daily routine (spends at least 6 hours a day Twitch streaming or gaming)"}, {"time": "18:00", "activity": "have dinner"}, {"time": "22:00", "activity": "relax and wind down"}, {"time": "23:00", "activity": "go to bed"}]}
```

**Validated output**

```json
{
  "wake_up_time": "10:00",
  "items": [
    {
      "time": "10:00",
      "activity": "wake up and complete the morning routine"
    },
    {
      "time": "11:00",
      "activity": "have breakfast"
    },
    {
      "time": "12:00",
      "activity": "have lunch at Hobbs Cafe"
    },
    {
      "time": "13:00",
      "activity": "go about the daily routine (spends at least 6 hours a day Twitch streaming or gaming)"
    },
    {
      "time": "18:00",
      "activity": "have dinner"
    },
    {
      "time": "22:00",
      "activity": "relax and wind down"
    },
    {
      "time": "23:00",
      "activity": "go to bed"
    }
  ]
}
```

No call for this task needed a repair in this run.
