"""Tests for the review form /learn opens (qa-session.html) and the script that writes it.

The form is a static page, skills/learning-form/assets/qa-session-form.html, and the
learning-reviewer agent only builds its session JSON. generate_qa_form.py injects that
JSON and writes qa-session.html. Each form case runs the generator, takes the <script>
from the page it wrote, runs it in Node against a stub DOM, calls doSubmit() and reads
the paste block it produces. /apply-learning reads the Open patterns only from that
block, so a pattern missing from it is lost for good.

Run:  python3 tests/test_learning_form.py   (needs `node` on PATH)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, os.pardir))
AGENT = os.path.join(REPO, 'global', 'agents', 'learning-reviewer.md')
FORM = os.path.join(REPO, 'project-template', 'Meeting Notes', 'skills', 'learning-form')
TEMPLATE = os.path.join(FORM, 'assets', 'qa-session-form.html')
GENERATOR = os.path.join(FORM, 'scripts', 'generate_qa_form.py')

failures = []


def check(name, condition, detail=''):
    if condition:
        print('PASS  %s' % name)
    else:
        failures.append(name)
        print('FAIL  %s%s' % (name, ('\n      ' + detail) if detail else ''))


def read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def example_session_data():
    """The worked session JSON example in the agent's Step 2."""
    match = re.search(r'Use this exact shape:\n\n(\{\n.*?\n\})\n', read(AGENT), re.S)
    return match.group(1)


def generate(data):
    """Run the generator on data (a JSON string). Returns (exit code, output, page or None)."""
    out_dir = tempfile.mkdtemp()
    try:
        result = subprocess.run(
            [sys.executable, GENERATOR, '--data', data, '--out', out_dir, '--no-open'],
            capture_output=True, text=True)
        page = os.path.join(out_dir, 'qa-session.html')
        html = read(page) if os.path.isfile(page) else None
        return result.returncode, result.stdout + result.stderr, html
    finally:
        shutil.rmtree(out_dir)


STUB_DOM = r'''
const els = {};
function el(id){
  if(!els[id]) els[id] = {id, value:'', textContent:'', innerHTML:'', style:{},
                          scrollIntoView(){}, select(){}};
  return els[id];
}
global.document = {
  getElementById: el,
  querySelector(sel){
    const m = /name="ch(\d+)"/.exec(sel);
    return m && ANSWERS[m[1]] ? {value: ANSWERS[m[1]]} : null;
  },
  execCommand(){},
};
'''


