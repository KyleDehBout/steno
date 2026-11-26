"""Validate a .docx file: zip integrity, document.xml presence, XML parse, and numbering.

Numbering check rationale
-------------------------
`numId="0"` on a paragraph that has text is NOT an error on its own. It is how Word
suppresses numbering on a paragraph that still carries a list style, and both project
house styles rely on that for the bold section title (Style A sets numId="0" explicitly,
Style B omits numPr entirely). Flagging it rejected every valid Style A document.

What is a real failure is numbering that never got linked at all — the renderer emitted
numPr everywhere but no paragraph points at a live list. That is checked document-wide.
A leading typed number ("1.1.1 ...") is always a failure: the renderer faked numbering
as literal text instead of using numPr/numId.

Constants cross-check
---------------------
Since the deterministic Step 3 generator drives everything from the project's
constants.json, validate.py independently verifies the two values whose failure is
silent in the XML yet visible in Word:
- every numId referenced in document.xml must be declared in numbering.xml;
- each table's gridCol widths must sum to its declared tblW.
A stale or misparsed constant fails here, on every render, instead of drifting the
table layout until a human notices.
"""
import re
import sys
import zipfile
import xml.etree.ElementTree as ET


# A Word package needs all of these to open. document.xml alone is not enough:
# without _rels/.rels or word/_rels/document.xml.rels the package has no path from
# the OPC root to the document part, and Word reports unreadable content — while a
# validator that only checks document.xml happily passes it.
REQUIRED_FILES = [
    '[Content_Types].xml',
    '_rels/.rels',
    'word/document.xml',
    'word/_rels/document.xml.rels',
    'word/styles.xml',
    'word/numbering.xml',
]
W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'

# A typed list number is hierarchical ("1.1", "1.2.3") or a single number with a
# trailing dot ("1."). A bare leading integer is NOT one — "2025 budget approved",
# "48 hours notice" and "3 units delivered" are ordinary sentences, and failing them
# leaves the agent with a render it cannot fix, because the XML is already correct.
LEADING_NUMBER_RE = re.compile(r'^(\d+(?:\.\d+)+\.?|\d+\.)\s')


def w(tag):
    return f'{{{W_NS}}}{tag}'


def style_numbering(styles_root):
    """Map each paragraph styleId to the (numId, ilvl) it inherits through basedOn.

    Returns (mapping, default paragraph styleId). A value is None when no style in
    the chain declares it."""
    declared = {}
    default = None
    for s in styles_root.findall(w('style')):
        if s.get(w('type')) != 'paragraph':
            continue
        sid = s.get(w('styleId'))
        if s.get(w('default')) in ('1', 'true'):
            default = sid
        based = s.find(w('basedOn'))
        num = s.find(f'./{w("pPr")}/{w("numPr")}/{w("numId")}')
        lvl = s.find(f'./{w("pPr")}/{w("numPr")}/{w("ilvl")}')
        declared[sid] = (based.get(w('val')) if based is not None else None,
                         num.get(w('val')) if num is not None else None,
                         lvl.get(w('val')) if lvl is not None else None)

    resolved = {}
    for sid in declared:
        num = lvl = None
        seen = set()
        cur = sid
        while cur in declared and cur not in seen:
            seen.add(cur)
            based, n, l = declared[cur]
            num = n if num is None else num
            lvl = l if lvl is None else lvl
            cur = based
        resolved[sid] = (num, lvl)
    return resolved, default


def effective_numbering(p, styles, default_style):
    """(numId, ilvl) a paragraph actually gets: its own numPr over its style's.

    Style B section titles carry no numPr and rely on the 10List style's numId="0";
    Style A titles set numId="0" on the paragraph. Both are suppressed, unnumbered
    titles. A title that loses its numPr under a style with live numbering is not."""
    ppr_style = p.find(f'./{w("pPr")}/{w("pStyle")}')
    sid = ppr_style.get(w('val')) if ppr_style is not None else default_style
    num, lvl = styles.get(sid, (None, None))
    own_num = p.find(f'./{w("pPr")}/{w("numPr")}/{w("numId")}')
    own_lvl = p.find(f'./{w("pPr")}/{w("numPr")}/{w("ilvl")}')
    if own_num is not None:
        num = own_num.get(w('val'))
    if own_lvl is not None:
        lvl = own_lvl.get(w('val'))
    return num, lvl


def section_title(cell, styles, default_style):
    """Text of the first suppressed-numbering level-0 paragraph in column 2, or None."""
    for p in cell.findall(w('p')):
        num, lvl = effective_numbering(p, styles, default_style)
        if num != '0' or lvl not in (None, '0'):
            continue
        text = ''.join(t.text or '' for t in p.findall(f'.//{w("t")}')).strip()
        if text:
            return text
    return None


