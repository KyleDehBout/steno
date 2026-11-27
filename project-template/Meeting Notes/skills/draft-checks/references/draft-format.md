# Draft format contract

Every draft passed between Stages 1 and 6 uses the format below. It is a contract, not a
suggestion: `check_draft.py` parses it, and a draft it cannot parse fails the pipeline
before anything is rendered.

The format exists because Stages 1–4 used to exchange free-form text. Nothing could be
checked mechanically, so rules that were already written down were missed silently and
only caught weeks later by the supervisor.

## Shape

```
TITLE: Harbour Point – Project Meeting
HELD ON: Thursday July 16, 2026
TIME: 4:00PM
MEETING NO: 15

ATTENDEES:
Sam Carter<TAB>NOVA<TAB>Project Manager
Morgan Hughes<TAB>Brook Systems<TAB>Hydrologist

## 1. Stormwater and Drainage
### 1.1 Cross-Section Graphic
1.1.1 | A cross-section graphic is to be prepared for the retention area. | Brook Systems | Pending
1.1.2 | The invert level was confirmed at 12.4m. |  | No Action
- Supporting detail that belongs to 1.1.2 and carries no Action or Status.
- The level survey is to be checked against the confirmed invert. | Caldwell Surveying | Pending

## 2. Electrical
### 2.1 Panel Schedule
2.1.1 | Panel schedule to be reissued. | BTR | In Progress

MEETINGS: Next meeting date: July 23, 2026 4:00PM

Prepared by: NOVA Limited
```

## Rules

1. **Header block** — four `KEY: value` lines in this order: `TITLE`, `HELD ON`, `TIME`,
   `MEETING NO`. `MEETING NO` may be `[not provided]`. `TIME` may be only when AGENTS.md
   has no "Recurring meeting time" line. `TITLE` and `HELD ON` never may.
2. **`HELD ON`** — `Thursday July 16, 2026`. No comma after the day name, no ordinal
   suffix. The day name must match the calendar date.
3. **`TIME`** — `4:00PM`. No space before the meridiem.
4. **`ATTENDEES:`** — one person per line, three tab-separated fields:
   Name, Organisation, Title. No field may be empty or `[not provided]`.
5. **Sections** — `## N. Title`, numbered from 1 with no gaps.
6. **Subsections** — `### N.M Label`, numbered from 1 within their section. Required:
   every sub-item needs one above it.
7. **Sub-items** — `N.M.K | text | Action | Status`. The Action and Status cells may be
   empty, but the two pipes are always present. This rule is the one home of both
   cells' permitted values; other files point here rather than restate them:
   - **Action** — organisation names only, each spelled as in AGENTS.md "Organisation
     names". Never a person's name or initials. Two or more organisations sharing an
     action are joined by `/` with no spaces (`Org A/Org B`). When to name a second
     organisation is the project's rule, in its hard rules or supervisor style guide.
   - **Status** — exactly one of `In Progress`, `Pending`, `No Action`, `Completed`.
     Never `Outstanding` or any other word, whatever a wording preference says.
     `Completed` only where the transcript says the work is done, never for work that
     is only expected, scheduled or nearly finished. When to use each
     value is defined in the project's style rules.

   An informational item takes Status
   `No Action` with the Action left empty (1.1.2 above). `N.M` must match a subsection heading —
   a sub-item with no subsection renders with a zero in the middle ("3.0.1"), because
   the renderer has no level-1 paragraph to hang it from.
8. **Bullets** — a line starting with `- ` attaches to the sub-item above it, and never
   appears below the `MEETINGS:` line. A plain bullet (supporting detail) carries no
   cells. A follow-up action that depends on the sub-item above may carry its own
   ` | Action | Status`, written exactly like a sub-item's: `- text | Action | Status`.
   The renderer puts that owner and status level with the bullet, as the supervisor
   does in issued notes. Once a bullet has cells, both are needed: the Status always,
   and the Action unless the Status is `No Action`.
9. **A literal `|` inside text** is written `\|`.
10. **`MEETINGS:`** — one line, after the last section, reading exactly
    `Next meeting date: <Month D, YYYY> <H:MMAM|PM>`. Joining the date and time with
    "and" (`Next meeting date: July 23, 2026 and 4:00PM`) is equally valid: issued notes
    use both, and the project's structure reference says which one it prefers. No day
    name, no ordinal, no other words. Never the words "Next meeting will be held".
11. **`Prepared by: <Organisation> Limited`** — the final line of the document.
12. **Pipeline notes** — an agent's notes (EDITORIAL NOTE, DISCIPLINE NOTE, SUPERVISOR
    NOTE and the like) go after a line reading exactly `---PIPELINE NOTES---`, below the
    document and any `LEDGER:` block. The checker stops reading there, so a note may run to
    several lines or a list. A bare `X NOTE:` line without the sentinel is still skipped,
    but a bullet under it is an error.

## What the checker enforces beyond the shape

Run `python3 check_draft.py <draft> --agents-md <path to AGENTS.md>`. It reads the roster
and the permitted organisation list from AGENTS.md, so it never carries names of its own.

Errors (exit 1):

- A Status value outside the rule 7 set, including the literal `Outstanding`.
- An Action value that is not an organisation name from AGENTS.md, or that names a
  person from the roster (rule 7). Case is not an error: `Horizon` for `HORIZON` is a warning, and
  the AGENTS.md spelling stays the one to use.
- A sub-item with empty text, a section or subsection with no sub-items, a bullet below
  the `MEETINGS:` line or under a NOTE line, and a `MEETING NO` that is neither a number
  nor `[not provided]`.
- A bullet with malformed cells: one cell or more than two, no Status, an empty Action
  with any Status but `No Action`, or no text. A bullet's Action and Status are
  otherwise checked exactly like a sub-item's.
- `[not provided]` in the title block, an attendee row, or the Meetings line.
- A relative deadline in sub-item text — "next week", "end of the week", "end of the
  month", "within two weeks", "in a couple of weeks", or a bare day name in an item that carries no calendar date and is not a span like "Monday to Friday".
- A Meetings line not in the rule 10 shape: a missing or malformed time, a malformed
  date, or any extra words.
- A next-meeting date that falls on the wrong day. The day and the interval come from
  the "Recurring meeting day" and "Recurring meeting interval (days)" keys in AGENTS.md;
  leave a key out and that check does not run.
- Speaker attribution: "he said", "she noted", "<roster name> confirmed", including a
  roster first name or surname alone ("Sam confirmed").
- Section, subsection or sub-item numbering that is out of sequence.
- A date in the header block that does not match its stated day name.

Warnings (exit 0, reported):

- A sub-item with no Action or no Status.
- An attendee who is not on the AGENTS.md roster.
- An Action or attendee organisation that differs from AGENTS.md only in case.
- A next-meeting date on the right day but not exactly one interval after this meeting.
- An XML entity such as `&amp;` in text. Drafts carry raw text (`T&T`); the renderer
  escapes it, so a pre-escaped entity would print literally.
- A phrase the supervisor style guide bans. Only its "Wording preferences" lines written
  `- Say "X" not "Y"` or `- Never use "Y"` are read, from the "Supervisor style guide"
  path in AGENTS.md; the warning names the phrase to use. Stage 4 owns the rewrite.

## Why these and not others

Every error above is a rule the pipeline has already broken in production at least once.
When the supervisor corrects the same class of thing twice, the fix is a new check here,
not another sentence in a skill file — a script applies a rule the same way on every run.
