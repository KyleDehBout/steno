#!/usr/bin/env python3
"""Validate a meeting-notes markdown draft before it is rendered to .docx.

Usage: check_draft.py <draft.md> [--agents-md <path>] [--ledger <path>] [--json <path>]
                      [--scorecard <path> --stage 2|4 [--run-date YYYY-MM-DD]] [--quiet]

The draft format is documented in ../references/draft-format.md. The project roster,
permitted organisation names and the recurring meeting day are read from the project
instruction file (AGENTS.md, or CLAUDE.md in a project set up before AGENTS.md existed),
so this script carries no project data of its own — a rule it cannot source from the
project is a rule it does not enforce.

Every error below is a rule the pipeline has already broken in production. A script
applies a rule the same way on every run; a sentence in a skill file does not.

Exit codes: 0 = no errors (warnings may be present), 1 = errors found, 2 = bad usage.
"""
import argparse
import datetime
import difflib
import json
import re
import sys
from pathlib import Path

STATUSES = ("In Progress", "Pending", "No Action", "Completed")
PLACEHOLDER = "[not provided]"

MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# Agents append their note after the draft, and supervisor-alignment emits it as a
# markdown blockquote. A note the parser fails to recognise lands in the catch-all and
# fails the run over a line that is not part of the document at all.
NOTE_RE = re.compile(
    r'^>?\s*(EDITORIAL|HUMANIZER|DISCIPLINE|SUPERVISOR|REVIEW|CHECK) NOTE:')
# Agents put their notes below this line, so a note of any shape — several lines, a
# list of changes — is never read as document content. Parsing stops here.
NOTES_SENTINEL = "---PIPELINE NOTES---"
# The ledger is a block, not a line: its rows look like sub-items and would otherwise be
# parsed as document content. Parsing stops there — and says so, rather than reporting
# the missing sections that stopping causes.
LEDGER_RE = re.compile(r'^>?\s*LEDGER:')
# The speaker tag before each ledger quote: `[HORIZON] "..." / [Brook Systems] "..."`.
LEDGER_SPEAKER_RE = re.compile(r'\[[^\]"]*\]\s*(?=")')
SECTION_RE = re.compile(r'^##\s+(\d+)\.\s+(.+?)\s*$')
SUBSECTION_RE = re.compile(r'^###\s+(\d+)\.(\d+)\s+(.+?)\s*$')
ITEM_RE = re.compile(r'^(\d+)\.(\d+)\.(\d+)\s*\|(.*)$')
BULLET_RE = re.compile(r'^-\s+(.+?)\s*$')
HEADER_RE = re.compile(r'^(TITLE|HELD ON|TIME|MEETING NO):\s*(.*?)\s*$')
LONG_DATE_RE = re.compile(r'^([A-Za-z]+)\s+([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$')
DATE_IN_TEXT_RE = re.compile(r'\b([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})\b')
TIME_RE = re.compile(r'^\d{1,2}:\d{2}(AM|PM)$')
# Issued notes write the Meetings row both ways: "July 23, 2026 and 4:00PM" (Style B #9)
# and "July 23, 2026 4:00PM" (Style B #10). Anything else is a malformed row.
MEETINGS_SHAPE_RE = re.compile(
    r'^Next meeting date: [A-Za-z]+ \d{1,2}, \d{4}(?: and)? '
    r'(?:[1-9]|1[0-2]):[0-5]\d(?:AM|PM)$')
ORDINAL_RE = re.compile(r'\b\d{1,2}(st|nd|rd|th)\b')
# validate.py's typed-number pattern, kept identical (a test compares the two). Text
# that opens with a number of its own list depth fails validate.py, and repair.py
# never strips it: the number may be content ("4.2.1 of the spec requires...").
LEADING_NUMBER_RE = re.compile(r'^(\d+(?:\.\d+)+\.?|\d+\.)\s')
# Characters XML 1.0 forbids. build_body_xml.py imports this and illegal_characters(),
# so the renderer's Step 3 and this check apply one rule.
XML_ILLEGAL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff\ud800-\udfff]')

RELATIVE_PHRASES = (
    "next week", "early next week", "late next week", "end of the week",
    "later this week", "this week", "next month", "tomorrow", "yesterday",
    "in a few days", "over the weekend", "by the weekend", "end of next week",
    "end of the month", "end of this month", "end of month", "end of next month",
)
# "within two weeks", "in a couple of weeks", "within 10 days": a span counted from the
# meeting is as relative as "next week", and just as unreadable a month later.
RELATIVE_SPAN_RE = re.compile(
    r'\b(within|in) (the next )?(a|an|one|two|three|four|five|six|a couple of|a few|\d+) '
    r'(days?|weeks?|months?|fortnights?)\b')
SPEAKER_VERBS = ("said", "noted", "stated", "confirmed", "advised", "indicated",
                 "mentioned", "explained", "asked")
PRONOUN_SPEAKER_RE = re.compile(
    r'\b(he|she|they)\s+(%s)\b' % "|".join(SPEAKER_VERBS), re.IGNORECASE)


class Finding:
    def __init__(self, level, code, line, message):
        self.level = level
        self.code = code
        self.line = line
        self.message = message

    def as_dict(self):
        return {"level": self.level, "code": self.code,
                "line": self.line, "message": self.message}

    def __str__(self):
        where = "line %d" % self.line if self.line else "-"
        return "%-5s [%s] %s: %s" % (self.level, self.code, where, self.message)


# ------------------------------------------------- project instruction file

# The file that holds the roster, organisations and project keys. AGENTS.md is the
# neutral name every agent tool reads; CLAUDE.md is where projects set up before it
# keep them. At one folder level AGENTS.md wins, so a CLAUDE.md stub beside it that
# only points to AGENTS.md is never read as the project's data.
INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md")

# The name of the file the current run read, so a message names the file the user
# has to open. read_project_file sets it.
SOURCE_NAME = INSTRUCTION_FILES[0]


def find_project_file(start):
    """Walk up from the draft to the nearest folder holding a project instruction file."""
    for parent in [start.resolve()] + list(start.resolve().parents):
        for name in INSTRUCTION_FILES:
            candidate = parent / name
            if candidate.is_file():
                return candidate
    return None


find_claude_md = find_project_file  # the name before AGENTS.md; kept for callers


