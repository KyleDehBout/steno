"""Tests for the draft checker.

Every case is built from one good draft, mutated to break exactly one rule. The good
draft doubles as the worked example of the format contract in
project-template/Meeting Notes/skills/draft-checks/references/draft-format.md.

Run:  python3 tests/test_check_draft.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(
    HERE, os.pardir, 'project-template', 'Meeting Notes',
    'skills', 'draft-checks', 'scripts', 'check_draft.py')

CLAUDE_MD = """# Test Project — Claude Code Context

## Project
- Project name: Test Project
- Document title: Test Project – Project Meeting
- Prepared by line: Prepared by: NOVA Limited
- Recurring meeting day: Thursday
- Recurring meeting interval (days): 7
- Recurring meeting time: 4:00PM

## Project roster — Test Project
| Name | Organisation | Title |
|---|---|---|
| Sam Carter | NOVA | Project Manager |
| Morgan Hughes | Brook Systems | Hydrologist |
| Alex Bennett | ORLA | Client QS |

## Organisation names (Action column — use exactly as listed)
NOVA, ORLA, Brook Systems, BTR
"""

GOOD = """TITLE: Test Project – Project Meeting
HELD ON: Thursday July 16, 2026
TIME: 4:00PM
MEETING NO: 15

ATTENDEES:
Sam Carter\tNOVA\tProject Manager
Morgan Hughes\tBrook Systems\tHydrologist

## 1. Stormwater and Drainage
### 1.1 Cross-Section Graphic
1.1.1 | A cross-section graphic is to be prepared for the retention area. | \
Brook Systems | Pending
1.1.2 | The invert level was confirmed at 12.4m. | NOVA | No Action
- Supporting detail that belongs to the item above.

## 2. Electrical
### 2.1 Panel Schedule
2.1.1 | The panel schedule is to be reissued by July 23, 2026. | BTR/NOVA | In Progress

MEETINGS: Next meeting date: July 23, 2026 4:00PM

Prepared by: NOVA Limited
"""

failures = []


def check(name, condition, detail=''):
    if condition:
        print('  pass  %s' % name)
    else:
        print('  FAIL  %s\n        %s' % (name, detail))
        failures.append(name)


def run(draft_text, claude_md=CLAUDE_MD):
    """Run the checker on a draft, returning (exit code, output, codes found)."""
    tmp = tempfile.mkdtemp()
    try:
        claude = os.path.join(tmp, 'CLAUDE.md')
        with open(claude, 'w', encoding='utf-8') as handle:
            handle.write(claude_md)
        draft = os.path.join(tmp, 'draft.md')
        with open(draft, 'w', encoding='utf-8') as handle:
            handle.write(draft_text)
        out_json = os.path.join(tmp, 'out.json')
        proc = subprocess.run(
            [sys.executable, CHECK, draft, '--claude-md', claude,
             '--json', out_json],
            capture_output=True, text=True)
        codes = []
        if os.path.exists(out_json):
            with open(out_json, encoding='utf-8') as handle:
                payload = json.load(handle)
            codes = [f['code'] for f in payload['findings'] if f['level'] == 'ERROR']
        return proc.returncode, (proc.stdout + proc.stderr).strip(), codes
    finally:
        shutil.rmtree(tmp)


def expect_clean(name, draft_text):
    code, out, _ = run(draft_text)
    check(name, code == 0, 'expected exit 0, got %d:\n%s' % (code, out))


def expect_error(name, draft_text, expected_code):
    code, out, codes = run(draft_text)
    check(name, code == 1 and expected_code in codes,
          'expected exit 1 with %s, got exit %d with %s\n%s'
          % (expected_code, code, codes or 'no error codes', out))


def test_accepts_a_good_draft():
    expect_clean('accepts a well-formed draft', GOOD)


def test_accepts_trailing_note_lines():
    """Stage agents append NOTE lines; the checker tolerates and ignores them."""
    expect_clean('ignores trailing NOTE lines',
                 GOOD + "\nEDITORIAL NOTE: removed 3 filler points\n"
                        "HUMANIZER NOTE: applied patterns 2, 23; 4 rewrites.\n")


def test_raw_ampersand_is_not_flagged():
    """Drafts carry raw text; the renderer escapes it, so T&T is correct as written."""
    code, out, _ = run(GOOD.replace('the retention area', 'the T&T retention area'))
    check('accepts a raw & without an AMPERSAND warning',
          code == 0 and 'AMPERSAND' not in out, 'got exit %d:\n%s' % (code, out))


def test_warns_on_a_pre_escaped_entity():
    """A pre-escaped &amp; would render literally as "&amp;" in the Word document."""
    code, out, _ = run(GOOD.replace('the retention area', 'the T&amp;T retention area'))
    check('warns on a pre-escaped &amp; in sub-item text',
          code == 0 and 'AMPERSAND' in out, 'got exit %d:\n%s' % (code, out))


def test_rejects_bad_status():
    expect_error('rejects a Status outside the four values',
                 GOOD.replace('| Pending', '| Outstanding'), 'STATUS_VALUE')


def test_rejects_person_in_action():
    expect_error('rejects a person name in the Action column',
                 GOOD.replace('| Brook Systems | Pending',
                              '| Morgan Hughes | Pending'), 'ACTION_PERSON')


def test_rejects_unknown_org():
    expect_error('rejects an Action org that is not in CLAUDE.md',
                 GOOD.replace('| BTR/NOVA |', '| Acme Civils |'),
                 'ACTION_UNKNOWN_ORG')


def test_rejects_placeholder_in_header():
    expect_error('rejects [not provided] in the header block',
                 GOOD.replace('TIME: 4:00PM', 'TIME: [not provided]'), 'PLACEHOLDER')


def test_allows_time_placeholder_without_a_recurring_time():
    """Setup left the meeting time blank: an unstated start time is genuinely unknown."""
    code, out, _ = run(GOOD.replace('TIME: 4:00PM', 'TIME: [not provided]'),
                       CLAUDE_MD.replace('- Recurring meeting time: 4:00PM\n', ''))
    check('allows TIME [not provided] when CLAUDE.md sets no meeting time',
          code == 0 and 'PLACEHOLDER' in out, 'expected exit 0 with a warning, got %d:\n%s'
          % (code, out))


def test_still_rejects_held_on_placeholder_without_a_recurring_time():
    code, out, codes = run(
        GOOD.replace('HELD ON: Thursday July 16, 2026', 'HELD ON: [not provided]'),
        CLAUDE_MD.replace('- Recurring meeting time: 4:00PM\n', ''))
    check('still rejects HELD ON [not provided] with no meeting time set',
          code == 1 and 'PLACEHOLDER' in codes, 'got exit %d with %s\n%s' % (code, codes, out))


def test_rejects_placeholder_in_attendees():
    expect_error('rejects [not provided] in an attendee row',
                 GOOD.replace('Sam Carter\tNOVA\tProject Manager',
                              '[not provided]\tNOVA\t[not provided]'), 'PLACEHOLDER')


def test_rejects_comma_after_day_name():
    """The supervisor removed this comma by hand; the rule has been missed since."""
    expect_error('rejects a comma after the day name',
                 GOOD.replace('HELD ON: Thursday July 16, 2026',
                              'HELD ON: Thursday, July 16, 2026'), 'DATE_FORMAT')


def test_rejects_day_name_that_contradicts_the_date():
    expect_error('rejects a day name that is not that date',
                 GOOD.replace('HELD ON: Thursday July 16, 2026',
                              'HELD ON: Tuesday July 16, 2026'), 'DATE_MISMATCH')


def test_rejects_relative_deadline():
    expect_error('rejects a relative deadline phrase',
                 GOOD.replace('by July 23, 2026', 'by early next week'),
                 'RELATIVE_DATE')


def test_rejects_bare_day_name_in_an_item():
    expect_error('rejects a bare day name in a sub-item',
                 GOOD.replace('by July 23, 2026', 'by Monday'), 'RELATIVE_DATE')


def test_rejects_speaker_attribution():
    expect_error('rejects speaker attribution by name',
                 GOOD.replace('The invert level was confirmed at 12.4m.',
                              'Sam Carter confirmed the invert level at 12.4m.'),
                 'SPEAKER')


def test_rejects_pronoun_attribution():
    expect_error('rejects pronoun speaker attribution',
                 GOOD.replace('The invert level was confirmed at 12.4m.',
                              'They said the invert level is 12.4m.'), 'SPEAKER')


def test_rejects_next_meeting_on_the_wrong_day():
    expect_error('rejects a next-meeting date that is not the scheduled day',
                 GOOD.replace('Next meeting date: July 23, 2026',
                              'Next meeting date: July 24, 2026'), 'MEETINGS_DAY')


def test_rejects_deprecated_meetings_label():
    expect_error('rejects the "Next meeting will be held" label',
                 GOOD.replace('Next meeting date: July 23, 2026 4:00PM',
                              'Next meeting will be held on July 23, 2026'),
                 'MEETINGS_LABEL')


MEETINGS_GOOD = 'Next meeting date: July 23, 2026 4:00PM'


def test_accepts_both_meetings_line_variants():
    """Issued Style B #9 joins date and time with "and", #10 does not; both are the
    supervisor's own wording."""
    expect_clean('accepts the Meetings line without "and"', GOOD)
    expect_clean('accepts the Meetings line with "and"',
                 GOOD.replace(MEETINGS_GOOD,
                              'Next meeting date: July 23, 2026 and 4:00PM'))


