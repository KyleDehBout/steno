"""Tests for scripts/sync_pipeline.py and the launcher that calls it.

Each case copies the script, global/ and project-template/ into a throwaway repo (the
script finds its sources from its own location) and builds a throwaway project in one of
the two live layouts:
  INNER: <root>/Meeting Notes/CLAUDE.md, <root>/Meeting Notes/skills/
  OUTER: <root>/CLAUDE.md,               <root>/Meeting Notes/skills/
HOME points at a temp folder, so --global never reaches the real ~/.claude.

Run:  python3 tests/test_sync_pipeline.py
"""
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, os.pardir))
SETUP = os.path.join(REPO, 'global', 'commands', 'setup-pipeline.md')

failures = []


def check(name, condition, detail=''):
    if condition:
        print('PASS  %s' % name)
    else:
        failures.append(name)
        print('FAIL  %s%s' % (name, ('\n      ' + detail) if detail else ''))


def build_repo(base):
    repo = os.path.join(base, 'repo')
    ignore = shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store', '.claude')
    for part in ('scripts', 'global', 'project-template'):
        shutil.copytree(os.path.join(REPO, part), os.path.join(repo, part), ignore=ignore)
    shutil.copytree(os.path.join(REPO, '.claude', 'commands'),
                    os.path.join(repo, '.claude', 'commands'))
    return repo


# Which instruction files a project holds. 'claude' is a project set up before AGENTS.md;
# 'both' is a current one, where CLAUDE.md is a stub that only points to AGENTS.md.
FILE_SETS = ('claude', 'agents', 'both')


def build_project(base, layout, repo, files='claude'):
    """A synced-once project: skills present, plus a stale check_draft.py to update."""
    root = os.path.join(base, layout)
    notes = os.path.join(root, 'Meeting Notes')
    os.makedirs(os.path.join(notes, 'skills', 'draft-checks', 'scripts'))
    home_dir = notes if layout == 'INNER' else root
    data = '# %s\n- Pipeline repo (for /sync-pipeline): %s\n' % (layout, repo)
    written = {'claude': {'CLAUDE.md': data},
               'agents': {'AGENTS.md': data},
               'both': {'AGENTS.md': data, 'CLAUDE.md': '@AGENTS.md\n'}}[files]
    for name, text in written.items():
        with open(os.path.join(home_dir, name), 'w', encoding='utf-8') as handle:
            handle.write(text)
    with open(os.path.join(notes, 'skills', 'draft-checks', 'scripts',
                           'check_draft.py'), 'w') as handle:
        handle.write('# stale\n')
    return root, notes


def add_backups(folder, count, start=1):
    """Old sync-shaped backups: a timestamped name holding only skills/."""
    names = []
    for index in range(start, start + count):
        name = '.pipeline-backup-202609%02d-120000' % index
        os.makedirs(os.path.join(folder, name, 'skills', 'skills', 'draft-checks'))
        names.append(name)
    return names


def backups(folder):
    return sorted(n for n in os.listdir(folder) if n.startswith('.pipeline-backup-'))


def run(repo, home, *args):
    env = dict(os.environ, HOME=home)
    result = subprocess.run(
        [sys.executable, os.path.join(repo, 'scripts', 'sync_pipeline.py')] + list(args),
        capture_output=True, text=True, env=env)
    return result.returncode, result.stdout + result.stderr


def synced(notes):
    with open(os.path.join(notes, 'skills', 'draft-checks', 'scripts',
                           'check_draft.py')) as handle:
        return handle.read() != '# stale\n'


def setup(layout, files='claude'):
    base = tempfile.mkdtemp()
    home = os.path.join(base, 'home')
    os.makedirs(home)
    repo = build_repo(base)
    root, notes = build_project(base, layout, repo, files)
    return base, home, repo, root, notes


