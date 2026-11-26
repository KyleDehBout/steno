# Process meeting notes

## Before starting
Load CLAUDE.md — project roster, org names, and all file locations.
All file paths used in this pipeline are read from CLAUDE.md under "Key file locations".

Each meeting gets its own run folder, `[DOCX working dir]/runs/<stem>/`, where `<stem>`
is the transcript's filename without its extension (`transcript-2026-10-08.txt` →
`runs/transcript-2026-10-08/`). Every `runs/<stem>/` below means this meeting's folder.

Before Stage 1, delete this meeting's run folder and create it empty, then write
`run.txt` in it with one line: `transcript: <transcript filename>`. Touch no other
meeting's run folder: a meeting processed before the last one's `/learn` must not
destroy the stage files that `/learn` still needs.

Log every stage, checks included, to `run.txt`. Take the time with
`date +%Y-%m-%dT%H:%M:%S` just before the stage starts and again when it returns, then
append one line:

```
stage <N> <agent or check>: start <time> end <time> tokens <n|n/a>
```

`tokens` is the total the agent's result reported (its usage line), or `n/a` for a check
or when no figure was reported. Never estimate it. A re-run stage adds another line, so a
repair loop shows as extra lines. These lines carry no meeting content; they are what the
scorecard's Run time column is computed from.

Deleting this meeting's folder first is not tidiness. A re-run that stopped at Stage 3
would leave the earlier run's `stage-4.md` behind, and `/learn` would read it as this
run's — a wrong attribution. A fresh folder also starts a fresh scorecard row (see
"Scorecard" below).

Every stage's returned draft is written there as `stage-1.md`, `stage-2.md`, … before the
next stage starts. Two reasons, both load-bearing:
- `check_draft.py` needs a file to read.
- `/learn` compares consecutive stage files to name the stage that introduced a
  supervisor correction, which is how a correction becomes an agent fix instead of
  another sentence in a skill file.

The run folder is scratch, not history. `cleanup-cycle.sh --stem <stem>` clears it, with
that meeting's transcript and output draft, at the end of that meeting's `/learn` cycle,
so no meeting's content survives into the next.

## Pre-flight check — run before Stage 1

Check the following in order.

### What counts as a transcript
Before any check below, build the candidate list from the transcripts folder. A file is a
candidate only if ALL of the following hold:
- the filename does not start with `.` (excludes `.DS_Store`, `.gitkeep`)
- the filename does not start with `~$` (excludes Word lock files)
- it is a file, not a directory
- it is non-empty

"The most recent transcript" means the candidate with the newest modification time. If two
share a timestamp, take the one whose name sorts last.

### Blocking (stop entirely):
- If the candidate list is empty:
  Print "No transcript found in [transcripts path] — add a transcript file and run /process-notes again."
  Stop. Do not proceed.
  (Say this even when the folder contains files, if none of them are candidates — name the
  files that were skipped and why.)

- If the DOCX blank template listed in CLAUDE.md does not exist on disk:
  Print "DOCX blank template not found at [path] — Stage 6 cannot render. Run
  setup_docx_renderer.py before /process-notes."
  Stop. Do not proceed. Stage 6 would fail after five stages of work have already run.

- If `check_draft.py` is not present at the "Draft checks scripts" path in CLAUDE.md:
  Print "Draft checks script not found at [path] — run /sync-pipeline to install it."
  Stop. Do not proceed. Running without it silently removes both mechanical gates.

- If the "Draft format contract" file listed in CLAUDE.md does not exist on disk:
  Print "Draft format contract not found at [path] — run /sync-pipeline to install it."
  Stop. Do not proceed. Stage 1 is told to write to a contract it cannot read, and every
  later check is against a format nothing defined.