def test_rejects_a_malformed_meetings_line():
    for label, value in (
            ('a missing time', 'Next meeting date: July 23, 2026'),
            ('a malformed date', 'Next meeting date: July 23 2026 4:00PM'),
            ('a malformed time', 'Next meeting date: July 23, 2026 4PM'),
            ('a spaced time', 'Next meeting date: July 23, 2026 4:00 PM'),
            ('an impossible time', 'Next meeting date: July 23, 2026 13:00PM'),
            ('extra words', 'Next meeting date: July 23, 2026 at 4:00PM'),
            ('trailing words', 'Next meeting date: July 23, 2026 4:00PM on site'),
            ('a doubled joiner', 'Next meeting date: July 23, 2026 and and 4:00PM'),
            ('a missing label', 'July 23, 2026 4:00PM')):
        expect_error('rejects a Meetings line with %s' % label,
                     GOOD.replace(MEETINGS_GOOD, value), 'MEETINGS_FORMAT')
    # Right shape, wrong date: the date checks behind the shape still name the fault.
    for label, value in (
            ('an abbreviated month', 'Next meeting date: Jul 23, 2026 4:00PM'),
            ('an impossible date', 'Next meeting date: June 31, 2026 and 4:00PM')):
        expect_error('rejects a Meetings line with %s' % label,
                     GOOD.replace(MEETINGS_GOOD, value), 'MEETINGS_DATE')


def test_rejects_out_of_sequence_numbering():
    expect_error('rejects sub-item numbering that skips',
                 GOOD.replace('1.1.2 |', '1.1.5 |'), 'NUMBERING')


def test_rejects_a_row_that_is_not_in_the_format():
    expect_error('rejects a sub-item missing its Action and Status cells',
                 GOOD.replace(
                     '1.1.2 | The invert level was confirmed at 12.4m. | NOVA | '
                     'No Action',
                     '1.1.2 | The invert level was confirmed at 12.4m.'), 'FORMAT')


def test_rejects_wrong_document_title():
    expect_error('rejects a title that is not the one CLAUDE.md sets',
                 GOOD.replace('TITLE: Test Project – Project Meeting',
                              'TITLE: Test Project – Hydrology Project Meeting'),
                 'TITLE')


def test_warns_but_passes_on_an_empty_title_for_a_non_roster_attendee():
    """The supervisor issues some non-roster attendees with no title, so an error here
    can never be repaired. Name, Organisation and placeholders stay errors."""
    attendee = 'Jordan Reyes\tDLK\t'
    code, out, _ = run(GOOD.replace('Sam Carter\tNOVA\tProject Manager', attendee))
    check('empty Title for a non-roster attendee is a warning, not an error',
          code == 0 and 'EMPTY_TITLE' in out,
          'expected exit 0 with EMPTY_TITLE, got exit %d:\n%s' % (code, out))
    expect_error('empty Title for a roster attendee is still an error',
                 GOOD.replace('Sam Carter\tNOVA\tProject Manager',
                              'Sam Carter\tNOVA\t'), 'PLACEHOLDER')
    expect_error('empty Organisation for a non-roster attendee is still an error',
                 GOOD.replace('Sam Carter\tNOVA\tProject Manager',
                              'Jordan Reyes\t\tCivil'), 'PLACEHOLDER')