def test_both_layouts_accept_root_and_meeting_notes_path():
    for layout in ('INNER', 'OUTER'):
        for which in ('root', 'notes'):
            for count in (0, 1, 2, 6):
                base, home, repo, root, notes = setup(layout)
                try:
                    old = add_backups(notes, count)
                    target = root if which == 'root' else notes
                    code, out = run(repo, home, '--project', target)
                    label = '%s %s path, %d backup(s)' % (layout, which, count)
                    check('%s: exits 0' % label, code == 0, out)
                    check('%s: live skills updated' % label, synced(notes), out)
                    check('%s: nothing written into an old backup' % label,
                          not any(os.path.exists(os.path.join(notes, b, 'skills',
                                                              'draft-checks', 'scripts'))
                                  for b in old if os.path.isdir(os.path.join(notes, b))),
                          out)
                finally:
                    shutil.rmtree(base)


def test_learning_form_is_delivered():
    """/learn's agent finds the form page and its generator in the project's skills."""
    base, home, repo, root, notes = setup('OUTER')
    try:
        code, out = run(repo, home, '--project', root)
        form = os.path.join(notes, 'skills', 'learning-form')
        check('learning-form: page and generator synced into the project',
              code == 0
              and os.path.isfile(os.path.join(form, 'assets', 'qa-session-form.html'))
              and os.path.isfile(os.path.join(form, 'scripts', 'generate_qa_form.py')), out)
    finally:
        shutil.rmtree(base)


def test_backup_is_not_nested():
    base, home, repo, root, notes = setup('INNER')
    try:
        code, out = run(repo, home, '--project', root)
        made = backups(notes)
        check('one backup made', code == 0 and len(made) == 1, out)
        backup = os.path.join(notes, made[0]) if made else ''
        check('backup holds skills/draft-checks, not skills/skills',
              os.path.isfile(os.path.join(backup, 'skills', 'draft-checks', 'scripts',
                                          'check_draft.py'))
              and not os.path.exists(os.path.join(backup, 'skills', 'skills')), out)
    finally:
        shutil.rmtree(base)


def test_retention_prunes_to_five():
    base, home, repo, root, notes = setup('OUTER')
    try:
        old = add_backups(notes, 6)
        code, out = run(repo, home, '--project', root)
        left = backups(notes)
        check('retention: exits 0', code == 0, out)
        check('retention: 5 left', len(left) == 5, str(left))
        check('retention: oldest two pruned', old[0] not in left and old[1] not in left,
              str(left))
        check('retention: new backup kept', any(n not in old for n in left), str(left))
        check('retention: reports what it pruned', 'pruned' in out and old[0] in out, out)
    finally:
        shutil.rmtree(base)


def test_retention_keep_flag_and_foreign_folders():
    base, home, repo, root, notes = setup('INNER')
    try:
        old = add_backups(notes, 3)
        # A hand-made backup with a flat layout, and a near-miss name: neither is ours.
        os.makedirs(os.path.join(notes, '.pipeline-backup-20260801-120000', 'style-rules'))
        os.makedirs(os.path.join(notes, '.pipeline-backup-old', 'skills'))
        code, out = run(repo, home, '--project', notes, '--keep', '2')
        left = backups(notes)
        check('--keep 2: exits 0', code == 0, out)
        check('--keep 2: older sync backups pruned',
              old[0] not in left and old[1] not in left and old[2] in left, str(left))
        check('--keep 2: hand-made backups left alone',
              '.pipeline-backup-20260801-120000' in left and '.pipeline-backup-old' in left,
              str(left))
        code, out = run(repo, home, '--project', notes, '--keep', '0')
        check('--keep 0 rejected', code == 2, out)
    finally:
        shutil.rmtree(base)


def test_dry_run_prunes_nothing():
    base, home, repo, root, notes = setup('OUTER')
    try:
        old = add_backups(notes, 7)
        code, out = run(repo, home, '--project', root, '--dry-run')
        check('dry run: exits 0', code == 0, out)
        check('dry run: no backup removed or added', backups(notes) == old, out)
        check('dry run: says what it would prune', 'would prune' in out.lower(), out)
    finally:
        shutil.rmtree(base)


def test_multiple_projects_all_synced():
    base, home, repo, inner_root, inner_notes = setup('INNER')
    try:
        outer_root, outer_notes = build_project(base, 'OUTER', repo)
        code, out = run(repo, home, '--project', inner_notes, '--project', outer_root)
        check('two --project flags: exits 0', code == 0, out)
        check('two --project flags: both synced', synced(inner_notes) and synced(outer_notes),
              out)
    finally:
        shutil.rmtree(base)