def read_project_file(path):
    """Extract roster, permitted orgs and optional project keys.

    Returns a dict. Missing sections come back empty rather than raising: the checks
    that need them are skipped and reported, so a half-filled project still runs.
    """
    global SOURCE_NAME
    SOURCE_NAME = path.name
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    roster = []
    orgs = []
    keys = {}

    in_roster = False
    for i, raw in enumerate(lines):
        line = raw.strip()

        if line.startswith("## Project roster"):
            in_roster = True
            continue
        if in_roster:
            # A new heading ends the roster, then falls through to be matched below —
            # the organisation list heading comes straight after the roster table.
            if line.startswith("##"):
                in_roster = False
            else:
                if line.startswith("|"):
                    cells = [c.strip() for c in line.strip("|").split("|")]
                    if len(cells) >= 3 and not set("".join(cells)) <= set("-: "):
                        if cells[0].lower() != "name":
                            roster.append({"name": cells[0], "org": cells[1],
                                           "title": cells[2]})
                continue

        if line.startswith("## Organisation names"):
            for follow in lines[i + 1:]:
                stripped = follow.strip()
                if not stripped or stripped.startswith("<!--"):
                    continue
                if stripped.startswith("#"):
                    break
                orgs = [o.strip() for o in stripped.split(",") if o.strip()]
                break
            continue

        match = re.match(r'^-\s*([A-Za-z][A-Za-z /()]+):\s*(.+?)\s*$', line)
        if match:
            keys[match.group(1).strip().lower()] = match.group(2).strip()

    return {"roster": roster, "orgs": orgs, "keys": keys, "path": path}


# ------------------------------------------------------------------ parsing


read_claude_md = read_project_file  # the name before AGENTS.md; kept for callers

def parse_draft(text):
    """Parse the draft into a structure. Returns (draft, findings)."""
    findings = []
    draft = {"header": {}, "header_lines": {}, "attendees": [], "sections": [],
             "meetings": None, "meetings_line": 0, "prepared": None,
             "prepared_line": 0}

    lines = [l.rstrip("\n") for l in text.splitlines()]
    state = "header"
    section = None
    item = None
    ledger_at = None
    content_after_ledger = False
    after_note = False

    for number, raw in enumerate(lines, start=1):
        line = raw.strip()

        if line == NOTES_SENTINEL:
            break
        if LEDGER_RE.match(line):
            ledger_at = number
            state = "ledger"
            continue
        if state == "ledger":
            # A blank line is formatting, not content. Testing for a ledger row before
            # skipping blanks meant one trailing newline after the ledger marked the
            # block misplaced, and a well-formed draft failed the gate over whitespace.
            if not line:
                continue
            # Ledger rows are expected here. Anything else means document content sits
            # below the ledger and was never checked — that, not the mere presence of a
            # ledger, is what makes the block misplaced.
            if not re.match(r'^\d+\.\d+\.\d+\s*\|', line) and not NOTE_RE.match(line):
                content_after_ledger = True
            continue
        # A note line is skipped on its own. Latching here instead would mean one
        # stray note in the middle of a draft silently disables every check below it.
        if NOTE_RE.match(line):
            after_note = True
            continue
        if not line:
            continue
        under_note, after_note = after_note, False

        header_match = HEADER_RE.match(line)
        if header_match and state in ("header", "attendees"):
            draft["header"][header_match.group(1)] = header_match.group(2)
            draft["header_lines"][header_match.group(1)] = number
            continue

        if line.upper().startswith("ATTENDEES:"):
            state = "attendees"
            continue

        if line.startswith("MEETINGS:"):
            draft["meetings"] = line[len("MEETINGS:"):].strip()
            draft["meetings_line"] = number
            state = "tail"
            continue

        if line.startswith("Prepared by:"):
            draft["prepared"] = line
            draft["prepared_line"] = number
            state = "tail"
            continue

        section_match = SECTION_RE.match(line)
        if section_match:
            section = {"num": int(section_match.group(1)),
                       "title": section_match.group(2),
                       "line": number, "subsections": [], "items": []}
            draft["sections"].append(section)
            item = None
            state = "body"
            continue

        subsection_match = SUBSECTION_RE.match(line)
        if subsection_match:
            if section is None:
                findings.append(Finding("ERROR", "FORMAT", number,
                                        "subsection before any section heading"))
                continue
            section["subsections"].append({
                "num": (int(subsection_match.group(1)), int(subsection_match.group(2))),
                "label": subsection_match.group(3), "line": number})
            item = None
            continue

        item_match = ITEM_RE.match(line)
        if item_match:
            if section is None:
                findings.append(Finding("ERROR", "FORMAT", number,
                                        "sub-item before any section heading"))
                continue
            rest = item_match.group(4)
            parts = re.split(r'(?<!\\)\|', rest)
            if len(parts) != 3:
                findings.append(Finding(
                    "ERROR", "FORMAT", number,
                    "sub-item needs exactly 3 pipes: 'N.M.K | text | Action | Status' "
                    "(escape a literal pipe as \\|)"))
                section["unparsed"] = True
                continue
            item = {"num": (int(item_match.group(1)), int(item_match.group(2)),
                            int(item_match.group(3))),
                    "text": parts[0].strip().replace("\\|", "|"),
                    "action": parts[1].strip(),
                    "status": parts[2].strip(),
                    "line": number, "bullets": []}
            section["items"].append(item)
            continue

        bullet_match = BULLET_RE.match(line)
        if bullet_match:
            # A note's own list would otherwise attach to the last sub-item as a bullet
            # and be rendered into the issued document.
            if state == "tail" or under_note:
                findings.append(Finding(
                    "ERROR", "FORMAT", number,
                    "bullet %s — pipeline notes belong after a '%s' line"
                    % ("below the MEETINGS line" if state == "tail"
                       else "directly under a NOTE line", NOTES_SENTINEL)))
                continue
            if item is None:
                findings.append(Finding("ERROR", "FORMAT", number,
                                        "bullet with no sub-item above it"))
                continue
            # A dependent follow-up nested under its sub-item may carry its own Action
            # and Status, written like a sub-item's: "- text | Action | Status".
            parts = re.split(r'(?<!\\)\|', bullet_match.group(1))
            if len(parts) not in (1, 3):
                findings.append(Finding(
                    "ERROR", "BULLET_CELLS", number,
                    "bullet with cells needs exactly 2 pipes: '- text | Action | Status' "
                    "(escape a literal pipe as \\|)"))
                continue
            bullet = {"text": parts[0].strip().replace("\\|", "|"), "line": number,
                      "cells": len(parts) == 3, "action": "", "status": ""}
            if bullet["cells"]:
                bullet["action"] = parts[1].strip()
                bullet["status"] = parts[2].strip()
            item["bullets"].append(bullet)
            continue

        if state == "attendees":
            # Tabs are the contract, but a draft is generated text passed between six
            # agents and tabs do not always survive. Two or more spaces, or a pipe,
            # separate the three fields just as unambiguously.
            if "\t" in raw:
                fields = raw.split("\t")
            else:
                fields = re.split(r'\s*\|\s*|\s{2,}', line)
            draft["attendees"].append({
                "fields": [f.strip() for f in fields], "line": number, "raw": line})
            continue

        if section is not None:
            section["unparsed"] = True
        findings.append(Finding(
            "ERROR", "FORMAT", number,
            "line does not match the draft format: %r" % line[:60]))

    # The symptoms this causes — a missing Meetings row, a missing prepared-by line —
    # are raised later by run_checks, so they are suppressed there, not here. The flag
    # is set only when the ledger really did cut the document short: a correctly placed
    # trailing ledger beside a genuinely missing Meetings row must report the missing
    # row, not blame the ledger.
    draft["ledger_at"] = ledger_at if content_after_ledger else None
    if content_after_ledger:
        findings.append(Finding(
            "ERROR", "LEDGER_POSITION", ledger_at,
            "the LEDGER: block starts here, before the end of the document — "
            "everything below it was not checked, including the Meetings row and the "
            "prepared-by line. The ledger belongs after the 'Prepared by:' line"))

    return draft, findings


