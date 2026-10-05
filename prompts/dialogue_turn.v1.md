---
id: dialogue_turn
version: 1
output: DialogueTurnOut
source: "Paper §4.3.2 pp. 11–12 (utterance conditioned on the speaker's summarized memory about the other agent, the intended reaction and the dialogue history; continues until one agent ends it); released v3_ChatGPT/iterative_convo_v1.txt"
scope: "The speaker's dynamic summary, the speaker's own retrieved memories, the place, and the transcript so far. Never the partner's memories."
max_output_tokens: 300
effort: medium
---
### system
{{system_role}}
### user
{{agent_summary}}
It is {{now}}.
{{agent_name}}'s status: {{status}}
Observation: {{observation}}
Location: {{location}}
Summary of relevant context from {{agent_name}}'s memory:
{{relationship_summary}}
{{turn_memories}}
{{intent}}
Here is the dialogue history:
{{transcript}}
How would {{agent_name}} respond to {{partner_name}}? Say one natural turn. End the conversation when it has run its course.

Respond with JSON: {"utterance": "<what {{agent_name}} says>", "end_conversation": true | false}
