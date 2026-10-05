---
id: importance
version: 1
output: ImportanceOut
source: "Paper §4.1 p. 9 (prompt quoted there; core sentence kept); identity block and per-kind anchors from released v3_ChatGPT/poignancy_event_v1.txt, poignancy_chat_v1.txt, poignancy_thought_v1.txt"
scope: "The rating agent's own summary description and the single memory being rated."
max_output_tokens: 64
effort: low
---
### system
{{system_role}}
### user
Here is a brief description of {{agent_name}}.
{{agent_summary}}

On the scale of 1 to 10, where 1 is purely mundane (e.g., {{mundane_examples}}) and 10 is extremely poignant (e.g., {{poignant_examples}}), rate the likely poignancy of the following {{kind_label}} for {{agent_name}}.

{{kind_title}}: {{memory}}

Respond with JSON: {"rating": <integer from 1 to 10>}
