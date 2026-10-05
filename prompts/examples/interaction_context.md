# `interaction_context@v1`

> Example from run `examples-main` (offline two-day pilot (MOCK)), default architecture settings. Inputs are exactly what the model was sent in that state; outputs show the format only, not model behavior.

* Template: [`prompts/interaction_context.v1.md`](../interaction_context.v1.md) · SHA-256 `0e8c7677956a1fdd376c938dd739f12ae8823b4dae7774bb9aaa6062b1ee5123`
* Source: Paper §4.3.1 p. 11 (context summary from the queries 'What is [observer]'s relationship with the [observed entity]?' and '[Observed entity] is [action status]', summarized together); released v3_ChatGPT/summarize_chat_relationship_v2.txt
* Information scope: Memories retrieved from the observer's own stream for the two queries.
* Output model: `SummaryOut` · max output tokens 300 · effort low
* Calls in this run: 212 (ok 212; 0 repair attempts)

## Output schema

```json
{
  "additionalProperties": false,
  "properties": {
    "summary": {
      "type": "string"
    }
  },
  "required": [
    "summary"
  ],
  "type": "object"
}
```

## Smallest successful call

Ledger call 595 · scope `examples-main` · sim time 2023-02-13T12:03:30 · agent `maria_lopez` · model `mock-llm-v1` · status `ok` · tokens 597 in / 44 out (estimated)

**System**

```text
You are one component of a research simulation of believable characters, reproducing the generative agents architecture (Park et al., UIST 2023). Use only the information in the request; do not invent facts about the world or other characters. Reply with JSON that matches the requested schema and nothing else.
```

**User**

```text
[Statements from Maria Lopez's memory]
- This is very important -- you have a secret crush on Klaus Mueller
- You and Klaus Mueller are close friends and classmates
- Maria Lopez is have lunch at Hobbs Cafe (getting started)
- Maria Lopez plans to sleeping from 23:30 to 24:00 on Monday February 13.
- Maria Lopez plans to have breakfast from 11:00 to 12:00 on Monday February 13.
- Maria Lopez plans to have lunch at Hobbs Cafe from 12:00 to 13:00 on Monday February 13.
- Maria Lopez plans to go about the daily routine (spends at least 6 hours a day Twitch streaming or gaming) from 13:00 to 18:00 on Monday February 13.
- Klaus Mueller is have lunch at Hobbs Cafe (getting started)
- Maria Lopez plans to wake up and complete the morning routine from 10:00 to 11:00 on Monday February 13.
- Maria Lopez is sleeping
- Maria Lopez plans to go to bed from 23:00 to 23:30 on Monday February 13.
- For planning, you frequent Hobbs Cafe for studying
- You are close with Ayesha Khan, who is a classmate in one of your classes and a dormmate
- Maria Lopez plans to have dinner from 18:00 to 22:00 on Monday February 13.
- You and Wolfgang Schulz are classmates and dormmates
- Maria Lopez plans to relax and wind down from 22:00 to 23:00 on Monday February 13.
- Maria Lopez is have breakfast (getting started)
- Maria Lopez is have breakfast (getting started)
- Maria Lopez is wake up and complete the morning routine (getting started)
- cooking area is being used to cook
- kitchen sink is being used
- cooking area is idle
- refrigerator is idle
- kitchen sink is idle
- toaster is idle
- computer is idle
- blackboard is idle
- closet is idle
- desk is idle
- bed is idle

Based only on the statements above, summarize what Maria Lopez knows about their relationship with Klaus Mueller and about Klaus Mueller (currently: Klaus Mueller is have lunch at Hobbs Cafe (getting started)). Write two or three sentences in the third person. If the statements say nothing about Klaus Mueller, say that Maria Lopez does not know Klaus Mueller.

Respond with JSON: {"summary": "..."}
```

**Raw output**

```json
{"summary": "Maria Lopez knows Klaus Mueller: This is very important -- you have a secret crush on Klaus Mueller. Klaus Mueller is have lunch at Hobbs Cafe (getting started)."}
```

**Validated output**

```json
{
  "summary": "Maria Lopez knows Klaus Mueller: This is very important -- you have a secret crush on Klaus Mueller. Klaus Mueller is have lunch at Hobbs Cafe (getting started)."
}
```

No call for this task needed a repair in this run.
