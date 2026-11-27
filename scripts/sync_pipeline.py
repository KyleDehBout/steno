#!/usr/bin/env python3
"""Install or update the pipeline's global agents, commands and project skills.

Usage:
  sync_pipeline.py --global [--target claude|codex|gemini] [--dry-run]
  sync_pipeline.py --project "<path to project folder>" [--dry-run]
  sync_pipeline.py --global --project "<path>" [--dry-run]
  sync_pipeline.py --project "<path A>" --project "<path B>" [--keep N]
  sync_pipeline.py --global --all-projects [--dry-run]

Why this exists: /setup-pipeline installs by copy-if-absent. It skips any file that
already exists, so a new agent, command or skill script never reaches a machine that has
already been set up — the pipeline could only be updated by hand, which is how the live
project ended up with ad-hoc `.pipeline-backup-*` folders beside it.

This script overwrites, but never silently: every file it replaces is copied into a
timestamped backup folder first, and it prints exactly what changed.

  --global   installs the shared agents and commands for each --target tool (see
             TARGETS below for where each tool's files go)
             backup: <tool folder>/.pipeline-backup-<stamp>/, e.g. ~/.claude/...
  --target   claude (default), codex or gemini; repeat it to install for several.
             claude installs exactly what this script always has.
  --project  copies the skills that carry executable content (draft-checks,
             docx-renderer, pipeline-cleanup, learning-form) into
             <project>/Meeting Notes/skills/
             backup: <project>/Meeting Notes/.pipeline-backup-<stamp>/
             The path may be the project root or its Meeting Notes folder, and the
             flag may be repeated. Every path is resolved before anything is written.
  --all-projects  adds every project listed in the repo's projects.txt (one path per
             line, # comments), so a shared AGENT or CHECK change reaches all of them.
  --keep N   after a sync, keep the newest N (default 5) .pipeline-backup-<stamp>
             folders in each location and delete older ones. Only folders this script
             made are ever deleted: the exact name pattern, holding only the folders it
             backs up into.

What it never touches: a project's AGENTS.md or CLAUDE.md, style guide, memory log, scorecard,
formatter skill, style-rules, hard-rules, terminology, or anything under
docx-renderer/references/. Those are project-owned and carry the supervisor's rules.

Exit codes: 0 = done (or nothing to do), 1 = a copy failed, 2 = bad usage.
"""
import argparse
import filecmp
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROJECTS_LIST = REPO / 'projects.txt'

# A project's instruction file: AGENTS.md, or CLAUDE.md in a project set up before it.
INSTRUCTION_FILES = ('AGENTS.md', 'CLAUDE.md')

# Skills whose content is executable or contract-like: the pipeline owns these, and a
# project that keeps an old copy runs old logic. Skills holding project rules are absent
# from this list on purpose.
PROJECT_SKILLS = ('draft-checks', 'docx-renderer', 'pipeline-cleanup', 'learning-form')

# Project-owned paths inside a synced skill, as (skill, subfolder) pairs. Only the
# docx-renderer's references are project-owned: they are rendered once from the project's
# own branded .docx and edited by hand afterwards. draft-checks/references holds the
# draft format contract, which is pipeline-owned and must be delivered — skipping every
# folder named "references" silently left every project without it.
SKIP_WITHIN_SKILL = (('docx-renderer', 'references'),)

# A backup folder this script made: its exact name, and the top-level folders it can hold
# in each location. A hand-made backup with any other shape is never pruned.
BACKUP_NAME = re.compile(r'^\.pipeline-backup-\d{8}-\d{6}$')
GLOBAL_BACKUP_PARTS = {'agents', 'commands', 'skills', '.claude'}

