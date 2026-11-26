#!/usr/bin/env python3
"""Write and open the /learn review form.

Renders ../assets/qa-session-form.html into qa-session.html with the learning-reviewer's
session data injected in place of __SESSION_DATA__, then opens it in the default browser.
The page itself never changes between runs; only the data does.

Usage:
  python3 generate_qa_form.py --data FILE|JSON [--out DIR] [--no-open]

--out defaults to the current folder, which is where /learn has always written the form.
Exit codes: 0 = written, 1 = bad data or missing template (nothing written).
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

PLACEHOLDER = "__SESSION_DATA__"
TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "qa-session-form.html"
REQUIRED = ("project", "date", "transcript", "stem", "meetingNo")
LISTS = ("patterns", "changes", "styleQ")


def fail(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def load_data(raw):
    """Accept a path to a JSON file or a literal JSON string; return the checked object."""
    candidate = Path(raw)
    if candidate.is_file():
        raw = candidate.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"--data is not valid JSON ({exc})")
    if not isinstance(data, dict):
        fail("--data must be a JSON object")
    missing = [key for key in REQUIRED if key not in data]
    if missing:
        fail("--data is missing " + ", ".join(missing))
    wrong = [key for key in LISTS if key in data and not isinstance(data[key], list)]
    if wrong:
        fail("--data must give " + ", ".join(wrong) + " as a list")
    return data


def open_in_browser(path):
    if sys.platform == "darwin":
        cmd = ["open", str(path)]
    elif sys.platform.startswith("win"):
        cmd = ["cmd", "/c", "start", "", str(path)]
    else:
        cmd = ["xdg-open", str(path)]
    try:
        subprocess.run(cmd, check=True)
        return True
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"warning: could not open a browser ({exc})", file=sys.stderr)
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="JSON file or literal JSON of the session data")
    ap.add_argument("--out", default=".", help="directory to write qa-session.html into")
    ap.add_argument("--no-open", action="store_true", help="write the file but do not open a browser")
    args = ap.parse_args()

    if not TEMPLATE.is_file():
        fail(f"form template missing at {TEMPLATE}")
    html = TEMPLATE.read_text(encoding="utf-8")
    if html.count(PLACEHOLDER) != 1:
        fail(f"{PLACEHOLDER} must appear exactly once in {TEMPLATE}")

    data = load_data(args.data)
    # "</" inside a value would close the page's <script> early; "<\/" is the same string in JS.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace(PLACEHOLDER, payload)

    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "qa-session.html"
    out_file.write_text(html, encoding="utf-8")

    opened = False if args.no_open else open_in_browser(out_file)
    print(str(out_file))
    print("opened" if opened else "not opened")


if __name__ == "__main__":
    main()