### Warnings (collect all, then ask once):
- CLAUDE.md roster contains a `[Name]` placeholder → "Roster has placeholder entries — attribution validation will be unreliable."
- The formatter skill file (listed in CLAUDE.md) contains `[TO BE FILLED IN]` → "Formatter skill file has unfilled sections — output quality may be low."
- The style rules skill file (listed in CLAUDE.md) contains `[TO BE FILLED IN]` → "Style rules skill file has unfilled sections — output quality may be low."
- The humanizer skill file (listed in CLAUDE.md) is missing, or its `references/` folder is empty → "Humanizer skill not found — Stage 2 will run the editorial pass only."
- More than one candidate transcript is present → "N transcripts present — only the most recent ([filename]) will be processed."
- The output folder already contains a draft whose name or content matches the transcript about to be processed → "[filename] appears to have been processed already — running again will produce a duplicate draft."
- `[DOCX working dir]/runs/<stem>/` already holds files for the transcript about to be processed → "[stem] has been run before — its run folder will be replaced." Other meetings' run folders are not a warning: they are meetings waiting for `/learn`.

If any warnings exist, print all of them, then ask:
"Proceed anyway? (y/n)"
If n: stop. If y: proceed to Stage 1.
If no warnings: proceed to Stage 1 silently.

---

## Pipeline — 6 stages in strict order, no skipping

**If any stage fails, stop the pipeline there.** A stage has failed if its agent returns an
error, returns nothing, or returns a draft that is empty or obviously truncated. When that
happens: print "PIPELINE FAILED at Stage [N] ([agent name]): [what went wrong]", print the
notes collected from the stages that did complete, and stop. Never pass a failed or empty
draft to the next stage, never substitute your own draft for a failed agent's output, and
never print the summary report as though the run succeeded. A `RENDER FAILED` result from
Stage 6 is the one exception: Stage 6 below routes it back for repair before stopping.

**What a re-run means.** When a check or the reviewer sends findings back to Stage N,
re-run every stage from N through 4, in order, each taking the previous stage's new
draft, then check again. Each re-run stage overwrites its `stage-k.md`, so the files
always describe one consistent pass. Before overwriting, rename the old file to
`stage-k.attemptN.md` (N = 1 for the first earlier attempt, 2 for the next), so `/learn`
can still see what the earlier pass did.

Agents return pipeline metadata after the draft, below a line reading exactly
`---PIPELINE NOTES---`: FORMATTER NOTE, EDITORIAL NOTE, HUMANIZER NOTE, DISCIPLINE NOTE,
SUPERVISOR NOTE.
Collect everything below the sentinel for the summary report, then cut from the sentinel
to the end before passing the draft to the next stage. `check_draft.py` stops reading at
the sentinel, and errors on a bullet below the `MEETINGS:` line or under a NOTE line, so
a note list left in the draft fails the gate rather than reaching the document. No NOTE line ever
reaches the docx-renderer. The REVIEW NOTE comes from Stage 5, which returns no draft.
The Stage 1 `LEDGER:` block is not a NOTE line — keep it, save it to
`runs/<stem>/ledger.md`, and pass it to Stage 5.

### Stage 1 — formatter
Find the most recent file in the transcripts folder listed in CLAUDE.md.

Files to pass to the formatter agent:
- CLAUDE.md
- The formatter skill file listed in CLAUDE.md
- The style rules skill file listed in CLAUDE.md
- The style rules skill references/ subfolder (structure.md and typography.md, at the same path as the style rules skill)
- The hard rules skill file listed in CLAUDE.md
- The hard rules skill references/ subfolder (terminology.md, at the same path as the hard rules skill)
- The draft format contract listed in CLAUDE.md
- The supervisor style guide listed in CLAUDE.md — the formatter applies its Scope
  preferences here, because Stage 4 may not delete an item

Receive a complete first draft plus a `LEDGER:` block.
Write the draft to `runs/<stem>/stage-1.md` and the ledger to `runs/<stem>/ledger.md`.

### Stage 2 — editorial-qa
Files to pass to the editorial-qa agent:
- Stage 1 draft
- The Stage 1 ledger — it may not delete an item that appears there
- CLAUDE.md
- The style rules skill file listed in CLAUDE.md
- The style rules typography reference (at the same path as the style rules skill)
- The hard rules skill file listed in CLAUDE.md
- The hard rules terminology reference (at the same path as the hard rules skill)
- The humanizer skill file listed in CLAUDE.md
- The humanizer references/ subfolder (at the same path as the humanizer skill)

