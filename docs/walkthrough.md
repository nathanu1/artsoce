# Walkthrough: from one conversation to a changed plan

This follows one invitation through the architecture: Isabella invites Klaus to her party, the
lines become memories, a retrieval the next morning surfaces them (or not), a reflection cites
them, and Tuesday's plan changes. Reproduce it offline:

```bash
python examples/walkthrough.py
```

The script uses the project's real modules on the real Smallville identities and seeds. Only the
model's *words* are scripted (the lines of dialogue, the reflection questions, the previous-day
summary and the day plan), so the output reads naturally and is identical on every machine.
Storage, importance accounting, retrieval scoring, evidence validation, plan validation and
decomposition are the code under test. Output below is from an actual run.

## 1. A conversation is a sequence of separate model calls

```
Isabella: Hi Klaus! I'm hosting a Valentine's Day party here at Hobbs Cafe tomorrow, February 14th, from 5 to 7 pm. Would you like to come?
Klaus: I'd love to come! Thanks for inviting me, Isabella.
Isabella: Wonderful, see you there!
(1 min; both agents' plans are revised from the end of the conversation)
```

Each line is one `dialogue_turn` call made *as the speaker*: the speaker's summary description,
a summary of what the speaker remembers about the partner (retrieved from the speaker's own
stream with the paper's two queries), memories retrieved for the partner's last line, and the
transcript so far (`cognition/dialogue.py`). Isabella's seed about the party is in Isabella's
prompt; Klaus never sees it except through what she says. The conversation lasts
`ceil((characters / 8) / 30)` minutes, the released code's rule, and both agents' remaining plans
are regenerated from its end.

## 2. What Klaus stores

```
klaus_mueller.m00009  statement     importance 7  Isabella Rodriguez said to Klaus Mueller: "Hi Klaus! I'm hosting a Valentine's Day party here at …
klaus_mueller.m00010  own_statement importance 5  Klaus Mueller said to Isabella Rodriguez: "I'd love to come! Thanks for inviting me, Isabella."
klaus_mueller.m00011  statement     importance 3  Isabella Rodriguez said to Klaus Mueller: "Wonderful, see you there!"
klaus_mueller.m00012  conversation  importance 6  Klaus Mueller had a conversation with Isabella Rodriguez. This is a conversation about Isabella …
reflection trigger (sum of importance of newly perceived memories): 21 / 150
```

Every line is stored in both participants' streams, typed by who said it, with the speaker's ID
and the conversation ID, plus a one-sentence observational summary. Bystanders only perceive
"Isabella Rodriguez is chatting with Klaus Mueller". Importance is rated 1–10 for each line in
one batched call per listener (an engineering batch; the scale and anchors are the paper's).
The ratings feed Klaus's reflection trigger: newly perceived memories add their importance.

## 3. Retrieval the next morning

At midnight Klaus plans Tuesday. Planning first summarizes his previous day from memories
retrieved for "Important recent events for Klaus Mueller's life." (the released code's query):

```
query: "Important recent events for Klaus Mueller's life."  (22 eligible memories)
#1 1.990 = recency 1.00 + importance 0.14 + relevance 0.85  Klaus Mueller is writing his research paper (part 10)
#2 1.957 = recency 0.00 + importance 1.00 + relevance 0.96  This is very important -- you have a crush on Maria Lopez
#3 1.906 = recency 0.92 + importance 0.14 + relevance 0.85  Klaus Mueller is writing his research paper (part 9)
#4 1.857 = recency 0.00 + importance 0.86 + relevance 1.00  Isabella Rodriguez said to Klaus Mueller: "Hi Klaus! I'm hosting a Val…
#5 1.822 = recency 0.83 + importance 0.14 + relevance 0.85  Klaus Mueller is writing his research paper (part 8)
klaus_mueller.m00022 outranks klaus_mueller.m00009 by 0.133, mostly on recency (+1.000) despite trailing on importance, relevance.
```

This is the paper's formula exactly: recency `0.995 ^ hours since last access`, importance, and
cosine relevance, each min-max normalized over the eligible memories and summed with weight 1.
Note what normalization does here. The invitation was last accessed at 12:10 and the latest
writing observation was made at 16:10, so at midnight their raw recency values are 0.942 and
0.962, a 2% difference.
After min-max normalization that difference becomes the full range from 0 to 1, as large as the
gap between a trivial and a life-changing memory on the importance scale. The invitation still
makes the top five because its importance and relevance are high, but it is fourth, behind
routine observations. `ga inspect-memory` and the viewer's Retrieval tab show this breakdown
for any recorded retrieval, and every trace is scored before access times change.

(Relevance here comes from the offline hash embeddings, which only measure word overlap. With a
real embedding model the relevance column would change; this is why mock runs are labeled.)

## 4. A reflection cites its evidence

```
question: What is Klaus Mueller looking forward to?
insight klaus_mueller.m00023 (depth 1): Klaus Mueller intends to go to Isabella Rodriguez's Valentine's Day party at Hobbs Cafe on February 14
  cites klaus_mueller.m00012 [observation]: Klaus Mueller had a conversation with Isabella Rodriguez. This is a conversation about Isa…
  cites klaus_mueller.m00009 [observation]: Isabella Rodriguez said to Klaus Mueller: "Hi Klaus! I'm hosting a Valentine's Day party h…
stored 6 insight(s) in total; rejected citations: 0; trigger reset to 0
```

When the summed importance exceeds 150 (strictly), Klaus asks three questions about his 100 most
recent memories, retrieves memories for each question, and asks for insights that cite the
numbered statements he was shown (`cognition/reflection.py`). The engine maps the numbers back
to memory IDs and rejects a citation that does not exist, belongs to another agent, was not
shown in that prompt, or would create a cycle. Accepted insights become reflection memories
with evidence links; their depth is one more than their deepest evidence, so reflections on
reflections form trees (Reflections tab in the viewer).

The check is structural. While writing this walkthrough, a first version of the script cited
statements 1 and 2 without looking at them; those happened to be unrelated observations about
the paper, and the validator accepted them, because they had been shown. Whether a citation
*supports* a claim is not something these checks can decide; the evaluation measures it instead
(claims are compared with the memories that could support them).

## 5. Tuesday's plan changes

```
previous day: On Monday Klaus worked on his gentrification paper at the library, and at lunch Isabella invited him to her Valentine's Day party at Hobbs Cafe on February 14 from 5 to 7 pm, which he accepted.
00:00–07:00  sleeping
07:00–08:00  wake up and complete the morning routine
08:00–12:00  work on his research paper at the library
12:00–13:00  have lunch at Hobbs Cafe
13:00–17:00  keep writing his research paper at the library
17:00–19:00  go to Isabella's Valentine's Day party at Hobbs Cafe
19:00–23:00  have dinner
23:00–23:30  go to bed
23:30–00:00  sleeping
at 17:05 the current task is: go to Isabella's Valentine's Day party at Hobbs Cafe (getting started) (17:00, 15 min)
```

The day plan is drafted from Klaus's identity, his dynamic summary and the previous-day summary
built from his own memories (`cognition/planning.py`). It is validated (5–8 items, valid times
in order), expanded into hour blocks that must cover 00:00–24:00 without gaps or overlaps, and
stored in his memory stream as plan memories. Only when he reaches a block is its current
hour-long window decomposed into 5–15 minute tasks that must add up exactly. At 17:05 the
engine asks for the current task, chooses where it happens by walking Klaus's own spatial
memory (area → room → object), finds a path, and he walks there one tile per step.

None of this guarantees he arrives: in a full run something else can happen first. That is why
the end-to-end evaluation counts **physical presence** at Hobbs Cafe during the party window and
keeps exposure, invitation, acceptance, scheduling and arrival as separate variables.
