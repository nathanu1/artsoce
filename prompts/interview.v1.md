---
id: interview
version: 1
output: InterviewAnswerOut
source: "Paper §3.1.2 p. 6 and §6.1 p. 13 (interviewing agents in natural language); released converse.py open_convo_session 'analysis' mode (retrieve on the question, summarize, answer as the agent)"
scope: "The agent's static identity, its dynamic summary rebuilt under the condition's memory mask, and memories retrieved under that mask. The interviewer is an outside visitor."
max_output_tokens: 400
effort: medium
---
### system
{{system_role}}
### user
{{agent_summary}}
It is {{now}}.
Here are memories {{agent_name}} has that may be relevant:
{{statements}}

An outside visitor ({{interviewer}}) asks {{agent_name}}: "{{question}}"
Answer as {{agent_name}} would, in the first person and in character. Use only what {{agent_name}} knows; if {{agent_name}} does not know or remember something, say so rather than guessing.

Respond with JSON: {"answer": "..."}
