# apply-learning

> **Project instruction file.** `AGENTS.md` here means the project's instruction file: `AGENTS.md`, or `CLAUDE.md` in a project set up before Steno moved to AGENTS.md. Read whichever the project has. When both sit in one folder, AGENTS.md holds the project and CLAUDE.md only points to it.

## Trigger
This command runs automatically when the user pastes a block beginning with
==LEARNING_REVIEW== into the terminal. The user does not need to type
/apply-learning manually — detecting the paste marker is enough to begin.

## Step 1 — Validate the block
Check the pasted content starts with ==LEARNING_REVIEW== and ends with ==END_REVIEW==.
If malformed or incomplete: stop and say "Paste looks incomplete — copy again from the
browser form and paste the full block."
If valid: proceed silently. Do not echo the block back.

## Step 2 — Load AGENTS.md
Read AGENTS.md to get all file paths before writing anything.

## Step 3.0 — Open a run entry in pipeline memory
Everything this command does is logged under one dated entry. `/audit` counts run
entries by their date header and counts approved changes by the CATEGORY tag on each
line, so a cycle that writes rules to skill files but logs nothing here is invisible
to `/audit` forever.

Append to the pipeline memory file listed in AGENTS.md:

```
## [YYYY-MM-DD] — [transcript name from the block header]
```

Every line written in Steps 3 to 9 goes under this header, in these exact forms:

```
APPROVED [CATEGORY]: [rule text] — applied to [file]
REJECTED [DATE]: [rule text] — [reason, or "not applied" if the form gave none]
DEFERRED [DATE]: [rule text] — no answer given
DERIVED [CATEGORY]: [rule text] — applied to [file]
PROPOSED [CATEGORY]: [rule text] — [repo file], awaiting yes (Step 9)
```

CATEGORY is one of WORDING, FORMAT, STRUCTURE, ATTRIBUTION, STATUS, SCOPE,
TERMINOLOGY, SUPERVISOR-PREF, HARD-RULE, AGENT, CHECK. Use the category the block
already carries on that change — never invent one, and never drop it.

AGENT and CHECK are how a correction stops repeating instead of accumulating:

- **AGENT** — the rule already exists and an agent did not follow it. The fix belongs in
  that agent's instructions, not in another sentence of a skill file. The block names the
  stage; `/learn` gets it from the per-stage drafts in `working/runs/<stem>/`.
- **CHECK** — the rule is mechanical and has now been missed twice. The fix is a check in
  `check_draft.py` plus a test, which is the only way a rule gets applied identically on
  every run.

Both are written to the shared pipeline repo, so they change every installed project, not
just this one. They are never written in Steps 3 to 5.5: each becomes a proposal, and
Step 9 writes it only after an explicit "yes" in the chat, the repo tests and
`/test-pipeline` on every project in the repo's `projects.txt`. An [APPROVE] in the form
approves the idea, not the shared edit.

## Step 3 — Process Section 1: Proposed changes
For each line marked [APPROVE]:
- Resolve the target file. The block names a category and a target; turn it into a
  real path using "Key file locations" in AGENTS.md, never a bare `skills/...` path:
  - WORDING → the supervisor style guide, under "Recurring corrections" (see Step 4).
    Never the style rules skill file: it is always on, so one approval there skips the
    threshold.
  - FORMAT → the style rules skill's `references/typography.md`
  - STRUCTURE → that skill's `references/structure.md`
  - ATTRIBUTION / STATUS / SCOPE / HARD-RULE → the hard rules skill file listed in AGENTS.md
  - TERMINOLOGY → the hard rules skill's `references/terminology.md`
  - SUPERVISOR-PREF → the supervisor style guide, under "Recurring corrections" (see Step 4)
  - AGENT → the named agent in the pipeline repo's `global/agents/`, never the installed
    copy in `~/.claude/agents/`. Editing the installed copy alone means the next
    `/sync-pipeline` overwrites the fix.
  - CHECK → `check_draft.py` **in the pipeline repo**
    (`project-template/Meeting Notes/skills/draft-checks/scripts/`), plus a case in the
    repo's `tests/test_check_draft.py`. Never the project's copy: `/sync-pipeline` copies
    the repo version over it, so a check written into the project survives until the next
    sync and then vanishes — the same silent loss the AGENT category exists to prevent.
    Propose the check only if you can state it as a yes/no a script can decide with no
    opinion; if you cannot, log it as DEFERRED and say why.
