---
id: action_grounding
version: 1
output: ActionGroundingOut
source: "Paper §5.1 p. 13 (the language model says what happens to the object's state, e.g. coffee machine 'off' → 'brewing coffee'); released v2/generate_event_triple_v1.txt and v3_ChatGPT/generate_obj_event_v1.txt"
scope: "The agent's own action and the target object's name."
max_output_tokens: 160
effort: low
---
### system
{{system_role}}
### user
{{agent_name}} is {{activity}} at {{place}}, using the {{object_name}}.

1. Express what {{agent_name}} is doing as a subject, predicate and object (e.g., "Isabella Rodriguez", "is serving", "coffee").
2. In a few words, what state is the {{object_name}} in while this happens (e.g., "brewing coffee", "being used", "occupied")? Use "idle" if the action does not affect it.

Respond with JSON: {"subject": "{{agent_name}}", "predicate": "...", "object": "...", "object_state": "..."}
