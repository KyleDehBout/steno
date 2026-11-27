# Test pipeline

> **Project instruction file.** `AGENTS.md` here means the project's instruction file: `AGENTS.md`, or `CLAUDE.md` in a project set up before Steno moved to AGENTS.md. Read whichever the project has. When both sit in one folder, AGENTS.md holds the project and CLAUDE.md only points to it.

Run the pipeline against past meetings and score the result against what the supervisor
actually issued. Use it before trusting any change to an agent, a skill rule or a check.

## Why this exists

Drafts are deleted at the end of every `/learn` cycle, so meeting #16's draft cannot be
compared with meeting #20's. Past meetings are the only fixed point left: the same
transcript, run through the old and the new pipeline, is a comparison that means
something.

## The test set

```
[project]/pipeline-tests/
├── 2026-07-16/
│   ├── transcript/
│   │   └── transcript.txt    ← the raw transcript, alone in its own folder
│   ├── issued.docx           ← the supervisor's final, from the archive
│   ├── baseline.json         ← the last recorded score (written by this command)
│   └── .from-cleanup         ← present when cleanup made this folder
├── 2026-09-03/
└── .runs/                    ← scratch, deleted after each run
```

This folder sits **outside** `Meeting Notes/`. `/process-notes` is never given its path,
and no normal run reads it. That is what keeps a past meeting from leaking into a new one.

The set fills itself. At the end of every `/learn` cycle, `cleanup-cycle.sh` copies that
meeting's transcript and issued .docx into `pipeline-tests/<HELD ON date>/` (or
`undated-<stem>/` when the run has no scorecard key) before it deletes them, and keeps
only the newest 8 folders it made. A folder you add by hand, without the
`.from-cleanup` file, is never pruned: use that for a meeting you want tested for good.
An issued PDF is not kept, because the scorer reads .docx only.

Every folder under `pipeline-tests/` except `.runs/` is a meeting in the test set. A
folder with no `transcript/` or no `issued.docx` is skipped and named in the report.

The transcript sits alone in `transcript/` because Stage 1 takes the newest file in the
transcripts folder. Pointed at the meeting folder itself, it took `baseline.json`, which
this command rewrites after every passing gate. A meeting folder from before this layout
has its transcript beside `issued.docx`: move it into `transcript/` first.

## Running it

For each meeting folder, in order:

1. Create `pipeline-tests/.runs/<meeting-id>/`. Everything below happens there. Never
   write to `Meeting Notes/transcripts/`, `output/`, `intake/` or `working/`.

2. **Write an override AGENTS.md into the run folder and pass that file to every stage,
   in place of the project's own.** Every agent resolves its paths from AGENTS.md, so
   redirecting them in prose here would not redirect them at all — the agents would read
   the real one and write into the live folders.

   Copy the project AGENTS.md and change exactly five lines:

   ```
   - Transcripts: pipeline-tests/<meeting-id>/transcript/
   - Output (pipeline drafts): pipeline-tests/.runs/<meeting-id>/output/
   - Intake (final issued files for learning): pipeline-tests/.runs/<meeting-id>/intake/
   - DOCX working dir: pipeline-tests/.runs/<meeting-id>/working/
   - Pipeline scorecard: pipeline-tests/.runs/<meeting-id>/scorecard.md
   ```

   Leave everything else exactly as it is — the roster, organisation names, document
   conventions and skill paths are what is being tested. Before Stage 1, create the
   `output/`, `intake/` and `working/` folders and copy the project scorecard to
   `scorecard.md` in the run folder. Stages 2.5 and 4.5 write a scorecard row on every
   run, and a test run must never write one into the live scorecard.

3. Run Stages 1 to 5 of `/process-notes` exactly as written, passing the override
   AGENTS.md wherever a stage is told to pass AGENTS.md. Skip Stage 6 — rendering is
   checked by `validate.py` and adds nothing here.

   If any stage writes outside `pipeline-tests/`, stop the whole run and report it. That
   is a real isolation bug, not a test failure. So is any change to the live scorecard.
4. Score the Stage 5 draft. It is in the run folder Stage 1 created under the override's
   working dir, named after the transcript's stem:

```bash
python3 "[draft checks scripts]/score_draft.py" \
  "pipeline-tests/.runs/<meeting-id>/working/runs/<transcript stem>/stage-5.md" \
  "pipeline-tests/<meeting-id>/issued.docx" \
  --json "pipeline-tests/.runs/<meeting-id>/score.json"
```

5. Compare with `baseline.json` for that meeting. A meeting with no baseline yet (one
   cleanup just added) has nothing to compare against: report its numbers, leave it out
   of the gate below, and record its `score.json` as its first `baseline.json` whether or
   not the gate passes.

## The release gate

A change ships only if **every** meeting in the test set that has a baseline holds:

1. No new errors from `check_draft.py` that the baseline did not have.
2. Coverage is not lower than baseline by more than 0.02 — a dropped item is the failure
   this whole pipeline exists to prevent.
3. Action and Status agreement are each no lower than baseline by more than 0.02. An
   "approx" figure still counts: the estimate comes from the issued notes, which do not
   change between runs, so the same owners are uncertain in the baseline too.
4. The total score is higher than baseline on at least one meeting, and not lower on any.

If the gate fails, report which meeting and which number moved, and do not update any
baseline. A failed gate is information, not an error to work around.

If the gate passes, copy each `score.json` over its `baseline.json` and say what the new
numbers are.

## Testing an unsynced change

`/apply-learning` Step 9 runs this command on every project in the pipeline repo's
`projects.txt` after committing an AGENT or CHECK change and before anyone syncs it. The
installed agents and each project's `check_draft.py` are still the old ones then, so a
plain run would test the old pipeline and pass by default. For such a run:

- Use each listed project's own root, AGENTS.md and `pipeline-tests/`, not the current
  project's.
- CHECK: in the override AGENTS.md, also change the "Draft checks scripts" line to
  `[pipeline repo]/project-template/Meeting Notes/skills/draft-checks/scripts/`.
- AGENT: run the edited stage as a general-purpose agent whose instructions are the
  repo's `global/agents/<name>.md` (everything after its front matter), not the installed
  agent. Every other stage runs as usual.
- Gate rule 4 applies only to the project the change was learned on. On every other
  project it reads "not lower than baseline on any meeting": the change has to do no
  harm there, not improve it.
- Update no baseline until every listed project has passed; then update them all.

## Recording the result

Append one line per meeting to the "Test runs" table in the scorecard listed in the
project's own AGENTS.md (not the override), matching its seven columns:

```
| [YYYY-MM-DD] | [meeting id] | [score] | [coverage] | [action agreement] | [status agreement] | [what changed since the last run] |
```

Take score, coverage, action and status from the `scorecard` object in `score.json`, as
they are, including any "approx" or "n/a".

Numbers only. "What changed" names the file or agent that was edited — never anything
about the meeting itself.

## Cleaning up

Delete `pipeline-tests/.runs/` when finished. Report anything left behind.

## When the test set is empty

Say so and stop. Do not fall back to running against the live `Meeting Notes/` folders —
that would write a draft for a meeting that was already issued, and the next `/learn`
cycle would compare against it.
