---
description: "Set up Steno for a new project: open the setup form, then scaffold the project folder and install the agents and skills. Use when the user wants to start using the meeting notes pipeline on a new project."
---

# Setup Steno

> **Project instruction file.** `AGENTS.md` here means the project's instruction file: `AGENTS.md`, or `CLAUDE.md` in a project set up before Steno moved to AGENTS.md. Read whichever the project has. When both sit in one folder, AGENTS.md holds the project and CLAUDE.md only points to it.

## What this does
Installs the global pipeline components for your agent tool and scaffolds
a new project folder ready to use. If you provide past meeting notes, the setup extracts
your style, roster, and organisation names automatically.

Project details are collected in a browser form, not in the terminal. The user opens it
with `python3 scripts/generate_setup_form.py` (in Claude Code it also opens by itself on a
fresh clone), fills it in, copies the generated block, and pastes it back into the agent.
See Step 1.

---

## Step 0 — Upload documents

Before asking any questions, prompt the user with exactly this:

---
Before we set up your project, do you have any past meeting notes you'd like to upload?

Upload one or two finished .docx files you're happy with — I'll extract your style, roster,
organisation names, and document branding automatically, and use them to pre-fill your project
files. Say "skip" to fill everything in manually.
---

Wait for the user to respond.

### Handling the upload:

Past meeting notes almost always carry the organisation's branded header, footer, and logo.
When a .docx is uploaded, it serves two purposes simultaneously:

1. **Template source** — the body content is stripped and the file becomes the blank template
   that every rendered output is cloned from, preserving headers, footers, logos, styles, and
   fonts automatically.
2. **Style reference** — the content is read to extract roster, tone, terminology, and structure.

Save the first uploaded .docx file path as TEMPLATE_SOURCE.

If the user uploads no .docx file (uploads only text/paste, or says "skip"):
- Set TEMPLATE_SOURCE to empty.
- Ask once: "Do you have a branded .docx file — any meeting notes or letterhead — I can use
  to set up the document template? This gives every output your organisation's header, footer,
  and logo automatically."
- If still none: set TEMPLATE_SOURCE to empty and warn at the end of setup:
  "⚠ No .docx uploaded — the DOCX renderer will not be fully set up. Run this when you have
  a file: python3 Meeting Notes/skills/docx-renderer/scripts/setup_docx_renderer.py <source.docx>
  <ProjectName> <Meeting Notes path>"

### Handling past notes:

If the user uploads or pastes past notes, read every document fully before proceeding. Extract
the following silently — do not print the analysis, just hold it for use in later steps:

**From the Attendees section:**
- Team roster: every person's full name, organisation, and title
- Organisation names: every org listed (these become the Action column source of truth)

**From the document structure:**
- Header layout: what appears, in what order, what formatting
- Section numbering format (e.g. 1. / 1.1 / 1.1.1 or A. / A.1 etc.)
- Whether subsections use bold, italic, or plain labels
- Column layout: how many columns, what they are, how they are headed

**From the header and footer:**
- Document title: the title line exactly as issued (e.g. "DEPOT – Project Meeting"), keeping
  its dash character
- Meeting day: the weekday of each "Held on" date. HIGH only when every document agrees
- Days between meetings: the gap between consecutive "Held on" dates. Needs two or more
  documents; one document gives no interval
- Usual start time: the start time in the header, if the documents show one
- Prepared-by line: the final line exactly as issued (e.g. "Prepared by: Acme Limited")

**From the content:**
- Tone and register: formal/informal, first/third person, outcome-focused vs. discussion-focused
- Action column convention: org name only, individual name, initials, or mixed
- Status values used and what they appear to mean
- Whether speaker attribution is used or avoided
- Preferred constructions (e.g. "[Org] to provide..." vs "[Org] will provide...")
- Date format used in the header
- Text weight conventions (what is bold, italic, plain)
- Any technical terms, abbreviations, or project-specific vocabulary

**Confidence flag each item** internally as HIGH (clearly consistent across the document),
MEDIUM (present but ambiguous), or LOW (inferred/uncertain). HIGH and MEDIUM items
are used to auto-populate files. LOW items are flagged for the user to confirm.

Save all extracted data as EXTRACTED_DATA for use in Steps 1–4.

### If the user says "skip" for past notes:
Set EXTRACTED_DATA to empty. Proceed to Step 1 and open the setup form with no prefill.

---