def test_warns_but_passes_on_an_empty_action_cell():
    """An informational item takes Status No Action with the Action left blank, as every
    rule file now says. That pairing is correct and gets no warning: one on every
    informational row buried the warnings that matter. A blank Action with any other
    Status is still a warning, and never blocks the pipeline."""
    code, out, _ = run(GOOD.replace('| NOVA | No Action', '|  | No Action'))
    check('blank Action with No Action: clean, no NO_ACTION_CELL',
          code == 0 and 'NO_ACTION_CELL' not in out,
          'expected exit 0 and no warning, got exit %d:\n%s' % (code, out))
    code, out, _ = run(GOOD.replace('| NOVA | No Action', '|  | Pending'))
    check('blank Action with Pending: a warning, not an error',
          code == 0 and 'WARN  [NO_ACTION_CELL]' in out,
          'expected exit 0 with NO_ACTION_CELL, got exit %d:\n%s' % (code, out))


def test_accepts_space_separated_attendee_rows():
    """Tabs are the contract, but they do not always survive six agents of generated
    text. Two or more spaces separate the three fields just as unambiguously, and
    failing a correct draft over whitespace is how a check gets switched off."""
    expect_clean('accepts attendee rows separated by spaces',
                 GOOD.replace('Sam Carter\tNOVA\tProject Manager',
                              'Sam Carter   NOVA   Project Manager'))


def test_accepts_a_day_name_alongside_a_calendar_date():
    """"The Thursday site walk was moved to July 23, 2026" is not a relative deadline."""
    expect_clean('accepts a day name when the item carries a calendar date',
                 GOOD.replace('The invert level was confirmed at 12.4m.',
                              'The Thursday site walk was moved to July 23, 2026.'))


def test_accepts_a_day_range():
    expect_clean('accepts a recurring day range',
                 GOOD.replace('The invert level was confirmed at 12.4m.',
                              'Drainage works continue on a Monday to Friday schedule.'))


def test_accepts_a_blockquoted_supervisor_note():
    """supervisor-alignment emits its note as a blockquote; an unrecognised note line
    used to fail the blocking gate on every run below the threshold."""
    expect_clean('ignores a blockquoted SUPERVISOR NOTE',
                 GOOD + '\n> SUPERVISOR NOTE: 1 of 3 recurring corrections logged.\n')


def test_accepts_a_trailing_ledger_block():
    expect_clean('ignores a trailing LEDGER block',
                 GOOD + '\nLEDGER:\n1.1.1 | A cross-section graphic | "quote"\n')


def test_rejects_a_sub_item_with_no_subsection():
    """The shape that renders as "3.0.1"."""
    expect_error('rejects a sub-item with no subsection heading',
                 GOOD.replace('### 2.1 Panel Schedule\n', ''), 'NUMBERING')


def test_accepts_completed_status():
    """The supervisor issues "Completed" when the transcript says the work is done."""
    expect_clean('accepts Status "Completed"', GOOD.replace('| Pending', '| Completed'))


def test_org_case_difference_is_a_warning():
    """CLAUDE.md spelling is canonical, but a case-only difference never blocks a run."""
    for name, draft_text in (
            ('Action', GOOD.replace('| Brook Systems | Pending', '| BROOK SYSTEMS | Pending')),
            ('attendee', GOOD.replace('Sam Carter\tNOVA\t', 'Sam Carter\tNova\t'))):
        code, out, _ = run(draft_text)
        check('a case-only %s org difference is a warning, not an error' % name,
              code == 0 and 'ORG_CASE' in out,
              'expected exit 0 with an ORG_CASE warning, got %d:\n%s' % (code, out))


def test_notes_after_the_sentinel_are_ignored():
    """Agents put their notes after the sentinel; nothing below it is document content."""
    expect_clean('ignores everything after ---PIPELINE NOTES---',
                 GOOD + '\n---PIPELINE NOTES---\nDISCIPLINE NOTE:\n'
                        '- 1.1.1 NOVA -> Brook Systems (judgement call)\n'
                        'SUPERVISOR NOTE: 1 of 3 recurring corrections logged.\n'
                        'Recurring corrections will activate at 3.\n')


def test_rejects_a_bullet_after_the_meetings_line():
    """An unstripped note list used to attach to the last sub-item and be rendered."""
    expect_error('rejects a bullet below the MEETINGS line',
                 GOOD + '\nDISCIPLINE NOTE: 1 change\n- judgement call on 1.1.1\n',
                 'FORMAT')


def test_rejects_a_bullet_under_a_note_line():
    expect_error('rejects a bullet directly under a NOTE line in the body',
                 GOOD.replace('\n## 2. Electrical',
                              '\nDISCIPLINE NOTE: 1 change\n- judgement call\n'
                              '\n## 2. Electrical'), 'FORMAT')


def test_rejects_empty_item_text():
    expect_error('rejects a sub-item with empty text',
                 GOOD.replace('| The invert level was confirmed at 12.4m. |', '|  |'),
                 'EMPTY_ITEM')


def test_rejects_an_empty_section_or_subsection():
    expect_error('rejects a section with no sub-items',
                 GOOD.replace('\nMEETINGS:', '\n## 3. Drainage\n\nMEETINGS:'),
                 'EMPTY_SECTION')
    expect_error('rejects a subsection with no sub-items',
                 GOOD.replace('\n## 2. Electrical', '### 1.2 Manholes\n\n## 2. Electrical'),
                 'EMPTY_SECTION')
    code, out, codes = run(GOOD.replace('| BTR/NOVA | In Progress', ''))
    check('a malformed sub-item does not also call its section empty',
          code == 1 and 'FORMAT' in codes and 'EMPTY_SECTION' not in codes,
          'got exit %d with %s\n%s' % (code, codes, out))


def test_rejects_a_non_numeric_meeting_number():
    expect_error('rejects MEETING NO that is not a number',
                 GOOD.replace('MEETING NO: 15', 'MEETING NO: fifteen'), 'MEETING_NO')
    expect_clean('accepts MEETING NO [not provided]',
                 GOOD.replace('MEETING NO: 15', 'MEETING NO: [not provided]'))


