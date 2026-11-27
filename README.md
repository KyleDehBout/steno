# Steno

Steno is a meeting notes pipeline for AI coding agents (Claude Code, Codex CLI and Gemini CLI) that transforms raw meeting transcripts into polished, professionally formatted meeting notes — and gets better with every correction your supervisor makes.

## What it does

1. **`/process-notes`** — Drop a transcript in `transcripts/`, run the command, or ask your agent to process the latest meeting. Six stages take it from transcript to .docx: format, sharpen, validate attributions, apply your supervisor's preferences, review the result against the transcript, and render. Two mechanical checks run in between. A clean draft lands in `output/`.

2. **`/learn`** — Drop your supervisor's corrected version in `intake/`. The pipeline diffs it against what it produced, opens a browser review form, and proposes specific rule updates for you to approve or reject.

3. **`/apply-learning`** — Paste the form output back into your agent. Approved rules write directly to the right skill files. The file archives to `Meeting Notes/`. The system improves.

4. **`/test-pipeline`** — Run the pipeline against past meetings and score the result against what your supervisor actually issued. A change to an agent or a rule ships only if the numbers hold or improve.

5. **`/sync-pipeline`** — Install or update the agents, commands and skill scripts. `/setup-pipeline` only ever adds files that are absent, so this is what delivers a change to a machine or project that is already set up.

## How the pipeline improves over time

Every correction your supervisor makes becomes a rule. Rules accumulate in project-level skill files and a supervisor style guide. After enough repetitions, patterns promote to permanent hard rules. The pipeline that formats meeting #20 is meaningfully better than the one that formatted meeting #1.

## What you get per project

- A roster-aware attribution checker (no individual names in the Action column — ever)
- A living supervisor style guide that grows with each issued set of notes
- A pipeline memory log tracking approved and rejected rule changes
- Full data isolation — nothing from one transcript ever bleeds into another

---

## Setup

### Prerequisites
- One of the supported agent tools installed (see **Supported tools** below)
- Python 3 (3.11 or later to run the tests)
- A GitHub account (optional, for version control)

### Install

1. Clone this repo.
2. Start setup in the clone:

   ```bash
   python3 scripts/generate_setup_form.py
   ```

   The setup form opens in your browser. In Claude Code you can skip this step: on the first session after you clone, a hook runs it for you.
3. Fill it in: project name, folder path, team roster, organisation names, and your document style defaults
4. Click **Generate setup block**, then **Copy to clipboard** or **Copy & close**
5. Paste the block into your AI agent opened in the clone folder. Setup runs from there with no further questions
6. Open your new project folder in your agent and you're live

Setup installs the shared agents, commands and skills for your tool (`scripts/sync_pipeline.py --target …`) and scaffolds your project folder from the template. It never overwrites a file that already exists.

Optional: before filling in the form, give your agent a past `.docx` set of meeting notes. It reads your roster, organisation names, branding, and style out of the file and reopens the form with those fields already filled in and badged **Prefilled**.

### Supported tools

Steno runs in any of these. Install its agents and skills for each tool you use; you can install for more than one.