# ------------------------------------------------------------------- checks

def parse_long_date(value):
    """'Thursday July 16, 2026' -> (dayname, date) or (None, None)."""
    match = LONG_DATE_RE.match(value)
    if not match:
        return None, None
    dayname, month, day, year = match.groups()
    if month not in MONTHS or dayname not in DAYS:
        return None, None
    try:
        return dayname, datetime.date(int(year), MONTHS.index(month) + 1, int(day))
    except ValueError:
        return None, None


def check_header(draft, project, findings):
    header = draft["header"]
    lines = draft["header_lines"]

    for key in ("TITLE", "HELD ON", "TIME", "MEETING NO"):
        if key not in header:
            findings.append(Finding("ERROR", "FORMAT", 0,
                                    "header block is missing '%s:'" % key))

    for key in ("TITLE", "HELD ON", "TIME"):
        value = header.get(key, "")
        if PLACEHOLDER in value and key == "TIME" \
                and not project["keys"].get("recurring meeting time"):
            # With no recurring time in the project file there is nothing to fall back on, so an
            # unstated start time is genuinely unknown. Failing here could not be repaired.
            findings.append(Finding(
                "WARN", "PLACEHOLDER", lines.get(key, 0),
                "TIME is %s — add 'Recurring meeting time' to %s to fill it"
                % (PLACEHOLDER, SOURCE_NAME)))
        elif PLACEHOLDER in value or not value:
            findings.append(Finding(
                "ERROR", "PLACEHOLDER", lines.get(key, 0),
                "%s may never be empty or %s — derive it per the project hard rules"
                % (key, PLACEHOLDER)))

    expected_title = project["keys"].get("document title")
    if expected_title and header.get("TITLE") and header["TITLE"] != expected_title:
        findings.append(Finding(
            "ERROR", "TITLE", lines.get("TITLE", 0),
            "TITLE is %r but %s sets %r" % (header["TITLE"], SOURCE_NAME, expected_title)))

    held = header.get("HELD ON", "")
    if held and PLACEHOLDER not in held:
        dayname, date = parse_long_date(held)
        if date is None:
            detail = "expected 'Thursday July 16, 2026'"
            if "," in held.split(" ")[0] or re.match(r'^[A-Za-z]+,', held):
                detail = "no comma after the day name"
            elif ORDINAL_RE.search(held):
                detail = "no ordinal suffix on the day number"
            findings.append(Finding("ERROR", "DATE_FORMAT", lines.get("HELD ON", 0),
                                    "HELD ON %r is not a valid date — %s"
                                    % (held, detail)))
        elif DAYS[date.weekday()] != dayname:
            findings.append(Finding(
                "ERROR", "DATE_MISMATCH", lines.get("HELD ON", 0),
                "HELD ON says %s but %s %d, %d is a %s"
                % (dayname, MONTHS[date.month - 1], date.day, date.year,
                   DAYS[date.weekday()])))

    time_value = header.get("TIME", "")
    if time_value and PLACEHOLDER not in time_value and not TIME_RE.match(time_value):
        findings.append(Finding("ERROR", "TIME_FORMAT", lines.get("TIME", 0),
                                "TIME %r is not in the form '4:00PM'" % time_value))

    number = header.get("MEETING NO")
    if number is not None and number != PLACEHOLDER and not number.isdigit():
        findings.append(Finding("ERROR", "MEETING_NO", lines.get("MEETING NO", 0),
                                "MEETING NO %r is not a number or %s"
                                % (number, PLACEHOLDER)))


def check_attendees(draft, project, findings):
    if not draft["attendees"]:
        findings.append(Finding("ERROR", "FORMAT", 0, "no ATTENDEES rows found"))
        return

    roster_by_name = {person["name"]: person for person in project["roster"]}

    for row in draft["attendees"]:
        fields = row["fields"]
        if len(fields) != 3:
            findings.append(Finding(
                "ERROR", "ATTENDEE_FIELDS", row["line"],
                "attendee row needs 3 tab-separated fields (Name / Organisation / "
                "Title), found %d: %r" % (len(fields), row["raw"][:60])))
            continue
        name, org, title = fields
        # A non-roster attendee may be issued with no title: the supervisor leaves it
        # blank, so an error here can never be repaired. It stays a warning; an empty
        # Name or Organisation, or any placeholder text, remains an error.
        if (project["roster"] and not title and name and org
                and name not in roster_by_name
                and PLACEHOLDER not in name and PLACEHOLDER not in org):
            findings.append(Finding(
                "WARN", "EMPTY_TITLE", row["line"],
                "%r is not on the %s roster and has no title" % (name, SOURCE_NAME)))
            continue
        if any(not field or PLACEHOLDER in field for field in fields):
            findings.append(Finding(
                "ERROR", "PLACEHOLDER", row["line"],
                "attendee row may never contain an empty field or %s — resolve the "
                "speaker label against the %s roster: %r"
                % (PLACEHOLDER, SOURCE_NAME, row["raw"][:60])))
            continue

        name, org, _title = fields
        if not project["roster"]:
            continue
        person = roster_by_name.get(name)
        if person is None:
            findings.append(Finding("WARN", "UNKNOWN_ATTENDEE", row["line"],
                                    "%r is not on the %s roster" % (name, SOURCE_NAME)))
        elif person["org"].lower() == org.lower() and person["org"] != org:
            findings.append(Finding(
                "WARN", "ATTENDEE_ORG_CASE", row["line"],
                "%s is listed as %r — %s spells it %r"
                % (name, org, SOURCE_NAME, person["org"])))
        elif person["org"] != org:
            findings.append(Finding(
                "ERROR", "ATTENDEE_ORG", row["line"],
                "%s is listed as %r but the roster says %r"
                % (name, org, person["org"])))


