# Supervisor style guide — [PROJECT NAME]

## Purpose
This file records every correction your supervisor makes to issued meeting notes.
It is read by the supervisor-alignment agent on every /process-notes run and updated
automatically by /apply-learning after every /learn cycle.

## What is always active
The sections below — Wording preferences, Structural preferences, Scope preferences,
and Promoted rules — are applied on every /process-notes run the moment you write
anything in them. Seed them manually with known preferences and they take effect immediately.

## What activates at the threshold
Each "Recurring corrections" entry carries the dates it was seen on. An entry is applied
once it has been seen on as many distinct dates as "Supervisor activation threshold" in
AGENTS.md (default: 3); until then it waits, however many other entries there are. This
protects against one-off corrections becoming permanent rules prematurely. Approved
WORDING changes and supervisor preferences go here too, never straight into the
always-on style rules.

## Wording preferences
<!-- Add known wording preferences here. Example:
- Say "contractor to provide" not "contractor will provide"
- Say "outstanding" not "pending" for incomplete items
A line written `- Say "X" not "Y"` or `- Never use "Y"` is also checked by check_draft.py,
which warns wherever "Y" appears in item text.
-->

## Structural preferences
<!-- Add known structural preferences here. Example:
- Decisions section always appears before Action Items
- Action items include a deadline only if stated in the transcript
-->

## Scope preferences
<!-- Add known scope preferences here. Example:
- Remove scheduling items unless a date was formally confirmed
- Do not include items where no decision, action or informational value was recorded
-->

<!--
The three "preferences" sections above and "Promoted rules" below are applied on every
run regardless of the threshold, so they are for preferences YOU seed deliberately.
/apply-learning never writes to them — a rule it derived has been seen once, and writing
it here would make a single correction permanent immediately. Derived rules go to
"Recurring corrections", which is threshold-gated.
-->

## Recurring corrections
<!--
Written to automatically by /apply-learning after each /learn cycle. A rule seen again
gets the new date added to its entry rather than a second entry.

Format for each entry:
- [rule text] — [CATEGORY] — seen: YYYY-MM-DD, YYYY-MM-DD
-->

## Promoted rules (always applied)
<!--
Rules you move here by hand to make them permanent whatever their date count. An entry in
Recurring corrections does not need to move here to be applied: it is live once its
own dates reach the threshold. /apply-learning does not write here.
-->
