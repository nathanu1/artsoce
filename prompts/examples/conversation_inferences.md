# `conversation_inferences@v1`

> Example from run `examples-compat` (offline smoke (MOCK)), settings that differ from the defaults: `architecture.post_conversation_inferences=True`, `scenario.seed_rendering=inner_thought_llm`. Inputs are exactly what the model was sent in that state; outputs show the format only, not model behavior.

* Template: [`prompts/conversation_inferences.v1.md`](../conversation_inferences.v1.md) · SHA-256 `8bc8a1628fc30819245120ff724c2e464e2fa780f2c1b54750ee7c72e63a3a5d`
* Source: Released v2/planning_thought_on_convo_v1.txt and v2/memo_on_convo_v1.txt (reflect.py:186-245). Not in the paper. Released-code compatibility only; disabled when reflection is off.
* Information scope: The transcript of one conversation the agent took part in.
* Output model: `ConversationInferencesOut` · max output tokens 300 · effort low
* Calls in this run: 2 (ok 2; 0 repair attempts)

## Output schema

```json
{
  "additionalProperties": false,
  "properties": {
    "planning_note": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "memo": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "type": "object",
  "required": [
    "planning_note",
    "memo"
  ]
}
```

## Smallest successful call

Ledger call 284 · scope `examples-compat` · sim time 2023-02-13T08:17:00 · agent `sam_moore` · model `mock-llm-v1` · status `ok` · tokens 298 in / 20 out (estimated)

**System**

```text
You are one component of a research simulation of believable characters, reproducing the generative agents architecture (Park et al., UIST 2023). Use only the information in the request; do not invent facts about the world or other characters. Reply with JSON that matches the requested schema and nothing else.
```

**User**

```text
[Conversation]
Sam Moore: Hi Wolfgang! Did you hear? Sam Moore is telling people that Sam are running for the upcoming local mayor election.
Wolfgang Schulz: Oh, also: Wolfgang Schulz is close with Ayesha Khan, who is a classmate in one of their classes and a dormmate.
Sam Moore: Oh, also: Sam Moore is thinking of running in the upcoming local mayor election.
Wolfgang Schulz: Good to know!
Sam Moore: It was good talking to you, Wolfgang. See you around!

1. Write down if there is anything from the conversation that Sam Moore needs to remember for their planning, from Sam Moore's perspective, in a full sentence (or null).
2. Write down if there is anything from the conversation that Sam Moore might have found interesting, from Sam Moore's perspective, in a full sentence (or null).

Respond with JSON: {"planning_note": "<sentence or null>", "memo": "<sentence or null>"}
```

**Raw output**

```json
{"planning_note": null, "memo": "Sam Moore found the conversation pleasant."}
```

**Validated output**

```json
{
  "planning_note": null,
  "memo": "Sam Moore found the conversation pleasant."
}
```

No call for this task needed a repair in this run.