def check_numbering(draft, findings):
    for index, section in enumerate(draft["sections"], start=1):
        if section["num"] != index:
            findings.append(Finding(
                "ERROR", "NUMBERING", section["line"],
                "section numbered %d but is section %d in order"
                % (section["num"], index)))

        for sub_index, subsection in enumerate(section["subsections"], start=1):
            expected = (section["num"], sub_index)
            if subsection["num"] != expected:
                findings.append(Finding(
                    "ERROR", "NUMBERING", subsection["line"],
                    "subsection numbered %d.%d but should be %d.%d"
                    % (subsection["num"] + expected)))

        counters = {}
        for item in section["items"]:
            major, minor, last = item["num"]
            if major != section["num"]:
                findings.append(Finding(
                    "ERROR", "NUMBERING", item["line"],
                    "sub-item %d.%d.%d sits under section %d"
                    % (major, minor, last, section["num"])))
                continue
            known = [sub["num"][1] for sub in section["subsections"]]
            if minor not in known:
                # A sub-item with no subsection above it is the shape that renders as
                # "3.0.1": the renderer has no ilvl-1 paragraph to hang it from.
                findings.append(Finding(
                    "ERROR", "NUMBERING", item["line"],
                    "sub-item %d.%d.%d has no matching subsection heading '### %d.%d' — "
                    "without one it renders with a zero in the middle"
                    % (major, minor, last, major, minor)))
                continue
            counters[minor] = counters.get(minor, 0) + 1
            if last != counters[minor]:
                findings.append(Finding(
                    "ERROR", "NUMBERING", item["line"],
                    "sub-item numbered %d.%d.%d but is item %d under %d.%d"
                    % (major, minor, last, counters[minor], major, minor)))


def check_actions_and_status(draft, project, findings):
    orgs = project["orgs"]
    roster_names = {person["name"] for person in project["roster"]}
    first_names = {name.split()[0] for name in roster_names if name.split()}
    canonical = {org.lower(): org for org in orgs}

    for section in draft["sections"]:
        # A sub-item line that failed to parse already has a FORMAT error. Calling its
        # section empty as well would invite a repair that writes new content into it.
        if not section.get("unparsed"):
            if not section["items"]:
                findings.append(Finding("ERROR", "EMPTY_SECTION", section["line"],
                                        "section %d has no sub-items" % section["num"]))
            for subsection in section["subsections"]:
                if not any(item["num"][1] == subsection["num"][1]
                           for item in section["items"]):
                    findings.append(Finding(
                        "ERROR", "EMPTY_SECTION", subsection["line"],
                        "subsection %d.%d has no sub-items" % subsection["num"]))
        for item in section["items"]:
            if not item["text"]:
                findings.append(Finding("ERROR", "EMPTY_ITEM", item["line"],
                                        "sub-item has no text"))
            # A blank Action with Status "No Action" is the informational-row rule, not
            # a gap; warning on it buried every warning that matters.
            if not item["action"] and item["status"] != "No Action":
                findings.append(Finding("WARN", "NO_ACTION_CELL", item["line"],
                                        "sub-item has no Action value"))
            if not item["status"]:
                findings.append(Finding("WARN", "NO_STATUS_CELL", item["line"],
                                        "sub-item has no Status value"))
            _check_cells(item, orgs, canonical, roster_names, first_names, findings)

            for bullet in item["bullets"]:
                if not bullet["cells"]:
                    continue
                # Cells on a bullet are a choice to give it its own owner line, so a
                # half-filled pair is a mistake, not a missing value.
                if not bullet["text"]:
                    findings.append(Finding("ERROR", "EMPTY_ITEM", bullet["line"],
                                            "bullet has no text"))
                if not bullet["status"]:
                    findings.append(Finding(
                        "ERROR", "BULLET_CELLS", bullet["line"],
                        "bullet has Action/Status cells but no Status — fill it in, or "
                        "drop both cells for a plain bullet"))
                elif not bullet["action"] and bullet["status"] != "No Action":
                    findings.append(Finding(
                        "ERROR", "BULLET_CELLS", bullet["line"],
                        "bullet has Status %r but no Action — only 'No Action' may "
                        "leave the Action empty" % bullet["status"]))
                _check_cells(bullet, orgs, canonical, roster_names, first_names, findings)


def _check_cells(row, orgs, canonical, roster_names, first_names, findings):
    """Check a sub-item's or a bullet's Action and Status values. Empty cells pass."""
    action = row["action"]
    status = row["status"]
    if action:
        if " /" in action or "/ " in action:
            findings.append(Finding(
                "ERROR", "ACTION_FORMAT", row["line"],
                "two-party Action uses 'Org A/Org B' with no spaces, found %r"
                % action))
        for part in [p.strip() for p in action.split("/")]:
            if not part:
                continue
            if part in roster_names or part in first_names:
                findings.append(Finding(
                    "ERROR", "ACTION_PERSON", row["line"],
                    "Action names a person (%r) — the Action column takes "
                    "organisation names only" % part))
            elif orgs and part not in orgs and part.lower() in canonical:
                # The supervisor writes both "Horizon" and "HORIZON"; a case-only
                # difference names the right organisation and never blocks a run.
                findings.append(Finding(
                    "WARN", "ACTION_ORG_CASE", row["line"],
                    "Action %r — %s spells it %r"
                    % (part, SOURCE_NAME, canonical[part.lower()])))
            elif orgs and part not in orgs:
                findings.append(Finding(
                    "ERROR", "ACTION_UNKNOWN_ORG", row["line"],
                    "Action %r is not one of the organisation names in "
                    "%s" % (part, SOURCE_NAME)))

    if status and status not in STATUSES:
        hint = ""
        if status.lower() == "outstanding":
            hint = " — Stage 3 converts 'Outstanding' to 'Pending'"
        findings.append(Finding(
            "ERROR", "STATUS_VALUE", row["line"],
            "Status %r is not one of %s%s"
            % (status, ", ".join(STATUSES), hint)))


def _item_texts(draft):
    for section in draft["sections"]:
        for item in section["items"]:
            yield item["line"], item["text"]
            for bullet in item["bullets"]:
                yield bullet["line"], bullet["text"]