## Step 1 — Collect project information via the setup form

**Hardcoded rule: project information is always collected in the browser form, never by
asking the questions one at a time in the terminal.**

The form may already be open, in which case skip straight to Step 1c and wait for the
paste:
- The user started setup the documented way, which works in every tool: they ran
  `python3 scripts/generate_setup_form.py` in the Steno folder, and are now pasting the
  `==PROJECT_SETUP==` block it produced.
- In Claude Code on a fresh clone, the SessionStart hook (`scripts/first_run_check.py`,
  wired in `.claude/settings.json`) ran that same command before this one.

If the form is not already open — the user ran `/setup-pipeline` by hand, or setup has run
on this machine before — generate and open it now.

### Step 1a — Build the prefill object

If EXTRACTED_DATA is empty, the prefill is `{}` — skip to Step 1b.

Otherwise build a JSON object from the HIGH and MEDIUM confidence items only. LOW
confidence items are left blank so the user fills them in deliberately. Use this exact
shape; every key is optional:

```json
{
  "project": "DEPOT",
  "path": "/Users/you/Projects/DEPOT",
  "folderName": "Site Minutes",
  "templateSource": "/Users/you/Documents/past-minutes.docx",
  "roster": [{"name": "Jane Smith", "org": "Acme Corp", "title": "Structural Engineer"}],
  "orgs": "Acme Corp, BuildCo, City Council",
  "actionColumn": "ORG_ONLY",
  "dateFormat": "Monday 22 June 2026",
  "numbering": "DECIMAL",
  "tone": "FORMAL_THIRD",
  "attribution": "NEVER",
  "statusValues": "In Progress, Pending, No Action, Completed",
  "terms": "precast panels, ROW, BQ",
  "threshold": "3",
  "meetingDay": "Thursday",
  "meetingInterval": "7",
  "meetingTime": "3:00PM",
  "docTitle": "DEPOT – Project Meeting",
  "preparedBy": "Prepared by: Acme Limited",
  "sourceNote": "Prefilled from past-minutes.docx — check each field before submitting."
}
```

Dropdown values must match the option values in `assets/setup-form.html` exactly, or the
dropdown silently keeps its default:

- `actionColumn`: ORG_ONLY | INDIVIDUAL | INITIALS | MIXED
- `numbering`: DECIMAL | ALPHA | MIXED | NONE
- `tone`: FORMAL_THIRD | FORMAL_FIRST | NEUTRAL | INFORMAL
- `attribution`: NEVER | DECISIONS | ALWAYS
- `threshold`: 3 | 5 | 10
- `meetingDay`: a full weekday name, capitalised (Monday … Sunday)
- `dateFormat`: one of the six literal strings listed in the form

Write the JSON to a temporary file rather than passing it inline — rosters and
organisation lists contain quotes and commas that break shell escaping.

### Step 1b — Generate and open the form

```bash
python3 "[repo-root]/scripts/generate_setup_form.py" \
  --out "[repo-root]" \
  --prefill "[path to prefill.json]"
```

Omit `--prefill` entirely when EXTRACTED_DATA is empty. The script writes
`setup-session.html` and opens it in the default browser. The file is self-contained — no
network, no CDN, works offline — and is gitignored.

If the script prints `not opened`, print the file path and ask the user to open it manually.

### Step 1c — Wait for the pasted block

Print exactly this and nothing else:

---
Setup form open in your browser.

Fill it in, click "Generate setup block", then either "Copy to clipboard" or
"Copy & close", and paste the result back here.
---

Then stop. Do not ask setup questions in the terminal. Do not proceed until the user
pastes. If the user answers in prose instead of pasting, accept the prose — do not send
them back to the form.

### Step 1d — Parse the pasted block

The paste is delimited by `==PROJECT_SETUP==` and `==END_SETUP==`. Read these values:

