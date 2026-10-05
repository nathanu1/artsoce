---
id: reflection_questions
version: 1
output: ReflectionQuestionsOut
source: "Paper §4.2 p. 10 ('Given only the information above, what are 3 most salient high-level questions we can answer about the subjects in the statements?'); released v2/generate_focal_pt_v1.txt"
scope: "The agent's most recent memory records (100 in paper mode)."
max_output_tokens: 300
effort: low
---
### system
{{system_role}}
### user
{{statements}}

Given only the information above, what are {{n}} most salient high-level questions we can answer about the subjects in the statements?

Respond with JSON: {"questions": ["...", "...", "..."]} with exactly {{n}} questions.
