---
id: action_grounding
version: 1
output: ActionGroundingOut
source: "Paper §5.1 p. 13 (the language model says what happens to the object's state, e.g. coffee machine 'off' → 'brewing coffee'); released v2/generate_event_triple_v1.txt and v3_ChatGPT/generate_obj_event_v1.txt"
scope: "The agent's own action, the target object's name and the condition the agent last saw it in (its own spatial memory, never the world's true state)."
max_output_tokens: 200
effort: low
---
### system
{{system_role}}
### user
{{agent_name}} is {{activity}} at {{place}}, using the {{object_name}}.

1. Express what {{agent_name}} is doing as a subject, predicate and object (e.g., "Isabella Rodriguez", "is serving", "coffee").
2. In a few words, what state is the {{object_name}} in while this happens (e.g., "brewing coffee", "being used", "occupied")? Use "idle" if the action does not affect it.
3. The {{object_name}} is currently {{object_condition}}. If this action leaves it in a different lasting condition once {{agent_name}} is done (e.g., a burning stove that is now "turned off", an empty refrigerator that is now "stocked"), give that condition; otherwise null.

Respond with JSON: {"subject": "{{agent_name}}", "predicate": "...", "object": "...", "object_state": "...", "lasting_state": "<condition or null>"}
