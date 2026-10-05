---
id: replan
version: 1
output: DecomposeOut
source: "Paper §4.3.1 p. 11 ('We then regenerate the agent's existing plan starting from the time when the reaction takes place'); released v2/new_decomp_schedule_v1.txt"
scope: "The agent's own schedule, the inserted action and the time; nothing about other agents beyond the inserted action's text."
max_output_tokens: 900
effort: low
---
### system
{{system_role}}
### user
{{agent_summary}}

Here was {{first_name}}'s originally planned schedule from {{window_start}} to {{window_end}}:
{{original_schedule}}

At {{now}}, {{first_name}} started something unplanned: "{{inserted_activity}}" for {{inserted_minutes}} minutes, until {{inserted_end}}.

Write {{first_name}}'s revised schedule from {{inserted_end}} to {{window_end}} ({{remaining_minutes}} minutes). Keep what still makes sense from the original plan. Each action lasts {{min_minutes}} to {{max_minutes}} minutes and the durations add up to exactly {{remaining_minutes}} minutes.

Respond with JSON: {"tasks": [{"start": "HH:MM", "duration_minutes": <int>, "activity": "<what>"}, ...]}
