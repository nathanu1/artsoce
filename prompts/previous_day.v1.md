---
id: previous_day
version: 1
output: SummaryOut
source: "Paper §4.3 p. 11 (day plan uses 'a summary of their previous day'); released plan.py revise_identity (retrieval of '[name]'s plan for [day]' and 'Important recent events for [name]'s life')"
scope: "Memories retrieved from the agent's own stream about yesterday's plan and important recent events."
max_output_tokens: 400
effort: low
---
### system
{{system_role}}
### user
Statements:
{{statements}}

Given the statements above, summarize {{agent_name}}'s {{yesterday_label}} in two or three sentences, written in the third person. Include anything {{first_name}} should remember while planning {{today_label}}; if there is scheduling information, be as specific as the statements are (date, time and place).

Respond with JSON: {"summary": "..."}
