---
id: seed_thought
version: 1
output: StatementOut
source: "Released v2/whisper_inner_thought_v1.txt via converse.py load_history_via_whisper (released-code seed rendering; scenario.seed_rendering=inner_thought_llm)"
scope: "One authored history statement for this agent."
max_output_tokens: 160
effort: low
---
### system
{{system_role}}
### user
Translate the following thought into a statement about {{agent_name}}.

Thought: "{{thought}}"

Respond with JSON: {"statement": "..."}