BULLET = 'Supporting detail that belongs to the item above.'


def with_bullet_cells(cells):
    return GOOD.replace(BULLET, BULLET + cells)


def test_accepts_a_bullet_with_its_own_cells():
    """Style A issued #13, #16, #17: a dependent follow-up nested as a bullet carries its own
    owner and status (approved 2026-10-01). A plain bullet still carries none."""
    for cells in (' | ORLA | In Progress', ' | NOVA | Completed', ' |  | No Action',
                  ' | ORLA/Brook Systems | Pending'):
        expect_clean('accepts a bullet with cells %r' % cells, with_bullet_cells(cells))
    expect_clean('accepts an escaped pipe in a bullet',
                 GOOD.replace(BULLET, 'belongs to A \\| B.'))
    expect_clean('accepts an escaped pipe in a bullet that has cells',
                 GOOD.replace(BULLET, 'belongs to A \\| B. | NOVA | Pending'))


def test_validates_bullet_cells_like_an_item():
    for cells, code in ((' | Synergy | Pending', 'ACTION_UNKNOWN_ORG'),
                        (' | Sam Carter | Pending', 'ACTION_PERSON'),
                        (' | NOVA / ORLA | Pending', 'ACTION_FORMAT'),
                        (' | NOVA | Outstanding', 'STATUS_VALUE')):
        expect_error('rejects bullet cells %r' % cells, with_bullet_cells(cells), code)
    code, out, _ = run(with_bullet_cells(' | Orla | Pending'))
    check('a case-only org difference in bullet cells is a warning',
          code == 0 and 'ACTION_ORG_CASE' in out,
          'expected exit 0 with ACTION_ORG_CASE, got %d:\n%s' % (code, out))


def test_rejects_malformed_bullet_cells():
    for cells in (' | NOVA', ' | NOVA | Pending | Extra', ' |  | Pending',
                  ' | NOVA | ', ' |  | '):
        expect_error('rejects malformed bullet cells %r' % cells,
                     with_bullet_cells(cells), 'BULLET_CELLS')
    expect_error('rejects a bullet with cells but no text',
                 GOOD.replace('- ' + BULLET, '- | NOVA | Pending'), 'EMPTY_ITEM')


def test_rejects_vague_relative_deadlines():
    for phrase in ('by the end of the month', 'within two weeks', 'within 10 days',
                   'in a couple of weeks'):
        expect_error('rejects the relative deadline %r' % phrase,
                     GOOD.replace('by July 23, 2026', phrase), 'RELATIVE_DATE')


def test_rejects_first_name_or_surname_attribution():
    for who in ('Sam', 'Carter'):
        expect_error('rejects speaker attribution by %s alone' % who,
                     GOOD.replace('The invert level was confirmed at 12.4m.',
                                  '%s confirmed the invert level at 12.4m.' % who),
                     'SPEAKER')


SCORECARD = """# Pipeline scorecard — Test Project

## Pipeline runs

| Date | Sections | Sub-items | Stage 2.5 errors | Stage 4.5 errors | Repair attempts | Review findings | Render attempts | Run time |
|---|---|---|---|---|---|---|---|---|

What to watch: nothing, this is a fixture.
"""

# A scorecard made before the Run time column: its rows must keep eight cells.
SCORECARD_8 = SCORECARD.replace(' Run time |', '').replace('|---' * 9, '|---' * 8)


def test_scorecard_row_lands_in_the_right_columns():
    """The Stage 2.5 count belongs in column 4 and the Stage 4.5 count in column 5.
    An off-by-one here is invisible — the row looks plausible and the numbers are in
    the wrong columns forever. The row has as many cells as the table's header: nine
    with the Run time column, eight in a scorecard made before it."""
    for fixture, width in ((SCORECARD, 9), (SCORECARD_8, 8)):
        scorecard_columns_case(fixture, width)


def scorecard_columns_case(fixture, width):
    tmp = tempfile.mkdtemp()
    try:
        claude = os.path.join(tmp, 'CLAUDE.md')
        with open(claude, 'w', encoding='utf-8') as handle:
            handle.write(CLAUDE_MD)
        draft = os.path.join(tmp, 'draft.md')
        with open(draft, 'w', encoding='utf-8') as handle:
            handle.write(GOOD.replace('| Pending', '| Outstanding'))  # 1 error
        clean = os.path.join(tmp, 'clean.md')
        with open(clean, 'w', encoding='utf-8') as handle:
            handle.write(GOOD)
        card = os.path.join(tmp, 'card.md')
        with open(card, 'w', encoding='utf-8') as handle:
            handle.write(fixture)

        for path, stage in ((draft, '2'), (clean, '4')):
            subprocess.run(
                [sys.executable, CHECK, path, '--claude-md', claude,
                 '--scorecard', card, '--stage', stage,
                 '--run-date', '2026-01-01', '--quiet'],
                capture_output=True, text=True)

        with open(card, encoding='utf-8') as handle:
            rows = [l for l in handle if l.startswith('| 2026-01-01')]
        label = 'scorecard (%d columns)' % width
        check('%s: exactly one row per run' % label, len(rows) == 1,
              'got %d rows' % len(rows))
        if not rows:
            return
        cells = [c.strip() for c in rows[0].strip().strip('|').split('|')]
        check('%s: row matches the header width' % label, len(cells) == width,
              'got %r' % cells)
        check('%s: Stage 2.5 errors in column 4' % label,
              len(cells) == width and cells[3] == '1', 'got %r' % cells)
        check('%s: Stage 4.5 errors in column 5' % label,
              len(cells) == width and cells[4] == '0', 'got %r' % cells)
        check('%s: columns the script cannot know are left blank' % label,
              len(cells) == width and cells[5:] == ['—'] * (width - 5), 'got %r' % cells)
    finally:
        shutil.rmtree(tmp)