- AGENT or CHECK: write nothing. Log `PROPOSED [CATEGORY]: [rule text] — [repo file],
  awaiting yes (Step 9)` and add it to the Step 9 list.
- Any other category: write the rule to that file, silently — the user already approved
  it in the form. A "Recurring corrections" entry takes the dates of the matching "Open
  patterns" row plus this cycle's date (Step 4 gives the format), so it goes live only at
  the threshold. Log it: `APPROVED [CATEGORY]: [rule text] — applied to [file]`

For each line marked [REJECT]:
- Log it: `REJECTED [DATE]: [rule text] — [reason, or "not applied"]`
- Write nothing to any skill file
- Set the matching "Open patterns" row to `blocked — rejected [DATE]` (Step 5.5)

For each line marked [NO ANSWER]:
- Log it: `DEFERRED [DATE]: [rule text] — no answer given`
- Write nothing to any skill file

## Step 4 — Process Section 2: Style Q&A
For each Q&A pair where an answer is not "(no answer)":
- Read the question and the answer
- Derive the most specific rule possible from the answer
- Determine the correct target file using the paths from AGENTS.md:
  - Supervisor wording or tone preference → the supervisor style guide listed in AGENTS.md,
    under **"Recurring corrections"** — never under "Wording preferences"
  - Formatting detail → the style rules skill references/typography.md (derived from the style rules skill path in AGENTS.md)
  - Section ordering or layout → the style rules skill references/structure.md
  - General style principle → the style rules skill file listed in AGENTS.md
  - Absolute rule → the hard rules skill file listed in AGENTS.md
  - Technical term → the hard rules skill references/terminology.md
- Write the derived rule directly to that file — no confirmation needed
- The rule must be a single actionable sentence, not a summary of the answer
- Log it: `DERIVED [CATEGORY]: [rule text] — applied to [file]`

**Why "Recurring corrections" and not "Wording preferences".** The four sections
"Wording preferences", "Structural preferences", "Scope preferences" and "Promoted
rules" are applied by `supervisor-alignment` on every run regardless of the threshold.
They are for preferences a human deliberately seeds. A preference this command derives
from one cycle has been seen exactly once — writing it there makes a single correction
permanent immediately, which is the opposite of what the threshold exists to prevent.
"Recurring corrections" is gated per entry, so a derived rule only starts influencing
output once it has been confirmed enough times.

**One counting model.** Every "Recurring corrections" entry, like every "Open patterns"
row (Step 5.5), carries a list of the dates it was seen on:

```
- [rule text] — [CATEGORY] — seen: YYYY-MM-DD, YYYY-MM-DD
```

The date for this cycle is the block's DATE line (the meeting date), written YYYY-MM-DD.
A date already in the list is not added again. `supervisor-alignment` applies an entry
only when its number of distinct dates is at least the "Supervisor activation
threshold" key in AGENTS.md (default 3); entries below it wait, whatever the others do.
If the same rule is already present, do not duplicate it — add this cycle's date to the
existing entry.

For each Q&A pair where the answer is "(no answer)":
- Skip silently

## Step 5 — Process Section 3: Project context
Work through each field. For any field that is not "none":

New members:
- Parse name, organisation, title from the value
- Add a new row to the project roster table in AGENTS.md
- Write directly — no confirmation needed

Departed:
- Find the matching row in AGENTS.md project roster
- Remove or annotate as departed with the date
- Write directly

New orgs:
- Add to the organisation names list in AGENTS.md
- Write directly

Scope changes:
- Append a note to AGENTS.md under a "Scope notes" section (create if not exists)
- Write directly