| Key in block | Variable | Notes |
|---|---|---|
| PROJECT_NAME | PROJECT_NAME | required |
| PROJECT_PATH | PROJECT_PATH | required — project root, not the Meeting Notes subfolder |
| MEETING_NOTES_FOLDER | MEETING_NOTES_FOLDER | |
| FOLDER_MODE | FOLDER_MODE | CREATE or EXISTING |
| EXISTING_DOCS | EXISTING_DOCS | ARCHIVE or LEAVE |
| TEMPLATE_SOURCE | TEMPLATE_SOURCE | `none` means empty |
| `--- ROSTER ---` rows | ROSTER | one `\| Name \| Organisation \| Title \|` row per person |
| ORG_NAMES | ORG_NAMES | |
| ACTION_COLUMN | ACTION_COLUMN | |
| DATE_FORMAT | DATE_FORMAT | |
| NUMBERING | NUMBERING | |
| TONE | TONE | |
| SPEAKER_ATTRIBUTION | SPEAKER_ATTRIBUTION | |
| STATUS_VALUES | STATUS_VALUES | |
| TERMINOLOGY | TERMINOLOGY | `none` means empty |
| MEETING_DAY | MEETING_DAY | `not provided` means empty |
| MEETING_INTERVAL | MEETING_INTERVAL | `not provided` means empty |
| MEETING_TIME | MEETING_TIME | `not provided` means empty |
| DOCUMENT_TITLE | DOCUMENT_TITLE | `not provided` means empty |
| PREPARED_BY | PREPARED_BY | `not provided` means empty |
| SUPERVISOR_THRESHOLD | SUPERVISOR_THRESHOLD | |
| CREATE_LAUNCHER | CREATE_LAUNCHER | YES or NO |
| NOTES | NOTES | `none` means empty |

Then run these checks before continuing:

- PROJECT_PATH exists. If not, ask whether to create it.
- If FOLDER_MODE is EXISTING, PROJECT_PATH/MEETING_NOTES_FOLDER exists. If not, say so and
  create it.
- If TEMPLATE_SOURCE is set, the file exists and ends in `.docx`.
- **Existing project guard.** Look for `AGENTS.md` or `CLAUDE.md` in PROJECT_PATH and in
  PROJECT_PATH/MEETING_NOTES_FOLDER (some projects keep it inside the Meeting Notes
  folder), and for `pipeline-memory-*.md` in PROJECT_PATH/MEETING_NOTES_FOLDER. If any
  exists, this project is already set up and holds learned rules: its roster, org names,
  memory and scorecard history.
  - Unless the command was run as `/setup-pipeline --reinit`, stop here and print:
    "This project is already set up ([the file found]). Setup will not overwrite it. To
    update agents, commands and skill scripts, run /sync-pipeline. To start the project
    files again from blank templates, run /setup-pipeline --reinit (it backs up first)."
    Write nothing.
  - With `--reinit`, back up before anything else is written: copy `AGENTS.md`, `CLAUDE.md` and `GEMINI.md` from both
    places it may be, every top-level file in PROJECT_PATH/MEETING_NOTES_FOLDER, the
    `skills/` folder and any `Claude — * Launcher.command` into
    `PROJECT_PATH/MEETING_NOTES_FOLDER/.setup-backup-<YYYYMMDD-HHMMSS>/`, keeping their
    relative paths (a root file goes in as `project-root/<name>`, e.g. `project-root/AGENTS.md`). Print the
    backup path. Then carry on; with `--reinit` the copy steps below overwrite.

Ask about a failed check only. Everything that parsed cleanly is settled — do not read it
back to the user field by field for confirmation.

A value the user typed into the form always beats a value extracted from the uploaded
document. The form is the last word.

---

## Step 2 — Install global files

The repo root is the Steno clone: the folder holding `scripts/sync_pipeline.py`, normally
the folder this session was opened in.

Install for the tool you are running in — `claude` for Claude Code, `codex` for Codex
CLI, `gemini` for Gemini CLI:

```bash
python3 "[repo-root]/scripts/sync_pipeline.py" --global --target [tool] --only-missing
```

It adds the agents, commands (Claude Code only) and skills that are absent, and leaves
every file that already exists alone, listing each as `skipped`. If anything was
skipped, warn: "⚠ Skipped [file] — already exists. Review and merge manually if needed."

**Setup only ever adds files that are absent.** That is deliberate — it must never
overwrite an agent someone has edited. It also means setup cannot deliver an update: if
any file was skipped above, say so and tell the user to run `/sync-pipeline`, which
overwrites and backs up what it replaces.

---

## Step 3 — Scaffold project structure

### Handle existing Meeting Notes folder content
If MEETING_NOTES_FOLDER already existed and contains .pdf or .docx files directly in
its root (not in subfolders), ask:
"I found [N] document(s) in [MEETING_NOTES_FOLDER]/. These look like issued meeting notes.
Shall I move them to [MEETING_NOTES_FOLDER]/Archive/ to keep the folder clean? (y/n)"
If y: create Archive/ and move those files there.
If n: leave them in place.