The agent runs two passes: editorial sharpening, then AI-writing cleanup scoped by the
humanizer skill file. Later stages re-validate its output, so it runs here and nowhere else.

Receive sharpened draft plus EDITORIAL NOTE and HUMANIZER NOTE.
Write it to `runs/<stem>/stage-2.md`.

### Stage 2.5 — first mechanical check
Run, from the "Draft checks scripts" path in CLAUDE.md:

```bash
python3 "[draft checks scripts]/check_draft.py" "[working dir]/runs/<stem>/stage-2.md" \
  --claude-md "[path to CLAUDE.md]" --stage 2 \
  --scorecard "[pipeline scorecard from CLAUDE.md]" \
  --json "[working dir]/runs/<stem>/checks-stage-2.json"
```

Exit 0: continue to Stage 3, mentioning the warning count only.
Exit 1: hand the error list back to the stage that owns it — a format, ledger or content
error to Stage 1, a removal to Stage 2 — and re-run that stage once. If the check still
fails, continue to Stage 3 anyway and carry the findings forward; Stage 3 and Stage 4 fix
attribution and wording, and the Stage 4.5 check is the gate that actually blocks.

This early check exists so a broken draft is caught while it is still cheap to fix, not
after two more stages have edited it.

### Stage 3 — discipline-checker
Files to pass to the discipline-checker agent:
- Stage 2 draft
- The Stage 2.5 check findings, if any
- `runs/<stem>/ledger.md` — its verbatim quotes are the agent's only evidence of who owns
  each action; it never sees the transcript
- CLAUDE.md
- The hard rules skill file listed in CLAUDE.md
- The hard rules terminology reference (at the same path as the hard rules skill)
- The supervisor style guide listed in CLAUDE.md — a project's joint-attribution rule may
  live under its "Promoted rules"
- The draft format contract listed in CLAUDE.md — rule 7 defines the Action and Status cells

Receive corrected draft plus DISCIPLINE NOTE. Write it to `runs/<stem>/stage-3.md`.

### Stage 4 — supervisor-alignment
Files to pass to the supervisor-alignment agent:
- Stage 3 draft
- CLAUDE.md
- The supervisor style guide file listed in CLAUDE.md
- The hard rules skill file listed in CLAUDE.md

Agent applies manually seeded preferences always, and recurring corrections once the
threshold in CLAUDE.md is reached.
Receive final draft. Write it to `runs/<stem>/stage-4.md`.

### Stage 4.5 — second mechanical check (blocking)
Run the same command against `runs/<stem>/stage-4.md`, writing `checks-stage-4.json`,
and add the ledger so a dropped item is caught here rather than left to judgement:

```bash
python3 "[draft checks scripts]/check_draft.py" "[working dir]/runs/<stem>/stage-4.md" \
  --claude-md "[path to CLAUDE.md]" --ledger "[working dir]/runs/<stem>/ledger.md" \
  --stage 4 --scorecard "[pipeline scorecard from CLAUDE.md]" \
  --json "[working dir]/runs/<stem>/checks-stage-4.json"
```

Stage 4 is the last stage that edits text, so this is the last chance to catch a
mechanical break before rendering.

Exit 0: continue to Stage 5.
Exit 1: return the findings to the stage that owns each one, re-run from that stage, and
check again. **Maximum 2 repair attempts.**

If errors remain after the second attempt, print "STAGE 4.5: [N] error(s) after 2 repair
attempts", list them, and ask once:

"Render anyway? The listed errors will be in the document. (y/n)"

- **n** — print the path to `runs/<stem>/stage-4.md` and stop.
- **y** — continue to Stage 5, and record the outstanding errors in the summary report
  and in the scorecard line for this run.

The override exists because a check that cannot be overridden gets switched off the first
time it is wrong about a document the supervisor needs today. Every use of it is a
reported number, so a check that is wrong often shows up in the scorecard as a pattern
rather than disappearing.

### Stage 5 — draft-reviewer
Files to pass to the draft-reviewer agent:
- The transcript (Stage 5 is the only stage after Stage 1 that sees it)
- `runs/<stem>/ledger.md`
- `runs/<stem>/stage-4.md`
- CLAUDE.md, the hard rules skill and the style rules skill

