# Project status — Steno

## What this does
Prints a snapshot of the current project state: what is in each folder, whether the
skill files, renderer and checks are ready, and what to do next. What the pipeline has
learned (the style guide, patterns, recurring corrections, rejected rules) is /audit's.

## Before starting
Load CLAUDE.md to get the project name and all file locations.

## Check each area

### Folders
Using the paths listed in CLAUDE.md, check each folder and note the file count and most recent filename:
- Transcripts folder
- Output folder
- Intake folder
- Issued archive folder

### Skill file completeness
Check each of the following files for any remaining `[TO BE FILLED IN]` text,
using paths derived from CLAUDE.md:
- The formatter skill file
- The style rules skill file
- The style rules structure reference
- The style rules typography reference
- The hard rules terminology reference

Also read `metadata.upstream` from the humanizer skill file listed in CLAUDE.md: the
vendored humanizer version. /learn never writes to that skill, so it is state, not
learning.

### DOCX renderer readiness
Check the "DOCX blank template" path from CLAUDE.md:
- Present on disk → ✓, and note the date from
  `skills/docx-renderer/references/.rendered.json` if that file exists
- Missing → ⚠, because Stage 6 will fail after the other five stages have run

### Pipeline checks readiness
- `check_draft.py` at the "Draft checks scripts" path → ✓ present, or ⚠ missing, in
  which case /process-notes will refuse to start
- The "Draft format contract" file listed in CLAUDE.md → ✓ present, or ⚠ missing.
  /process-notes blocks on this one too, so a project missing it is not ready no matter
  what else is in place
- The pipeline scorecard listed in CLAUDE.md → count the rows under "Pipeline runs" and
  under "Learn cycles", or ⬜ if the file does not exist yet
- The "Pipeline tests" folder → count the meeting folders holding both a transcript and
  an issued .docx, or ⬜ if there are none
- `[DOCX working dir]/runs/` → list each run folder (one per meeting awaiting `/learn`).
  A run folder whose `run.txt` has no `output:` line is a run that was interrupted

### Suggested next action
Determine one clear next step:
- If `check_draft.py` or the draft format contract is missing: "Run /sync-pipeline — /process-notes will not start without the draft checks and the format contract"
- If the DOCX blank template is missing: "Run setup_docx_renderer.py to build your document template — /process-notes cannot render without it"
- Else if any skill file has `[TO BE FILLED IN]`: "Complete your style profile before running /process-notes — see files listed above"
- Else if transcripts folder is empty: "Drop a transcript in [transcripts path] and run /process-notes"
- Else if output folder is empty: "Run /process-notes to generate your first draft"
- Else if intake folder is empty: "Review the draft in [output path], get supervisor approval, drop the final version in [intake path] and run /learn"
- Else if intake folder has files: "Run /learn to compare the pipeline draft against your supervisor's version"

## Output
Print exactly this structure:

---
[PROJECT NAME] — Pipeline status

FOLDERS
  [transcripts path]   [N files | empty] [most recent: filename]
  [output path]        [N files | empty] [most recent: filename]
  [intake path]        [N files | empty]
  [archive path]       [N archived | none yet] [most recent: filename]

SKILL FILES
  [✓ Complete | ⚠ Placeholders remain] — [filename]
  (one line per file checked)
  Humanizer: [metadata.upstream value, or "not installed"]

DOCX RENDERER
  Blank template:  [✓ present | ⚠ MISSING — Stage 6 will fail]
  References set:  [rendered YYYY-MM-DD from <source .docx> | not yet run]

PIPELINE CHECKS
  check_draft.py:  [✓ present | ⚠ MISSING — run /sync-pipeline]
  Format contract: [✓ present | ⚠ MISSING — run /sync-pipeline]
  Scorecard:       [N runs, N learn cycles | ⬜ not started]
  Test set:        [N meeting(s) | ⬜ none]
  Working folder:  [clean | ⚠ N file(s) from an unfinished run]

NEXT
  [single recommended action]

For what the pipeline has learned, run /audit.
---

Do not ask follow-up questions. Print the report and stop.