def main():
    if len(sys.argv) != 2:
        print("Usage: validate.py <file.docx>")
        sys.exit(1)

    path = sys.argv[1]

    try:
        with zipfile.ZipFile(path, 'r') as z:
            bad = z.testzip()
            if bad:
                print(f"FAIL: corrupt zip entry: {bad}")
                sys.exit(1)

            names = z.namelist()
            for req in REQUIRED_FILES:
                if req not in names:
                    print(f"FAIL: missing required file: {req}")
                    sys.exit(1)

            try:
                root = ET.fromstring(z.read('word/document.xml'))
            except ET.ParseError as e:
                print(f"FAIL: document.xml is not valid XML: {e}")
                sys.exit(1)

            # Every r:id the body references must resolve in the rels part, or the
            # header, footer or image it points at silently fails to load.
            try:
                rels_root = ET.fromstring(z.read('word/_rels/document.xml.rels'))
            except ET.ParseError as e:
                print(f"FAIL: document.xml.rels is not valid XML: {e}")
                sys.exit(1)
            declared = {r.get('Id') for r in rels_root}
            used = {v for el in root.iter() for k, v in el.attrib.items()
                    if k.startswith(f'{{{R_NS}}}')}
            missing = sorted(used - declared)
            if missing:
                print(f"FAIL: {len(missing)} relationship id(s) referenced in document.xml "
                      f"are not declared in document.xml.rels: {missing[:5]} — the header, "
                      f"footer or image they point at will not load")
                sys.exit(1)

            # Every numId a paragraph references must be declared in numbering.xml.
            # A stale-silently-rendered table is exactly what a misparsed numId
            # constant looks like; this catches it on every render instead of on a
            # human noticing months later that the numbers are wrong.
            try:
                num_root = ET.fromstring(z.read('word/numbering.xml'))
            except ET.ParseError as e:
                print(f"FAIL: numbering.xml is not valid XML: {e}")
                sys.exit(1)
            declared_nums = {n.get(w('numId')) for n in num_root.findall(w('num'))}

            try:
                styles, default_style = style_numbering(
                    ET.fromstring(z.read('word/styles.xml')))
            except ET.ParseError as e:
                print(f"FAIL: styles.xml is not valid XML: {e}")
                sys.exit(1)

            body = root.find(f'.//{w("body")}')
            if body is None:
                print("FAIL: <w:body> not found in document.xml")
                sys.exit(1)

            if body.find(w('sectPr')) is None:
                print("FAIL: <w:sectPr> not found in <w:body> — header/footer references will be lost")
                sys.exit(1)

            numbered = 0
            suppressed = 0
            referenced_num_ids = set()

            for p in body.iter(w('p')):
                text = ''.join(t.text or '' for t in p.findall(f'.//{w("t")}'))

                m = LEADING_NUMBER_RE.match(text)
                if m and p.find(f'./{w("pPr")}/{w("numPr")}') is not None:
                    ilvl = p.find(f'./{w("pPr")}/{w("numPr")}/{w("ilvl")}')
                    try:
                        depth = int(ilvl.get(w('val'))) if ilvl is not None else None
                    except (TypeError, ValueError):
                        depth = None
                    segments = len(m.group(1).rstrip('.').split('.'))
                    # Only a failure when the typed number duplicates the one Word is
                    # about to print at this paragraph's own level.
                    if depth is not None and segments == depth + 1:
                        print(f"FAIL: paragraph text starts with a typed number instead of "
                              f"relying on numId/ilvl: {text[:60]!r}")
                        sys.exit(1)

                numId = p.find(f'./{w("pPr")}/{w("numPr")}/{w("numId")}')
                if numId is None:
                    continue
                if numId.get(w('val')) == '0':
                    if text.strip():
                        suppressed += 1
                else:
                    numbered += 1
                    ref = numId.get(w('val'))
                    if ref:
                        referenced_num_ids.add(ref)

            missing_nums = sorted(referenced_num_ids - declared_nums)
            if missing_nums:
                print(f"FAIL: numId(s) {missing_nums} referenced in document.xml are not "
                      f"declared in numbering.xml ({sorted(declared_nums)}) — a stale "
                      f"constant fed the renderer. Missing: {missing_nums}")
                sys.exit(1)

            # A meeting-notes table with no live numbering anywhere never numbered a
            # single section. suppressed==0 hid this before: the old check only fired
            # when numPr existed but pointed nowhere.
            if body.find(f'.//{w("tbl")}') is not None and numbered == 0:
                print("FAIL: the document contains a table but no paragraph is linked to an "
                      "active list — no section will carry a number")
                sys.exit(1)

            # Wholesale failure: numPr was emitted but nothing points at a live list.
            if suppressed and not numbered:
                print(f"FAIL: {suppressed} paragraph(s) carry numPr but no paragraph in the "
                      f"document is linked to an active list — numbering was never wired up")
                sys.exit(1)

            # Structural check: one numbered row per section, not per sub-item.
            #
            # The house format puts a whole section in ONE table row: column 1 carries
            # the section counter (a live numId at ilvl 0) and column 2 opens with the
            # section title, which suppresses its own number with numId="0" at ilvl 0,
            # set on the paragraph (Style A) or inherited from its style (Style B's 10List).
            # Sub-items live in that same row at ilvl 1+.
            #
            # A renderer that emits one row per sub-item advances the section counter on
            # every row, so headings lose their number and sub-items render with a zero
            # in the middle ("3.0.1"). That shows up here as counter rows with no section
            # title behind them.
            orphans = []
            for tr in body.iter(w('tr')):
                cells = tr.findall(w('tc'))
                if len(cells) < 2:
                    continue

                has_counter = any(
                    num.get(w('val')) != '0'
                    and (lvl is None or lvl.get(w('val')) == '0')
                    for p in cells[0].findall(w('p'))
                    for num in [p.find(f'./{w("pPr")}/{w("numPr")}/{w("numId")}')]
                    if num is not None
                    for lvl in [p.find(f'./{w("pPr")}/{w("numPr")}/{w("ilvl")}')]
                )
                if not has_counter:
                    continue

                if section_title(cells[1], styles, default_style) is None:
                    first = ''.join(
                        t.text or '' for t in cells[1].findall(f'.//{w("t")}')).strip()
                    orphans.append(first[:50] or '(empty)')

            if orphans:
                print(f"FAIL: {len(orphans)} table row(s) advance the section counter but "
                      f"contain no section title — the renderer is emitting one row per "
                      f"sub-item instead of one row per section. First offenders: "
                      f"{orphans[:3]}")
                sys.exit(1)

            # The orphan check above catches a row that advances the counter with no
            # title behind it. It does NOT catch the mirror case: a renderer that splits
            # one section across several rows while dutifully repeating the title in each.
            # The counter still advances per row, so the same section is numbered two or
            # three times over. Compare counter rows against distinct section titles.
            counter_rows = 0
            titles = []
            for tr in body.iter(w('tr')):
                cells = tr.findall(w('tc'))
                if len(cells) < 2:
                    continue
                if not any(
                    num.get(w('val')) != '0'
                    and (lvl is None or lvl.get(w('val')) == '0')
                    for p in cells[0].findall(w('p'))
                    for num in [p.find(f'./{w("pPr")}/{w("numPr")}/{w("numId")}')]
                    if num is not None
                    for lvl in [p.find(f'./{w("pPr")}/{w("numPr")}/{w("ilvl")}')]
                ):
                    continue
                counter_rows += 1
                t = section_title(cells[1], styles, default_style)
                if t:
                    titles.append(t)

            if counter_rows and len(set(titles)) < counter_rows:
                dupes = sorted({t for t in titles if titles.count(t) > 1})
                print(f"FAIL: {counter_rows} rows advance the section counter but only "
                      f"{len(set(titles))} distinct section title(s) exist — a section is "
                      f"split across multiple rows and will be numbered more than once. "
                      f"Repeated: {dupes[:3]}")
                sys.exit(1)

        # Column widths: gridCol values must sum to the table's declared tblW.
        # A wrong col_widths constant still parses and renders — only the visual
        # layout drifts. Check it mechanically instead of on human inspection.
        for table in body.findall(f'.//{w("tbl")}'):
            tw = table.find(f'./{w("tblPr")}/{w("tblW")}')
            if tw is None:
                continue
            if tw.get(w('type')) not in (None, 'dxa'):
                continue
            try:
                declared_w = int(tw.get(w('w')))
            except (TypeError, ValueError):
                continue
            grid = table.find(w('tblGrid'))
            if grid is None:
                continue
            widths = []
            for gc in grid.findall(w('gridCol')):
                try:
                    widths.append(int(gc.get(w('w'))))
                except (TypeError, ValueError):
                    widths = None
                    break
            if widths is None or not widths:
                continue
            if sum(widths) != declared_w:
                print(f"FAIL: table column widths ({widths}) sum to {sum(widths)} but "
                      f"tblW declares {declared_w} — col_widths in constants.json do not "
                      f"match the table's declared width")
                sys.exit(1)

    except zipfile.BadZipFile as e:
        print(f"FAIL: not a valid zip/docx: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print(f"FAIL: file not found: {path}")
        sys.exit(1)
    except Exception as e:
        print(f"FAIL: {e}")
        sys.exit(1)

    print("OK")


if __name__ == "__main__":
    main()
