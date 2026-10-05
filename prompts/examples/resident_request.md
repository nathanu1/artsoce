# `resident_request@v1`

> Example from run `examples-game` (town game (MOCK)), settings that differ from the defaults: `game.enabled=True`. Inputs are exactly what the model was sent in that state; outputs show the format only, not model behavior.

* Template: [`prompts/resident_request.v1.md`](../resident_request.v1.md) · SHA-256 `9fc9b8491025404867ffb79cad0f5dbadf510bb2379d1718110aae89de1d2453`
* Source: Game layer (extension); not in the paper. A request derived from the resident's own identity, plan and memories, in the style of the paper's planning prompts (§4.3).
* Information scope: The resident's summary description, today's plan, the resident's own memories retrieved for their wishes, places from the resident's own spatial memory, and the six kinds of things the builder makes. Never game meters or other residents' memories.
* Output model: `ResidentRequestOut` · max output tokens 260 · effort low
* Calls in this run: 3 (ok 3; 0 repair attempts)

## Output schema

```json
{
  "additionalProperties": false,
  "description": "Something a resident would like the town builder to make (game layer).\n\n``theme`` and ``place`` are checked against the offered lists by the caller.",
  "properties": {
    "wish": {
      "type": "string"
    },
    "theme": {
      "type": "string"
    },
    "place": {
      "type": "string"
    },
    "reason": {
      "type": "string"
    },
    "request_line": {
      "type": "string"
    }
  },
  "required": [
    "wish",
    "theme",
    "place",
    "reason",
    "request_line"
  ],
  "type": "object"
}
```

## Smallest successful call

Ledger call 12 · scope `examples-game` · sim time 2023-02-13T10:00:00 · agent `klaus_mueller` · model `mock-llm-v1` · status `ok` · tokens 791 in / 80 out (estimated)

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
Klaus Mueller is kind, inquisitive, passionate. Notably: You and Maria Lopez are dormmates; This is very important -- you have a crush on Maria Lopez.
Klaus Mueller spends the day on the usual routine. Notably: This is very important -- you have a crush on Maria Lopez; You and Maria Lopez are close friends and classmates.
Klaus Mueller feels steady about recent progress. Notably: This is very important -- you have a crush on Maria Lopez; You and Maria Lopez are close friends and classmates.
It is February 13, 2023, 10:00 am.
Klaus Mueller's plan for today:
(no plan yet)
What Klaus Mueller remembers that may be relevant:
- This is very important -- you have a crush on Maria Lopez
- You and Maria Lopez have known each other for over 2 years now
- You and Isabella Rodriguez are aquintances since Isabella works at Hobbs Cafe that you frequent
- You and Maria Lopez are close friends and classmates
- You and Maria Lopez are dormmates

The town builder is a friendly visitor who makes and places things around town: furniture, decorations and garden pieces, of these kinds:
- cozy (Cozy): Warm homes, good food and slow mornings.
- bloom (Bloom): Gardens, parks and fresh air.
- lore (Lore): Books, study and big ideas.
- spark (Spark): Parties, music and lively evenings.
- craft (Craft): Making things by hand.
- kin (Kin): Neighbors, community and helping out.
Places Klaus Mueller knows:
- Dorm for Oak Hill College: Klaus Mueller's room
- Dorm for Oak Hill College: common room
- Dorm for Oak Hill College: garden
- Harvey Oak Supply Store: supply store
- Hobbs Cafe: cafe
- Johnson Park: park
- Oak Hill College: classroom
- Oak Hill College: hallway
- Oak Hill College: library
- The Rose and Crown Pub: pub
- The Willows Market and Pharmacy: store

Thinking about Klaus Mueller's goals and days, what is one small thing Klaus Mueller would like the town builder to make, and where? Choose one kind and one place from the lists above.

Respond with JSON: {"wish": "<a short phrase, e.g. a quiet corner to read>", "theme": "<one kind id from the list>", "place": "<one place exactly as listed>", "reason": "<one sentence>", "request_line": "<what Klaus Mueller says to the town builder, in the first person>"}
```

**Raw output**

```json
{"wish": "a bookshelf for my notes", "theme": "lore", "place": "Dorm for Oak Hill College: common room", "reason": "It would make my days at Dorm for Oak Hill College: common room nicer.", "request_line": "Could you make a bookshelf for my notes for me at Dorm for Oak Hill College: common room? It would mean a lot."}
```

**Validated output**

```json
{
  "wish": "a bookshelf for my notes",
  "theme": "lore",
  "place": "Dorm for Oak Hill College: common room",
  "reason": "It would make my days at Dorm for Oak Hill College: common room nicer.",
  "request_line": "Could you make a bookshelf for my notes for me at Dorm for Oak Hill College: common room? It would mean a lot."
}
```

No call for this task needed a repair in this run.