def check_relative_dates(draft, findings):
    for line, text in _item_texts(draft):
        lowered = text.lower()
        for phrase in RELATIVE_PHRASES:
            if re.search(r'\b%s\b' % re.escape(phrase), lowered):
                findings.append(Finding(
                    "ERROR", "RELATIVE_DATE", line,
                    "relative deadline %r — convert it to a calendar date" % phrase))
                break
        else:
            span = RELATIVE_SPAN_RE.search(lowered)
            if span:
                findings.append(Finding(
                    "ERROR", "RELATIVE_DATE", line,
                    "relative deadline %r — convert it to a calendar date"
                    % span.group(0)))

        # A day name is only a relative deadline when nothing else pins it down. An item
        # that already carries a calendar date, or describes a recurring span such as
        # "Monday to Friday", is not what this rule is for.
        if DATE_IN_TEXT_RE.search(text):
            continue
        days = "|".join(DAYS)
        if re.search(r'\b(%s)\s*(to|through|-|–|and)\s*(%s)\b' % (days, days), text):
            continue

        for match in re.finditer(r'\b(%s)\b' % days, text):
            tail = text[match.end():]
            if not re.match(r'\s+(%s)\s+\d{1,2}' % "|".join(MONTHS), tail):
                findings.append(Finding(
                    "ERROR", "RELATIVE_DATE", line,
                    "bare day name %r — convert it to a calendar date"
                    % match.group(1)))
                break


def check_speaker_attribution(draft, project, findings):
    names = sorted({person["name"] for person in project["roster"]}, key=len,
                   reverse=True)
    verbs = "|".join(SPEAKER_VERBS)
    # Transcripts call people by first name ("Sam confirmed"), so a first name or a
    # surname alone is attribution too. Matched with its capital, and never a word that
    # is also an organisation name, which is how the notes are meant to attribute.
    orgs = {org.lower() for org in project["orgs"]}
    parts = sorted({part for name in names if name.split()
                    for part in (name.split()[0], name.split()[-1])
                    if len(part) > 2 and part.lower() not in orgs},
                   key=len, reverse=True)

    for line, text in _item_texts(draft):
        match = PRONOUN_SPEAKER_RE.search(text)
        if match:
            findings.append(Finding(
                "ERROR", "SPEAKER", line,
                "speaker attribution %r — report outcomes in neutral third person"
                % match.group(0)))
            continue
        for name in names:
            if re.search(r'\b%s\b\s+(%s)\b' % (re.escape(name), verbs), text,
                         re.IGNORECASE):
                findings.append(Finding(
                    "ERROR", "SPEAKER", line,
                    "speaker attribution names a person (%r) — attribute to the "
                    "organisation or write it impersonally" % name))
                break
        else:
            for part in parts:
                if re.search(r'\b%s\s+(%s)\b' % (re.escape(part), verbs), text):
                    findings.append(Finding(
                        "ERROR", "SPEAKER", line,
                        "speaker attribution names a person (%r) — attribute to the "
                        "organisation or write it impersonally" % part))
                    break


def check_meetings_row(draft, project, findings):
    value = draft["meetings"]
    if value is None:
        findings.append(Finding("ERROR", "FORMAT", 0, "no MEETINGS: line found"))
        return

    line = draft["meetings_line"]
    if PLACEHOLDER in value:
        findings.append(Finding(
            "ERROR", "PLACEHOLDER", line,
            "the Meetings row may never be %s — derive the next date from the "
            "recurring schedule" % PLACEHOLDER))
        return
    if "next meeting will be held" in value.lower():
        findings.append(Finding(
            "ERROR", "MEETINGS_LABEL", line,
            "'Next meeting will be held' appears in no issued document — use "
            "'Next meeting date: ...'"))
        return
    if not MEETINGS_SHAPE_RE.match(value):
        findings.append(Finding(
            "ERROR", "MEETINGS_FORMAT", line,
            "the Meetings row must read 'Next meeting date: July 23, 2026 4:00PM' or "
            "'Next meeting date: July 23, 2026 and 4:00PM', got %r" % value))
        return

    match = DATE_IN_TEXT_RE.search(value)
    if not match:
        findings.append(Finding("ERROR", "MEETINGS_DATE", line,
                                "no date found in the Meetings row: %r" % value))
        return

    month, day, year = match.groups()
    if month not in MONTHS:
        findings.append(Finding("ERROR", "MEETINGS_DATE", line,
                                "%r is not a month name" % month))
        return
    try:
        next_date = datetime.date(int(year), MONTHS.index(month) + 1, int(day))
    except ValueError:
        findings.append(Finding("ERROR", "MEETINGS_DATE", line,
                                "invalid date in the Meetings row: %r" % value))
        return

    expected_day = project["keys"].get("recurring meeting day")
    if expected_day:
        expected_day = expected_day.strip().capitalize()
        if expected_day in DAYS and DAYS[next_date.weekday()] != expected_day:
            findings.append(Finding(
                "ERROR", "MEETINGS_DAY", line,
                "next meeting falls on a %s but meetings are held on %s"
                % (DAYS[next_date.weekday()], expected_day)))

    interval = project["keys"].get("recurring meeting interval (days)")
    held = draft["header"].get("HELD ON", "")
    _dayname, meeting_date = parse_long_date(held) if held else (None, None)
    if interval and meeting_date:
        try:
            gap = int(interval)
        except ValueError:
            gap = None
        if gap and (next_date - meeting_date).days != gap:
            findings.append(Finding(
                "WARN", "MEETINGS_INTERVAL", line,
                "next meeting is %d days after this one, the schedule says %d"
                % ((next_date - meeting_date).days, gap)))


def check_tail_and_text(draft, project, findings):
    prepared = draft["prepared"]
    if prepared is None:
        findings.append(Finding("ERROR", "FORMAT", 0,
                                "no 'Prepared by:' line found"))
    else:
        expected = project["keys"].get("prepared by line")
        if expected and prepared != expected:
            findings.append(Finding(
                "ERROR", "PREPARED_BY", draft["prepared_line"],
                "prepared-by line is %r but %s sets %r"
                % (prepared, SOURCE_NAME, expected)))

    for line, text in _item_texts(draft):
        if PLACEHOLDER in text:
            findings.append(Finding("WARN", "PLACEHOLDER", line,
                                    "sub-item text contains %s" % PLACEHOLDER))
        # Drafts carry raw text and the renderer does the escaping, so a raw '&'
        # is correct. A pre-escaped entity would be escaped again and print
        # literally ("T&amp;T") in the issued document.
        if re.search(r'&(?:amp|lt|gt|quot|apos|#\d+|#x[0-9A-Fa-f]+);', text):
            findings.append(Finding(
                "WARN", "AMPERSAND", line,
                "XML entity in draft text — write the raw character (e.g. '&', "
                "not '&amp;'); the renderer escapes it"))


