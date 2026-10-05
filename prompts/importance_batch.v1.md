---
id: importance_batch
version: 1
output: ImportanceBatchOut
source: "Same rating scale and per-kind anchors as importance@v1 (paper p. 9); batching the statements of one conversation, or the items of one plan, is our engineering choice (spec D-5)"
scope: "The rating agent's own summary description and the memories of one batch (one conversation the agent took part in, or the agent's own plan)."
max_output_tokens: 400
effort: low
---
### system
{{system_role}}
### user
Here is a brief description of {{agent_name}}.
{{agent_summary}}

On the scale of 1 to 10, where 1 is purely mundane (e.g., {{mundane_examples}}) and 10 is extremely poignant (e.g., {{poignant_examples}}), rate the likely poignancy of each of the following {{kind_label_plural}} for {{agent_name}}. Rate each one independently.

{{numbered_memories}}

Respond with JSON: {"ratings": [{"id": "<the number shown>", "rating": <integer from 1 to 10>}, ...]} with one entry per item.
