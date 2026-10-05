---
id: decompose
version: 1
output: DecomposeOut
source: "Paper §4.3 p. 11 ('recursively decompose this again into 5–15 minute chunks'); Appendix A p. 21 (just-in-time); released v2/task_decomp_v3.txt"
scope: "The agent's identity, dynamic summary and the hour-level plan around the activity."
max_output_tokens: 900
effort: low
---
### system
{{system_role}}
### user
{{agent_summary}}

Today is {{day_label}}. {{first_name}}'s schedule around this time:
{{schedule_context}}

Decompose "{{activity}}" from {{start}} to {{end}} ({{duration}} minutes) into smaller actions of {{min_minutes}} to {{max_minutes}} minutes each, in order. Durations must add up to exactly {{duration}} minutes.

Respond with JSON: {"tasks": [{"start": "HH:MM", "duration_minutes": <int>, "activity": "<what {{first_name}} is doing>"}, ...]}