def _normalise(text):
    """Lowercase, strip punctuation, collapse whitespace — for comparison only."""
    text = re.sub(r'[^a-z0-9\s]', ' ', text.lower())
    return re.sub(r'\s+', ' ', text).strip()


STOPWORDS = frozenset("""
a an and are as at be been by for from has have in is it its of on or that the to was
were will with be to should shall may can could would
""".split())


def _content_words(text):
    """Meaningful words, crudely stemmed so 'confirm' matches 'confirmed'."""
    words = set()
    for word in _normalise(text).split():
        if word in STOPWORDS or len(word) < 3:
            continue
        for suffix in ("ing", "ed", "es", "s"):
            if len(word) > len(suffix) + 2 and word.endswith(suffix):
                word = word[: -len(suffix)]
                break
        words.add(word)
    return words


def _dice(left, right):
    """Symmetric overlap: 2|A∩B| / (|A|+|B|).

    One-sided containment — "how much of the ledger entry appears in this item" — hits
    1.0 whenever a short entry's words all turn up somewhere in a longer item, including
    a different item that merely mentions the same subject. Symmetry costs a little
    tolerance for rewrites and buys back the ability to tell two items apart.
    """
    if not left or not right:
        return 0.0
    return 2 * len(left & right) / (len(left) + len(right))


def _similarity(ledger_text, quote, item_text):
    """How strongly a ledger entry and a draft item describe the same thing.

    Whole-string similarity alone was wrong here: Stage 2 is told to cut wording to its
    core, so a kept item is routinely rewritten shorter than its ledger entry, and the
    length difference alone sank the ratio below any usable threshold. Shared content
    words survive a rewrite; wording does not.

    The transcript quote joins the ledger's own words rather than being scored
    separately, so an item whose wording changed completely still has the words it was
    written from. A quote of one or two words ("yes", "that's right") carries no signal
    and is ignored — scored on its own it matched almost anything.
    """
    item_words = _content_words(item_text)
    if not item_words:
        return 0.0

    ledger_words = _content_words(ledger_text)
    quote_words = _content_words(quote)
    if len(quote_words) >= 3:
        ledger_words = ledger_words | quote_words

    # Two shared content words is the floor for claiming these describe the same thing.
    # Character-level similarity between two unrelated English sentences of similar
    # length sits at 0.3-0.5 on its own — the same height as the warning band — so
    # letting it carry a pairing turned dropped items into warnings, and one unrelated
    # pair into a silent match at 0.513. Measured true matches share five words;
    # measured false ones share nought or one.
    if len(ledger_words & item_words) < 2:
        return 0.0

    return max(
        difflib.SequenceMatcher(
            None, _normalise(ledger_text), _normalise(item_text)).ratio(),
        _dice(ledger_words, item_words))


def check_ledger(draft, ledger_path, findings):
    """Every item the formatter recorded must still be in the draft.

    A dropped action is the one failure no later stage can see, because no stage after
    Stage 1 reads the transcript. The ledger makes it decidable by a script.

    Items are matched on their text, not their number. Stage 2 is told to reorder points
    within a section, so numbers move; matching on number reports whichever number ended
    up unused, which is rarely the item that was actually dropped.
    """
    entries = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        # Stage 1 sometimes writes ledger rows as a list or a table; the row is the same.
        match = re.match(r'^\s*(?:[-*>|]\s*)?(\d+)\.(\d+)\.(\d+)\s*\|([^|]*)\|?(.*)$', line)
        if match:
            # A quote carries its speaker's organisation, `[HORIZON] "..."`, so Stage 3
            # can tell who said it. The tag is not transcript wording: scored, it would
            # add a word to every quote and move matches, so it is dropped here. Ledgers
            # written before the tag existed parse the same.
            quote = LEDGER_SPEAKER_RE.sub('', match.group(5)).strip()
            entries.append((
                (int(match.group(1)), int(match.group(2)), int(match.group(3))),
                match.group(4).strip(), quote))

    if not entries:
        # An empty ledger checks nothing, so passing it would let a dropped action through.
        findings.append(Finding("ERROR", "LEDGER_EMPTY", 0,
                                "ledger %s holds no items" % ledger_path))
        return

    items = [item for section in draft["sections"] for item in section["items"]]

    # Assign the strongest pairings first, across the whole ledger at once. Walking the
    # ledger in order and taking each entry's best remaining item let an early weak
    # pairing consume the item a later entry matched exactly — so the same draft and the
    # same ledger reported a different dropped item depending on the ledger's line order.
    scored = []
    strongest = {}
    for entry_index, (_numbers, text, quote) in enumerate(entries):
        for item_index, item in enumerate(items):
            score = _similarity(text, quote, item["text"])
            if score > 0:
                scored.append((score, entry_index, item_index))
                strongest[entry_index] = max(strongest.get(entry_index, 0.0), score)
    scored.sort(key=lambda pair: (-pair[0], pair[1], pair[2]))

    best = {}
    taken = set()
    for score, entry_index, item_index in scored:
        if entry_index in best or item_index in taken:
            continue
        best[entry_index] = score
        taken.add(item_index)

    for entry_index, (numbers, text, _quote) in enumerate(entries):
        score = best.get(entry_index, 0.0)
        if score >= 0.5:
            continue

        # The entry matched an item strongly, but that item went to another entry. The
        # style rules tell the pipeline to consolidate several transcript exchanges into
        # one outcome, so two ledger entries legitimately land in one sub-item. Nothing
        # was dropped, and calling it a drop blocks the gate on a correct document.
        if strongest.get(entry_index, 0.0) >= 0.5:
            findings.append(Finding(
                "WARN", "LEDGER_UNCERTAIN", 0,
                "ledger item %d.%d.%d matches an item already claimed by another ledger "
                "entry — it was probably consolidated into it, which the style rules "
                "ask for: %r" % (numbers[0], numbers[1], numbers[2], text[:70])))
            continue

        # Judged on the assigned score — the best item still available to this entry.
        # Judging it on the best score the entry could reach instead swallows real
        # drops: a deleted item usually still shares a word or two with some item that
        # another entry already owns, which is enough to clear 0.3. Only a strong
        # resemblance to a claimed item (the branch above) means consolidation.
        if score >= 0.3:
            # Something in the draft resembles it. Graded rather than absolute, because
            # an error here asks the supervisor to override a finding they can see is
            # wrong, and an override reflex costs more than a missed warning.
            findings.append(Finding(
                "WARN", "LEDGER_UNCERTAIN", 0,
                "ledger item %d.%d.%d matches a draft item only loosely — check it was "
                "rewritten rather than replaced: %r"
                % (numbers[0], numbers[1], numbers[2], text[:70])))
        else:
            findings.append(Finding(
                "ERROR", "LEDGER_DROPPED", 0,
                "ledger item %d.%d.%d is not in this draft — a later stage removed "
                "something the transcript recorded: %r"
                % (numbers[0], numbers[1], numbers[2], text[:70])))


