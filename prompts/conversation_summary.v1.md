---
id: conversation_summary
version: 1
output: SummaryOut
source: "Released v3_ChatGPT/summarize_conversation_v1.txt ('Summarize the conversation above in one sentence: This is a conversation about')"
scope: "The transcript of one conversation, which both participants heard. Observational: no inferences about intentions or traits."
max_output_tokens: 160
effort: low
---
### system
{{system_role}}
### user
Conversation:
{{transcript}}

Summarize the conversation above in one sentence, describing only what was said. Start with "This is a conversation about".

Respond with JSON: {"summary": "This is a conversation about ..."}
