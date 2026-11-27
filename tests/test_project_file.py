"""The renderer finds the blank template in AGENTS.md, or in CLAUDE.md for a project set
up before AGENTS.md existed. With both in one folder, AGENTS.md wins: the CLAUDE.md
beside it is a stub that only points to it.

Run:  python3 tests/test_project_file.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, os.pardir, 'project-template', 'Meeting Notes',
                       'skills', 'docx-renderer', 'scripts')
sys.path.insert(0, SCRIPTS)
import render  # noqa: E402

failures = []


def check(name, condition, detail=''):
    if condition:
        print('  pass  %s' % name)
    else:
        failures.append(name)
        print('  FAIL  %s%s' % (name, ('\n        ' + detail) if detail else ''))


def template_line(name):
    return '## Key file locations\n- DOCX blank template: Meeting Notes/%s.docx\n' % name


def blank_template(files, where='root'):
    """Lay out a project, then ask the renderer for its blank template.
    Returns the template's file name, or the error message."""
    tmp = Path(tempfile.mkdtemp())
    try:
        notes = tmp / 'Meeting Notes'
        notes.mkdir()
        folder = tmp if where == 'root' else notes
        for name, text in files.items():
            (folder / name).write_text(text, encoding='utf-8')
        try:
            return render.blank_template(notes).name
        except render.RenderFailed as error:
            return str(error)
    finally:
        shutil.rmtree(tmp)


def test_each_instruction_file_set():
    for where in ('root', 'Meeting Notes'):
        found = blank_template({'AGENTS.md': template_line('from-agents')}, where)
        check('%s, AGENTS.md only: template found' % where,
              found == 'from-agents.docx', found)
        found = blank_template({'CLAUDE.md': template_line('from-claude')}, where)
        check('%s, CLAUDE.md only: template found' % where,
              found == 'from-claude.docx', found)
        found = blank_template({'AGENTS.md': template_line('from-agents'),
                                'CLAUDE.md': '@AGENTS.md\n'}, where)
        check('%s, both with a CLAUDE.md stub: AGENTS.md is read' % where,
              found == 'from-agents.docx', found)
    found = blank_template({})
    check('neither file: the error names both', 'AGENTS.md' in found and 'CLAUDE.md' in found,
          found)


if __name__ == '__main__':
    for name, function in sorted(globals().items()):
        if name.startswith('test_') and callable(function):
            function()
    print('\n%d failure(s)' % len(failures))
    sys.exit(1 if failures else 0)
