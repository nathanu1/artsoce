# `seed_thought@v1`

> Example from run `examples-compat` (offline smoke (MOCK)), settings that differ from the defaults: `architecture.post_conversation_inferences=True`, `scenario.seed_rendering=inner_thought_llm`. Inputs are exactly what the model was sent in that state; outputs show the format only, not model behavior.

* Template: [`prompts/seed_thought.v1.md`](../seed_thought.v1.md) · SHA-256 `801240348348022eaa82308b78de94669be27229aa04abf2c680f72bb31de6ed`
* Source: Released v2/whisper_inner_thought_v1.txt via converse.py load_history_via_whisper (released-code seed rendering; scenario.seed_rendering=inner_thought_llm)
* Information scope: One authored history statement for this agent.
* Output model: `StatementOut` · max output tokens 160 · effort low
* Calls in this run: 51 (ok 51; 0 repair attempts)

## Output schema

```json
{
  "additionalProperties": false,
  "properties": {
    "statement": {
      "type": "string"
    }
  },
  "required": [
    "statement"
  ],
  "type": "object"
}
```

## Smallest successful call

Ledger call 23 · scope `examples-compat` · sim time 2023-02-13T06:00:00 · agent `maria_lopez` · model `mock-llm-v1` · status `ok` · tokens 116 in / 14 out (estimated)

**System**

```text
You are one component of a research simulation of believable characters, reproducing the generative agents architecture (Park et al., UIST 2023). Use only the information in the request; do not invent facts about the world or other characters. Reply with JSON that matches the requested schema and nothing else.
```

**User**

```text
Translate the following thought into a statement about Maria Lopez.

Thought: "You and Eddy Lin are classmates"

Respond with JSON: {"statement": "..."}
```

**Raw output**

```json
{"statement": "Maria Lopez and Eddy Lin are classmates"}
```

**Validated output**

```json
{
  "statement": "Maria Lopez and Eddy Lin are classmates"
}
```

No call for this task needed a repair in this run.
