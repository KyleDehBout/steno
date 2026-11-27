# Pipeline memory log — [PROJECT NAME]

## How this file is used
- Written to by /apply-learning at the end of every /learn cycle
- Read by /audit (counts and reports) and by /learn (prior context)
- /process-notes does NOT read this file — rules must live in the skill files to take effect
- One counting model: each "Open patterns" row lists the dates the pattern was seen, and
  its count is the number of distinct dates. /learn proposes a pattern on its second
  date; /apply-learning promotes it automatically once its dates reach the "Supervisor
  activation threshold" in AGENTS.md, unless it is blocked. The supervisor guide's
  "Recurring corrections" entries count their dates the same way.
- AGENT and CHECK patterns are never promoted automatically. They change the shared
  pipeline repo, which every project runs, so /apply-learning logs each as PROPOSED and
  writes it only after an explicit yes in the chat, the repo tests, a commit, and
  /test-pipeline passing on every project in the repo's projects.txt (its Step 9).
- Status is `watching`, `promoted [date]` or `blocked — [reason]`. A pattern the user
  rejected, or one that would contradict a hard rule, is blocked and never promoted.

## What gets logged here
- Approved changes (written to skill files — logged for pattern tracking)
- Proposed AGENT and CHECK changes, and what became of each in Step 9
- Rejected proposed changes (logged with reason)
- Judgment calls that don't yet have enough repetitions to become rules

## Entry format
One dated header per cycle, `## YYYY-MM-DD — [transcript name]`, then one line per
change. /audit counts run entries by the date header and approved changes by the
CATEGORY tag, so the tags must not be dropped.

```
## 2026-06-18 — [transcript name]
APPROVED WORDING: [rule text] — applied to skills/style-rules/SKILL.md
DERIVED FORMAT: [rule text] — applied to skills/style-rules/references/typography.md
PROPOSED CHECK: [rule text] — [repo file], awaiting yes (Step 9)
REJECTED 2026-06-18: [rule text] — not applied
DEFERRED 2026-06-18: [rule text] — no answer given
```

CATEGORY is one of WORDING, FORMAT, STRUCTURE, ATTRIBUTION, STATUS, SCOPE,
TERMINOLOGY, SUPERVISOR-PREF, HARD-RULE, AGENT, CHECK.

## Nothing here names a meeting

Every line in this file is a pattern, not an example. No participant names, lot numbers,
dimensions, or quoted sentences from a transcript. Write "rationale behind a scope
decision was dropped", never the rationale itself. This file is read by /learn on every
later cycle, so anything specific written here follows the project forward into meetings
it has nothing to do with.

## Open patterns

Maintained by /apply-learning from the SECTION 0 lines of the review paste. A difference
seen once is logged here and nowhere else. It becomes a proposal on its second date and
a rule at the threshold set in AGENTS.md. This table is why a correction can accumulate
instead of being rejected as a one-off.

| Pattern | Dates seen | Category | Status |
|---|---|---|---|

## Open decisions

Questions the supervisor has not answered. They go to the top of the next review form,
with their cycle count. Three cycles unanswered means stop asking in the form and ask
directly.

| Question | First asked | Cycles open |
|---|---|---|

---
<!-- Run entries appear below — newest at bottom -->
