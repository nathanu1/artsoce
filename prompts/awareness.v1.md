---
id: awareness
version: 1
output: AwarenessOut
source: "Paper §7.1.1 p. 15 (answers labeled 'yes' if they indicate knowledge, 'no' otherwise; done by hand in the paper). Automated labeling is our extension and is reported as such."
scope: "One interview question and answer, plus the list of details to check. No access to the agent's memory."
max_output_tokens: 300
effort: low
---
### system
{{system_role}}
### user
Question: {{question}}
Answer: {{answer}}

Does the answer say the speaker knows about {{topic}}? Answer false if the speaker says they don't know, are unsure, or only speculate.
Which of these details does the answer state (list only those it states): {{details}}

Respond with JSON: {"claims_knowledge": true | false, "details": ["<detail names>"], "quote": "<the phrase that shows it, or empty>"}