SAY_NOT_RE = re.compile(r'^-\s*Say\s+"([^"]+)"\s+not\s+"([^"]+)"', re.IGNORECASE)
NEVER_USE_RE = re.compile(r'^-\s*Never use\s+"([^"]+)"', re.IGNORECASE)


def wording_rules(project):
    """(banned, wanted or None) pairs from the supervisor guide's Wording preferences.

    Only the two string-shaped forms are read: `Say "X" not "Y"` and `Never use "Y"`.
    Everything else in the guide is judgement and stays with Stage 4. The guide path in
    the project file starts at the project root, which holds that file or its parent does."""
    rel = project["keys"].get("supervisor style guide")
    if not rel:
        return []
    for base in (project["path"].parent, project["path"].parent.parent):
        guide = base / rel
        if guide.is_file():
            break
    else:
        return []
    rules = []
    in_section = in_comment = False
    for raw in guide.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            in_section = line == "## Wording preferences"
            continue
        if "<!--" in line:
            in_comment = True
        if in_comment:
            in_comment = "-->" not in line
            continue
        if not in_section:
            continue
        say = SAY_NOT_RE.match(line)
        never = NEVER_USE_RE.match(line)
        if say:
            rules.append((say.group(2), say.group(1)))
        elif never:
            rules.append((never.group(1), None))
    return rules


def check_supervisor_wording(draft, project, findings):
    """Warn on a phrase the supervisor guide bans. A warning, not an error: the fix can
    need a grammar change ("in hopes of finding" -> "in an effort to find"), and Stage 4
    owns that rewrite."""
    rules = wording_rules(project)
    for line, text in _item_texts(draft):
        for banned, wanted in rules:
            if re.search(r'\b%s\b' % re.escape(banned), text, re.IGNORECASE):
                findings.append(Finding(
                    "WARN", "SUPERVISOR_WORDING", line,
                    "%r — the supervisor style guide says %s" % (
                        banned, '"%s"' % wanted if wanted else "never use it")))


def check_typed_numbers(draft, findings):
    """ERROR on text validate.py will definitely fail: a leading number with as many
    levels as the list depth build_body_xml.py gives that text (section title 0,
    subsection 1, sub-item 2, bullet 3), which Word would print a second time."""
    texts = []
    for section in draft["sections"]:
        texts.append((0, section["title"], section["line"]))
        texts += [(1, sub["label"], sub["line"]) for sub in section["subsections"]]
        for item in section["items"]:
            texts.append((2, item["text"], item["line"]))
            texts += [(3, b["text"], b["line"]) for b in item["bullets"]]
    for depth, text, line in texts:
        match = LEADING_NUMBER_RE.match(text)
        if match and len(match.group(1).rstrip(".").split(".")) == depth + 1:
            findings.append(Finding(
                "ERROR", "TYPED_NUMBER", line,
                "text starts with %r, which reads as a typed list number — validate.py "
                "fails the render on it. Reword so the number is not first "
                "(e.g. 'Section %s ...')" % (match.group(1), match.group(1))))


def illegal_characters(text):
    """(draft line, character, text before it) for each line holding a character Word
    cannot store — the first such character per line.

    Splits on newlines only: str.splitlines() also breaks at form feeds and other
    separators, which would shift every later line number. The ledger and the pipeline
    notes are never rendered, so the scan stops at either."""
    for number, line in enumerate(text.split("\n"), start=1):
        if line.strip() == NOTES_SENTINEL or LEDGER_RE.match(line.strip()):
            return
        bad = XML_ILLEGAL_RE.search(line)
        if bad:
            yield number, bad.group(0), line[max(0, bad.start() - 30):bad.start()].strip()


def check_characters(text, findings):
    for number, char, context in illegal_characters(text):
        findings.append(Finding(
            "ERROR", "CHARACTER", number,
            "character U+%04X cannot go into a Word document (an invisible control or "
            "non-character) — delete it. It follows %r" % (ord(char), context)))


def run_checks(draft, project, findings):
    check_header(draft, project, findings)
    check_attendees(draft, project, findings)
    check_numbering(draft, findings)
    check_typed_numbers(draft, findings)
    check_actions_and_status(draft, project, findings)
    check_relative_dates(draft, findings)
    check_speaker_attribution(draft, project, findings)
    check_meetings_row(draft, project, findings)
    check_tail_and_text(draft, project, findings)
    check_supervisor_wording(draft, project, findings)
    return findings


# ---------------------------------------------------------------------- CLI

SCORECARD_HEADING = "## Pipeline runs"
SCORECARD_COLUMNS = 8
SCORECARD_RUN_FILE = "scorecard-row.txt"


def scorecard_key(lines, run_folder, run_date):
    """Return this run's row key, "<HELD ON date> #<run>".

    A row keyed on the date alone let a second run of the same meeting, or a test run,
    overwrite the first run's row with a hybrid of both. The run folder is the run: its
    first check takes the next counter for the date and records it there, and every
    later check in that folder (a repair re-check, Stage 4.5) reuses it.
    """
    marker = run_folder / SCORECARD_RUN_FILE
    if marker.is_file():
        key = marker.read_text(encoding="utf-8").strip()
        if key.startswith(run_date + " #"):
            return key
    taken = 0
    for line in lines:
        cell = line.split("|")[1].strip() if line.startswith("|") else ""
        if cell == run_date:
            taken = max(taken, 1)   # a row from before run counters
        elif cell.startswith(run_date + " #") and cell[len(run_date) + 2:].isdigit():
            taken = max(taken, int(cell[len(run_date) + 2:]))
    key = "%s #%d" % (run_date, taken + 1)
    marker.write_text(key + "\n", encoding="utf-8")
    return key


