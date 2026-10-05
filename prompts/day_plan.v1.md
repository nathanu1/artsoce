---
id: day_plan
version: 1
output: DayPlanOut
source: "Paper §4.3 p. 11 (Eddy Lin prompt: name, age, traits, summary, previous day, 'Here is Eddy's plan today in broad strokes'); released v2/daily_planning_v6.txt (lifestyle and daily requirement fields)"
scope: "The agent's authored identity, its dynamic summary (own memories only), its own previous-day summary."
max_output_tokens: 700
effort: medium
---
### system
{{system_role}}
### user
Name: {{agent_name}} (age: {{age}})
Innate traits: {{traits}}
{{agent_summary}}
Lifestyle: {{lifestyle}}
Daily routine: {{daily_requirement}}
{{previous_day}}
Today is {{day_label}}. Here is {{first_name}}'s plan today in broad strokes, as {{min_items}} to {{max_items}} items, each with the time of day (e.g., "wake up and complete the morning routine at 8:00 am").

Respond with JSON: {"wake_up_time": "HH:MM", "items": [{"time": "HH:MM", "activity": "<what>"}, ...]} in chronological order, 24-hour times.
