---
id: hourly_schedule
version: 1
output: HourlyScheduleOut
source: "Paper §4.3 p. 11 (decompose the day plan into hour-long chunks); released v2/generate_hourly_schedule_v2.txt asked one hour per call"
scope: "The agent's authored identity, dynamic summary and today's broad plan."
max_output_tokens: 1200
effort: medium
---
### system
{{system_role}}
### user
Name: {{agent_name}} (age: {{age}})
Innate traits: {{traits}}
{{agent_summary}}
Lifestyle: {{lifestyle}}

Today is {{day_label}}. {{first_name}}'s plan in broad strokes:
{{day_plan}}

Turn this into an hour-by-hour schedule that covers the whole day from 00:00 to 24:00 with no gaps or overlaps. Use hour-long chunks (longer chunks are fine for sleep or long activities). {{first_name}} is sleeping before waking up at {{wake_up_time}} and after going to bed.

Respond with JSON: {"blocks": [{"start": "HH:MM", "end": "HH:MM", "activity": "<what {{first_name}} is doing>"}, ...]}. The first block starts at 00:00, each block starts where the previous one ended, and the last block ends at 24:00.