def write_projects_list(repo, lines):
    with open(os.path.join(repo, 'projects.txt'), 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines) + '\n')


def test_all_projects_syncs_every_listed_project():
    base, home, repo, inner_root, inner_notes = setup('INNER')
    try:
        outer_root, outer_notes = build_project(base, 'OUTER', repo)
        write_projects_list(repo, ['# installed projects', '', inner_root, outer_root])
        code, out = run(repo, home, '--all-projects')
        check('--all-projects: exits 0', code == 0, out)
        check('--all-projects: both listed projects synced',
              synced(inner_notes) and synced(outer_notes), out)
        check('--all-projects: one backup per project, not two',
              len(backups(inner_notes)) == 1 and len(backups(outer_notes)) == 1, out)
        # Naming a listed project again with --project must not sync it twice.
        code, out = run(repo, home, '--all-projects', '--project', inner_notes)
        check('--all-projects + --project: listed project not doubled',
              code == 0 and out.count('Project : ') == 2, out)
    finally:
        shutil.rmtree(base)


def test_all_projects_refuses_missing_or_bad_list():
    base, home, repo, root, notes = setup('OUTER')
    try:
        code, out = run(repo, home, '--all-projects')
        check('--all-projects, no projects.txt: refused',
              code != 0 and 'projects.txt' in out and not synced(notes), out)
        write_projects_list(repo, ['# nothing listed'])
        code, out = run(repo, home, '--all-projects')
        check('--all-projects, empty list: refused', code != 0 and not synced(notes), out)
        write_projects_list(repo, [root, os.path.join(base, 'gone')])
        code, out = run(repo, home, '--all-projects')
        check('--all-projects, one bad path: nothing written',
              code != 0 and not synced(notes), out)
    finally:
        shutil.rmtree(base)


def test_bad_project_stops_before_global():
    base, home, repo, root, notes = setup('OUTER')
    try:
        os.makedirs(os.path.join(base, 'empty'))
        code, out = run(repo, home, '--global', '--project', os.path.join(base, 'empty'))
        check('bad project: exits nonzero', code != 0, out)
        check('bad project: ~/.claude untouched',
              not os.path.exists(os.path.join(home, '.claude')), out)
    finally:
        shutil.rmtree(base)


def test_dot_dirs_never_match():
    """Only a backup holds skills/: the project path must still be refused."""
    base, home, repo, root, notes = setup('OUTER')
    try:
        bare = os.path.join(base, 'bare')
        os.makedirs(os.path.join(bare, '.pipeline-backup-20260901-120000', 'skills'))
        os.makedirs(os.path.join(bare, '.skills-backup-1', 'skills'))
        with open(os.path.join(bare, 'CLAUDE.md'), 'w') as handle:
            handle.write('x')
        code, out = run(repo, home, '--project', bare)
        check('dot-dirs only: refused', code != 0 and 'could not find' in out, out)
    finally:
        shutil.rmtree(base)


def launcher_text():
    with open(SETUP, encoding='utf-8') as handle:
        text = handle.read()
    match = re.search(r'Write the following content into it:\n```\n(.*?)```', text, re.S)
    return match.group(1)


def run_launcher(base, home, notes, layout, text=None):
    """Write the launcher into notes and run it with a stub `claude` on PATH."""
    launcher = os.path.join(notes, 'Claude - %s Launcher.command' % layout)
    with open(launcher, 'w') as handle:
        handle.write(text if text is not None else launcher_text())
    os.chmod(launcher, os.stat(launcher).st_mode | stat.S_IEXEC)
    # A stub `claude` on PATH: the launcher's last step, without starting Claude.
    stub_dir = os.path.join(base, 'bin')
    if not os.path.isdir(stub_dir):
        os.makedirs(stub_dir)
        with open(os.path.join(stub_dir, 'claude'), 'w') as handle:
            handle.write('#!/bin/sh\necho CLAUDE-STARTED\n')
        os.chmod(os.path.join(stub_dir, 'claude'), 0o755)
    env = dict(os.environ, HOME=home,
               PATH=stub_dir + os.pathsep + os.environ.get('PATH', ''))
    result = subprocess.run(['bash', launcher], capture_output=True, text=True, env=env)
    return result.returncode, result.stdout + result.stderr


