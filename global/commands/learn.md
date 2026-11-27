---
description: "Compare the pipeline's draft with the final version the supervisor issued and propose rule changes in a browser review form. Use when the user has put an issued set of notes in the intake folder, or asks the pipeline to learn from corrections."
---

# Learn from final issued notes

> **Project instruction file.** `AGENTS.md` here means the project's instruction file: `AGENTS.md`, or `CLAUDE.md` in a project set up before Steno moved to AGENTS.md. Read whichever the project has. When both sit in one folder, AGENTS.md holds the project and CLAUDE.md only points to it.

## Purpose
Compare what the pipeline produced against the final supervisor-approved version.
Extract every difference. Propose targeted improvements to skill files and agents.
Move the final file to the issued archive with correct numbering.

## Before starting — verify intake
Load AGENTS.md to get all file paths.
Check the intake folder listed in AGENTS.md for the issued file. Ignore any name that
starts with `.` (`.DS_Store`) or `~$` (a Word lock file), folders and empty files.
If nothing is left: stop and tell the user "No file found in [intake path] — drop your
final issued .docx or .pdf there and run /learn again." Say this even when the folder
holds a `.DS_Store`.
If more than one file is left: list them and ask which one is the issued final.
If exactly one: proceed.

## Select this meeting's run
Each processed meeting has its own run folder, `[DOCX working dir]/runs/<stem>/`, where
`<stem>` is its transcript's filename without the extension. More than one can be present
when a meeting was processed before the previous one's `/learn`, so pick the one that
belongs to the issued file — never "the newest".

- If the user ran `/learn <stem>`, use that run folder. If it does not exist, say so and
  stop.
- Otherwise read the HELD ON date from the issued file (its "Held on" line), and the
  HELD ON and MEETING NO lines from each run folder's latest stage file (`stage-5.md`,
  else the highest `stage-k.md`).
  - Exactly one run has the same HELD ON date: that is this meeting's run.
  - More than one matches, or the issued file's date cannot be read: list each run
    folder with its HELD ON, MEETING NO and output draft, and ask which one.
  - None matches: say so plainly — "No run folder matches the issued notes held on
    [date]. Run folders present: [stem, HELD ON for each, or 'none']." — and stop. Tell
    the user to run `/learn <stem>` if one of them is the right meeting. Do not fall back
    to another meeting's run: its stage files would mis-attribute every correction.

Carry the chosen stem and that run's MEETING NO into the form (see below):
`/apply-learning` numbers the archive file from the MEETING NO and cleans up only this
stem's files.

## Files to load
- The intake folder listed in AGENTS.md — the final supervisor-approved version (source of truth)
- The pipeline draft named on the `output:` line of `runs/<stem>/run.txt`, in the output
  folder listed in AGENTS.md. If the line is missing, use the draft whose date matches
  HELD ON, and ask if more than one does
- The per-stage drafts `stage-1.md` through `stage-5.md` in `[DOCX working dir]/runs/<stem>/`
  (resolve the working folder from "DOCX working dir" in AGENTS.md), and any
  `stage-k.attemptN.md` an earlier repair pass left — the draft as each stage left it.
  Comparing consecutive files names the stage that introduced a correction, which is
  what turns it into an AGENT fix instead of another rule
- `[DOCX working dir]/runs/<stem>/ledger.md` — an item in the ledger but missing from the
  issued file was dropped by a later stage, not by the supervisor
- The pipeline memory file listed in AGENTS.md — running learning log, open patterns, and
  open decisions that must be asked again first
- The pipeline scorecard listed in AGENTS.md — receives one line per cycle
- The style rules skill file listed in AGENTS.md — may receive updates
- The hard rules skill file listed in AGENTS.md — may receive updates
- The supervisor style guide file listed in AGENTS.md — may receive updates
- The pipeline repo's `global/agents/` — agent instructions may receive updates, only
  through `/apply-learning` Step 9 (a shown diff, an explicit yes, and `/test-pipeline`
  on every installed project). Never the installed copies in `~/.claude/agents/`: an
  edit there is overwritten by the next `/sync-pipeline`

If `runs/<stem>/` holds no stage files, say so and carry on. The cycle still works; it just cannot
attribute a correction to a stage, so no AGENT proposals come out of it.

## Score the draft against the issued notes
Before the review, measure how close the pipeline got. Run, from the project root:

```bash
python3 "[Draft checks scripts from AGENTS.md]/score_draft.py" \
  "[DOCX working dir]/runs/<stem>/stage-5.md" "[the issued .docx in intake]" \
  --json "[DOCX working dir]/runs/<stem>/score.json"
```

`/apply-learning` copies the cells from `score.json` into this cycle's scorecard row
before cleanup deletes the run folder. Show the user the `SCORE` line, and the `APPROX`
line if the script printed one: the issued notes pad the Action and Status columns with
blank lines, so the script pairs owners to items by estimated position, and it says when
an owner could sit beside more than one item. Never round "approx" away.

Skip this step, and say why, when there is no `stage-5.md` in the run folder or the
issued file is not a .docx; the scorecard row then shows "n/a". If the script exits
non-zero, report its error and carry on with the review: the score measures the cycle,
it does not gate it.

## Hand off to learning-reviewer agent
Pass it both documents, all context files above, the stem and the run's MEETING NO.
The agent triages the differences before proposing anything, asks unanswered questions
from earlier cycles first, caps the form at 6 proposals, then generates the browser
review form and waits.

If your tool cannot start the installed `learning-reviewer` agent, run it yourself in
sequential mode, as /process-notes "Run mode" describes: load the same files, then follow
the pipeline repo's `global/agents/learning-reviewer.md` (the body after its front
matter).

## After user pastes the review block
/apply-learning handles all writes automatically when the user pastes the ==LEARNING_REVIEW== block.
