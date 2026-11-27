# Pipeline scorecard — [PROJECT NAME]

Numbers only. No meeting content, ever — not a name, a lot number, a dimension or a
quoted phrase. This file outlives every cleanup cycle, and that is only safe while it
holds nothing about any particular meeting.

It answers one question the drafts cannot, because they are deleted each cycle: **is the
pipeline getting better?**

## Pipeline runs

Written by `/process-notes` after Stage 6. One line per run, keyed on the meeting's HELD
ON date plus a run counter (`2026-07-16 #1`, then `#2` if that meeting is run again).

| Held on #run | Sections | Sub-items | Stage 2.5 errors | Stage 4.5 errors | Repair attempts | Review findings | Render attempts | Run time |
|---|---|---|---|---|---|---|---|---|

What to watch:

- **Stage 4.5 errors above zero** means a rule got past four stages. The draft was
  repaired, but the stage that broke the rule still needs fixing.
- **Repair attempts rising** means the checks are catching things the agents keep
  re-breaking — look at which stage the findings were routed to.
- **Review findings rising** means content is being dropped or invented, which no script
  can catch. That is the serious direction. A figure marked "(not independent)" came from
  a sequential run, where the session that wrote the draft also reviewed it, so expect it
  to find less than a fresh reviewer would.
- **Run time rising** with no rise in repairs means a stage got slower or bigger. The
  per-stage times and tokens are in that run's `run.txt` until `/learn` cleans it up.

## Learn cycles

Written by `/apply-learning`. One line per cycle. The last five columns score the
pipeline's Stage 5 draft against the issued notes (`score_draft.py`, run by `/learn`):
"n/a" means nothing to compare (no Stage 5 draft, a PDF, or no Action/Status cells), and
"approx" means some owners in the issued notes could sit beside more than one item, so
that agreement figure is an estimate.

| Date | Proposed | Approved | Rejected | Deferred | Q&A answered | Open decisions carried | Score | Coverage | Precision | Action | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|

What to watch:

- **Deferred and unanswered Q&A staying high** means the review form is asking for more
  than the supervisor has time to give. Cut the number of proposals before adding rules.
- **Open decisions carried growing** means the same question keeps going unanswered. Ask
  it directly instead of putting it in the form again.
- **Approved falling while proposed stays flat** means the pipeline is proposing rules
  from one-off edits. Tighten the triage, not the supervisor.
- **Coverage falling** means the pipeline is dropping items the supervisor kept, the
  failure this pipeline exists to prevent. **Precision falling** means it is adding
  items the supervisor cut. Read both before adding or trimming any scope rule.

## Test runs

Written by `/test-pipeline`. One line per meeting per run.

| Date | Meeting id | Score | Coverage | Action | Status | What changed |
|---|---|---|---|---|---|---|

A change to an agent or a rule ships only when these numbers hold or improve across every
meeting in the test set.
