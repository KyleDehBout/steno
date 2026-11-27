---
name: rendering-meeting-notes-docx
description: Renders polished meeting notes markdown into a properly formatted [PROJECT NAME]-template Word document (.docx). Use when the supervisor-alignment agent has completed its pass and a .docx output file is required. Runs render.py, which handles the template clone, body generation, header/footer preservation, validation and one automatic repair. Do not use for content editing — rendering only.
---

# Meeting Notes DOCX Renderer

Converts the finalised draft into a `.docx` that matches the project's branded template.
One script does the whole render. Your job is to run it and report what it printed.

## Run it

Read from AGENTS.md: `DOCX renderer scripts`, `Output (pipeline drafts)`, and the project
name. Take the meeting date from the draft's `HELD ON:` line, as `YYYY-MM-DD`.

```bash
python3 "[DOCX renderer scripts]/render.py" "[finalized draft markdown path]" \
  --project "[the Meeting Notes folder]" \
  --out "[output folder]/[PROJECT NAME]-Meeting-Notes-YYYY-MM-DD.docx"
```

Report its last line exactly as printed, and its `repair.py:` line if there is one:
- `RENDER COMPLETE: [output path]` — done.
- `RENDER FAILED at Step N (<step>): [<kind>] <reason>` — stop. That line is your whole
  answer. /process-notes routes it by the kind: `draft` goes back to the stage that owns
  the named `draft line N`; `config`, `install`, `input`, `system` and `renderer` go to
  the user.

## What render.py does

| Step | Script | On failure (kind) |
|------|--------|-------------------|
| 1 clone | copies AGENTS.md's `DOCX blank template`, which carries the image headers and footers | template, AGENTS.md or its template line missing (`config`) |
| 2 unpack | `unpack.py` | template is not a valid .docx (`config`) |
| 3 build body | `build_body_xml.py`, with the project's `references/constants.json` | the draft line at fault (`draft`: attendee fields, unparseable rows, control characters, non-UTF-8 bytes); the constant at fault (`config`); `check_draft.py` missing (`install`); draft file missing (`input`) |
| 4 splice | `splice_body.py` keeps the root tag, namespaces and `<w:sectPr>` | template has no body or sectPr (`config`); write error (`system`) |
| 5 repack | `repack.py` | write error (`system`) |
| 6 validate | `validate.py`; if it fails, `repair.py` once, which re-validates | still invalid after the repair: a typed number or a repeated section title, with its draft line (`draft`); numId, column widths or template parts (`config`); unparseable document.xml or a row without a title (`renderer`) |
| 7 save | copies to `--out`, only after validation passes | write error (`system`) |

A missing sibling script is `install`; anything a script did not anticipate is `renderer`.

Scratch goes in `render/` inside the draft's run folder (`[DOCX working dir]/runs/<stem>/`),
or in `[DOCX working dir]/render/` for a draft kept elsewhere. render.py clears it before
and after every run, so a re-run is safe. Repair runs are logged to `render-log.tsv`
beside it.

## Hard rules

| Rule | Detail |
|------|--------|
| **Failure stops the render** | A `RENDER FAILED` line is the result. Never write body XML yourself or by a script you write, never splice or repack by hand, and never edit the renderer's scripts to get past an error. The fix belongs upstream, in the draft or in `constants.json`, and the render is re-run after it. |
| **render.py missing** | Return `RENDER FAILED at Step 0 (render.py): [install] not found in [DOCX renderer scripts] — re-run /sync-pipeline`. There is no manual method. |
| **No XML or scripts in responses** | Report only render.py's output lines. |
| Content | Do not alter content — rendering only. |

The files in `references/` describe the XML that `build_body_xml.py` and
`setup_docx_renderer.py` work from. They are project-owned, rendered once from this
project's own branded .docx: never rewrite them.
