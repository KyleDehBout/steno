# Audit pipeline learning — meeting notes pipeline

## What this does
Summarises everything the pipeline has learned, rejected, and promoted across all
/learn cycles for the current project. Project state (folders, skill files still holding
placeholders, renderer, checks, humanizer version) is /status's.

## Before starting
Load CLAUDE.md to get the project name and file locations.
Load the pipeline memory file listed in CLAUDE.md under "Key file locations".

## What to read and count

### From the pipeline memory file
- Count total /learn run entries (each entry is separated by a date header)
- Count approved changes, grouped by category:
  WORDING, FORMAT, STRUCTURE, ATTRIBUTION, STATUS, SCOPE, TERMINOLOGY, SUPERVISOR-PREF,
  HARD-RULE, AGENT, CHECK
- Read the "Open patterns" table: count rows. A row's sightings are the distinct dates
  in its "Dates seen" cell. Its status starts with one of `watching`, `promoted` or
  `blocked`. List every `promoted` row under PROMOTED, every `blocked` row with its
  reason under BLOCKED, and any `watching` row whose sightings already reach the
  "Supervisor activation threshold" in CLAUDE.md (default 3) as missed promotions. An
  AGENT or CHECK row is never promoted automatically: list one at the threshold as
  awaiting a yes in /apply-learning Step 9, not as missed. PROPOSED lines are not
  approved changes.
- Read "Open decisions": list each with the number of cycles it has gone unanswered
- Count rejected changes (lines marked REJECTED) — list each with its reason text
- Count deferred items (lines marked as deferred or NO ANSWER)

### From the supervisor style guide
List each "Recurring corrections" entry with the number of distinct dates in its
`seen:` list, marked live (at or above the threshold) or waiting. List the entries
under "Promoted rules". Count the non-comment, non-blank entries under Wording,
Structural and Scope preferences.

### From the scorecard
Read the pipeline scorecard listed in CLAUDE.md and report the last three rows of
"Pipeline runs" and "Learn cycles". It is the only record that survives cleanup, so a
trend there is the only evidence of whether the pipeline is improving.

## Output
Print exactly this structure:

---
[PROJECT NAME] — Pipeline audit

LEARN CYCLES
  Total runs: N

APPROVED CHANGES BY CATEGORY
  WORDING:          N
  FORMAT:           N
  STRUCTURE:        N
  ATTRIBUTION:      N
  STATUS:           N
  SCOPE:            N
  TERMINOLOGY:      N
  SUPERVISOR-PREF:  N
  HARD-RULE:        N
  AGENT:            N
  CHECK:            N
  ─────────────────
  Total approved:   N

OPEN PATTERNS  (N total)
  [pattern] — seen on N dates — [status]
  [or "none yet"]
  Missed promotions: [each `watching` row at or above the threshold, or "none"]

SUPERVISOR STYLE GUIDE
  Wording / Structural / Scope preferences: N / N / N

RECURRING CORRECTIONS  (threshold N)
  [rule] — seen on N dates — live | waiting
  [or "none"]

OPEN DECISIONS  (N total)
  [question] — unanswered for N cycle(s)
  [or "none"]

REJECTED CHANGES  (N total)
  [list each: "REJECTED [DATE]: [rule text] — [reason]"]
  [or "none" if empty]

DEFERRED  (N total)
  [or "none"]

PROMOTED
  [each `promoted` pattern row, then each "Promoted rules" entry in the guide]
  [or "none yet — a pattern promotes when seen on [threshold] distinct dates"]

BLOCKED
  [each `blocked` pattern row — reason]
  [or "none"]

SCORECARD (last three rows of each table)
  Pipeline runs: [rows, or "none yet"]
  Learn cycles:  [rows, or "none yet"]
---

Do not ask follow-up questions. Print the report and stop.
