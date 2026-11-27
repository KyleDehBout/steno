# Sync pipeline

> **Project instruction file.** `AGENTS.md` here means the project's instruction file: `AGENTS.md`, or `CLAUDE.md` in a project set up before Steno moved to AGENTS.md. Read whichever the project has. When both sit in one folder, AGENTS.md holds the project and CLAUDE.md only points to it.

Install or update the pipeline's agents, commands and executable skills.

## When to run it

- After pulling a new version of the pipeline repo
- When `/apply-learning` Step 9 says so: an `AGENT` or `CHECK` change was committed and
  passed `/test-pipeline` on every project in `projects.txt`. It is only live once it
  reaches `~/.claude/agents/` and every project's `draft-checks/`
- When `/process-notes` stops with "Draft checks script not found"

`/setup-pipeline` installs by copy-if-absent and skips anything that already exists, so
it cannot deliver an update. That is what this command is for.

## What it does

```bash
python3 "[pipeline repo]/scripts/sync_pipeline.py" --global --all-projects \
  --project "[full project path from AGENTS.md]"
```

- `--all-projects` adds every project listed in the repo's `projects.txt`, so a shared
  check reaches all of them at once. A project named twice is synced once. If this
  project is not in `projects.txt`, say so and ask the user to add it.
- `--global` copies `global/agents/*.md` and `global/commands/*.md` into `~/.claude/`
- `--project` copies the `draft-checks`, `docx-renderer`, `pipeline-cleanup` and
  `learning-form` skills into the project's `Meeting Notes/skills/`
- `--project` takes the project root or its Meeting Notes folder, and may be repeated to
  sync several projects in one run
- Every replaced file is copied to a timestamped `.pipeline-backup-<stamp>/` folder first
- After a successful sync it keeps the newest 5 of its own backups in each location and
  prints each one it prunes (`--keep N` to change the number). Hand-made backups are
  never deleted.
- `--dry-run` prints the changes and writes nothing

## What it never overwrites

AGENTS.md, the supervisor style guide, the pipeline memory log, the scorecard, the
formatter skill, style-rules, hard-rules, terminology, and everything under
`docx-renderer/references/`. Those hold the project's own rules, rendered once during
setup and edited by hand since.

## How to run it

1. Run with `--dry-run` first and read the list.
2. Run it for real.
3. Report which files were added, which were updated, and where the backup went.
4. If any file failed to copy, say which and stop — do not retry with a different method.

If the repo path is not in AGENTS.md, ask for it once rather than guessing.
