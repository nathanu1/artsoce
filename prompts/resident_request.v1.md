---
id: resident_request
version: 1
output: ResidentRequestOut
source: "Game layer (extension); not in the paper. A request derived from the resident's own identity, plan and memories, in the style of the paper's planning prompts (§4.3)."
scope: "The resident's summary description, today's plan, the resident's own memories retrieved for their wishes, places from the resident's own spatial memory, and the six kinds of things the builder makes. Never game meters or other residents' memories."
max_output_tokens: 260
effort: low
---
### system
{{system_role}}
### user
{{agent_summary}}
It is {{now}}.
{{agent_name}}'s plan for today:
{{plan}}
What {{agent_name}} remembers that may be relevant:
{{memories}}

{{builder_cap}} is a friendly visitor who makes and places things around town: furniture, decorations and garden pieces, of these kinds:
{{themes}}
Places {{agent_name}} knows:
{{places}}

Thinking about {{agent_name}}'s goals and days, what is one small thing {{agent_name}} would like {{builder}} to make, and where? Choose one kind and one place from the lists above.

Respond with JSON: {"wish": "<a short phrase, e.g. a quiet corner to read>", "theme": "<one kind id from the list>", "place": "<one place exactly as listed>", "reason": "<one sentence>", "request_line": "<what {{agent_name}} says to {{builder}}, in the first person>"}