New terms:
- Add each term to the hard rules references/terminology.md (derived from the hard rules skill path in AGENTS.md)
- Infer the category from the term
- If category is unclear, add under a new "Other" section
- Write directly

Other:
- Determine the correct file from context
- Write directly

## Step 5.5 — Update the pattern table, open decisions and scorecard

Three writes, all to files that survive cleanup. None of them may contain meeting
content — no names, lot numbers, dimensions or quoted phrases. A pattern is a shape, not
an example: "rationale behind a scope decision dropped", never "the WWTP rationale for
lots 7/8/9".

**1. Open patterns.** Read this cycle's patterns **only** from the block's
`--- SECTION 0: PATTERNS ---` lines (`PATTERN [CATEGORY]: [pattern]`, or `none`). Never
rebuild the list from the conversation, the form or memory of the review: a fresh session
has none of it. If the block has no SECTION 0 (a form from before this step), update no
row and say in the summary that this cycle's patterns were not logged.

In the pipeline memory file, under "Open patterns", add or update one row per PATTERN
line:

```
| [pattern, content-free] | [dates seen] | [category] | [status] |
```

A line whose text matches a row's Pattern exactly updates that row: add this cycle's date
(Step 4) unless it is already listed. Any other line opens a new row. If the row's rule
sits in the supervisor guide's "Recurring corrections", add the date to that entry too.
A pattern's count is the number of distinct dates in its row — there is no separate
count to keep in step. The threshold is the "Supervisor activation threshold" key in
AGENTS.md (default 3), the same number that gates "Recurring corrections", so a project
sets it once.

Status is one of three words, optionally followed by ` — [note]`:
- `watching` — below the threshold, or its rule is in "Recurring corrections" and not
  yet live
- `promoted [YYYY-MM-DD]` — a rule covering it has been written and is live
- `blocked — [reason]` — it will never be promoted automatically

A proposal approved in Step 3 sets its row to `promoted [YYYY-MM-DD]`, or to
`watching — in Recurring corrections` when that is where it was written and its dates
are still below the threshold. Once such a row's dates reach the threshold, its entry is
already live: set the row to `promoted [YYYY-MM-DD]` and write nothing else. An AGENT or
CHECK proposal sets its row to `watching — proposed, awaiting yes`; Step 9 sets the final
status.

**At the threshold, promote it in this same step — do not leave it for a human — unless
a block below applies.**

**Never promote a pattern when either is true:**
- The memory file holds a `REJECTED` line for this rule or the same correction, at any
  date. The user already said no; three sightings do not overrule them.
- The rule would contradict, weaken or carve an exception out of any hard rule.

