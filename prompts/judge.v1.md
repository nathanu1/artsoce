---
id: judge
version: 1
output: JudgeOut
source: "Experimental extension (spec §8): optional exploratory LLM judge. Never reported as human believability."
scope: "One interview question, the agent's public description and one anonymized answer."
max_output_tokens: 300
effort: low
---
### system
{{system_role}}
### user
Character: {{public_description}}
Question: {{question}}
Answer: {{answer}}

On a scale of 1 to 7, how believable is this answer as something this character would say? This is an exploratory automated rating, not a human judgment.

Respond with JSON: {"score": <integer 1-7>, "rationale": "<one sentence>"}