# Where each tool keeps its user-level files, checked against each tool's docs in
# November 2026:
#   Claude Code  ~/.claude/agents/*.md sub-agents, ~/.claude/commands/*.md slash commands
#   Codex CLI    $CODEX_HOME (default ~/.codex); sub-agents are TOML files in agents/
#                with name, description and developer_instructions. Its custom prompts
#                (~/.codex/prompts) are deprecated in favour of skills, so commands are
#                not installed there.
#   Gemini CLI   ~/.gemini/agents/*.md sub-agents with name and description frontmatter,
#                the same shape as ours, so the files are copied as they are.
# Skills (a folder holding SKILL.md, the open Agent Skills format) are built from the
# commands: Claude Code reads ~/.claude/skills, Codex reads ~/.agents/skills (not under
# its own home), Gemini CLI reads ~/.gemini/skills.
# Each kind maps to (base, folder, format): base 'tool' is the tool's home, 'HOME' the
# user's home. A kind is absent when the tool gets nothing of it.
TARGETS = {
    'claude': {'home': ('HOME', '.claude'),
               'kinds': {'agents': ('tool', 'agents', 'md'),
                         'commands': ('tool', 'commands', 'md'),
                         'skills': ('tool', 'skills', 'skill')}},
    'codex': {'home': ('CODEX_HOME', '.codex'),
              'kinds': {'agents': ('tool', 'agents', 'codex-toml'),
                        'skills': ('HOME', '.agents/skills', 'skill')}},
    'gemini': {'home': ('HOME', '.gemini'),
               'kinds': {'agents': ('tool', 'agents', 'md'),
                         'skills': ('tool', 'skills', 'skill')}},
}

# A command's skill is named for the pipeline, so it never collides with a user's own
# skill called "status" or "audit".
SKILL_PREFIX = 'steno-'


def target_home(target, home):
    """The tool's user folder. A tool whose home has its own variable honours it."""
    variable, folder = TARGETS[target]['home']
    if variable != 'HOME' and os.environ.get(variable):
        return Path(os.environ[variable]).expanduser()
    return home / folder


def split_frontmatter(text):
    """(fields, body) for a file that opens with a --- block of `key: value` lines.
    A value written `key: >` folds the indented lines under it into one line."""
    if not text.startswith('---\n'):
        return {}, text
    end = text.index('\n---\n', 4)
    fields, key = {}, None
    for line in text[4:end].splitlines():
        if line[:1] in (' ', '\t') and key:
            fields[key] = (fields[key] + ' ' + line.strip()).strip()
        elif ':' in line:
            key, _, value = line.partition(':')
            key, value = key.strip(), value.strip()
            if len(value) > 1 and value[0] == value[-1] == '"':
                value = json.loads(value)
            fields[key] = '' if value in ('>', '|', '>-', '|-') else value
    return fields, text[end + 5:].lstrip('\n')


def toml_string(value):
    """A TOML multi-line basic string holding value exactly."""
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return '"""\n' + escaped + '"""'


def command_skill(source):
    """(skill folder name, SKILL.md text) built from one command file. The command file
    is the only copy anyone edits; the skill is rebuilt from it on every sync."""
    fields, body = split_frontmatter(source.read_text(encoding='utf-8'))
    if not fields.get('description'):
        raise ValueError('%s has no description in its frontmatter' % source.name)
    name = SKILL_PREFIX + source.stem
    return name, ('---\nname: %s\ndescription: %s\n---\n\n'
                  '<!-- Built from global/commands/%s by scripts/sync_pipeline.py. '
                  'Edit that file, not this one. -->\n\n%s'
                  % (name, json.dumps(fields['description'], ensure_ascii=False),
                     source.name, body))


def codex_agent(text):
    """A Codex sub-agent file (TOML) built from one of our agent .md files."""
    fields, body = split_frontmatter(text)
    return ('name = %s\ndescription = %s\ndeveloper_instructions = %s\n'
            % (toml_string(fields['name']).replace('\n', '', 1),
               toml_string(fields.get('description', '')).replace('\n', '', 1),
               toml_string(body)))
PROJECT_BACKUP_PARTS = {'skills'}


def stamp():
    return datetime.now().strftime('%Y%m%d-%H%M%S')