Instead set the row's status to `blocked — [rejected YYYY-MM-DD | conflicts with hard
rule]`, add it under "Open decisions" so the user settles it on the next form, and write
nothing to any rule file. A blocked row stays blocked whatever its count becomes.

Otherwise:

1. Write the rule to the file its category maps to in Step 3. A WORDING or
   SUPERVISOR-PREF rule goes to "Recurring corrections" with the row's dates, so it is
   live at once. An AGENT or CHECK row is never promoted automatically: log it as
   PROPOSED, add it to the Step 9 list, set the row to `watching — proposed, awaiting
   yes`, and skip 2 and 3.
2. Log it as `APPROVED [CATEGORY]: [rule text] — applied to [file] (promoted after N
   sightings)`.
3. Set the row's status to `promoted [YYYY-MM-DD]` and leave it in the table as the
   record of why that rule exists.

Promotion was left to a human before, and in five cycles nothing was ever promoted. A
rule that a table says has been seen three times does not need a second judgement call.
List every promotion and every block in the final summary, so none happens silently.

**2. Open decisions.** Any Q&A question that came back "(no answer)", and any proposal
marked [NO ANSWER], goes under "Open decisions" in the same file with its date and the
number of cycles it has now gone unanswered. Anything already there gains a cycle.
These are asked first, at the top of the next review form. A question that has gone
three cycles unanswered is not a form question any more — name it in the summary and
tell the user to settle it directly.

**3. Scorecard.** Append one line to the pipeline scorecard listed in AGENTS.md, under
"Learn cycles":

```
| [YYYY-MM-DD] | [proposed] | [approved] | [rejected] | [deferred] | [Q&A answered]/[Q&A asked] | [open decisions carried] | [score] | [coverage] | [precision] | [action] | [status] |
```

The last five cells come from the `scorecard` object in `[DOCX working dir]/runs/<STEM>/
score.json`, which `/learn` wrote: copy `score`, `coverage`, `precision`, `action` and
`status` exactly as they are, including any "approx" or "n/a". Never recompute them or
drop the "approx". If the file is missing, write "n/a" in all five. If the table header
has only seven columns (a scorecard from before this change), add the five column names
to the header and separator first, and leave older rows' new cells blank.

## Step 6 — Move the final file
Read the "Issued archive" path from AGENTS.md.
Check the intake folder (listed in AGENTS.md) for the issued file. Ignore any name that
starts with `.` (`.DS_Store`) or `~$`, folders and empty files; if none or more than one
file is left, say so and stop.
Read the existing filenames in the issued archive and follow the naming convention already
in use there rather than assuming one. The number is the `MEETING NO` line of the pasted
block — the meeting number of the draft that was issued. A count of the archive is not:
PDFs, duplicates and stray files make it drift. If the block's MEETING NO is missing,
empty or `[not provided]`, find the highest number in the archive, add 1, and say in the
summary that the number was not taken from the draft. If a file with the chosen name is
already in the archive, stop and ask — never overwrite an issued file.
Move the intake file to the archive under that name.

Do NOT delete anything in this step — Step 7 clears every folder at once, and only after
it has verified the archived file is really there.

## Step 7 — Clean up pipeline folders
Run the cleanup script, passing the exact filename you just archived and the `STEM`
line of the pasted block:

```bash
bash "[MEETING_NOTES_FOLDER]/skills/pipeline-cleanup/cleanup-cycle.sh" "[archived filename]" \
  --stem "[STEM from the block]"
