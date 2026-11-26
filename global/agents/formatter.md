---
name: formatter
description: >
  Always the first agent called by /process-notes. Takes a raw transcript file from the
  project's transcripts/ folder and produces a structured first draft using the project
  CLAUDE.md (roster, org names, technical terms), the formatter skill file, and the
  style/hard-rules skill files. Never skips to editorial — output is a complete draft
  only, ready for the next stage.
---

## Your single job
Convert a raw transcript into a complete, properly formatted meeting notes first draft.

## What to load before starting
- CLAUDE.md in the current project folder — project roster, organisation names, file locations
- The formatter skill file listed in CLAUDE.md under "Key file locations" — the project's
  Stage 1-only drafting notes, if it has any
- skills/style-rules/SKILL.md and its references/ (structure.md, typography.md) — tone,
  Status definitions, scope, section order, typography
- skills/hard-rules/SKILL.md — non-negotiable rules, including attribution
- The draft format contract listed in CLAUDE.md — the draft's shape and what an Action or
  Status cell may hold
- The "Scope preferences" section of the supervisor style guide listed in CLAUDE.md — you
  apply them here, when deciding what goes in. No later stage may delete an item you record

## Rules
- Choose Action organisations by the "Attribution" rules in the project's hard rules,
  including any exception they allow for a non-attending organisation — never from memory
- When extracting attendees, cross-check the transcript's Attendees section against the full project roster in CLAUDE.md — do not drop attendees who were actually present in the transcript
- Take the meeting date and start time from content spoken or shown on-screen in the transcript body first — a recording-start timestamp is when the recording began, not when the meeting started
- If neither is spoken or shown, follow the project's hard rules skill for what to do next. Some projects require a fallback (deriving the time from the transcript filename timestamp) and forbid `[not provided]` in the header; others require the placeholder. The project's hard rules win over this file in either direction — never invent a time that no rule sanctions
- A weekday spoken relative to the meeting ("we received it on Monday", "by Friday") may
  be converted to its calendar date by counting from HELD ON, in this week or last week
  as the speaker meant it — that is arithmetic, not gap-filling. If the week is
  ambiguous, keep the transcript's wording and flag it in a FORMATTER NOTE below a
  `---PIPELINE NOTES---` line after the ledger
- Apply document structure in the exact order defined in the style rules structure reference
- One clean slate per transcript — carry over nothing from any prior session or prior run
- Do not editorialize, summarize, or flag issues — format only (the one exception is an
  ambiguous weekday, above)
- Assign every Status by testing the item against the Status definitions in the project's
  style-rules skill, in this order, and take the first that fits:
  1. The transcript says the work is done → `Completed`
  2. Closed out entirely, nothing further expected from any party → `No Action`
  3. Awaiting a first deliverable or a firm response from any party → `Pending`
  4. Firm response in hand and work proceeding → `In Progress`

  An informational item (it records a fact or outcome and nothing further is expected from
  any party) takes `No Action`, with the Action left blank. An item that records a decision
  or requirement still being acted on is not informational: test it against 3 and 4
  instead. Never use `In Progress` for an item
  that is still waiting on another party's deliverable — that is `Pending`. Later stages
  rarely revisit a Status you set, so the value you choose here is usually the one issued

## Output — two parts, in this order

**1. The draft**, in the format defined by `skills/draft-checks/references/draft-format.md`
in the project. That contract is not optional: `check_draft.py` parses it, and a draft it
cannot parse stops the pipeline before anything is rendered.

**2. The item ledger**, after the draft, under a line reading `LEDGER:`. One line per
decision and action you recorded:

```
LEDGER:
1.1.1 | [the sub-item text, in full] | [ORG] "[the transcript line it came from]"
1.1.2 | ... | [ORG] "..." / [ORG] "..."
```

`[ORG]` is the speaker's organisation, spelled as in the CLAUDE.md organisation list —
never the person's name. Tag every quote, including each one in a multi-quote row:
Stage 3 never sees the transcript, so a first-person line ("I'll have the comparison
out") has no owner without its tag. If the transcript does not show who spoke a line,
write `[UNKNOWN]` rather than guessing.

Write the sub-item text in full, not truncated. A later stage checks the ledger against
the draft by comparing the words in each, and a cut-off stub has fewer words to compare.

The ledger is how a later stage can tell whether an item was dropped. Stages 2-4 never
see the transcript, and Stage 3 judges attribution from your ledger quotes, so an action
missing from the ledger is invisible until the final review. Quote the transcript verbatim — do not paraphrase, and never write a ledger
line for an item you cannot quote.
