# `summary_aspect@v1`

> Example from run `examples-main` (offline two-day pilot (MOCK)), default architecture settings. Inputs are exactly what the model was sent in that state; outputs show the format only, not model behavior.

* Template: [`prompts/summary_aspect.v1.md`](../summary_aspect.v1.md) · SHA-256 `50449d8eae9cdea6da4fd40f637f4ea5fbe7027334aa0e8d3841b40d15018ebf`
* Source: Paper Appendix A p. 21 ('How would one describe Eddy Lin's core characteristics given the following statements?')
* Information scope: Statements retrieved from the agent's own memory stream under the active memory mask.
* Output model: `SummaryOut` · max output tokens 300 · effort low
* Calls in this run: 294 (ok 294; 0 repair attempts)

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

Ledger call 27 · scope `examples-main` · sim time 2023-02-13T00:00:00 · agent `klaus_mueller` · model `mock-llm-v1` · status `ok` · tokens 227 in / 46 out (estimated)

**System**

```text
You are one component of a research simulation of believable characters, reproducing the generative agents architecture (Park et al., UIST 2023). Use only the information in the request; do not invent facts about the world or other characters. Reply with JSON that matches the requested schema and nothing else.
```

**User**

```text
How would one describe Klaus Mueller's core characteristics given the following statements?
- You and Wolfgang Schulz are classmates and dormmates
- This is very important -- you have a crush on Maria Lopez
- You and Maria Lopez are dormmates
- You are close with Ayesha Khan, who is a classmate in one of your classes and a dormmate
- You and Eddy Lin are classmates
- You and Maria Lopez are close friends and classmates
- You know Mei Lin is a professor at your college
- You and Maria Lopez have known each other for over 2 years now

Respond with JSON: {"summary": "<one to three sentences>"}
```

**Raw output**

```json
{"summary": "Klaus Mueller is kind, inquisitive, passionate. Notably: You and Wolfgang Schulz are classmates and dormmates; This is very important -- you have a crush on Maria Lopez."}
```

**Validated output**

```json
{
  "summary": "Klaus Mueller is kind, inquisitive, passionate. Notably: You and Wolfgang Schulz are classmates and dormmates; This is very important -- you have a crush on Maria Lopez."
}
```

No call for this task needed a repair in this run.