def git(repo, home, *args):
    env = dict(os.environ, HOME=home, GIT_CONFIG_NOSYSTEM='1')
    return subprocess.run(['git', '-C', repo, '-c', 'user.name=t', '-c', 'user.email=t@t']
                          + list(args), capture_output=True, text=True, env=env)


def test_launcher_runs_sync_for_both_layouts():
    for layout in ('INNER', 'OUTER'):
        base, home, repo, root, notes = setup(layout)
        try:
            add_backups(notes, 3)
            code, out = run_launcher(base, home, notes, layout)
            check('launcher %s: exits 0 and reaches claude' % layout,
                  code == 0 and 'CLAUDE-STARTED' in out, out)
            check('launcher %s: live skills updated' % layout, synced(notes), out)
        finally:
            shutil.rmtree(base)


def test_every_instruction_file_set_syncs_and_launches():
    """AGENTS.md only, CLAUDE.md only (a project set up before AGENTS.md), and both: the
    sync finds the project and the launcher reads the repo path from the real file, never
    from the CLAUDE.md stub."""
    for layout in ('INNER', 'OUTER'):
        for files in FILE_SETS:
            label = '%s, %s' % (layout, files)
            base, home, repo, root, notes = setup(layout, files)
            try:
                code, out = run(repo, home, '--project', root)
                check('%s: sync finds the project' % label, code == 0 and synced(notes), out)
            finally:
                shutil.rmtree(base)
            base, home, repo, root, notes = setup(layout, files)
            try:
                code, out = run_launcher(base, home, notes, layout)
                check('%s: launcher syncs and reaches claude' % label,
                      code == 0 and 'CLAUDE-STARTED' in out and synced(notes), out)
            finally:
                shutil.rmtree(base)


def test_launcher_skips_sync_when_repo_has_uncommitted_synced_changes():
    """A half-made edit in the repo must never reach a project. The launcher says why,
    still opens Claude, and syncs again once the repo is clean."""
    for layout in ('INNER', 'OUTER'):
        base, home, repo, root, notes = setup(layout)
        try:
            git(repo, home, 'init', '-q')
            git(repo, home, 'add', '-A')
            git(repo, home, 'commit', '-q', '-m', 'base')
            check_draft = os.path.join(repo, 'project-template', 'Meeting Notes', 'skills',
                                       'draft-checks', 'scripts', 'check_draft.py')
            with open(check_draft, 'a') as handle:
                handle.write('# half-made edit\n')
            code, out = run_launcher(base, home, notes, layout)
            check('dirty repo %s: launcher still reaches claude' % layout,
                  code == 0 and 'CLAUDE-STARTED' in out, out)
            check('dirty repo %s: nothing synced' % layout,
                  not synced(notes) and not backups(notes)
                  and not os.path.exists(os.path.join(home, '.claude')), out)
            check('dirty repo %s: says sync was skipped and why' % layout,
                  'uncommitted' in out and 'skip' in out.lower(), out)
            # A change outside the synced paths does not block the sync.
            git(repo, home, 'checkout', '-q', '--', '.')
            with open(os.path.join(repo, 'notes.txt'), 'w') as handle:
                handle.write('scratch\n')
            code, out = run_launcher(base, home, notes, layout)
            check('clean synced paths %s: launcher syncs' % layout,
                  code == 0 and 'CLAUDE-STARTED' in out and synced(notes), out)
        finally:
            shutil.rmtree(base)


if __name__ == '__main__':
    print('script   : %s\n' % os.path.join(REPO, 'scripts', 'sync_pipeline.py'))
    for name, function in sorted(globals().items()):
        if name.startswith('test_') and callable(function):
            function()
    print('\n%d failure(s)' % len(failures))
    sys.exit(1 if failures else 0)
