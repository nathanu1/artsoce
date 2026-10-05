---
id: reflection_insights
version: 1
output: ReflectionInsightsOut
source: "Paper §4.2 p. 10 ('What 5 high-level insights can you infer from the above statements? (example format: insight (because of 1, 5, 3))'); released v2/insight_and_evidence_v1.txt"
scope: "Memories retrieved from the agent's own stream for one reflection question, numbered so citations can be checked."
max_output_tokens: 700
effort: medium
---
### system
{{system_role}}
### user
Statements about {{agent_name}}
{{numbered_statements}}

What {{n}} high-level insights can you infer from the above statements? (example format: insight (because of 1, 5, 3))

Respond with JSON: {"insights": [{"insight": "<one sentence>", "evidence": ["<statement number>", ...]}, ...]} with up to {{n}} insights. Cite only statement numbers shown above.
