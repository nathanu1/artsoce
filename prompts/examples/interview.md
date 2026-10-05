# `interview@v1`

> Example from run `examples-main` (offline two-day pilot (MOCK)), default architecture settings. Inputs are exactly what the model was sent in that state; outputs show the format only, not model behavior.

* Template: [`prompts/interview.v1.md`](../interview.v1.md) · SHA-256 `115b2f05086eec4b1203c6b85959962f16e844f8af42e1ba4bbc7bc3a18c991a`
* Source: Paper §3.1.2 p. 6 and §6.1 p. 13 (interviewing agents in natural language); released converse.py open_convo_session 'analysis' mode (retrieve on the question, summarize, answer as the agent)
* Information scope: The agent's static identity, its dynamic summary rebuilt under the condition's memory mask, and memories retrieved under that mask. The interviewer is an outside visitor.
* Output model: `InterviewAnswerOut` · max output tokens 400 · effort medium
* Calls in this run: 560 (ok 560; 0 repair attempts)

## Output schema

```json
{
  "additionalProperties": false,
  "properties": {
    "answer": {
      "type": "string"
    }
  },
  "required": [
    "answer"
  ],
  "type": "object"
}
```

## Smallest successful call

Ledger call 5505 · scope `examples-main::interview::appendix_b::no_memory_stream` · sim time 2023-02-15T00:01:00 · agent `klaus_mueller` · model `mock-llm-v1` · status `ok` · tokens 341 in / 17 out (estimated)

**System**

```text
You are one component of a research simulation of believable characters, reproducing the generative agents architecture (Park et al., UIST 2023). Use only the information in the request; do not invent facts about the world or other characters. Reply with JSON that matches the requested schema and nothing else.
```

**User**

```text
Name: Klaus Mueller
Age: 20
Innate traits: kind, inquisitive, passionate
Learned traits: Klaus Mueller is a student at Oak Hill College studying sociology. He is passionate about social justice and loves to explore different perspectives.
Currently: Klaus Mueller is writing a research paper on the effects of gentrification in low-income communities.
Lifestyle: Klaus Mueller goes to bed around 11pm, awakes up around 7am, eats dinner around 5pm.
Daily plan requirement: Klaus Mueller goes to the library at Oak Hill College early in the morning, spends his days writing, and eats at Hobbs Cafe.
Current Date: Wednesday February 15
It is February 15, 2023, 12:01 am.
Here are memories Klaus Mueller has that may be relevant:
(no memories available)

An outside visitor (an interviewer) asks Klaus Mueller: "Who is Maria Lopez?"
Answer as Klaus Mueller would, in the first person and in character. Use only what Klaus Mueller knows; if Klaus Mueller does not know or remember something, say so rather than guessing.

Respond with JSON: {"answer": "..."}
```

**Raw output**

```json
{"answer": "I'm not sure; I don't remember anything about that."}
```

**Validated output**

```json
{
  "answer": "I'm not sure; I don't remember anything about that."
}
```

No call for this task needed a repair in this run.
