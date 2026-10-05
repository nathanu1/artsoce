# `judge@v1`

> Example from run `examples-main` (offline two-day pilot (MOCK)), default architecture settings. Inputs are exactly what the model was sent in that state; outputs show the format only, not model behavior.

* Template: [`prompts/judge.v1.md`](../judge.v1.md) · SHA-256 `1872232bfc0cfac69fb72c6d1e5a8c82b38232c4185bc077f35bc90bc2be88b0`
* Source: Experimental extension (spec §8): optional exploratory LLM judge. Never reported as human believability.
* Information scope: One interview question, the agent's public description and one anonymized answer.
* Output model: `JudgeOut` · max output tokens 300 · effort low
* Calls in this run: 500 (ok 500; 0 repair attempts)

## Output schema

```json
{
  "additionalProperties": false,
  "properties": {
    "score": {
      "type": "integer"
    },
    "rationale": {
      "type": "string"
    }
  },
  "required": [
    "score",
    "rationale"
  ],
  "type": "object"
}
```

## Smallest successful call

Ledger call 5649 · scope `examples-main::judge::appendix_b` · sim time n/a · agent `n/a` · model `mock-llm-v1` · status `ok` · tokens 225 in / 17 out (estimated)

**System**

```text
You are one component of a research simulation of believable characters, reproducing the generative agents architecture (Park et al., UIST 2023). Use only the information in the request; do not invent facts about the world or other characters. Reply with JSON that matches the requested schema and nothing else.
```

**User**

```text
Character: Sam Moore, age 65. Traits: wise, resourceful, humorous. Sam Moore is a retired navy officer who loves to share stories from his time in the military. He is always full of interesting stories and advice. Sam Moore goes to bed around 9pm, awakes up around 5am, eats dinner around 5pm.
Question: Who do you live with?
Answer: I'm not sure about that.

On a scale of 1 to 7, how believable is this answer as something this character would say? This is an exploratory automated rating, not a human judgment.

Respond with JSON: {"score": <integer 1-7>, "rationale": "<one sentence>"}
```

**Raw output**

```json
{"score": 2, "rationale": "Mock heuristic based on answer length."}
```

**Validated output**

```json
{
  "score": 2,
  "rationale": "Mock heuristic based on answer length."
}
```

No call for this task needed a repair in this run.