def run_with_ledger(draft_text, ledger_text):
    tmp = tempfile.mkdtemp()
    try:
        claude = os.path.join(tmp, 'CLAUDE.md')
        with open(claude, 'w', encoding='utf-8') as handle:
            handle.write(CLAUDE_MD)
        draft = os.path.join(tmp, 'draft.md')
        with open(draft, 'w', encoding='utf-8') as handle:
            handle.write(draft_text)
        ledger = os.path.join(tmp, 'ledger.md')
        with open(ledger, 'w', encoding='utf-8') as handle:
            handle.write(ledger_text)
        out_json = os.path.join(tmp, 'out.json')
        proc = subprocess.run(
            [sys.executable, CHECK, draft, '--claude-md', claude,
             '--ledger', ledger, '--json', out_json],
            capture_output=True, text=True)
        codes = []
        if os.path.exists(out_json):
            with open(out_json, encoding='utf-8') as handle:
                payload = json.load(handle)
            codes = [f['code'] for f in payload['findings'] if f['level'] == 'ERROR']
        return proc.returncode, (proc.stdout + proc.stderr).strip(), codes
    finally:
        shutil.rmtree(tmp)


LEDGER = ('LEDGER:\n'
          '1.1.1 | A cross-section graphic is to be prepared | "quote one"\n'
          '1.1.2 | The invert level was confirmed | "quote two"\n'
          '2.1.1 | The panel schedule is to be reissued | "quote three"\n')


def test_ledger_match_passes():
    code, out, _ = run_with_ledger(GOOD, LEDGER)
    check('a draft holding every ledger item passes', code == 0,
          'expected exit 0, got %d:\n%s' % (code, out))


def test_rejects_an_item_dropped_since_the_ledger():
    """A dropped action is invisible to every later stage — no stage after Stage 1 reads
    the transcript. This is the one way a script can catch it."""
    without = GOOD.replace(
        '1.1.2 | The invert level was confirmed at 12.4m. | NOVA | No Action\n', '')
    code, out, codes = run_with_ledger(without, LEDGER)
    check('rejects a ledger item missing from the draft',
          code == 1 and 'LEDGER_DROPPED' in codes,
          'expected exit 1 with LEDGER_DROPPED, got exit %d with %s\n%s'
          % (code, codes or 'no error codes', out))


REWRITE_LEDGER = (
    'LEDGER:\n'
    '1.1.1 | Cross-section graphic to be prepared | "we need a cross section"\n'
    '1.1.2 | ORLA to confirm the invert level | "ORLA will confirm the invert"\n'
    '2.1.1 | Panel schedule to be reissued by BTR | "BTR to reissue the panel schedule"\n')


def test_ledger_tolerates_editorial_rewrites():
    """Stage 2 is told to cut wording to its core, so a kept item is routinely shorter
    and differently worded than its ledger entry. Whole-string similarity failed three
    of six realistic rewrites, which asks the supervisor to override a finding they can
    see is wrong — and an override reflex costs more than a missed warning."""
    code, out, codes = run_with_ledger(GOOD, REWRITE_LEDGER)
    check('rewritten items are not reported as dropped',
          code == 0 and 'LEDGER_DROPPED' not in codes,
          'expected exit 0 with no LEDGER_DROPPED, got exit %d with %s\n%s'
          % (code, codes or 'no error codes', out))


def test_ledger_tolerates_a_completely_reworded_item():
    """The hardest real case: the ledger stub and the draft share two words."""
    draft = GOOD.replace(
        'The invert level was confirmed at 12.4m.',
        'Preference for a fibre-reinforced plastic catch basin grating over cast iron.')
    ledger = REWRITE_LEDGER.replace(
        '1.1.2 | ORLA to confirm the invert level | "ORLA will confirm the invert"',
        '1.1.2 | Grating type preference recorded | '
        '"preference is for the plastic grating rather than cast iron"')
    code, out, codes = run_with_ledger(draft, ledger)
    check('a heavily reworded item is not reported as dropped',
          code == 0 and 'LEDGER_DROPPED' not in codes,
          'expected exit 0 with no LEDGER_DROPPED, got exit %d with %s\n%s'
          % (code, codes or 'no error codes', out))


def test_a_trailing_blank_line_after_the_ledger_is_not_misplacement():
    """A blank line is formatting, not content. Every position fixture happened to end
    at EOF with no trailing newline, which hid this for a whole round."""
    code, out, codes = run(
        GOOD + '\nLEDGER:\n1.1.1 | A cross-section graphic | "quote"\n\n')
    check('a ledger followed by a blank line is not reported as misplaced',
          code == 0 and 'LEDGER_POSITION' not in codes,
          'expected exit 0 without LEDGER_POSITION, got exit %d with %s\n%s'
          % (code, codes, out))


def test_a_blank_line_inside_the_ledger_is_not_misplacement():
    code, out, codes = run(
        GOOD + '\nLEDGER:\n\n1.1.1 | A cross-section graphic | "quote"\n\n'
               '1.1.2 | The invert level | "quote"\n')
    check('blank lines between ledger rows are not reported as misplaced',
          code == 0 and 'LEDGER_POSITION' not in codes,
          'expected exit 0 without LEDGER_POSITION, got exit %d with %s\n%s'
          % (code, codes, out))


def test_consolidated_items_are_not_reported_as_dropped():
    """The style rules require consolidating several transcript exchanges into one
    outcome, so two ledger entries legitimately land in a single sub-item. Both score
    above the match line against the survivor, but only one can claim it."""
    merged = GOOD.replace(
        '1.1.2 | The invert level was confirmed at 12.4m. | NOVA | No Action\n', '')
    merged = merged.replace(
        '1.1.1 | A cross-section graphic is to be prepared for the retention area. | '
        'Brook Systems | Pending',
        '1.1.1 | The invert level was confirmed at 12.4m and a cross-section graphic '
        'is to be prepared. | Brook Systems | Pending')
    ledger = ('LEDGER:\n'
              '1.1.1 | A cross-section graphic is to be prepared for the retention '
              'area | "we need a cross section of the retention area"\n'
              '1.1.2 | The invert level was confirmed at 12.4m | '
              '"the invert level is 12.4 metres confirmed"\n'
              '2.1.1 | The panel schedule is to be reissued | '
              '"BTR to reissue the panel schedule"\n')
    code, out, codes = run_with_ledger(merged, ledger)
    check('a consolidated ledger item is a warning, not a dropped-item error',
          code == 0 and 'LEDGER_DROPPED' not in codes,
          'expected exit 0 with no LEDGER_DROPPED, got exit %d with %s\n%s'
          % (code, codes, out))
    check('the consolidation is still reported as something to check',
          'LEDGER_UNCERTAIN' in out, out)


