---
name: draft-checks
description: >
  Mechanical checks that run on the meeting-notes draft before it is rendered.
  Covers the draft format contract, Status values, Action column organisations,
  placeholders, relative dates, speaker attribution, numbering, and the next-meeting
  date. Load references/draft-format.md when writing or repairing a draft.
compatibility: Designed for use with the meeting-notes-pipeline
metadata:
  version: "1.0"
allowed-tools: Read, Bash
---

## What this is

One script, `scripts/check_draft.py`, and one contract, `references/draft-format.md`.

The pipeline's earlier stages are agents, and an agent can miss a rule that is written
down. The supervisor then corrects the same class of thing weeks later. These checks
close that gap for every rule a machine can decide with no opinion.

## When it runs

`/process-notes` runs it twice:

- after Stage 2 (editorial-qa), so a format or attribution break is caught while three
  stages can still fix it cheaply
- after Stage 4 (supervisor-alignment), which is the last stage that edits text and is
  otherwise unchecked by anything

The two runs differ. Stage 2.5 checks the draft alone:

```bash
python3 "[draft checks scripts]/check_draft.py" "[working dir]/runs/[stem]/stage-2.md" \
  --claude-md "[project CLAUDE.md]" --stage 2 \
  --scorecard "[pipeline scorecard]" \
  --json "[working dir]/runs/[stem]/checks-stage-2.json"
```

Stage 4.5 adds the Stage 1 ledger, so an item a later stage dropped is caught here rather
than left to judgement:

```bash
python3 "[draft checks scripts]/check_draft.py" "[working dir]/runs/[stem]/stage-4.md" \
  --claude-md "[project CLAUDE.md]" --ledger "[working dir]/runs/[stem]/ledger.md" \
  --stage 4 --scorecard "[pipeline scorecard]" \
  --json "[working dir]/runs/[stem]/checks-stage-4.json"
```

`--scorecard` writes this run's row itself: the meeting's HELD ON date plus a run counter
(`2026-07-16 #2`), the section and sub-item counts, and the error count for whichever
stage `--stage` names. The counter is kept in `scorecard-row.txt` beside the draft, so
every check in one run folder updates one row and a second run of the meeting adds a
second row. The columns it cannot
know — repair attempts, review findings, render attempts, run time — are left as `—` for
the orchestrator to complete after Stage 6. The row has one cell per header column, so a
scorecard made before the Run time column keeps its eight.

Exit 0 means no errors. Exit 1 means errors, which the orchestrator hands back to the
stage that owns the rule. Exit 2 is a usage mistake.

## What it will not do

- It never edits the draft. It reports and exits.
- It carries no project data. Roster, organisation names, meeting day and interval all
  come from CLAUDE.md, so a rule the project has not written down is a rule it does not
  enforce.
- It does not judge writing quality, scope or fidelity to the transcript. That is the
  draft-reviewer agent's job, and no script can do it.

## Adding a check

When the supervisor corrects the same class of thing twice, add a check here rather than
another sentence to a skill file:

1. Add the check to `scripts/check_draft.py` with a short code (`STATUS_VALUE`,
   `RELATIVE_DATE`, …) and a message that names the fix, not just the fault.
2. Decide error or warning. Error means a machine can be certain. If a human could
   reasonably disagree, it is a warning.
3. Add a case to `tests/test_check_draft.py` in the pipeline repo — one that fails
   before your change and passes after.
4. If the rule needs a project value (a name, a day, a threshold), read it from
   CLAUDE.md. Never hardcode it.
