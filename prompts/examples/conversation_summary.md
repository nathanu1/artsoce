# `conversation_summary@v1`

> Example from run `examples-main` (offline two-day pilot (MOCK)), default architecture settings. Inputs are exactly what the model was sent in that state; outputs show the format only, not model behavior.

* Template: [`prompts/conversation_summary.v1.md`](../conversation_summary.v1.md) · SHA-256 `f32c7e8758b45df986495408db04677940f31f505119ca28cfd448dedfbb7812`
* Source: Released v3_ChatGPT/summarize_conversation_v1.txt ('Summarize the conversation above in one sentence: This is a conversation about')
* Information scope: The transcript of one conversation, which both participants heard. Observational: no inferences about intentions or traits.
* Output model: `SummaryOut` · max output tokens 160 · effort low
* Calls in this run: 31 (ok 31; 0 repair attempts)

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

Ledger call 3187 · scope `examples-main` · sim time 2023-02-14T12:11:30 · agent `isabella_rodriguez` · model `mock-llm-v1` · status `ok` · tokens 177 in / 17 out (estimated)

**System**

```text
You are one component of a research simulation of believable characters, reproducing the generative agents architecture (Park et al., UIST 2023). Use only the information in the request; do not invent facts about the world or other characters. Reply with JSON that matches the requested schema and nothing else.
```

**User**

```text
Conversation:
Isabella Rodriguez: Hi Klaus! Did you hear? Maria Lopez told me: That sounds wonderful, I'd love to come to the party!. You should come!
Klaus Mueller: Wonderful, see you there, Isabella!

Summarize the conversation above in one sentence, describing only what was said. Start with "This is a conversation about".

Respond with JSON: {"summary": "This is a conversation about ..."}
```

**Raw output**

```json
{"summary": "This is a conversation about a Valentine's Day party."}
```

**Validated output**

```json
{
  "summary": "This is a conversation about a Valentine's Day party."
}
```

No call for this task needed a repair in this run.
