---
id: interaction_context
version: 1
output: SummaryOut
source: "Paper §4.3.1 p. 11 (context summary from the queries 'What is [observer]'s relationship with the [observed entity]?' and '[Observed entity] is [action status]', summarized together); released v3_ChatGPT/summarize_chat_relationship_v2.txt"
scope: "Memories retrieved from the observer's own stream for the two queries."
max_output_tokens: 300
effort: low
---
### system
{{system_role}}
### user
[Statements from {{observer}}'s memory]
{{statements}}

Based only on the statements above, summarize what {{observer}} knows about their relationship with {{observed}} and about {{observed}} {{observed_status}}. Write two or three sentences in the third person. If the statements say nothing about {{observed}}, say that {{observer}} does not know {{observed}}.

Respond with JSON: {"summary": "..."}