### Create subfolders inside Meeting Notes
Create the following inside PROJECT_PATH/MEETING_NOTES_FOLDER/:
- Archive/
- transcripts/
- output/
- intake/
- working/
- skills/style-rules/references/
- skills/hard-rules/references/
- skills/humanizer/references/
- skills/humanizer/vendor/
- skills/docx-renderer/references/
- skills/docx-renderer/scripts/
- skills/draft-checks/references/
- skills/draft-checks/scripts/
- skills/pipeline-cleanup/
- skills/learning-form/assets/
- skills/learning-form/scripts/

Also create PROJECT_PATH/pipeline-tests/ — the golden meetings used by /test-pipeline.
It sits outside the Meeting Notes folder on purpose: no normal run is ever given its
path, which is what stops a past meeting reaching a new one.

### Copy template files
Copy all files from [repo-root]/project-template/Meeting Notes/ into
PROJECT_PATH/MEETING_NOTES_FOLDER/, with these renames — replace the literal string
[PROJECT] with PROJECT_NAME:
- supervisor-style-guide-[PROJECT].md → supervisor-style-guide-PROJECT_NAME.md
- pipeline-memory-[PROJECT].md → pipeline-memory-PROJECT_NAME.md
- meeting-notes-formatter-skill-[PROJECT].md → meeting-notes-formatter-skill-PROJECT_NAME.md
- pipeline-scorecard-[PROJECT].md → pipeline-scorecard-PROJECT_NAME.md

Copy skills/ subdirectory contents preserving folder structure.
Do not copy .gitkeep files.

**Copy-if-absent, for every project file.** If a file with the same name already exists
at the destination, skip it and list it under "Kept existing" in the Step 6 confirmation —
never overwrite it. Only `--reinit` (after its backup) overwrites. Step 4 fills in only the
files this run created; a skipped file is left exactly as it was.

### Run DOCX renderer setup

If TEMPLATE_SOURCE is set, run the setup script. This single step creates the blank
template AND extracts all formatting values (fonts, column widths, spacing, colours,
tab stops, numIds) from the source document, rendering them into the docx-renderer
reference files — no manual editing required.

```bash
python3 "[PROJECT_PATH/MEETING_NOTES_FOLDER/skills/docx-renderer/scripts/setup_docx_renderer.py]" \
  "[TEMPLATE_SOURCE]" \
  "[PROJECT_NAME]" \
  "[PROJECT_PATH/MEETING_NOTES_FOLDER]" \
  --date-format "[DATE_FORMAT]"
```

Pass DATE_FORMAT exactly as the form gave it — it is a literal example date, not a
strftime pattern. The renderer reference and the style skill's `typography.md` must state
the same convention; this flag is what keeps them in step.

**This runs once and only once.** The script writes
`skills/docx-renderer/references/.rendered.json` when it finishes. On any later run it
sees that marker and exits without touching a single file, so the reference files —
including anything the user has edited by hand — are never overwritten by a second
setup, by `/process-notes`, or by anything else in the pipeline.

Never add `--force` on your own initiative. It re-derives every reference file from a
new .docx and replaces hand edits. It first copies the blank template, the reference
files, `constants.json` and `.rendered.json` into
`MEETING_NOTES_FOLDER/.setup-backup-<YYYYMMDD-HHMMSS>/` and prints that path; pass it on
to the user. Use it only when the user explicitly asks to rebuild the template from a
different document.

If the script completes successfully: save the blank template path as BLANK_TEMPLATE_PATH.
If it fails: print the error, set BLANK_TEMPLATE_PATH to empty, and warn the user they will
need to run setup_docx_renderer.py manually before using /process-notes.

If it prints "Setup has already run for this project", that is not an error — the project
already has its template. Save the existing blank template path as BLANK_TEMPLATE_PATH and
carry on.

### Create AGENTS.md at project root
Copy [repo-root]/project-template/AGENTS.md to PROJECT_PATH/AGENTS.md, copy-if-absent like
every other project file. The existing project guard in Step 1d has already stopped setup
if an AGENTS.md or CLAUDE.md exists, unless `--reinit` was passed and the backup was made.

