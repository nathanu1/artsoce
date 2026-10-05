---
id: choose_location
version: 1
output: LocationChoiceOut
source: "Paper §5.1 p. 12 (Eddy Lin area prompt: current area, known areas, 'Prefer to stay in the current area if the activity can be done there'); released v1/action_location_sector_v1.txt, action_location_object_vMar11.txt, action_object_v2.txt"
scope: "The agent's dynamic summary and its private, possibly stale, spatial memory only."
max_output_tokens: 120
effort: low
---
### system
{{system_role}}
### user
{{agent_summary}}
{{agent_name}} is currently in {{current_place}}{{current_children}}.
{{agent_name}} knows of the following {{level_plural}}: {{options}}.
* Prefer to stay in the current area if the activity can be done there.
{{agent_name}} is planning to {{activity}}. Which {{level}} should {{agent_name}} go to?

Respond with JSON: {"choice": "<exactly one of the {{level_plural}} listed above>"}
