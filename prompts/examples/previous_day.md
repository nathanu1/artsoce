# `previous_day@v1`

> Example from run `examples-main` (offline two-day pilot (MOCK)), default architecture settings. Inputs are exactly what the model was sent in that state; outputs show the format only, not model behavior.

* Template: [`prompts/previous_day.v1.md`](../previous_day.v1.md) · SHA-256 `28bbdd7633400ab02db35a54f572952e3f82aff4897820585b8d78bc4b5fcd9a`
* Source: Paper §4.3 p. 11 (day plan uses 'a summary of their previous day'); released plan.py revise_identity (retrieval of '[name]'s plan for [day]' and 'Important recent events for [name]'s life')
* Information scope: Memories retrieved from the agent's own stream about yesterday's plan and important recent events.
* Output model: `SummaryOut` · max output tokens 400 · effort low
* Calls in this run: 10 (ok 10; 0 repair attempts)

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

Ledger call 2527 · scope `examples-main` · sim time 2023-02-14T00:00:00 · agent `wolfgang_schulz` · model `mock-llm-v1` · status `ok` · tokens 623 in / 105 out (estimated)

**System**

```text
You are one component of a research simulation of believable characters, reproducing the generative agents architecture (Park et al., UIST 2023). Use only the information in the request; do not invent facts about the world or other characters. Reply with JSON that matches the requested schema and nothing else.
```

**User**

```text
Statements:
- Sam Moore said to Wolfgang Schulz: "Hi Wolfgang! Did you hear? Maria Lopez told me: Wolfgang Schulz told me: Sam Moore told me: I am thinking of running in the upcoming local mayor election."
- Wolfgang Schulz keeps coming back to mayor
- Wolfgang Schulz keeps coming back to mayor
- Wolfgang Schulz keeps coming back to election
- Wolfgang Schulz said to Maria Lopez: "Oh, also: Sam Moore told me: I am thinking of running in the upcoming local mayor election."
- Sam Moore said to Wolfgang Schulz: "Oh, also: I am thinking of running in the upcoming local mayor election."
- Sam Moore said to Wolfgang Schulz: "Hi Wolfgang! Did you hear? I am telling people that I am running for the upcoming local mayor election."
- Maria Lopez said to Wolfgang Schulz: "Hi Wolfgang! Did you hear? Klaus Mueller told me: This is very important -- I have a crush on Maria Lopez."
- Klaus Mueller said to Wolfgang Schulz: "Hi Wolfgang! Did you hear? Maria Lopez told me: This is very important -- I have a secret crush on Klaus Mueller."
- Klaus Mueller said to Wolfgang Schulz: "Hi Wolfgang! Did you hear? Maria Lopez told me: This is very important -- I have a secret crush on Klaus Mueller."
- Maria Lopez said to Wolfgang Schulz: "Oh, also: Klaus Mueller told me: This is very important -- I have a crush on Maria Lopez."
- Wolfgang Schulz plans to sleeping from 00:00 to 05:00 on Monday February 13.
- Wolfgang Schulz keeps coming back to party
- Wolfgang Schulz said to Sam Moore: "That sounds wonderful, I'd love to come to the party!"
- Wolfgang Schulz said to Sam Moore: "Oh, also: Maria Lopez told me: Klaus Mueller told me: This is very important -- I have a crush on Maria Lopez."
- Sam Moore said to Wolfgang Schulz: "Hi Wolfgang! Did you hear? I am telling people that I am running for the upcoming local mayor election."

Given the statements above, summarize Wolfgang Schulz's Monday February 13 in two or three sentences, written in the third person. Include anything Wolfgang should remember while planning Tuesday February 14; if there is scheduling information, be as specific as the statements are (date, time and place).

Respond with JSON: {"summary": "..."}
```

**Raw output**

```json
{"summary": "Wolfgang Schulz followed their routine on Monday February 13. To remember: Sam Moore said to Wolfgang Schulz: \"Hi Wolfgang! Did you hear? Maria Lopez told me: Wolfgang Schulz told me: Sam Moore told me: I am thinking of running in the upcoming local mayor election.\"; Wolfgang Schulz said to Maria Lopez: \"Oh, also: Sam Moore told me: I am thinking of running in the upcoming local mayor election.\"."}
```

**Validated output**

```json
{
  "summary": "Wolfgang Schulz followed their routine on Monday February 13. To remember: Sam Moore said to Wolfgang Schulz: \"Hi Wolfgang! Did you hear? Maria Lopez told me: Wolfgang Schulz told me: Sam Moore told me: I am thinking of running in the upcoming local mayor election.\"; Wolfgang Schulz said to Maria Lopez: \"Oh, also: Sam Moore told me: I am thinking of running in the upcoming local mayor election.\"."
}
```

No call for this task needed a repair in this run.