Then copy the two stubs beside it, copy-if-absent: [repo-root]/project-template/CLAUDE.md
to PROJECT_PATH/CLAUDE.md and [repo-root]/project-template/GEMINI.md to
PROJECT_PATH/GEMINI.md. Claude Code reads CLAUDE.md and Gemini CLI reads GEMINI.md; each
stub only imports AGENTS.md. Never write project details into a stub.

### Create Claude launcher (Claude Code on macOS only)

Skip this whole section if CREATE_LAUNCHER is NO.

Create a file at PROJECT_PATH named exactly:
  Claude — PROJECT_NAME Meeting Notes Launcher.command
If it already exists, keep it (copy-if-absent) unless `--reinit` was passed.

Write the following content into it:
```
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
while [ ! -f "$DIR/AGENTS.md" ] && [ ! -f "$DIR/CLAUDE.md" ] && [ "$DIR" != "/" ]; do
  DIR="$(dirname "$DIR")"
done
# The project instruction file: AGENTS.md, or CLAUDE.md in a project set up before it.
if [ -f "$DIR/AGENTS.md" ]; then PROJECT_FILE=AGENTS.md
elif [ -f "$DIR/CLAUDE.md" ]; then PROJECT_FILE=CLAUDE.md
else
  echo "error: could not find AGENTS.md or CLAUDE.md above launcher — not launching Claude"
  exit 1
fi
cd "$DIR"
# DIR is the folder holding that file: the project root or its Meeting Notes folder.
# sync_pipeline.py accepts either.
REPO=$(grep -m1 "Pipeline repo (for /sync-pipeline" "$PROJECT_FILE" | sed 's/^[^:]*: *//')
if [ -z "$REPO" ] || [ ! -f "$REPO/scripts/sync_pipeline.py" ]; then
  echo "error: pipeline repo not found (check 'Pipeline repo' line in $PROJECT_FILE) — not launching Claude"
  exit 1
fi
# Uncommitted edits to what sync copies are unfinished work: never push them to a project.
DIRTY=$(git -C "$REPO" status --porcelain -- global "project-template/Meeting Notes/skills" 2>/dev/null)
if [ -n "$DIRTY" ]; then
  echo "warning: the pipeline repo has uncommitted changes to synced files — skipping sync."
  echo "  This project keeps its current agents and skills. Commit or discard the changes in"
  echo "  $REPO, then relaunch to sync."
else
  python3 "$REPO/scripts/sync_pipeline.py" --global --project "$DIR"
  if [ $? -ne 0 ]; then
    echo "error: pipeline sync failed — not launching Claude"
    exit 1
  fi
fi
claude
```

This runs `/sync-pipeline` automatically on every launch, before Claude opens, so a deployed
project never runs against stale skills or agents. Sync keeps the newest 5 of its own
`.pipeline-backup-*` folders in each location and prunes older ones. If sync fails for any reason (repo moved,
sync error), the launcher stops and does not open Claude — it never launches against a
partially-synced or unknown state. If the repo has uncommitted changes under `global/` or
the project-template skills, the launcher skips the sync, says so, and opens Claude on the
project's last synced state, so a half-made edit never reaches a live project.

Make it executable:
  chmod +x "PROJECT_PATH/Claude — PROJECT_NAME Meeting Notes Launcher.command"

---

## Step 4 — Populate project files

### AGENTS.md
Open the newly created AGENTS.md at PROJECT_PATH and make the following replacements:
- [PROJECT NAME] → PROJECT_NAME
- [FULL PATH TO PROJECT FOLDER] → PROJECT_PATH
- [FULL PATH TO THE steno REPO] → the repo root (the launcher and
  /sync-pipeline read it from the "Pipeline repo" line)
- Every occurrence of `Meeting Notes/` in file location values → MEETING_NOTES_FOLDER/
- Every occurrence of [PROJECT] in file location values → PROJECT_NAME
- Placeholder roster rows → one table row per ROSTER entry: | Name | Organisation | Title |
- [Org1, Org2, Org3...] → ORG_NAMES (comma-separated, exactly as confirmed)
- `Supervisor activation threshold: 3` → SUPERVISOR_THRESHOLD
- The five meeting lines under "Document conventions":
  - `Document title: …` → DOCUMENT_TITLE
  - `Prepared by line: …` → PREPARED_BY
  - `Recurring meeting day: [Thursday]` → MEETING_DAY
  - `Recurring meeting interval (days): 7` → MEETING_INTERVAL
  - `Recurring meeting time: [3:00PM]` → MEETING_TIME

  When one of these is empty, delete that whole line rather than leaving the bracketed
  example in place. A missing line switches its check off; a bracketed example would be read
  as the real value.