| Tool | Install | Run mode | Known limits |
|---|---|---|---|
| [Claude Code](https://claude.ai/code) | `python3 scripts/sync_pipeline.py --global --target claude` | Delegated: each stage is its own sub-agent | None. The slash commands (`/process-notes` and so on), the first-run hook and the macOS launcher are Claude Code only |
| [Codex CLI](https://github.com/openai/codex) | `python3 scripts/sync_pipeline.py --global --target codex` | Delegated, using Codex's file-defined sub-agents in `~/.codex/agents/`; sequential if they can't start | No slash commands: ask for what you want and the matching `steno-*` skill (in `~/.agents/skills/`) applies. Start setup with the form command |
| [Gemini CLI](https://github.com/google-gemini/gemini-cli) | `python3 scripts/sync_pipeline.py --global --target gemini` | Delegated, using Gemini's sub-agents in `~/.gemini/agents/`; sequential if they can't start | No slash commands: the `steno-*` skills in `~/.gemini/skills/` apply instead. Start setup with the form command |

In **sequential** mode, the fallback for a tool that can't start sub-agents, the main session runs each stage itself from the same stage files, with the same checks. The one difference is Stage 5: the session that wrote the draft also reviews it, so the scorecard marks that review "(not independent)". `/test-pipeline --compare-modes` checks that the two modes score the same on your past meetings.

Each project's instruction file is `AGENTS.md`, which all three tools read: Codex directly, Claude Code and Gemini CLI through the `CLAUDE.md` and `GEMINI.md` stubs beside it. A project set up before AGENTS.md keeps working from its `CLAUDE.md`.

### The first-run form

| | |
|---|---|
| Opens | When you run `python3 scripts/generate_setup_form.py`, in any tool. Claude Code also opens it automatically on the first session after you clone |
| Fires again (Claude Code) | Only if you delete `.steno/setup-state.json` (or `.claude/.setup-state.json` in a clone set up before that path), or run `/setup-pipeline` by hand |
| Skip the hook | `MNP_SKIP_FIRST_RUN=1` |
| Hook wired in | `.claude/settings.json` → `SessionStart` → `scripts/first_run_check.py` |
| Form source | `assets/setup-form.html`, rendered to a gitignored `setup-session.html` |

The generated form is fully self-contained — no network, no CDN, works offline. Nothing is written to your project until you paste the block back into your agent, so you can close the tab and walk away at any point.

Setting up a second project later does not use the hook — run the form command (or `/setup-pipeline` in Claude Code) and the same form opens.

---

## Repository structure

```
steno/
├── assets/
│   └── setup-form.html    ← the first-run setup form
├── scripts/
│   ├── generate_setup_form.py   ← renders + opens the form
│   ├── first_run_check.py       ← SessionStart hook: fires the form once per clone
│   └── sync_pipeline.py         ← installs/updates agents, commands and skill scripts
├── AGENTS.md              ← instructions for an agent working in this repo (CLAUDE.md, GEMINI.md import it)
├── projects.txt           ← your installed projects; created by /setup-pipeline, gitignored
├── tests/                 ← plain python, no framework: python3 tests/<file>.py
│   ├── test_check_draft.py      ← the draft checker, one case per rule
│   ├── test_sync_pipeline.py    ← the installer and updater, for every target tool
│   ├── test_project_file.py     ← AGENTS.md / CLAUDE.md lookup in the renderer
│   └── test_first_run.py        ← the setup form command, hook and marker
├── global/
│   ├── commands/          ← Claude Code slash commands; every tool also gets a steno-<command> skill built from each
│   │   ├── process-notes.md
│   │   ├── learn.md
│   │   ├── apply-learning.md
│   │   ├── test-pipeline.md
│   │   ├── sync-pipeline.md
│   │   ├── audit.md
│   │   ├── status.md
│   │   └── setup-pipeline.md
│   └── agents/            ← the stage files: sub-agents for each tool (Codex gets them as TOML)
│       ├── formatter.md
│       ├── editorial-qa.md
│       ├── discipline-checker.md
│       ├── supervisor-alignment.md
│       ├── draft-reviewer.md
│       ├── docx-renderer.md
│       └── learning-reviewer.md
└── project-template/      ← copied and renamed per project
    ├── AGENTS.md          ← the project file: roster, organisations, file locations
    ├── CLAUDE.md, GEMINI.md  ← stubs that import AGENTS.md
    └── Meeting Notes/
        ├── supervisor-style-guide-[PROJECT].md
        ├── pipeline-memory-[PROJECT].md     ← open patterns, open decisions, run log
        ├── pipeline-scorecard-[PROJECT].md  ← numbers only, survives cleanup
        ├── meeting-notes-formatter-skill-[PROJECT].md
        ├── skills/
        │   ├── style-rules/
        │   ├── hard-rules/
        │   ├── humanizer/      ← vendored blader/humanizer + project scoping layer
        │   ├── draft-checks/   ← the format contract, check_draft.py, score_draft.py
        │   ├── pipeline-cleanup/
        │   ├── learning-form/  ← the /learn review page and generate_qa_form.py
        │   └── docx-renderer/
        └── transcripts/ output/ intake/ working/ Archive/
```

---

## The document template

During setup you hand the pipeline one branded `.docx` — any past set of meeting notes or a
letterhead. From it, `/setup-pipeline` builds two things: a blank template carrying your
headers, footers and logo, and three reference files describing the exact XML your documents
use (column widths, fonts, numbering IDs, brand colour, tab stops).

**This happens once.** When setup finishes it writes
`Meeting Notes/skills/docx-renderer/references/.rendered.json`. Every later run — a second
`/setup-pipeline`, every `/process-notes`, anything else in the pipeline — sees that marker
and leaves all four files alone. `/process-notes` only ever reads them.

So once you are set up, those files are yours:

- **Change something** — edit the file in `references/` directly. Your edit is permanent.
- **Start over from a different `.docx`** — re-run setup with `--force`. This replaces hand
  edits and re-derives everything, after copying the old files into
  `Meeting Notes/.setup-backup-<stamp>/`.

The reference prose lives in `skills/docx-renderer/templates/` as `{{token}}` templates.
Setup substitutes your project's extracted values into them. Editing a template changes what
*future* projects get; editing a file in `references/` changes this project.

---

## Per-project setup (after install)

The installer scaffolds your project folder with placeholder content. Before running `/process-notes` for the first time, fill in:

1. **`skills/style-rules/`** — your document style: tone, Status definitions, scope discipline, and in `references/` the section structure, date format and typographic conventions. This is the most important folder. Base it on a few past meeting notes you're happy with. What an Action or Status cell may hold is fixed in `skills/draft-checks/references/draft-format.md`; point to it rather than restating it.

2. **`meeting-notes-formatter-skill-[PROJECT].md`** — optional Stage 1 drafting notes that belong in no other file. Most projects leave it empty.

3. **`skills/hard-rules/`** — non-negotiable rules: attribution, data isolation, output format. Add project-specific technical terminology to `references/terminology.md`.

   `skills/humanizer/` needs no setup. It ships complete and is project-independent.

4. **`supervisor-style-guide-[PROJECT].md`** — leave blank to start. It fills in automatically as you run `/learn` cycles. You can seed it manually with known preferences.

The pipeline's `supervisor-alignment` agent applies seeded preferences immediately, and holds recurring corrections back until the threshold in AGENTS.md is reached (default: 3) — so there's no pressure to pre-fill it.

---

## The six-stage pipeline

| Stage | Agent or check | Job |
|---|---|---|
| 1 | `formatter` | Raw transcript → structured first draft, plus an item ledger quoting the transcript line behind every item, tagged with the speaker's organisation |
| 2 | `editorial-qa` | Sharpen draft — remove filler, tighten wording, reorder by priority, then strip AI-writing tells |
| 2.5 | `check_draft.py` | Mechanical check: format, Status values, Action organisations, placeholders, relative dates, numbering, speaker attribution |
| 3 | `discipline-checker` | Judgement calls on attribution the script cannot decide |
| 4 | `supervisor-alignment` | Apply documented supervisor preferences |
| 4.5 | `check_draft.py` | The same check again — Stage 4 is the last stage that edits text, and nothing else re-validates it. Blocking, max 2 repair attempts |
| 5 | `draft-reviewer` | A fresh agent (in delegated mode) grades the draft against the transcript and the ledger: invented content, dropped actions, lost rationale, scope, status. Never edits |
| 6 | `docx-renderer` | Render the final markdown to a formatted .docx with `render.py`. A draft fault (named by its draft line) goes back to Stage 1, or Stage 4 if a later stage introduced it, then 4.5, 5 and 6 run again: max 2 repair attempts. A template, constants or install fault stops with the fix. Never a hand-written XML fallback |

Stages 1 to 5 write their draft to `working/runs/<transcript stem>/`, one folder per meeting, so `/learn` can tell which stage introduced a correction. A meeting can be processed before the previous one's `/learn`: the cleanup script takes `--stem` and deletes only that meeting's run folder, transcript and draft.

---

## Humanizer

Stage 2 runs a second pass over the sharpened draft that removes signs of AI-generated
writing — inflated significance, promotional wording, `-ing` padding, AI vocabulary,
copula avoidance, filler, and chatbot artifacts.

It is vendored, not installed as a dependency. The upstream pattern list from
[blader/humanizer](https://github.com/blader/humanizer) (MIT) sits verbatim in
`skills/humanizer/vendor/`. Stage 2 loads a copy in `skills/humanizer/references/` with the
switched-off sections removed, and `skills/humanizer/SKILL.md` is the project-owned layer
that decides how it behaves in formal minutes:

- **Personality and voice-matching are off.** Minutes are reference documents. Flat and
  neutral is the target, not a defect to fix.
- **7 patterns are suppressed** because they fight the document format — boldface, inline-header
  lists, heading case, curly quotes, hyphenation, fragmented headers, and diff-anchored
  writing all belong to `typography.md` and `structure.md`.
- **6 patterns are constrained.** The em dash rule stops at prose and never touches date,
  time, or reference-number ranges. The passive-voice rule can never re-introduce a person
  as the actor, because the speaker-attribution hard rule outranks it. Rule-of-three never
  deletes a real item to break up a group of three.
- **Hard rules always win.** Where upstream says "name a real source", the pipeline cuts the
  claim or marks it `[not provided]`. Nothing enters the draft that is not in the transcript.

It runs at Stage 2 and nowhere else, so `discipline-checker` re-validates every attribution
afterwards and `supervisor-alignment` gets the last word on style. Both act as guardrails on
anything the rewrite breaks.

To update the vendored copy, drop the newer upstream `SKILL.md` into
`skills/humanizer/vendor/` with its version in the filename, reconcile any new pattern
numbers against the tables in `skills/humanizer/SKILL.md`, bump `metadata.upstream`, then
re-derive the `references/` copy as that file's "Updating the vendored copy" says.
`/status` reports the vendored version.

---

## Adapting to your style

The pipeline ships with a neutral, formal-professional style profile. It is not pre-configured for any particular industry, organisation, or document format.

Your style profile lives in `skills/style-rules/` (SKILL.md and its `references/`). Edit it to match however your organisation formats its meeting notes — table structure, header layout, date conventions, wording register, whatever is standard for your context.

The skill files in `skills/` let you separate what is a hard rule (never violated) from what is a preference (applied when the supervisor guide is populated).

---

## Multiple projects

Each project gets its own copy of the project-template folder with its own roster, style guide, and memory log. The global commands and agents are shared across all projects. Running `/process-notes` in a project folder automatically uses that project's AGENTS.md, skill files, and style guide.

Because the agents and `check_draft.py` are shared, a fix learned on one project changes every project. `projects.txt` lists every installed project. `/apply-learning` only proposes an AGENT or CHECK change: it is written after you say yes, committed only if the repo tests pass, and synced only after `/test-pipeline` passes on every listed project. `sync_pipeline.py --all-projects` syncs them all in one run. `/setup-pipeline` adds each new project to `projects.txt` (once, even after `--reinit`).
