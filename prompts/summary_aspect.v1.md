---
id: summary_aspect
version: 1
output: SummaryOut
source: "Paper Appendix A p. 21 ('How would one describe Eddy Lin's core characteristics given the following statements?')"
scope: "Statements retrieved from the agent's own memory stream under the active memory mask."
max_output_tokens: 300
effort: low
---
### system
{{system_role}}
### user
How would one describe {{aspect_question}} given the following statements?
{{statements}}

Respond with JSON: {"summary": "<one to three sentences>"}
