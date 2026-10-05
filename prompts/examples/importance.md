# `importance@v1`

> Example from run `examples-main` (offline two-day pilot (MOCK)), default architecture settings. Inputs are exactly what the model was sent in that state; outputs show the format only, not model behavior.

* Template: [`prompts/importance.v1.md`](../importance.v1.md) · SHA-256 `bc3e75179b84d94f6c5dc7661a846ae87f00a60d1228f645ce4447db907ff2e9`
* Source: Paper §4.1 p. 9 (prompt quoted there; core sentence kept); identity block and per-kind anchors from released v3_ChatGPT/poignancy_event_v1.txt, poignancy_chat_v1.txt, poignancy_thought_v1.txt
* Information scope: The rating agent's own summary description and the single memory being rated.
* Output model: `ImportanceOut` · max output tokens 64 · effort low
* Calls in this run: 1273 (ok 1273; 0 repair attempts)

## Output schema

```json
{
  "additionalProperties": false,
  "properties": {
    "rating": {
      "type": "integer"
    }
  },
  "required": [
    "rating"
  ],
  "type": "object"
}
```

## Smallest successful call

Ledger call 2460 · scope `examples-main` · sim time 2023-02-13T23:03:40 · agent `klaus_mueller` · model `mock-llm-v1` · status `ok` · tokens 326 in / 4 out (estimated)

**System**

```text
You are one component of a research simulation of believable characters, reproducing the generative agents architecture (Park et al., UIST 2023). Use only the information in the request; do not invent facts about the world or other characters. Reply with JSON that matches the requested schema and nothing else.
```

**User**

```text
Here is a brief description of Klaus Mueller.
Name: Klaus Mueller
Age: 20
Innate traits: kind, inquisitive, passionate
Learned traits: Klaus Mueller is a student at Oak Hill College studying sociology. He is passionate about social justice and loves to explore different perspectives.
Currently: Klaus Mueller is writing a research paper on the effects of gentrification in low-income communities.
Lifestyle: Klaus Mueller goes to bed around 11pm, awakes up around 7am, eats dinner around 5pm.
Daily plan requirement: Klaus Mueller goes to the library at Oak Hill College early in the morning, spends his days writing, and eats at Hobbs Cafe.
Current Date: Monday February 13

On the scale of 1 to 10, where 1 is purely mundane (e.g., brushing teeth, making bed) and 10 is extremely poignant (e.g., a break up, college acceptance), rate the likely poignancy of the following piece of memory for Klaus Mueller.

Memory: bed is being used

Respond with JSON: {"rating": <integer from 1 to 10>}
```

**Raw output**

```json
{"rating": 2}
```

**Validated output**

```json
{
  "rating": 2
}
```

No call for this task needed a repair in this run.
