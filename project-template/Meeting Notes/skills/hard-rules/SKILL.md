---
name: hard-rules
description: >
  Absolute rules that must never be violated at any stage of the Steno pipeline.
  Covers data isolation between sessions, attribution rules, speaker attribution prohibition,
  content discipline, and output format. Load references/terminology.md when processing
  any item involving technical or industry-specific terms.
compatibility: Designed for use with the Steno pipeline
metadata:
  version: "1.0"
allowed-tools: Read
---

## Data isolation — non-negotiable
- NEVER carry over any content, names, dates, decisions, or action items from a previous session
- Each transcript is a clean slate — treat it as the first document ever seen
- If information is missing from the current transcript, mark as `[not provided]` or omit —
  except the header start time: if none is spoken or shown, write CLAUDE.md "Recurring meeting
  time". `[not provided]` is only for the header time when that line is absent too
- Never fill gaps using memory, inference, or prior uploads
- When in doubt, omit

## Attribution — non-negotiable
- What an Action cell may hold (organisations only, never a person): draft-format.md rule 7
- ONLY use organisation names sourced from the Attendees list in the current transcript
- NEVER use organisation names from memory, prior sessions, or this skill file

## Speaker attribution — non-negotiable
- NEVER write "he said", "she said", "[Name] said", or any variant
- NEVER attribute outcomes to speakers
- Report decisions and actions in neutral third-person only

## Content discipline — non-negotiable
- NEVER add summaries, overviews, or closing remarks not in the source transcript
- NEVER correct or second-guess technical information — transcribe as given
- NEVER add agenda items, context, or background not in the raw source
- NEVER invent or infer anything not explicitly in the transcript
- A weekday spoken relative to the meeting date ("we received it on Monday") may be converted
  to its calendar date by arithmetic from HELD ON — this week or last week, as the speaker
  meant it. That is not gap-filling or inference. If the week is ambiguous, keep the
  transcript's wording and flag it

## Output format — non-negotiable
- Default output is always a .docx file
- Never produce plain text output unless explicitly requested by the user

## Technical terms
See [terminology reference](references/terminology.md) for project-specific terms that
must be preserved exactly as written.
