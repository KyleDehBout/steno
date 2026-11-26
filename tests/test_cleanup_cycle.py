"""Shell-level tests for the end-of-cycle cleanup script.

Each case builds a throwaway project tree, copies cleanup-cycle.sh into it (the script
finds the project from its own location), runs it and inspects what is left. Two
meetings in flight is the case that matters: /learn of the first must not delete the
second's transcript, draft or stage files.

Run:  python3 tests/test_cleanup_cycle.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(
    HERE, os.pardir, 'project-template', 'Meeting Notes',
    'skills', 'pipeline-cleanup', 'cleanup-cycle.sh')

ARCHIVED = 'Test - Meeting Notes #15.docx'
A = 'transcript-2026-10-08'
B = 'transcript-2026-10-15'

failures = []


def check(name, condition, detail=''):
    if condition:
        print('PASS  %s' % name)
    else:
        failures.append(name)
        print('FAIL  %s%s' % (name, ('\n      ' + detail) if detail else ''))


def write(path, text='x'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)


def build_project():
    """Meeting A has been issued and archived; meeting B was processed after it and
    is still waiting for its own /learn."""
    root = tempfile.mkdtemp()
    notes = os.path.join(root, 'Meeting Notes')
    dest = os.path.join(notes, 'skills', 'pipeline-cleanup', 'cleanup-cycle.sh')
    os.makedirs(os.path.dirname(dest))
    shutil.copy(SCRIPT, dest)
    for folder in ('intake', 'output', 'transcripts', 'Archive'):
        os.makedirs(os.path.join(notes, folder))
    write(os.path.join(notes, 'Archive', ARCHIVED), 'issued')
    write(os.path.join(notes, 'intake', '.DS_Store'))
    for stem, date in ((A, '2026-10-08'), (B, '2026-10-15')):
        write(os.path.join(notes, 'transcripts', stem + '.txt'))
        draft = 'Test-Meeting-Notes-%s.docx' % date
        write(os.path.join(notes, 'output', draft))
        run = os.path.join(notes, 'working', 'runs', stem)
        write(os.path.join(run, 'stage-5.md'))
        write(os.path.join(run, 'run.txt'),
              'transcript: %s.txt\noutput: %s\n' % (stem, draft))
    write(os.path.join(notes, 'working', 'render', 'body.xml'))
    write(os.path.join(root, 'qa-session.html'))
    return root, notes, dest


def run(script, *args):
    result = subprocess.run(['bash', script] + list(args),
                            capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def exists(notes, *parts):
    return os.path.exists(os.path.join(notes, *parts))


def test_cleanup_of_one_meeting_leaves_the_other_intact():
    root, notes, script = build_project()
    try:
        code, out = run(script, ARCHIVED, '--stem', A)
        check('cleanup --stem A exits 0', code == 0, out)
        check('A: transcript deleted', not exists(notes, 'transcripts', A + '.txt'), out)
        check('A: output draft deleted',
              not exists(notes, 'output', 'Test-Meeting-Notes-2026-10-08.docx'), out)
        check('A: run folder deleted', not exists(notes, 'working', 'runs', A), out)
        check('B: transcript kept', exists(notes, 'transcripts', B + '.txt'), out)
        check('B: output draft kept',
              exists(notes, 'output', 'Test-Meeting-Notes-2026-10-15.docx'), out)
        check('B: run folder kept',
              exists(notes, 'working', 'runs', B, 'stage-5.md'), out)
        check('render scratch kept while another run is in flight',
              exists(notes, 'working', 'render', 'body.xml'), out)
        check('review form deleted', not os.path.exists(
            os.path.join(root, 'qa-session.html')), out)
        check('archive untouched', exists(notes, 'Archive', ARCHIVED), out)

        code, out = run(script, ARCHIVED, '--stem', B)
        check('cleanup --stem B exits 0', code == 0, out)
        check('B: everything cleared',
              not exists(notes, 'transcripts', B + '.txt')
              and not exists(notes, 'working', 'runs', B)
              and not os.listdir(os.path.join(notes, 'output')), out)
        check('render scratch cleared once no run is left',
              not exists(notes, 'working', 'render'), out)
    finally:
        shutil.rmtree(root)


def test_stale_archive_name_is_still_refused():
    """A stale archive name from an earlier cycle passes the archive check, so the
    intake file still sitting there is what proves the move did not happen."""
    root, notes, script = build_project()
    try:
        write(os.path.join(notes, 'intake', 'final.docx'))
        code, out = run(script, ARCHIVED, '--stem', A)
        check('stale archive name with a file in intake exits 1', code == 1, out)
        check('stale archive name deletes nothing',
              exists(notes, 'transcripts', A + '.txt')
              and exists(notes, 'working', 'runs', A)
              and exists(notes, 'intake', 'final.docx'), out)
    finally:
        shutil.rmtree(root)


def test_missing_archive_is_refused():
    root, notes, script = build_project()
    try:
        code, out = run(script, 'Test - Meeting Notes #99.docx', '--stem', A)
        check('archive file not present exits 1', code == 1, out)
        check('archive file not present deletes nothing',
              exists(notes, 'working', 'runs', A), out)
    finally:
        shutil.rmtree(root)


def test_stem_is_required_and_must_match():
    root, notes, script = build_project()
    try:
        code, out = run(script, ARCHIVED)
        check('no --stem is bad usage', code == 2, out)
        code, out = run(script, ARCHIVED, '--stem', '../' + A)
        check('a stem with a path separator is bad usage', code == 2, out)
        code, out = run(script, ARCHIVED, '--stem', 'transcript-1999-01-01')
        check('a stem that matches nothing exits 1', code == 1, out)
        check('a stem that matches nothing deletes nothing',
              exists(notes, 'working', 'runs', A)
              and os.path.exists(os.path.join(root, 'qa-session.html')), out)
    finally:
        shutil.rmtree(root)


def test_stem_does_not_match_a_longer_name():
    root, notes, script = build_project()
    try:
        write(os.path.join(notes, 'transcripts', A + '.v2.txt'))
        code, out = run(script, ARCHIVED, '--stem', A)
        check('a transcript whose stem only starts with A is kept',
              code == 0 and exists(notes, 'transcripts', A + '.v2.txt'), out)
    finally:
        shutil.rmtree(root)


def test_dry_run_deletes_nothing():
    root, notes, script = build_project()
    try:
        code, out = run(script, ARCHIVED, '--stem', A, '--dry-run')
        check('dry run exits 0', code == 0, out)
        check('dry run deletes nothing',
              exists(notes, 'transcripts', A + '.txt')
              and exists(notes, 'working', 'runs', A)
              and exists(notes, 'output', 'Test-Meeting-Notes-2026-10-08.docx'), out)
    finally:
        shutil.rmtree(root)


def test_unrecorded_output_is_left_while_another_meeting_is_in_flight():
    """A run folder with no output line (an interrupted run) cannot say which draft
    is its own, so nothing in output/ is safe to delete while B is still there."""
    root, notes, script = build_project()
    try:
        write(os.path.join(notes, 'working', 'runs', A, 'run.txt'),
              'transcript: %s.txt\n' % A)
        code, out = run(script, ARCHIVED, '--stem', A)
        check('unrecorded output: exits 0', code == 0, out)
        check('unrecorded output: both drafts left in place',
              len(os.listdir(os.path.join(notes, 'output'))) == 2, out)
        check('unrecorded output: says so', 'output' in out and 'left' in out, out)
    finally:
        shutil.rmtree(root)


def test_single_meeting_without_a_run_folder_still_clears():
    """A run that never got as far as its run folder (or one from before run folders
    existed) is still cleared when it is the only meeting in flight."""
    root, notes, script = build_project()
    try:
        shutil.rmtree(os.path.join(notes, 'working', 'runs'))
        os.remove(os.path.join(notes, 'transcripts', B + '.txt'))
        os.remove(os.path.join(notes, 'output', 'Test-Meeting-Notes-2026-10-15.docx'))
        code, out = run(script, ARCHIVED, '--stem', A)
        check('no run folder: exits 0', code == 0, out)
        check('no run folder: transcript, lone draft and render scratch cleared',
              not os.listdir(os.path.join(notes, 'transcripts'))
              and not os.listdir(os.path.join(notes, 'output'))
              and not exists(notes, 'working', 'render'), out)
    finally:
        shutil.rmtree(root)


def read(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def tests_dir(root, *parts):
    return os.path.join(root, 'pipeline-tests', *parts)


def test_pair_is_kept_for_the_regression_set():
    """Decision 7: the transcript and issued .docx go to pipeline-tests/<HELD ON>/,
    outside Meeting Notes, in the layout /test-pipeline reads."""
    root, notes, script = build_project()
    try:
        write(os.path.join(notes, 'working', 'runs', A, 'scorecard-row.txt'),
              '2026-10-08 #1\n')
        code, out = run(script, ARCHIVED, '--stem', A)
        case = tests_dir(root, '2026-10-08')
        check('pair kept: exits 0', code == 0, out)
        check('pair kept: transcript in transcript/',
              os.path.isfile(os.path.join(case, 'transcript', A + '.txt')), out)
        check('pair kept: issued.docx is the archived file',
              read(os.path.join(case, 'issued.docx')) == 'issued', out)
        check('pair kept: the transcript itself is still deleted',
              not exists(notes, 'transcripts', A + '.txt'), out)
        check('pair kept: nothing for B', os.path.isdir(tests_dir(root))
              and sorted(os.listdir(tests_dir(root))) == ['2026-10-08'], out)
    finally:
        shutil.rmtree(root)


def test_pair_without_a_held_on_date_is_named_by_stem():
    root, notes, script = build_project()
    try:
        code, out = run(script, ARCHIVED, '--stem', A)
        check('undated pair: kept under undated-<stem>',
              code == 0 and os.path.isfile(
                  tests_dir(root, 'undated-' + A, 'transcript', A + '.txt')), out)
    finally:
        shutil.rmtree(root)


def test_only_the_newest_eight_cases_it_made_are_kept():
    root, notes, script = build_project()
    try:
        write(os.path.join(notes, 'working', 'runs', A, 'scorecard-row.txt'),
              '2026-10-08 #1\n')
        made = ['2026-0%d-01' % month for month in range(1, 10)]   # 9 older cases
        for name in made:
            write(tests_dir(root, name, 'issued.docx'))
            write(tests_dir(root, name, '.from-cleanup'), name + '\n')
        write(tests_dir(root, '2026-01-02', 'issued.docx'))        # hand-picked
        write(tests_dir(root, 'my-favourite', 'issued.docx'))
        write(tests_dir(root, 'my-favourite', '.from-cleanup'), '2020-01-01\n')
        write(tests_dir(root, '.runs', 'x', 'score.json'))
        code, out = run(script, ARCHIVED, '--stem', A)
        left = sorted(os.listdir(tests_dir(root)))
        check('prune: exits 0', code == 0, out)
        check('prune: the newest 8 cases it made are kept, the 2 oldest pruned',
              [name for name in left if name in made + ['2026-10-08']]
              == made[2:] + ['2026-10-08'], 'left %r\n%s' % (left, out))
        check('prune: a folder without the marker is never pruned',
              '2026-01-02' in left, 'left %r' % left)
        check('prune: a marked folder whose name does not match is never pruned',
              'my-favourite' in left and '.runs' in left, 'left %r' % left)
    finally:
        shutil.rmtree(root)


def test_a_hand_made_case_is_not_overwritten():
    root, notes, script = build_project()
    try:
        write(os.path.join(notes, 'working', 'runs', A, 'scorecard-row.txt'),
              '2026-10-08 #1\n')
        write(tests_dir(root, '2026-10-08', 'issued.docx'), 'hand-picked')
        code, out = run(script, ARCHIVED, '--stem', A)
        check('hand-made case: left as it was, cleanup still runs',
              code == 0 and read(tests_dir(root, '2026-10-08', 'issued.docx'))
              == 'hand-picked'
              and not exists(notes, 'working', 'runs', A), out)
    finally:
        shutil.rmtree(root)


def test_a_reissued_meeting_replaces_its_case_and_drops_the_baseline():
    root, notes, script = build_project()
    try:
        write(os.path.join(notes, 'working', 'runs', A, 'scorecard-row.txt'),
              '2026-10-08 #2\n')
        case = tests_dir(root, '2026-10-08')
        write(os.path.join(case, '.from-cleanup'), '2026-10-08\n')
        write(os.path.join(case, 'transcript', 'old-stem.txt'))
        write(os.path.join(case, 'baseline.json'), '{}')
        code, out = run(script, ARCHIVED, '--stem', A)
        check('re-issue: transcript replaced, stale baseline removed',
              code == 0 and os.path.isdir(os.path.join(case, 'transcript'))
              and os.listdir(os.path.join(case, 'transcript')) == [A + '.txt']
              and not os.path.exists(os.path.join(case, 'baseline.json')), out)
    finally:
        shutil.rmtree(root)


def test_pdf_or_dry_run_keeps_no_case():
    root, notes, script = build_project()
    try:
        write(os.path.join(notes, 'Archive', 'Test - Meeting Notes #15.pdf'), 'pdf')
        code, out = run(script, ARCHIVED, '--stem', A, '--dry-run')
        check('dry run: no pipeline-tests folder written',
              code == 0 and not os.path.exists(tests_dir(root)), out)
        code, out = run(script, 'Test - Meeting Notes #15.pdf', '--stem', A)
        check('issued PDF: no case kept, cleanup still runs',
              code == 0 and not os.path.exists(tests_dir(root))
              and not exists(notes, 'working', 'runs', A), out)
    finally:
        shutil.rmtree(root)


if __name__ == '__main__':
    print('script   : %s\n' % os.path.normpath(SCRIPT))
    for name, function in sorted(globals().items()):
        if name.startswith('test_') and callable(function):
            function()
    print('\n%d failure(s)' % len(failures))
    sys.exit(1 if failures else 0)
