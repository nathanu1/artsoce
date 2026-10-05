# `hourly_schedule@v1`

> Example from run `examples-main` (offline two-day pilot (MOCK)), default architecture settings. Inputs are exactly what the model was sent in that state; outputs show the format only, not model behavior.

* Template: [`prompts/hourly_schedule.v1.md`](../hourly_schedule.v1.md) · SHA-256 `bda97a3bb2f4ea1a210ac9d120a2629920a2af50d62e1684aac9a7edc58e7138`
* Source: Paper §4.3 p. 11 (decompose the day plan into hour-long chunks); released v2/generate_hourly_schedule_v2.txt asked one hour per call
* Information scope: The agent's authored identity, dynamic summary and today's broad plan.
* Output model: `HourlyScheduleOut` · max output tokens 1200 · effort medium
* Calls in this run: 15 (ok 15; 0 repair attempts)

## Output schema

```json
{
  "$defs": {
    "HourlyBlock": {
      "additionalProperties": false,
      "properties": {
        "start": {
          "type": "string"
        },
        "end": {
          "type": "string"
        },
        "activity": {
          "type": "string"
        }
      },
      "required": [
        "start",
        "end",
        "activity"
      ],
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "blocks": {
      "items": {
        "$ref": "#/$defs/HourlyBlock"
      },
      "type": "array"
    }
  },
  "required": [
    "blocks"
  ],
  "type": "object"
}
```

## Smallest successful call

Ledger call 21 · scope `examples-main` · sim time 2023-02-13T00:00:00 · agent `maria_lopez` · model `mock-llm-v1` · status `ok` · tokens 537 in / 175 out (estimated)

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

Today is Monday February 13. Maria's plan in broad strokes:
10:00 wake up and complete the morning routine
11:00 have breakfast
12:00 have lunch at Hobbs Cafe
13:00 go about the daily routine (spends at least 6 hours a day Twitch streaming or gaming)
18:00 have dinner
22:00 relax and wind down
23:00 go to bed

Turn this into an hour-by-hour schedule that covers the whole day from 00:00 to 24:00 with no gaps or overlaps. Use hour-long chunks (longer chunks are fine for sleep or long activities). Maria is sleeping before waking up at 10:00 and after going to bed.

Respond with JSON: {"blocks": [{"start": "HH:MM", "end": "HH:MM", "activity": "<what Maria is doing>"}, ...]}. The first block starts at 00:00, each block starts where the previous one ended, and the last block ends at 24:00.
```

**Raw output**

```json
{"blocks": [{"start": "00:00", "end": "10:00", "activity": "sleeping"}, {"start": "10:00", "end": "11:00", "activity": "wake up and complete the morning routine"}, {"start": "11:00", "end": "12:00", "activity": "have breakfast"}, {"start": "12:00", "end": "13:00", "activity": "have lunch at Hobbs Cafe"}, {"start": "13:00", "end": "18:00", "activity": "go about the daily routine (spends at least 6 hours a day Twitch streaming or gaming)"}, {"start": "18:00", "end": "22:00", "activity": "have dinner"}, {"start": "22:00", "end": "23:00", "activity": "relax and wind down"}, {"start": "23:00", "end": "23:30", "activity": "go to bed"}, {"start": "23:30", "end": "24:00", "activity": "sleeping"}]}
```

**Validated output**

```json
{
  "blocks": [
    {
      "start": "00:00",
      "end": "10:00",
      "activity": "sleeping"
    },
    {
      "start": "10:00",
      "end": "11:00",
      "activity": "wake up and complete the morning routine"
    },
    {
      "start": "11:00",
      "end": "12:00",
      "activity": "have breakfast"
    },
    {
      "start": "12:00",
      "end": "13:00",
      "activity": "have lunch at Hobbs Cafe"
    },
    {
      "start": "13:00",
      "end": "18:00",
      "activity": "go about the daily routine (spends at least 6 hours a day Twitch streaming or gaming)"
    },
    {
      "start": "18:00",
      "end": "22:00",
      "activity": "have dinner"
    },
    {
      "start": "22:00",
      "end": "23:00",
      "activity": "relax and wind down"
    },
    {
      "start": "23:00",
      "end": "23:30",
      "activity": "go to bed"
    },
    {
      "start": "23:30",
      "end": "24:00",
      "activity": "sleeping"
    }
  ]
}
```

No call for this task needed a repair in this run.