class Sync:
    def __init__(self, dry_run):
        self.dry_run = dry_run
        self.copied = []
        self.updated = []
        self.unchanged = 0
        self.failed = []

    def copy(self, source, target, backup_root, relative, content=None):
        """Copy one file, backing up any file it replaces. With content, write that
        text instead of the source's bytes (a file converted for another tool)."""
        if target.exists() and (
                target.read_text(encoding='utf-8') == content if content is not None
                else filecmp.cmp(source, target, shallow=False)):
            self.unchanged += 1
            return

        action = 'update' if target.exists() else 'add'
        if self.dry_run:
            (self.updated if action == 'update' else self.copied).append(relative)
            return

        try:
            if target.exists():
                backup = backup_root / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
            target.parent.mkdir(parents=True, exist_ok=True)
            if content is None:
                shutil.copy2(source, target)
            else:
                target.write_text(content, encoding='utf-8')
        except OSError as error:
            self.failed.append('%s: %s' % (relative, error))
            return

        (self.updated if action == 'update' else self.copied).append(relative)


def sync_global(sync, home, target='claude'):
    tool_home = target_home(target, home)
    backup_root = tool_home / ('.pipeline-backup-%s' % stamp())

    for kind in ('agents', 'commands', 'skills'):
        if kind not in TARGETS[target]['kinds']:
            continue
        base, folder, form = TARGETS[target]['kinds'][kind]
        root = tool_home if base == 'tool' else home
        # Skills are built from the commands; every other kind has its own folder.
        source_dir = REPO / 'global' / ('commands' if kind == 'skills' else kind)
        if not source_dir.is_dir():
            continue
        for source in sorted(source_dir.glob('*.md')):
            if form == 'skill':
                name, content = command_skill(source)
                place = Path(folder) / name / 'SKILL.md'
                label = Path('skills') / name / 'SKILL.md'
            elif form == 'codex-toml':
                place = Path(folder) / (source.stem + '.toml')
                content = codex_agent(source.read_text(encoding='utf-8'))
                label = place
            else:
                place, content = Path(folder) / source.name, None
                label = place
            sync.copy(source, root / place, backup_root, label, content)

    return backup_root


def sync_repo_local(sync, backup_root):
    """Keep the repo's own .claude/commands/ copies in step with global/commands/.

    The repo carries a duplicate of setup-pipeline.md so /setup-pipeline works inside the
    pipeline repo itself. A directory-local command wins over the installed one, so a
    stale duplicate silently scaffolds new projects with the old steps.
    """
    local = REPO / '.claude' / 'commands'
    if not local.is_dir():
        return
    for target in sorted(local.glob('*.md')):
        source = REPO / 'global' / 'commands' / target.name
        if source.is_file():
            relative = Path('.claude/commands') / target.name
            sync.copy(source, target, backup_root, relative)


def is_notes_folder(folder, project_root):
    """The Meeting Notes folder holds skills/, with the project instruction file beside
    it or in the project root above it (Style B keeps it inside Meeting Notes, Style A at
    the root). That file is AGENTS.md, or CLAUDE.md in a project set up before it."""
    return ((folder / 'skills').is_dir()
            and any((place / name).is_file()
                    for place in (folder, project_root) for name in INSTRUCTION_FILES))


def find_notes(project):
    """Accept the project root or its Meeting Notes folder. Dot-folders are never
    candidates: each .pipeline-backup-* holds a skills/ folder of its own."""
    if is_notes_folder(project, project.parent):
        return project
    candidates = [child for child in sorted(project.iterdir())
                  if child.is_dir() and not child.name.startswith('.')
                  and is_notes_folder(child, project)]
    if len(candidates) != 1:
        sys.exit('error: could not find the Meeting Notes folder in %s' % project)
    return candidates[0]


def listed_projects():
    """The installed projects named in projects.txt, in file order."""
    if not PROJECTS_LIST.is_file():
        sys.exit('error: --all-projects needs %s' % PROJECTS_LIST)
    paths = [line.strip() for line in PROJECTS_LIST.read_text(encoding='utf-8').splitlines()
             if line.strip() and not line.strip().startswith('#')]
    if not paths:
        sys.exit('error: no projects listed in %s' % PROJECTS_LIST)
    return paths