The reviewer never edits. It returns `REVIEW: PASS`, or `REVIEW: FAIL` with findings
routed to a stage.

On FAIL: re-run the named stage with the findings, re-run the Stage 4.5 check, and review
again. **Maximum 2 review attempts.** If the second review still fails, do not stop the
pipeline — render the draft and print the outstanding findings in the summary report. The
findings are judgement calls, and a judgement call belongs to the supervisor, not to a
loop that spins until it agrees with itself.

Write the reviewed draft to `runs/<stem>/stage-5.md`.

### Stage 6 — docx-renderer
Files to pass to the docx-renderer agent:
- Stage 5 final draft (markdown)
- CLAUDE.md

Agent runs the renderer skill's `render.py`, which clones the blank template, builds and
splices the body XML, repacks, validates, and saves the output file. It returns
`RENDER COMPLETE: <path>`, or `RENDER FAILED at Step N (<step>): [<kind>] <reason>`.

Log every render in `run.txt`, after the usual `stage 6` line, with one more line:
`render <n>: complete`, or `render <n>: failed step <N> <kind> -> <where it went>`
(`-> stage 1`, `-> stage 4`, `-> stopped`). No reason text: it can quote the meeting.

On `RENDER COMPLETE`: append `output: <output filename>` (the bare filename) to
`runs/<stem>/run.txt`. The draft is named by date, not by stem, and this line is how
`/learn` and the cleanup script find this meeting's draft without touching another
meeting's.

#### Render failure: repair loop
A render failure is routed by its `[<kind>]` tag, never by guessing from the prose, and
never fixed by hand. There is no hand-written XML fallback, no running the render steps
one by one, and no editing of the renderer scripts: an earlier fallback of that kind hid a
real renderer crash for weeks.

| Kind | What failed | Who fixes it |
|------|-------------|--------------|
| `draft` | The draft: an attendee row without 3 fields, a sub-item or bullet with the wrong cells, a line outside the format, a bullet below `MEETINGS:`, a control character or non-UTF-8 bytes, a typed number in an item or heading, two sections with the same title. The reason names `draft line N` of `stage-5.md`. | The owning stage (below), then repair |
| `input` | The draft path given to the renderer does not exist. | You: re-run Stage 6 on `runs/<stem>/stage-5.md`, writing it from `stage-4.md` first if it is missing (Stage 5 never edits). Counts as a render attempt. |
| `config` | The project's blank template, the `DOCX blank template` line in CLAUDE.md, or `constants.json` (a missing key, a non-numeric value, a `num_id` not in the template, column widths that do not add up). | The user. Stop (below). |
| `install` | `render.py` or a script it runs, or `check_draft.py`, is missing. | The user: `/sync-pipeline`. Stop. |
| `system` | A file could not be written (disk full, permissions). | The user. Stop. |
| `renderer` | A bug in the renderer scripts. | The user, with the message. Stop. |

If the docx-renderer agent reports that `render.py` itself is missing, that is `install`.

**`draft` — find the owning stage.** Take the text of `draft line N` in `stage-5.md`, and
look for that exact line in `stage-1.md`:
- present in `stage-1.md`: the fault was there from the start, and structure is Stage 1's.
  Re-run from **Stage 1**.
- absent from `stage-1.md`: a later stage introduced it. Find the first of `stage-2.md`,
  `stage-3.md`, `stage-4.md` that has it, name that stage in the finding, and re-run from
  **Stage 4**, the last stage that edits text.
- no line named: Stage 1.

This is the Stage 4.5 rule (return each finding to the stage that owns it), with the stage
files as the evidence. Hand the re-run stage the full `RENDER FAILED` line and the
offending line's text, quoted: line numbers shift between stage files, the text does not.