```

If the block has no STEM line, do not guess one: report that cleanup was skipped and
why, and stop.

Add `--archive "[Issued archive path from AGENTS.md]"` if the archive is not the default
`Archive/` folder beside the pipeline.

The script deletes only this meeting's files: `working/runs/<stem>/`, the transcript with
that stem, and the output draft named in the run folder's `run.txt`. Another meeting
processed before this `/learn` keeps its transcript, draft and run folder. It also deletes
qa-session.html from the project root and from Meeting Notes/, and clears the shared
render scratch once no other run folder is left. Before deleting, it copies the
transcript and the issued .docx into `pipeline-tests/<HELD ON date>/` at the project root
for `/test-pipeline`, keeping the newest 8 such folders; say in the summary which folder
it kept, or that it kept none (an issued PDF). It refuses (exit 1, nothing deleted)
while intake/ still holds a file or when the stem matches no run folder and no
transcript — report that and stop. It refuses to delete anything unless
the named file is already present and non-empty in the archive, so the archive-confirmed
precondition is enforced by the script rather than by judgement. Never hand-roll `rm`
commands for this step, and never pass a filename you have not just verified in the archive.

Exit codes: 0 = cleared, 1 = refused and nothing was deleted, 2 = bad usage.
If the script exits non-zero, nothing was deleted: report the error and stop (any Step 9
proposals still go to Step 9).
If it is blocked by a permission prompt, say so plainly in the summary rather than
attempting the deletions another way.

Use `--dry-run` first if you want to show the user what will go before it goes.

This leaves each cycle's only surviving copy as the numbered file in the issued archive.

## Step 8 — Print summary and stop
Print this and nothing else:

---
Done.

Changes applied: [N]
Rules derived from Q&A: [N]
Project context updates: [N]
Patterns logged: [N, or "not logged — no SECTION 0"]
Promoted: [each pattern, or "none"]
Blocked: [each pattern and reason, or "none"]
Shared AGENT/CHECK proposals: [N, shown next for a yes or no, or "none"]

Files updated:
[list only files that were actually written to, one per line]

Archived to:
[Project Name] - Meeting Notes #[N].[ext]

Cleaned up:
[stem]: transcript, output draft and run folder cleared
Kept for /test-pipeline: [pipeline-tests/<folder>/, or "none" and why]
[only if a hard rules skill file or its references/ was written:] run /test-pipeline
---

If the Step 9 list is empty, stop here: do not ask follow-up questions or offer next
steps. Otherwise go to Step 9. Go to Step 9 even when an earlier step stopped after
Step 5.5 (a cleanup refusal, say): the proposals are already logged and must not be lost.

## Step 9 — Shared AGENT and CHECK proposals
An AGENT or CHECK change edits files every installed project runs: the agents and
`check_draft.py` in the pipeline repo ("Pipeline repo" in AGENTS.md). A rule learned
from one project's supervisor can be wrong for another, so nothing reaches the repo
without the user's yes, and nothing is synced until every project's test set passes.
The installed projects are the non-comment lines of `[pipeline repo]/projects.txt`. If
that file is missing or this project is not in it, say so before the first proposal.

Take the proposals one at a time:

1. **Show the exact change, write nothing.** Name the repo file(s) and print the unified
   diff against the current file, as it would be applied: the agent file for AGENT;
   `check_draft.py` plus its case in `tests/test_check_draft.py` for CHECK. Say which
   projects it will affect (every line of `projects.txt`). Then ask: "Apply this to the
   shared pipeline? yes / no".
2. **Only an explicit "yes" in the chat proceeds.** The form's [APPROVE] is not a yes.
   - "no" → log `REJECTED [DATE]: [rule text] — declined in chat`, set the pattern row
     to `blocked — rejected [DATE]`, next proposal.
   - Anything else, or no reply → log `DEFERRED [DATE]: [rule text] — no yes in chat`,
     add it to "Open decisions", leave the row `watching`, next proposal.
3. **Apply it in the repo.** First run `git -C "[pipeline repo]" status --porcelain` on
   the target files: if any has uncommitted changes, stop and report — never mix this
   edit with someone else's. Then write exactly the diff shown in 1.
4. **Run the repo test suite:** every `python3 "[pipeline repo]/tests/<file>.py"`. If any
   fails, undo the edit (`git -C "[pipeline repo]" checkout -- <each edited file>`,
   delete any file it added), log `DEFERRED [DATE]: [rule text] — repo tests failed,
   reverted`, report which test failed, next proposal.
5. **Commit it in the repo**, only the files you edited:
   `git -C "[pipeline repo]" add <files>` then `git -C "[pipeline repo]" commit -m
   "apply-learning: [CATEGORY] [rule, ≤60 chars] (learned on [project], [DATE])"`.
   Note the commit hash.
6. **Run `/test-pipeline` on every project in `projects.txt`**, testing the repo version
   as `/test-pipeline` describes under "Testing an unsynced change", and passing it the
   project name this change was learned on. Do not launch any project's launcher until
   this step ends: the launcher syncs from the repo, so it would install the change
   before it has passed. A project with an empty test set, or one `/test-pipeline` cannot
   run, has not passed: say so.
   - If any project fails or was not run: `git -C "[pipeline repo]" revert --no-edit
     [hash]`, run the repo tests once more, log `DEFERRED [DATE]: [rule text] —
     /test-pipeline failed on [project]: [number that moved], reverted [hash]`, report it,
     next proposal.
7. **Only when every listed project has passed:** log `APPROVED [CATEGORY]: [rule text] —
   applied to [repo file], commit [hash], /test-pipeline passed on [projects]`, set the
   pattern row to `promoted [YYYY-MM-DD]`, and tell the user to run `/sync-pipeline`; the
   change is not live in any project until then.

After the last proposal, print one line per proposal (applied with hash, declined,
deferred, or reverted and why). If any AGENT or CHECK change was committed, end with
`run /test-pipeline` (after /sync-pipeline, to confirm the installed copy), and stop. Do not offer other next steps.
