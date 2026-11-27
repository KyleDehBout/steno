# Steno — working in the pipeline repo

This folder is the Steno pipeline itself, not a meeting notes project. Projects are set
up from here and then live in their own folders.

## Setting up a project

Setup starts the same way in every agent tool. The user runs this in this folder:

```bash
python3 scripts/generate_setup_form.py
```

It opens a form in the browser. The user fills it in and pastes a block that starts
with `==PROJECT_SETUP==` and ends with `==END_SETUP==`. When that block arrives, follow
`global/commands/setup-pipeline.md` from Step 2 onward using the pasted values (Step 1c
explains how to read them). Do not ask again for anything the block already answers.

If the user uploads or names a past `.docx` set of meeting notes before filling in the
form, follow Step 0 of that file to read values out of it, then reopen the form with
them prefilled as Step 1b describes.

## The commands

Each file in `global/commands/` is a pipeline command, and is also installed as a skill
named `steno-<command>`. In a meeting notes project, ask for what you want ("process the
latest meeting notes", "learn from the issued notes") and the matching skill applies.
To install or update the agents and skills for your tool:

```bash
python3 scripts/sync_pipeline.py --global --target claude   # or codex, or gemini
```

## Changing the pipeline

- Tests are plain Python: `python3 tests/<file>.py`. Run them all before committing.
- Keep every example name, organisation and path made up. Never commit a real
  meeting, a real project's files or a personal path.