def test_a_dropped_item_errors_even_when_a_spare_item_is_free():
    """The residual case: a dropped entry used to be assigned an unrelated free item on
    character similarity alone — scoring 0.31 to 0.51 with no words in common — and was
    demoted to a warning that passed the gate. Two shared content words are now the
    floor for any pairing."""
    ledger = ('LEDGER:\n'
              '1.1.1 | A cross-section graphic is to be prepared for the retention '
              'area | "we need a cross section of the retention area"\n'
              '1.1.2 | Site plan to be reissued to the client | '
              '"the site plan has to go back out to the client"\n')
    code, out, codes = run_with_ledger(GOOD, ledger)
    check('a dropped item errors even when unclaimed items remain',
          code == 1 and 'LEDGER_DROPPED' in codes,
          'expected exit 1 with LEDGER_DROPPED, got exit %d with %s\n%s'
          % (code, codes, out))
    check('the finding names the item that was actually dropped',
          'Site plan' in out, out)


def test_ledger_findings_do_not_depend_on_ledger_line_order():
    """The same draft and the same three entries, in two orders. Taking each entry's
    best remaining item in ledger order let an early weak pairing consume the item a
    later entry matched exactly, so the reported drop moved with the line order."""
    without = GOOD.replace(
        '2.1.1 | The panel schedule is to be reissued by July 23, 2026. | BTR/NOVA | '
        'In Progress\n', '')
    lines = [l for l in REWRITE_LEDGER.splitlines() if l and not l.startswith('LEDGER')]
    forward = 'LEDGER:\n' + '\n'.join(lines) + '\n'
    reverse = 'LEDGER:\n' + '\n'.join(reversed(lines)) + '\n'

    results = []
    for ledger in (forward, reverse):
        _code, out, codes = run_with_ledger(without, ledger)
        dropped = [line for line in out.splitlines() if 'LEDGER_DROPPED' in line]
        results.append((codes.count('LEDGER_DROPPED'), dropped))

    check('the same drop is reported whichever order the ledger is written in',
          results[0][0] == 1 and results[1][0] == 1
          and 'Panel schedule' in ' '.join(results[0][1])
          and 'Panel schedule' in ' '.join(results[1][1]),
          'forward: %r\nreverse: %r' % (results[0], results[1]))


def _ledger_findings(draft_text, ledger_text):
    """Every ledger finding, level and message, from one checker run."""
    _code, out, _codes = run_with_ledger(draft_text, ledger_text)
    return sorted(line for line in out.splitlines() if 'LEDGER_' in line)


def test_ledger_quotes_may_carry_a_speaker_organisation():
    """Stage 1 tags each quote with the speaker's organisation so Stage 3 can tell who
    said "I'll have it out". Old ledgers have no tag; both must parse and score alike."""
    tagged = REWRITE_LEDGER.replace('| "', '| [NOVA] "')
    code, out, codes = run_with_ledger(GOOD, tagged)
    check('a ledger with [ORG] speaker tags passes like an untagged one',
          code == 0 and not codes, out)

    without = GOOD.replace(
        '1.1.2 | The invert level was confirmed at 12.4m. | NOVA | No Action\n', '')
    for label, plain in (('rewrites', REWRITE_LEDGER), ('a drop', LEDGER)):
        for draft in (GOOD, without):
            check('an [ORG] tag does not change the ledger findings (%s)' % label,
                  _ledger_findings(draft, plain)
                  == _ledger_findings(draft, plain.replace('| "', '| [Brook Systems] "')),
                  plain)

    # The sharpest case: a two-word quote is ignored when scoring, so if the tag were
    # scored as a word it would bring the quote in and turn this drop into a warning.
    ledger = ('LEDGER:\n'
              '1.1.1 | A cross-section graphic is to be prepared | "quote one"\n'
              '1.1.2 | Grating detail recorded | %s"invert level"\n'
              '2.1.1 | The panel schedule is to be reissued | "quote three"\n')
    check('an [ORG] tag is not scored as a quote word',
          _ledger_findings(GOOD, ledger % '')
          == _ledger_findings(GOOD, ledger % '[NOVA] '),
          '%r\n%r' % (_ledger_findings(GOOD, ledger % ''),
                      _ledger_findings(GOOD, ledger % '[NOVA] ')))

    multi = ('LEDGER:\n'
             '1.1.1 | A cross-section graphic is to be prepared | '
             '[NOVA] "we need a cross section" / [Brook Systems] "we will prepare it"\n'
             '1.1.2 | The invert level was confirmed | "quote two"\n'
             '2.1.1 | The panel schedule is to be reissued | [BTR] "quote three"\n')
    code, out, codes = run_with_ledger(GOOD, multi)
    check('a ledger row with two tagged quotes parses', code == 0 and not codes, out)


def test_a_trailing_ledger_does_not_mask_a_real_missing_row():
    """LEDGER_POSITION must fire on an actual misplacement, not on the presence of a
    ledger. A correctly placed ledger beside a genuinely missing Meetings row has to
    report the missing row."""
    draft = GOOD.replace(
        'MEETINGS: Next meeting date: July 23, 2026 4:00PM\n\n', '')
    draft += '\nLEDGER:\n1.1.1 | A cross-section graphic | "quote"\n'
    code, out, codes = run(draft)
    check('a correctly placed ledger is not blamed for a missing Meetings row',
          'LEDGER_POSITION' not in codes and 'no MEETINGS: line found' in out,
          'got %s\n%s' % (codes, out))
    check('the run still fails on the missing Meetings row', code == 1,
          'expected exit 1, got %d' % code)


def test_ledger_position_replaces_the_symptom_errors():
    """A ledger block in the wrong place stops the parse. Reporting the missing
    Meetings row as well sends the reader after a fault that is not there."""
    broken = GOOD.replace('MEETINGS:', 'LEDGER:\n1.1.1 | x | "y"\n\nMEETINGS:')
    code, out, codes = run(broken)
    check('a misplaced ledger reports its own position',
          'LEDGER_POSITION' in codes, 'got %s\n%s' % (codes, out))
    check('a misplaced ledger does not also report the missing Meetings row',
          'no MEETINGS: line' not in out, out)


