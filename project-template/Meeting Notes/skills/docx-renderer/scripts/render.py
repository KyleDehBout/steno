"""Render a finalized draft into the project's branded .docx, start to finish.

Usage: render.py <draft.md> --project <Meeting Notes dir> --out <path.docx>

Runs the seven render steps with the sibling scripts, in order:
  1 clone     copy the project's blank template (AGENTS.md "DOCX blank template")
  2 unpack    unpack.py
  3 build     build_body_xml.py, with the project's references/constants.json
  4 splice    splice_body.py
  5 repack    repack.py
  6 validate  validate.py; on failure repair.py once, which re-validates
  7 save      copy to --out

Any failure prints `RENDER FAILED at Step N (<step>): [<kind>] <reason>` and exits 1.
The kind says who can fix it, and /process-notes routes on it:
  draft     the draft is at fault; the reason names it as "draft line N" when it can
  config    the project's template, AGENTS.md template key or constants.json
  install   a pipeline script is missing (/sync-pipeline)
  input     the draft file passed in does not exist
  system    the disk: a file could not be written
  renderer  a bug in the renderer scripts themselves
There is no fallback: a draft or constant the scripts cannot render is fixed upstream,
never by hand-written XML. --out is only written once validation passes.

Scratch goes in render/ inside the draft's run folder (working/runs/<stem>/) when the
draft lives there, else in working/render/. It is cleared before and after every run,
so a re-run starts clean and leaves nothing behind but repair's render-log.tsv.
"""
import argparse
import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


KINDS = ('draft', 'config', 'install', 'input', 'system', 'renderer')
KIND_TAG_RE = re.compile(r'^(?:error:\s*|ERROR:\s*)?\[(%s)\]\s*' % '|'.join(KINDS))

CONFIG_FIX = ('fix: re-derive the template and constants from a branded .docx with '
              'setup_docx_renderer.py <source.docx> <project name> <Meeting Notes folder> '
              '--force (it backs up what it replaces), or correct constants.json by hand')

# Step 6 failures, from validate.py (directly or as repair.py's "still invalid" line).
# First match wins. A typed number or a repeated section title comes from the draft's
# own text; everything else validate.py checks is fixed by the template or constants.
VALIDATE_KINDS = (
    ('typed number', 'draft'),
    ('distinct section title', 'draft'),
    ('document.xml is not valid XML', 'renderer'),
    ('contain no section title', 'renderer'),
    ('not declared in numbering.xml', 'config'),
    ('linked to an active list', 'config'),
    ('column widths', 'config'),
    ('relationship id', 'config'),
    ('missing required file', 'config'),
    ('is not valid XML', 'config'),
    ('<w:sectPr>', 'config'),
    ('<w:body>', 'config'),
)


class RenderFailed(Exception):
    def __init__(self, step, reason, kind='renderer'):
        super().__init__(step, reason, kind)


def classify(step, line):
    """(kind, reason) for a sibling script's last output line."""
    tagged = KIND_TAG_RE.match(line)
    if tagged:
        return tagged.group(1), line[tagged.end():]
    reason = re.sub(r'^(?:error|ERROR|FAIL):\s*', '', line)
    if step.startswith('Step 2'):
        return 'config', reason          # the blank template is not a readable .docx
    if step.startswith('Step 4'):
        return ('config' if '<w:body>' in line or '<w:sectPr>' in line else 'system'), reason
    if step.startswith('Step 5'):
        return 'system', reason
    if step.startswith('Step 6'):
        for needle, kind in VALIDATE_KINDS:
            if needle in line:
                return kind, reason
    return 'renderer', reason


def run(step, script, *args):
    """Run a sibling script; raise RenderFailed with its last output line on failure."""
    if not (SCRIPTS / script).is_file():
        raise RenderFailed(step, f'{script} not found in {SCRIPTS} — run /sync-pipeline',
                           'install')
    p = subprocess.run([sys.executable, str(SCRIPTS / script)] + [str(a) for a in args],
                       capture_output=True, text=True)
    out = (p.stdout + p.stderr).strip()
    if p.returncode != 0:
        lines = [l for l in out.splitlines() if l.strip()]
        last = lines[-1] if lines else f"{script} exited {p.returncode}"
        kind, reason = classify(step, last)
        raise RenderFailed(step, reason, kind)
    return out


QUOTED_RE = re.compile(r"""'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*\"""")
TYPOGRAPHIC = str.maketrans({'\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"'})