def run_form(data, answers=None):
    """Generate the page from data (a JSON string), run its script; return the paste block."""
    code, out, html = generate(data)
    if code != 0 or html is None:
        raise RuntimeError('generator failed: %s' % out)
    script = re.search(r'<script>\n(.*?)</script>', html, re.S).group(1)
    program = ('const ANSWERS = %s;\n%s\n%s\ndoSubmit();\n'
               'process.stdout.write(document.getElementById("summary-out").value);\n'
               % (json.dumps(answers or {}), STUB_DOM, script))
    result = subprocess.run(['node', '-e', program], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout


def session(**extra):
    data = {
        'project': 'TEST', 'date': 'Thursday October 8, 2026',
        'transcript': 't.vtt', 'stem': 't', 'meetingNo': '9',
        'changes': [{'category': 'WORDING', 'targetFile': 'guide.md', 'before': 'a',
                     'after': 'b', 'proposedRule': 'Say b not a'}],
        'styleQ': [],
    }
    data.update(extra)
    return json.dumps(data)


def section(block, number):
    """Lines of '--- SECTION n: ... ---' up to the next blank line."""
    match = re.search(r'^--- SECTION %d: [^\n]*---\n(.*?)\n\n' % number, block, re.S | re.M)
    return match.group(1).split('\n') if match else None


def test_patterns_block_lists_every_pattern():
    block = run_form(session(patterns=[
        {'category': 'WORDING', 'pattern': 'informal phrase made formal'},
        {'category': 'SCOPE', 'pattern': 'provisional figure removed'},
    ]))
    lines = section(block, 0)
    check('SECTION 0: PATTERNS block is in the paste', lines is not None, block)
    check('SECTION 0 has one PATTERN line per pattern, with its category',
          lines == ['PATTERN [WORDING]: informal phrase made formal',
                    'PATTERN [SCOPE]: provisional figure removed'], repr(lines))
    check('SECTION 0 comes before SECTION 1',
          0 <= block.find('SECTION 0: PATTERNS') < block.find('SECTION 1:'), block)


def test_patterns_block_says_none_when_empty():
    for label, data in (('empty list', session(patterns=[])), ('no key', session())):
        lines = section(run_form(data), 0)
        check('SECTION 0 present and reads "none" (%s)' % label, lines == ['none'],
              repr(lines))


def test_other_sections_unchanged():
    block = run_form(session(patterns=[]), answers={'0': 'APPROVE'})
    check('paste still opens and closes with the markers',
          block.startswith('==LEARNING_REVIEW==') and block.rstrip().endswith('==END_REVIEW=='),
          block)
    check('SECTION 1 still carries the decision', '[APPROVE] WORDING: Say b not a' in block,
          block)
    check('SECTION 3 still present', section(block, 3) is not None, block)


def test_worked_example_runs_and_routes_wording_to_recurring_corrections():
    example = example_session_data()
    try:
        json.loads(example)
        valid = True
    except ValueError as error:
        valid = False
        example = str(error)
    check('worked example is valid JSON (the generator reads JSON)', valid, example)
    if not valid:
        return
    block = run_form(example)
    check('worked example has a patterns[] list that reaches SECTION 0',
          (section(block, 0) or ['none'])[0].startswith('PATTERN ['), block)
    target = re.search(r'Target: (.*)', block)
    check('worked WORDING example targets the supervisor guide Recurring corrections',
          target and 'supervisor-style-guide' in target.group(1)
          and 'Recurring corrections' in target.group(1), block)


def test_agent_no_longer_carries_the_page():
    text = read(AGENT)
    check('agent prompt holds no HTML page', '<!DOCTYPE' not in text and '<script>' not in text)
    check('agent names the generator script', 'generate_qa_form.py' in text)


def test_generator_changes_only_the_placeholder():
    template = read(TEMPLATE)
    check('template has exactly one __SESSION_DATA__', template.count('__SESSION_DATA__') == 1)
    head, tail = template.split('__SESSION_DATA__')
    data = session(patterns=[])
    code, out, html = generate(data)
    check('generator exits 0 and writes qa-session.html', code == 0 and html is not None, out)
    if html is None:
        return
    check('page is the template with the JSON in place of the placeholder',
          html.startswith(head) and html.endswith(tail)
          and json.loads(html[len(head):len(html) - len(tail)]) == json.loads(data), out)
    check('generator prints the page path and does not open it with --no-open',
          'qa-session.html' in out and 'not opened' in out, out)


def test_generator_keeps_script_closing_tag_inside_a_value():
    block = run_form(session(patterns=[{'category': 'WORDING',
                                        'pattern': 'a </script> tag in text'}]))
    check('a </script> inside a value does not end the page script',
          'PATTERN [WORDING]: a </script> tag in text' in block, block)


def test_generator_refuses_bad_data():
    for label, data in (('not JSON', '{project: "x"}'),
                        ('not an object', '[]'),
                        ('missing stem', json.dumps({k: v for k, v in
                                                     json.loads(session()).items()
                                                     if k != 'stem'})),
                        ('changes not a list', session(changes={}))):
        code, out, html = generate(data)
        check('generator refuses %s and writes nothing' % label,
              code != 0 and html is None and 'error' in out, out)


def test_generator_reads_a_json_file():
    folder = tempfile.mkdtemp()
    try:
        path = os.path.join(folder, 'qa-session.json')
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(session(patterns=[{'category': 'SCOPE', 'pattern': 'from file'}]))
        lines = section(run_form(path), 0)
        check('--data accepts a JSON file path', lines == ['PATTERN [SCOPE]: from file'],
              repr(lines))
    finally:
        shutil.rmtree(folder)


if __name__ == '__main__':
    print('template : %s\n' % TEMPLATE)
    if not shutil.which('node'):
        print('FAIL  node is not on PATH')
        sys.exit(1)
    for name, function in sorted(globals().items()):
        if name.startswith('test_') and callable(function):
            try:
                function()
            except Exception as error:  # a script error fails the case, not the run
                check(name, False, str(error))
    print('\n%d failure(s)' % len(failures))
    sys.exit(1 if failures else 0)
