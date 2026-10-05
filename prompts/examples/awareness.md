# `awareness@v1`

> Example from run `examples-main` (offline two-day pilot (MOCK)), default architecture settings. Inputs are exactly what the model was sent in that state; outputs show the format only, not model behavior.

* Template: [`prompts/awareness.v1.md`](../awareness.v1.md) · SHA-256 `ab3593bde0d63af12e1bcba0aeaacd02e5eb33f89a1547f95b8a23e2fffe6bba`
* Source: Paper §7.1.1 p. 15 (answers labeled 'yes' if they indicate knowledge, 'no' otherwise; done by hand in the paper). Automated labeling is our extension and is reported as such.
* Information scope: One interview question and answer, plus the list of details to check. No access to the agent's memory.
* Output model: `AwarenessOut` · max output tokens 300 · effort low
* Calls in this run: 60 (ok 60; 0 repair attempts)

## Output schema

```json
{
  "additionalProperties": false,
  "properties": {
    "claims_knowledge": {
      "type": "boolean"
    },
    "details": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "quote": {
      "type": "string"
    }
  },
  "required": [
    "claims_knowledge",
    "details",
    "quote"
  ],
  "type": "object"
}
```

## Smallest successful call

Ledger call 4916 · scope `examples-main::probe::initial` · sim time 2023-02-13T00:00:00 · agent `isabella_rodriguez` · model `mock-llm-v1` · status `ok` · tokens 183 in / 14 out (estimated)

**System**

```text
You are one component of a research simulation of believable characters, reproducing the generative agents architecture (Park et al., UIST 2023). Use only the information in the request; do not invent facts about the world or other characters. Reply with JSON that matches the requested schema and nothing else.
```

**User**

```text
Question: Do you know of Sam Moore?
Answer: I'm not sure about that.

Does the answer say the speaker knows about Sam Moore? Answer false if the speaker says they don't know, are unsure, or only speculate.
Which of these details does the answer state (list only those it states): (none)

Respond with JSON: {"claims_knowledge": true | false, "details": ["<detail names>"], "quote": "<the phrase that shows it, or empty>"}
```

**Raw output**

```json
{"claims_knowledge": false, "details": [], "quote": ""}
```

**Validated output**

```json
{
  "claims_knowledge": false,
  "details": [],
  "quote": ""
}
```

No call for this task needed a repair in this run.