def test_scorecard_refreshes_the_shape_columns_at_stage_4():
    """Stages 3 and 4 merge and split items, so the counts Stage 2.5 saw are not the
    document's final shape — and the scorecard is the only durable record."""
    short = '\n'.join([
        'TITLE: Test Project – Project Meeting',
        'HELD ON: Thursday July 16, 2026', 'TIME: 4:00PM', 'MEETING NO: 15', '',
        'ATTENDEES:', 'Sam Carter\tNOVA\tProject Manager', '',
        '## 1. Stormwater and Drainage', '### 1.1 Cross-Section Graphic',
        '1.1.1 | A cross-section graphic is to be prepared. | Brook Systems | Pending',
        '', 'MEETINGS: Next meeting date: July 23, 2026 4:00PM', '',
        'Prepared by: NOVA Limited']) + '\n'

    tmp = tempfile.mkdtemp()
    try:
        claude = os.path.join(tmp, 'CLAUDE.md')
        with open(claude, 'w', encoding='utf-8') as handle:
            handle.write(CLAUDE_MD)
        card = os.path.join(tmp, 'card.md')
        with open(card, 'w', encoding='utf-8') as handle:
            handle.write(SCORECARD)

        for text, stage, date in ((short, '2', '2026-02-02'),
                                  (GOOD, '4', '2026-02-02'),
                                  (GOOD, '4', '2026-03-03')):
            path = os.path.join(tmp, 'd-%s-%s.md' % (stage, date))
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(text)
            subprocess.run(
                [sys.executable, CHECK, path, '--claude-md', claude,
                 '--scorecard', card, '--stage', stage, '--run-date', date, '--quiet'],
                capture_output=True, text=True)

        with open(card, encoding='utf-8') as handle:
            rows = [l for l in handle if l.startswith('| 2026-0')]
        check('scorecard: one row per run', len(rows) == 2,
              'got %d rows: %r' % (len(rows), rows))
        if len(rows) != 2:
            return
        cells = [c.strip() for c in rows[0].strip().strip('|').split('|')]
        check('scorecard: Stage 4 refreshes sections and sub-items',
              cells[1] == '2' and cells[2] == '3',
              'expected 2 sections / 3 sub-items, got %r' % cells)
        check('scorecard: rows read oldest first, like the memory log',
              rows[0].startswith('| 2026-02-02') and rows[1].startswith('| 2026-03-03'),
              'got %r' % [r[:14] for r in rows])
    finally:
        shutil.rmtree(tmp)


def test_scorecard_rows_are_keyed_on_held_on_plus_a_run_counter():
    """Keying on the run date let a second run (or a test run) on the same day overwrite
    the first run's row with a hybrid of both. Each run folder is one run: the row is
    the meeting's HELD ON date plus a counter, and a re-check inside a run updates it."""
    tmp = tempfile.mkdtemp()
    try:
        claude = os.path.join(tmp, 'CLAUDE.md')
        with open(claude, 'w', encoding='utf-8') as handle:
            handle.write(CLAUDE_MD)
        card = os.path.join(tmp, 'card.md')
        with open(card, 'w', encoding='utf-8') as handle:
            handle.write(SCORECARD)

        for run_folder in ('run-1', 'run-2'):
            os.makedirs(os.path.join(tmp, run_folder))
            # Stage 2.5 twice (a repair re-check), then Stage 4.5: still one run.
            for name, text, stage in (
                    ('stage-2.md', GOOD.replace('| Pending', '| Outstanding'), '2'),
                    ('stage-2.md', GOOD, '2'),
                    ('stage-4.md', GOOD, '4')):
                path = os.path.join(tmp, run_folder, name)
                with open(path, 'w', encoding='utf-8') as handle:
                    handle.write(text)
                subprocess.run(
                    [sys.executable, CHECK, path, '--claude-md', claude,
                     '--scorecard', card, '--stage', stage, '--quiet'],
                    capture_output=True, text=True)

        with open(card, encoding='utf-8') as handle:
            rows = [l for l in handle if l.startswith('| 2026-')]
        check('scorecard: two runs for one HELD ON date make two rows',
              len(rows) == 2, 'got %r' % rows)
        check('scorecard: rows keyed on HELD ON plus run counter',
              [r.split('|')[1].strip() for r in rows]
              == ['2026-07-16 #1', '2026-07-16 #2'], 'got %r' % rows)
        check('scorecard: a Stage 2.5 re-check updates its own run row',
              all(r.split('|')[4].strip() == '0' for r in rows), 'got %r' % rows)
    finally:
        shutil.rmtree(tmp)


STYLE_GUIDE = """# Supervisor style guide — Test

## Wording preferences
<!-- Example:
- Say "outstanding" not "pending" for incomplete items
-->
- Say "updated drawings are to be provided" not "contractor will provide updated drawings" — the
  owner goes in the Action column
- Never use "it was discussed" — state what was decided or actioned directly
- Say "notified" not "alerted"

## Structural preferences
- Say "Decisions" not "Action Items"
"""


def test_warns_on_supervisor_banned_wording():
    """Say "X" not "Y" and Never use "Y" lines in the guide's Wording preferences are
    banned-phrase rules a script can see. Each hit is a warning naming the wanted phrase;
    comments, other sections and the Status cell are not read."""
    draft = (GOOD
             .replace('The invert level was confirmed', 'Brook Systems was Alerted that the '
                      'invert level was confirmed')
             .replace('Supporting detail that belongs', 'It was discussed that detail belongs')
             .replace('retention area.', 'retention area, which is pending.')
             .replace('is to be reissued', 'is to be reissued with the Action Items'))
    for layout in ('CLAUDE.md in Meeting Notes', 'CLAUDE.md at the project root'):
        tmp = tempfile.mkdtemp()
        try:
            notes = os.path.join(tmp, 'Meeting Notes')
            os.makedirs(notes)
            with open(os.path.join(notes, 'supervisor-style-guide-TEST.md'), 'w',
                      encoding='utf-8') as handle:
                handle.write(STYLE_GUIDE)
            claude = os.path.join(notes if layout.endswith('Meeting Notes') else tmp,
                                  'CLAUDE.md')
            with open(claude, 'w', encoding='utf-8') as handle:
                handle.write(CLAUDE_MD.replace(
                    '## Project roster',
                    '- Supervisor style guide: Meeting Notes/supervisor-style-guide-TEST.md'
                    '\n\n## Project roster'))
            path = os.path.join(tmp, 'draft.md')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(draft)
            out_json = os.path.join(tmp, 'out.json')
            proc = subprocess.run([sys.executable, CHECK, path, '--claude-md', claude,
                                   '--json', out_json], capture_output=True, text=True)
            out = (proc.stdout + proc.stderr).strip()
            with open(out_json, encoding='utf-8') as handle:
                found = [f for f in json.load(handle)['findings']
                         if f['code'] == 'SUPERVISOR_WORDING']
            messages = ' / '.join(f['message'] for f in found)
            check('%s: banned wording is a warning, not an error' % layout,
                  proc.returncode == 0 and all(f['level'] == 'WARN' for f in found), out)
            check('%s: "alerted" (any case) and "it was discussed" each warned once' % layout,
                  len(found) == 2 and '"notified"' in messages
                  and 'it was discussed' in messages, messages or out)
            check('%s: commented examples and other sections are not rules' % layout,
                  'pending' not in messages and 'Action Items' not in messages, messages)
        finally:
            shutil.rmtree(tmp)