If NOTES is not empty, append a `## Project notes` section at the end of AGENTS.md
containing that text verbatim.

### DOCX renderer entries in AGENTS.md

In addition to the standard replacements, fill in the four DOCX renderer keys:
- `[PROJECT]_blank_template.docx` → BLANK_TEMPLATE_PATH (or leave with warning comment if not set)
- `DOCX renderer scripts` → `MEETING_NOTES_FOLDER/skills/docx-renderer/scripts/`
- `DOCX working dir` → `MEETING_NOTES_FOLDER/working/`
- `DOCX renderer skill` → `MEETING_NOTES_FOLDER/skills/docx-renderer/SKILL.md`
- `Humanizer skill` → `MEETING_NOTES_FOLDER/skills/humanizer/SKILL.md`

### Formatter skill file
Open meeting-notes-formatter-skill-PROJECT_NAME.md. Replace [PROJECT NAME] with
PROJECT_NAME, and `[project]` in the `name:` line with PROJECT_NAME in lower case. Write
nothing else into it: it holds only Stage 1 drafting notes that fit no other file, and a
new project has none. Every style rule goes in the style rules files below, which every
stage that needs it reads.

### Apply the form's style answers

The form answers are explicit user choices, so they outrank anything inferred from the
uploaded document. Write each one as a stated rule into the file named:

- DATE_FORMAT → style rules `references/typography.md` "Date format", written out as the
  literal example
- NUMBERING → style rules `references/structure.md`: the section numbering scheme (DECIMAL
  `1. / 1.1 / 1.1.1`, ALPHA `A. / A.1`, MIXED `1) / a) / i)`, NONE for headings only)
- TONE → style rules "Tone": register (FORMAL_THIRD, FORMAL_FIRST, NEUTRAL, INFORMAL)
- SPEAKER_ATTRIBUTION → style rules "Tone": NEVER, DECISIONS, or ALWAYS
- ACTION_COLUMN → ORG_ONLY needs nothing written: draft-format.md rule 7 already holds it.
  Any other value is handled by the hard rules note below
- STATUS_VALUES → style rules "Status column": when to use each value. The permitted set is
  fixed by draft-format.md rule 7; if STATUS_VALUES names a value outside it, say so in the
  confirmation, because `check_draft.py` rejects that value

Where a form answer and EXTRACTED_DATA disagree, the form wins and no question is asked.

If ACTION_COLUMN is anything other than ORG_ONLY, note in the hard rules skill that the
default org-only attribution rule has been overridden for this project, so
`discipline-checker` validates against the chosen convention instead.

### Style rules and hard rules skill files
For each `[TO BE FILLED IN]` section in style rules (SKILL.md, `references/structure.md`,
`references/typography.md`) and hard rules:
- If EXTRACTED_DATA has HIGH or MEDIUM confidence: replace [TO BE FILLED IN] with extracted
  content written as specific, actionable rules. Style conventions only — no actual content
  (names, dates, decisions) from the uploaded notes.
- If EXTRACTED_DATA is empty or LOW confidence: leave [TO BE FILLED IN] but replace the
  comment block with a targeted prompt noting what to fill in.

Never restate draft-format.md rule 7 (what an Action or Status cell may hold): point to it.

The hard rules terminology reference: add every term from TERMINOLOGY, plus any technical
terms extracted from uploaded notes, under the appropriate category.

### Humanizer skill file
Do not populate this one. It ships complete and is project-independent — copy
`skills/humanizer/` across as-is, including `references/` and `vendor/`. It has no `[TO BE FILLED IN]`
sections and takes no extracted data.

---

## Step 5 — Mark setup complete

Write the marker that tells the first-run hook not to reopen the form. Without this the
setup form pops up again on the next Claude Code session.

Write to `[repo-root]/.steno/setup-state.json`, creating `.steno/` if needed. (A clone
set up before this path existed has `.claude/.setup-state.json`; leave it, the hook reads
both.)

```json
{
  "setupComplete": true,
  "completedAt": "[ISO 8601 timestamp]",
  "project": "[PROJECT_NAME]",
  "projectPath": "[PROJECT_PATH]"
}
```

Then delete the generated form so it does not sit stale in the repo root:

```bash
rm -f "[repo-root]/setup-session.html"
```

