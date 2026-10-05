# `choose_location@v1`

> Example from run `examples-main` (offline two-day pilot (MOCK)), default architecture settings. Inputs are exactly what the model was sent in that state; outputs show the format only, not model behavior.

* Template: [`prompts/choose_location.v1.md`](../choose_location.v1.md) · SHA-256 `683ebf47feedbd322dfbe2f7fc90eaa5110668e059a39cf4ddaf76f4ade2528e`
* Source: Paper §5.1 p. 12 (Eddy Lin area prompt: current area, known areas, 'Prefer to stay in the current area if the activity can be done there'); released v1/action_location_sector_v1.txt, action_location_object_vMar11.txt, action_object_v2.txt
* Information scope: The agent's dynamic summary and its private, possibly stale, spatial memory only.
* Output model: `LocationChoiceOut` · max output tokens 120 · effort low
* Calls in this run: 1694 (ok 1694; 0 repair attempts)

## Output schema

```json
{
  "additionalProperties": false,
  "properties": {
    "choice": {
      "type": "string"
    }
  },
  "required": [
    "choice"
  ],
  "type": "object"
}
```

## Smallest successful call

Ledger call 36 · scope `examples-main` · sim time 2023-02-13T00:00:00 · agent `klaus_mueller` · model `mock-llm-v1` · status `ok` · tokens 477 in / 5 out (estimated)

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
Current Date: Monday February 13
Klaus Mueller is kind, inquisitive, passionate. Notably: You and Wolfgang Schulz are classmates and dormmates; This is very important -- you have a crush on Maria Lopez.
Klaus Mueller spends the day on the usual routine. Notably: This is very important -- you have a crush on Maria Lopez; You and Wolfgang Schulz are classmates and dormmates.
Klaus Mueller feels steady about recent progress. Notably: This is very important -- you have a crush on Maria Lopez; You and Wolfgang Schulz are classmates and dormmates.
Klaus Mueller is currently in Dorm for Oak Hill College: Klaus Mueller's room, and is heading to Dorm for Oak Hill College: Klaus Mueller's room.
Klaus Mueller knows of the following objects: bed, closet, desk, game console.
* Prefer to stay in the current area if the activity can be done there.
Klaus Mueller is planning to sleeping. Which object should Klaus Mueller go to?

Respond with JSON: {"choice": "<exactly one of the objects listed above>"}
```

**Raw output**

```json
{"choice": "bed"}
```

**Validated output**

```json
{
  "choice": "bed"
}
```

No call for this task needed a repair in this run.