def append_scorecard(path, stage, counts, run_date, run_folder):
    """Write this run's numbers into the scorecard's "Pipeline runs" table.

    The orchestrator was told to do this by hand at the end of a long command, which
    makes it the first thing dropped under load — and it is the number that reveals a
    check that is wrong too often. The script has the figures already, so it writes them.

    One row per run (see scorecard_key): Stage 2.5 fills column 4, Stage 4.5 fills
    column 5, and the columns the script cannot know (repairs, review findings, render
    attempts) are left as "—" for the orchestrator to complete.
    """
    if not path.is_file():
        return "scorecard not found at %s" % path

    lines = path.read_text(encoding="utf-8").splitlines()
    run_key = scorecard_key(lines, run_folder, run_date)
    # Columns, 1-based within the row: 1 date, 2 sections, 3 sub-items,
    # 4 Stage 2.5 errors, 5 Stage 4.5 errors, 6 repairs, 7 review findings, 8 renders,
    # 9 run time (absent from scorecards made before it).
    column = 4 if str(stage).startswith("2") else 5

    for index, line in enumerate(lines):
        if line.startswith("| %s |" % run_key):
            cells = line.split("|")
            if len(cells) >= SCORECARD_COLUMNS + 2:
                cells[column] = " %s " % counts["errors"]
                # Refresh the shape columns too: Stage 3 and Stage 4 merge and split
                # items, so the figures Stage 2.5 saw are not the document's final shape.
                cells[2] = " %s " % counts["sections"]
                cells[3] = " %s " % counts["items"]
                lines[index] = "|".join(cells)
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return "scorecard row for %s updated" % run_key

    for index, line in enumerate(lines):
        if line.strip() == SCORECARD_HEADING:
            separator = index + 1
            while separator < len(lines) and not lines[separator].startswith("|---"):
                separator += 1
            if separator >= len(lines):
                return "no table found under '%s' in %s" % (SCORECARD_HEADING, path)
            # One cell per header column, so an older scorecard keeps its width. Index 0
            # and the last entry are the empty strings either side of the outer pipes, so
            # cell N lives at index N, as in a split() of an existing line.
            width = max(SCORECARD_COLUMNS, lines[separator].count("|") - 1)
            row = ["", run_key, str(counts["sections"]), str(counts["items"])]
            row += ["—"] * (width - 3) + [""]
            row[column] = str(counts["errors"])
            # Append after the last existing row, so the table reads oldest-first like
            # the memory log. Two durable records that read in opposite directions
            # invite a misreading.
            insert_at = separator + 1
            while insert_at < len(lines) and lines[insert_at].startswith("|"):
                insert_at += 1
            lines.insert(insert_at, "| " + " | ".join(row[1:-1]) + " |")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return "scorecard row for %s added" % run_key

    return "no '%s' heading in %s" % (SCORECARD_HEADING, path)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate a meeting-notes draft before rendering.")
    parser.add_argument("draft", help="path to the Stage 4 markdown draft")
    parser.add_argument("--agents-md", "--claude-md", dest="agents_md",
                        help="path to the project instruction file, AGENTS.md or "
                             "CLAUDE.md (default: search upward from the draft, "
                             "AGENTS.md first)")
    parser.add_argument("--ledger",
                        help="Stage 1 ledger — error on any item missing from the draft")
    parser.add_argument("--scorecard",
                        help="pipeline scorecard to write this run's numbers into")
    parser.add_argument("--stage", default="4",
                        help="which check this is (2 or 4) — picks the scorecard column")
    parser.add_argument("--run-date",
                        help="date for the scorecard row (default: the draft's HELD ON "
                             "date, else today)")
    parser.add_argument("--json", dest="json_out",
                        help="also write the findings to this path as JSON")
    parser.add_argument("--quiet", action="store_true",
                        help="print the summary line only")
    args = parser.parse_args(argv)

    draft_path = Path(args.draft)
    if not draft_path.is_file():
        sys.exit("error: draft not found: %s" % draft_path)

    project_path = (Path(args.agents_md) if args.agents_md
                    else find_project_file(draft_path))
    if project_path is None or not project_path.is_file():
        sys.exit("error: no AGENTS.md or CLAUDE.md found — pass --agents-md")

    project = read_project_file(project_path)
    text = draft_path.read_text(encoding="utf-8")
    draft, findings = parse_draft(text)
    check_characters(text, findings)
    run_checks(draft, project, findings)

    if draft.get("ledger_at"):
        # A ledger block in the wrong place stops the parse, so the Meetings row and the
        # prepared-by line go unseen. Reporting those as faults of their own sends the
        # reader after something that is not wrong — LEDGER_POSITION already named the
        # real cause and its line number.
        findings[:] = [
            f for f in findings
            if f.code != "FORMAT"
            or ("no MEETINGS: line found" not in f.message
                and "no 'Prepared by:' line found" not in f.message)]

    if args.ledger:
        ledger_path = Path(args.ledger)
        if ledger_path.is_file():
            check_ledger(draft, ledger_path, findings)
        else:
            # Asked for a ledger check and none ran: that is a failed gate, not a warning.
            findings.append(Finding("ERROR", "LEDGER_MISSING", 0,
                                    "ledger not found at %s" % ledger_path))

    if not project["orgs"]:
        findings.append(Finding(
            "WARN", "NO_ORG_LIST", 0,
            "%s lists no organisation names — Action values were not checked"
            % SOURCE_NAME))
    if not project["roster"]:
        findings.append(Finding(
            "WARN", "NO_ROSTER", 0,
            "%s has no roster — attendees and speaker names were not checked"
            % SOURCE_NAME))

    errors = [f for f in findings if f.level == "ERROR"]
    warnings = [f for f in findings if f.level == "WARN"]

    findings.sort(key=lambda f: (f.level != "ERROR", f.line))
    if not args.quiet:
        for finding in findings:
            print(finding)
        if findings:
            print("")

    counts = {"errors": len(errors), "warnings": len(warnings),
              "sections": len(draft["sections"]),
              "items": sum(len(s["items"]) for s in draft["sections"]),
              "attendees": len(draft["attendees"])}

    if args.json_out:
        payload = {"draft": str(draft_path), "counts": counts,
                   "findings": [f.as_dict() for f in findings]}
        Path(args.json_out).write_text(
            json.dumps(payload, indent=2), encoding="utf-8")

    if args.scorecard:
        held = parse_long_date(draft["header"].get("HELD ON", ""))[1]
        run_date = args.run_date or (held or datetime.date.today()).isoformat()
        print(append_scorecard(Path(args.scorecard), args.stage, counts, run_date,
                               draft_path.parent))

    if errors:
        print("FAIL: %d error(s), %d warning(s) — %d sections, %d sub-items"
              % (len(errors), len(warnings), counts["sections"], counts["items"]))
        return 1

    print("OK: 0 errors, %d warning(s) — %d sections, %d sub-items"
          % (len(warnings), counts["sections"], counts["items"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