Both paths are gitignored. To set up a second project later, the user runs
`/setup-pipeline` by hand, or `python3 scripts/generate_setup_form.py` and pastes the
block — the hook only ever fires on a fresh clone.

Register the project in `[repo-root]/projects.txt`, the list `/apply-learning` tests every
shared AGENT or CHECK change against. Add PROJECT_PATH (no trailing slash) only if no line
already equals it, so a `--reinit` never lists a project twice:

```bash
LIST="[repo-root]/projects.txt"
if ! grep -qxF "PROJECT_PATH" "$LIST" 2>/dev/null; then
  [ -s "$LIST" ] && [ -n "$(tail -c1 "$LIST")" ] && echo >> "$LIST"
  printf '%s\n' "PROJECT_PATH" >> "$LIST"
fi
```

---

## Step 6 — Print confirmation

Print exactly this (substituting real values):

---
Pipeline installed.

Global files added for [tool] (the folders sync_pipeline.py printed), e.g. for
Claude Code:
  ~/.claude/commands/
  ~/.claude/agents/
  ~/.claude/skills/

Project scaffolded at:
  PROJECT_PATH/
  ├── AGENTS.md  ← the project file: roster, organisations, file locations
  ├── CLAUDE.md  ← stub that points Claude Code to AGENTS.md
  └── GEMINI.md  ← stub that points Gemini CLI to AGENTS.md

Meeting Notes folder:
  PROJECT_PATH/MEETING_NOTES_FOLDER/
  ├── transcripts/       ← drop transcripts here
  ├── output/            ← pipeline drafts appear here
  ├── intake/            ← drop supervisor-approved files here
  ├── Archive/           ← issued notes archive
  ├── working/           ← docx renderer scratch space (not for manual editing)
  └── skills/            ← your style, hard rules, humanizer, and docx renderer

Listed in [repo-root]/projects.txt [or: already listed in projects.txt]

[If any project file was skipped because it already existed:]
Kept existing (not overwritten):
  [one line per skipped file]

[If --reinit made a backup:]
Previous project files backed up to:
  [the .setup-backup-<stamp> path]

[If CREATE_LAUNCHER is YES:]
Launcher created:
  PROJECT_PATH/Claude — PROJECT_NAME Meeting Notes Launcher.command
  └── Double-click this in Finder to open Claude Code in the right folder

[If BLANK_TEMPLATE_PATH is set:]
DOCX blank template created:
  BLANK_TEMPLATE_PATH
  └── Headers, footers, and branding preserved from your uploaded file

[If BLANK_TEMPLATE_PATH is empty:]
⚠ DOCX blank template not created — create it before running /process-notes:
  python3 MEETING_NOTES_FOLDER/skills/docx-renderer/scripts/setup_docx_renderer.py <source.docx> PROJECT_NAME MEETING_NOTES_FOLDER

  This also renders the reference files. It runs once — afterwards the files are yours to
  edit, and setup will not overwrite them. To rebuild from a different .docx, add --force.

Settings applied from the setup form:
  Date format          DATE_FORMAT
  Section numbering    NUMBERING
  Tone                 TONE
  Speaker attribution  SPEAKER_ATTRIBUTION
  Action column        ACTION_COLUMN
  Supervisor threshold SUPERVISOR_THRESHOLD
  Meeting schedule     MEETING_DAY, every MEETING_INTERVAL days, at MEETING_TIME
  Document title       DOCUMENT_TITLE
  Prepared-by line     PREPARED_BY
  [For any of these left empty, print "not set" and add one line: "The header falls back to
  this value when a transcript doesn't state it. Add it to AGENTS.md if you know it."]

[If past notes were uploaded, include this block:]
Auto-populated from your uploaded notes:
  ✓ Team roster ([N] members)
  ✓ Organisation names ([N] orgs)
  ✓ Style rules — [list sections that were filled in]
  ✓ Terminology — [N terms added] (or "none found")

Still needs your input:
  [List any style rules or hard rules sections left as [TO BE FILLED IN]]

Next steps:
1. Open your agent tool (Claude Code, Codex CLI or Gemini CLI) from PROJECT_PATH or
   PROJECT_PATH/MEETING_NOTES_FOLDER
2. Complete any [TO BE FILLED IN] sections in the skill files
3. Drop a transcript in MEETING_NOTES_FOLDER/transcripts/ and run /process-notes
---

Do not ask follow-up questions. The setup is complete.