def findings_for(draft_text):
    """Run the checker and return (exit code, output, every finding with its line)."""
    tmp = tempfile.mkdtemp()
    try:
        claude = os.path.join(tmp, 'CLAUDE.md')
        draft = os.path.join(tmp, 'draft.md')
        out_json = os.path.join(tmp, 'out.json')
        with open(claude, 'w', encoding='utf-8') as handle:
            handle.write(CLAUDE_MD)
        with open(draft, 'w', encoding='utf-8', newline='') as handle:
            handle.write(draft_text)
        proc = subprocess.run([sys.executable, CHECK, draft, '--claude-md', claude,
                               '--json', out_json], capture_output=True, text=True)
        found = []
        if os.path.exists(out_json):
            with open(out_json, encoding='utf-8') as handle:
                found = json.load(handle)['findings']
        return proc.returncode, (proc.stdout + proc.stderr).strip(), found
    finally:
        shutil.rmtree(tmp)


def line_of(text, needle):
    return next(n for n, l in enumerate(text.split('\n'), start=1) if needle in l)


def test_typed_number_validate_would_reject_is_an_error():
    """validate.py fails a paragraph whose text opens with a number of its own list depth
    (item 3 levels, bullet 4, subsection 2). repair.py no longer strips it, so the draft
    must be fixed before render: flag it at Stage 2.5/4.5 with its line."""
    cases = (
        ('item', GOOD.replace('A cross-section graphic is to be prepared',
                              '4.2.1 of the spec requires a cross-section graphic'),
         '4.2.1 of the spec'),
        ('bullet', GOOD.replace('- Supporting detail', '- 1.1.2.1 Supporting detail'),
         '1.1.2.1 Supporting'),
        ('subsection', GOOD.replace('### 1.1 Cross-Section', '### 1.1 1.1 Cross-Section'),
         '### 1.1 1.1'),
    )
    for label, text, needle in cases:
        code, out, found = findings_for(text)
        hits = [f for f in found if f['code'] == 'TYPED_NUMBER']
        check('typed number in %s: ERROR on draft line %d' % (label, line_of(text, needle)),
              code == 1 and len(hits) == 1 and hits[0]['level'] == 'ERROR'
              and hits[0]['line'] == line_of(text, needle), out)


def test_numbers_validate_accepts_are_not_flagged():
    """A number at another depth, or a bare integer, passes validate.py: no finding."""
    for label, text in (
            ('two-level number in an item',
             GOOD.replace('A cross-section graphic', '4.2 of the spec needs a graphic')),
            ('bare integer in an item',
             GOOD.replace('A cross-section graphic', '48 hours notice for a graphic')),
            ('three-level number mid-sentence',
             GOOD.replace('A cross-section graphic', 'Per 4.2.1 a cross-section graphic'))):
        code, out, found = findings_for(text)
        check('%s: no TYPED_NUMBER' % label,
              code == 0 and not any(f['code'] == 'TYPED_NUMBER' for f in found), out)


def test_typed_number_rule_matches_validate():
    """check_draft predicts validate.py's FAIL, so both must use the same pattern."""
    scripts = os.path.join(HERE, os.pardir, 'project-template', 'Meeting Notes', 'skills')
    sys.path[:0] = [os.path.join(scripts, 'draft-checks', 'scripts'),
                    os.path.join(scripts, 'docx-renderer', 'scripts')]
    try:
        import check_draft
        import validate
    finally:
        del sys.path[:2]
    check('check_draft and validate.py share one typed-number pattern',
          getattr(check_draft, 'LEADING_NUMBER_RE', None) is not None
          and check_draft.LEADING_NUMBER_RE.pattern == validate.LEADING_NUMBER_RE.pattern,
          '%r vs %r' % (getattr(check_draft, 'LEADING_NUMBER_RE', None),
                        validate.LEADING_NUMBER_RE))


def test_rejects_characters_word_cannot_store():
    """render.py Step 3 rejects these; Stage 4.5 must catch them two stages earlier."""
    for label, text, needle in (
            ('form feed in an item',
             GOOD.replace('The invert level', 'The\x0c invert level'), 'invert level'),
            ('escape in an attendee', GOOD.replace('Morgan Hughes', 'Morgan\x1bHughes'),
             'Morgan'),
            ('NUL in the title', GOOD.replace('Project Meeting', 'Project\x00 Meeting'),
             'TITLE:')):
        code, out, found = findings_for(text)
        hits = [f for f in found if f['code'] == 'CHARACTER']
        check('%s: CHARACTER ERROR on draft line %d' % (label, line_of(text, needle)),
              code == 1 and len(hits) == 1 and hits[0]['level'] == 'ERROR'
              and hits[0]['line'] == line_of(text, needle), out)
    code, out, found = findings_for(GOOD + '\n---PIPELINE NOTES---\nnote\x0c here\n')
    check('a control character in the pipeline notes is not flagged',
          not any(f['code'] == 'CHARACTER' for f in found), out)


if __name__ == '__main__':
    print('checker  : %s\n' % os.path.normpath(CHECK))
    for name, function in sorted(globals().items()):
        if name.startswith('test_') and callable(function):
            function()
    print('\n%d failure(s)' % len(failures))
    sys.exit(1 if failures else 0)