def sync_project(sync, notes):
    backup_root = notes / ('.pipeline-backup-%s' % stamp())
    template = REPO / 'project-template' / 'Meeting Notes' / 'skills'

    for skill in PROJECT_SKILLS:
        source_dir = template / skill
        if not source_dir.is_dir():
            continue
        for source in sorted(source_dir.rglob('*')):
            if not source.is_file() or source.name.startswith('.'):
                continue
            relative = source.relative_to(template)
            if tuple(relative.parts[:2]) in SKIP_WITHIN_SKILL:
                continue
            if source.suffix == '.pyc':
                continue
            sync.copy(source, notes / 'skills' / relative,
                      backup_root, Path('skills') / relative)

    return backup_root


def prune_backups(folder, parts, keep, dry_run):
    """Delete all but the newest `keep` sync-made backups in folder. Returns the names."""
    if not folder.is_dir():
        return []
    ours = sorted(path for path in folder.iterdir()
                  if path.is_dir() and BACKUP_NAME.match(path.name)
                  and {child.name for child in path.iterdir()} <= parts)
    old = ours[:-keep]
    if not dry_run:
        for path in old:
            shutil.rmtree(path)
    return [path.name for path in old]


def report(sync, backups):
    for path in sync.copied:
        print('  added    %s' % path)
    for path in sync.updated:
        print('  updated  %s' % path)
    if sync.unchanged:
        print('  %d file(s) already current' % sync.unchanged)
    for failure in sync.failed:
        print('  FAILED   %s' % failure)

    if sync.dry_run:
        print('\nDry run — nothing was written.')
        return 1 if sync.failed else 0

    for backup in backups:
        if backup.exists():
            print('\nReplaced files backed up to: %s' % backup)

    if sync.failed:
        print('\n%d file(s) failed to copy.' % len(sync.failed))
        return 1
    if not sync.copied and not sync.updated:
        print('\nNothing to do — everything is already current.')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Install or update pipeline agents, commands and skills.')
    parser.add_argument('--global', dest='do_global', action='store_true',
                        help='install the shared agents and commands for each --target')
    parser.add_argument('--target', action='append', choices=sorted(TARGETS),
                        help='tool to install for: claude (default), codex or gemini; '
                             'repeatable')
    parser.add_argument('--project', action='append', default=[],
                        help='project root or its Meeting Notes folder (repeatable)')
    parser.add_argument('--all-projects', action='store_true',
                        help="also sync every project listed in the repo's projects.txt")
    parser.add_argument('--dry-run', action='store_true',
                        help='print what would change and write nothing')
    parser.add_argument('--keep', type=int, default=5,
                        help='sync-made backups to keep per location (default 5)')
    args = parser.parse_args(argv)

    if not args.do_global and not args.project and not args.all_projects:
        parser.error('pass --global, --project <path>, --all-projects, or a mix')
    if args.keep < 1:
        parser.error('--keep must be 1 or more')
    if args.target and not args.do_global:
        parser.error('--target picks where --global installs; pass --global with it')
    targets = list(dict.fromkeys(args.target or ['claude']))

    # Resolve every project first, so a bad path stops before anything is written.
    notes_folders = []
    paths = args.project + (listed_projects() if args.all_projects else [])
    for path in paths:
        project = Path(path).expanduser().resolve()
        if not project.is_dir():
            sys.exit('error: project folder not found: %s' % project)
        notes = find_notes(project)
        if notes not in notes_folders:
            notes_folders.append(notes)

    sync = Sync(args.dry_run)
    backups = []
    prune = []

    if args.do_global:
        for target in targets:
            print('Global  : %s (%s)' % (target_home(target, Path.home()), target))
            backup_root = sync_global(sync, Path.home(), target)
            backups.append(backup_root)
            if target == 'claude':
                # The repo's own .claude/commands copy exists for Claude Code only.
                sync_repo_local(sync, backup_root)
            prune.append((backup_root.parent, GLOBAL_BACKUP_PARTS))

    for notes in notes_folders:
        print('Project : %s' % notes)
        backups.append(sync_project(sync, notes))
        prune.append((notes, PROJECT_BACKUP_PARTS))

    print('')
    code = report(sync, backups)
    if code == 0:
        for folder, parts in prune:
            for name in prune_backups(folder, parts, args.keep, args.dry_run):
                print('%s old backup: %s' % (
                    'Would prune' if args.dry_run else 'pruned', folder / name))
    return code


if __name__ == '__main__':
    sys.exit(main())
