---
id: conversation_inferences
version: 1
output: ConversationInferencesOut
source: "Released v2/planning_thought_on_convo_v1.txt and v2/memo_on_convo_v1.txt (reflect.py:186-245). Not in the paper. Released-code compatibility only; disabled when reflection is off."
scope: "The transcript of one conversation the agent took part in."
max_output_tokens: 300
effort: low
---
### system
{{system_role}}
### user
[Conversation]
{{transcript}}

1. Write down if there is anything from the conversation that {{agent_name}} needs to remember for their planning, from {{agent_name}}'s perspective, in a full sentence (or null).
2. Write down if there is anything from the conversation that {{agent_name}} might have found interesting, from {{agent_name}}'s perspective, in a full sentence (or null).

Respond with JSON: {"planning_note": "<sentence or null>", "memo": "<sentence or null>"}