def draft_lines(reason, draft):
    """Draft line numbers holding the text a validate.py message quotes.

    validate.py sees the document, not the draft, so it quotes the paragraph text. That
    text was the draft's (build_body_xml only turns straight quotes typographic), so
    finding it again names the line a stage has to change."""
    try:
        lines = draft.read_text(encoding='utf-8').split('\n')
    except (OSError, UnicodeDecodeError):
        return []
    found = []
    for quoted in QUOTED_RE.findall(reason):
        try:
            text = ast.literal_eval(quoted)
        except (ValueError, SyntaxError):
            continue
        text = text.translate(TYPOGRAPHIC).strip()
        if len(text) < 3:
            continue
        for number, line in enumerate(lines, start=1):
            if text in line.translate(TYPOGRAPHIC) and number not in found:
                found.append(number)
    return sorted(found)[:5]


def blank_template(project):
    """The template named in the project instruction file, which sits in the project
    folder or its parent.

    That file is AGENTS.md, or CLAUDE.md in a project set up before AGENTS.md; at one
    folder level AGENTS.md wins, since a CLAUDE.md beside it only points to it. Its
    paths start at the project root ("Meeting Notes/..."), the parent of the Meeting
    Notes folder."""
    candidates = [folder / name for folder in (project, project.parent)
                  for name in ('AGENTS.md', 'CLAUDE.md')]
    for claude_md in candidates:
        if not claude_md.is_file():
            continue
        for line in claude_md.read_text(encoding='utf-8').splitlines():
            key, _, value = line.lstrip('- ').partition(':')
            if key.strip() == 'DOCX blank template' and value.strip():
                return project.parent / value.strip()
        raise RenderFailed('Step 1 (clone)',
                           f'no "DOCX blank template" line in {claude_md} — add '
                           f'"- DOCX blank template: Meeting Notes/<PROJECT>_blank_template.docx" '
                           f'under Key file locations', 'config')
    raise RenderFailed('Step 1 (clone)', f'no AGENTS.md or CLAUDE.md in {project} or its parent',
                       'config')


def render(draft, project, out):
    working = project / 'working'
    runs = working / 'runs'
    run_dir = draft.parent if draft.parent.parent == runs else working
    work = run_dir / 'render'
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        template = blank_template(project)
        if not template.is_file():
            raise RenderFailed('Step 1 (clone)', f'blank template not found: {template} — '
                               f'{CONFIG_FIX}', 'config')
        docx = work / 'meeting-notes-working.docx'
        shutil.copyfile(template, docx)

        unpacked = work / 'unpacked'
        run('Step 2 (unpack)', 'unpack.py', docx, unpacked)

        body = work / 'body.xml'
        constants = project / 'skills' / 'docx-renderer' / 'references' / 'constants.json'
        run('Step 3 (build body)', 'build_body_xml.py', draft, body, '--constants', constants)

        run('Step 4 (splice)', 'splice_body.py', unpacked / 'word' / 'document.xml', body)

        final = work / 'meeting-notes-final.docx'
        run('Step 5 (repack)', 'repack.py', unpacked, final)

        repaired = ''
        try:
            run('Step 6 (validate)', 'validate.py', final)
        except RenderFailed:
            try:
                repaired = run('Step 6 (validate)', 'repair.py', final,
                               '--log', run_dir / 'render-log.tsv')
            except RenderFailed as e:
                step, reason, kind = e.args
                if kind == 'draft':
                    found = draft_lines(reason, draft)
                    if found:
                        reason = 'draft line%s %s: %s' % ('s' if len(found) > 1 else '',
                                                          ', '.join(map(str, found)), reason)
                elif kind == 'config':
                    reason = f'{reason} — {CONFIG_FIX}'
                raise RenderFailed(step, reason, kind)

        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(final, out)
        except OSError as e:
            raise RenderFailed('Step 7 (save)', str(e), 'system')
        return repaired
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('draft')
    parser.add_argument('--project', required=True, help='the Meeting Notes folder')
    parser.add_argument('--out', required=True, help='output .docx path')
    args = parser.parse_args()

    draft = Path(args.draft).resolve()
    project = Path(args.project).resolve()
    out = Path(args.out).resolve()
    try:
        if not draft.is_file():
            raise RenderFailed('Step 3 (build body)', f'draft not found: {draft}', 'input')
        repaired = render(draft, project, out)
    except RenderFailed as e:
        step, reason, kind = e.args
        print(f"RENDER FAILED at {step}: [{kind}] {reason}")
        sys.exit(1)
    if repaired:
        print(f"repair.py: {repaired.splitlines()[0]}")
    print(f"RENDER COMPLETE: {out}")


if __name__ == "__main__":
    main()
