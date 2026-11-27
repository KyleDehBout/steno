"""First-run setup: the manual form command, the Claude Code hook, and its marker.

Each case runs against a copy of the repo's scripts and form in a temporary folder, with
STENO_NO_BROWSER set so no browser ever opens.

Run:  python3 tests/test_first_run.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, os.pardir))
failures = []


def check(name, condition, detail=''):
    if condition:
        print('PASS  %s' % name)
    else:
        failures.append(name)
        print('FAIL  %s%s' % (name, ('\n      ' + detail) if detail else ''))


def clone():
    """A fresh clone's worth of what first-run setup needs, and nothing set up yet."""
    base = tempfile.mkdtemp()
    for part in ('scripts', 'assets'):
        shutil.copytree(os.path.join(REPO, part), os.path.join(base, part),
                        ignore=shutil.ignore_patterns('__pycache__'))
    return base


def env():
    found = dict(os.environ, STENO_NO_BROWSER='1')
    found.pop('MNP_SKIP_FIRST_RUN', None)
    return found


def hook(base, **extra):
    result = subprocess.run([sys.executable, os.path.join(base, 'scripts',
                                                          'first_run_check.py')],
                            capture_output=True, text=True, env=dict(env(), **extra))
    return result.returncode, result.stdout.strip()


def write_marker(base, relative):
    path = os.path.join(base, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump({'setupComplete': True}, handle)


def test_manual_command_writes_the_form():
    """The documented way to start setup in every tool."""
    base = clone()
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(base, 'scripts', 'generate_setup_form.py'),
             '--out', base, '--prefill', '{"projectName": "Harbour Point"}'],
            capture_output=True, text=True, env=env())
        lines = result.stdout.splitlines()
        form = os.path.join(base, 'setup-session.html')
        check('manual: exits 0, form path then "not opened" on stdout',
              result.returncode == 0 and len(lines) == 2
              and os.path.realpath(lines[0]) == os.path.realpath(form)
              and lines[1] == 'not opened', result.stdout)
        with open(form, encoding='utf-8') as handle:
            html = handle.read()
        check('manual: the prefill is in the form and the placeholder is gone',
              'Harbour Point' in html and '__PREFILL__' not in html)
        check('manual: tells the person to paste the block into their agent',
              'paste it into' in result.stderr and 'Codex' in result.stderr
              and 'Gemini' in result.stderr, result.stderr)
    finally:
        shutil.rmtree(base)


def test_hook_fires_on_a_fresh_clone():
    base = clone()
    try:
        code, out = hook(base)
        context = json.loads(out)['hookSpecificOutput']['additionalContext'] if out else ''
        check('fresh clone: hook opens the form and hands Claude the setup context',
              code == 0 and 'FIRST RUN' in context
              and os.path.isfile(os.path.join(base, 'setup-session.html')), out)
    finally:
        shutil.rmtree(base)


def test_either_marker_keeps_the_hook_quiet():
    for relative, label in ((os.path.join('.steno', 'setup-state.json'), 'new marker'),
                            (os.path.join('.claude', '.setup-state.json'),
                             'old marker (a clone set up before .steno/)')):
        base = clone()
        try:
            write_marker(base, relative)
            code, out = hook(base)
            check('%s: hook stays quiet and writes no form' % label,
                  code == 0 and out == ''
                  and not os.path.exists(os.path.join(base, 'setup-session.html')), out)
        finally:
            shutil.rmtree(base)
    base = clone()
    try:
        code, out = hook(base, MNP_SKIP_FIRST_RUN='1')
        check('MNP_SKIP_FIRST_RUN: hook stays quiet', code == 0 and out == '', out)
    finally:
        shutil.rmtree(base)


def test_setup_install_never_replaces_a_file():
    """Setup's Step 2 installs with --only-missing: absent files are added, an existing
    file is left exactly as it is and reported as skipped."""
    base = tempfile.mkdtemp()
    try:
        repo = os.path.join(base, 'repo')
        for part in ('scripts', 'global', 'project-template'):
            shutil.copytree(os.path.join(REPO, part), os.path.join(repo, part),
                            ignore=shutil.ignore_patterns('__pycache__'))
        home = os.path.join(base, 'home')
        edited = os.path.join(home, '.gemini', 'agents', 'formatter.md')
        os.makedirs(os.path.dirname(edited))
        with open(edited, 'w') as handle:
            handle.write('edited by hand\n')
        result = subprocess.run(
            [sys.executable, os.path.join(repo, 'scripts', 'sync_pipeline.py'), '--global',
             '--target', 'gemini', '--only-missing'],
            capture_output=True, text=True, env=dict(os.environ, HOME=home))
        out = result.stdout + result.stderr
        with open(edited) as handle:
            kept = handle.read() == 'edited by hand\n'
        check('--only-missing: exits 0 and keeps the edited file', result.returncode == 0
              and kept, out)
        check('--only-missing: reports it as skipped', 'skipped  agents/formatter.md' in out,
              out)
        check('--only-missing: adds what was absent, and backs nothing up',
              os.path.isfile(os.path.join(home, '.gemini', 'agents', 'draft-reviewer.md'))
              and os.path.isfile(os.path.join(home, '.gemini', 'skills', 'steno-status',
                                              'SKILL.md'))
              and not [n for n in os.listdir(os.path.join(home, '.gemini'))
                       if n.startswith('.pipeline-backup-')], out)
    finally:
        shutil.rmtree(base)


if __name__ == '__main__':
    for name, function in sorted(globals().items()):
        if name.startswith('test_') and callable(function):
            function()
    print('\n%d failure(s)' % len(failures))
    sys.exit(1 if failures else 0)
