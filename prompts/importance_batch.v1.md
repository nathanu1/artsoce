---
id: importance_batch
version: 1
output: ImportanceBatchOut
source: "Same rating scale as importance@v1 (paper p. 9); batching statements from one conversation is our engineering choice (spec D-5)"
scope: "The rating agent's own summary description and the statements from one conversation the agent took part in."
max_output_tokens: 400
effort: low
---
### system
{{system_role}}
### user
Here is a brief description of {{agent_name}}.
{{agent_summary}}

On the scale of 1 to 10, where 1 is purely mundane (e.g., routine morning greetings) and 10 is extremely poignant (e.g., a conversation about breaking up, a fight), rate the likely poignancy of each of the following memories for {{agent_name}}. Rate each one independently.

{{numbered_memories}}

Respond with JSON: {"ratings": [{"id": "<the number shown>", "rating": <integer from 1 to 10>}, ...]} with one entry per memory.