**One repair attempt** = re-run from the owning stage through Stage 4, under the re-run
rules above (each overwritten `stage-k.md`, `stage-5.md` included, is first renamed to the
next unused `stage-k.attemptN.md`), then Stage 4.5, Stage 5 and Stage 6 once each:
- Stage 4.5 does not start its own repair loop inside a render repair. Exit 1, with errors
  the run had not already accepted through the Stage 4.5 override, ends this attempt
  without rendering; the next attempt routes those errors by the Stage 4.5 rule, together
  with the render failure if it is still open.
- Stage 5 runs once. A FAIL is not looped: its findings go to the summary report as
  outstanding, as after its second review. The reviewed draft is written to `stage-5.md`
  as usual.
- Stage 6 renders the new `stage-5.md`.

**Maximum 2 repair attempts**, so at most 3 renders in a run. If the render still fails
after the second attempt, print:

```
PIPELINE STOPPED at Stage 6 after 2 repair attempts: <the last RENDER FAILED line>
Reviewed draft: <full path to runs/<stem>/stage-5.md>
```

then the notes collected so far, and stop. The work is in `stage-5.md`; nothing is lost.

**`config`, `install`, `system`, `renderer` — stop at once.** No pipeline stage can fix
these, so no repair attempt is made. Print:

```
PIPELINE STOPPED at Stage 6 (<kind>): <the RENDER FAILED line>
Fix: <the fix below>
Reviewed draft: <full path to runs/<stem>/stage-5.md>
Then render it with:
  python3 "<DOCX renderer scripts>/render.py" "<that stage-5.md>" --project "<Meeting Notes folder>" --out "<output folder>/<PROJECT>-Meeting-Notes-YYYY-MM-DD.docx"
```

with the paths filled in from CLAUDE.md, and the fix by kind:
- `config`: what the reason names. A missing template, missing or wrong constants, an
  undeclared `num_id` or column widths that do not add up are re-derived from a branded
  .docx with `python3 "<DOCX renderer scripts>/setup_docx_renderer.py" "<branded .docx>"
  "<PROJECT>" "<Meeting Notes folder>" --force` (it backs up what it replaces). A missing
  `DOCX blank template` line goes under "Key file locations" in CLAUDE.md.
- `install`: run `/sync-pipeline`.
- `system`: free disk space or fix the folder's permissions.
- `renderer`: a renderer bug; keep the message and report it. Do not work around it.

## Scorecard — complete the row after Stage 6

`check_draft.py` already wrote this run's row when it ran at Stage 2.5 and Stage 4.5: the
meeting's HELD ON date plus a run counter (`2026-10-08 #1`; a second run of the same
meeting gets `#2`), the section and sub-item counts, and both error counts. The remaining columns are left as
`—` because only you know them. Fill them in:

```
| [HELD ON as YYYY-MM-DD] #[run] | [sections] | [sub-items] | [stage-2 errors] | [stage-4 errors] | [repair attempts] | [review findings] | [render attempts] | [run time] |
```

Run time is the first `stage` line's start to the last one's end in `runs/<stem>/run.txt`,
in whole minutes (`14 min`). If the scorecard's table has no Run time column (a project
set up before it), leave the row at eight cells.

Render attempts is the number of times `render.py` ran in this run: `1` for a clean
render, up to `3` after two repairs. If the run stopped at Stage 6, add "(stopped)" after
the figure.

If the Stage 4.5 override was used, add "(override used)" after the render attempts
figure. That number is how a check that is wrong too often becomes visible instead of
being quietly worked around.

Numbers only, no meeting content — this file survives cleanup and is the pipeline's only
long-term record.

## Summary report — print after Stage 6 completes or stops
- Which transcript was processed and its date
- EDITORIAL NOTE and HUMANIZER NOTE from Stage 2
- Stage 2.5: errors and warnings, and whether a repair ran
- DISCIPLINE NOTE from Stage 3
- SUPERVISOR NOTE from Stage 4 (if any recurring correction is still below the threshold)
- Stage 4.5: errors and warnings after the final attempt
- REVIEW NOTE from Stage 5, including any finding left outstanding
- Render attempts, and for each repair the failure kind and the stage it went back to
- Output file path from Stage 6 — or, if the run stopped at Stage 6, the `PIPELINE
  STOPPED` message and the path to `runs/<stem>/stage-5.md` so the work is not lost
