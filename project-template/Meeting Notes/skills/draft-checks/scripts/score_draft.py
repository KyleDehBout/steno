#!/usr/bin/env python3
"""Score a pipeline-produced draft against the supervisor's issued .docx.

Usage: score_draft.py <draft.md> <issued.docx> [--json <path>] [--min-score N] [--quiet]

Used by /test-pipeline to answer one question: does a change to an agent or a rule make
the pipeline produce something closer to what the supervisor actually issued, or further
away? Drafts are deleted at the end of every cycle, so past meetings are the only place
that answer can come from. /learn runs it on each cycle's Stage 5 draft too, and the
SCORECARD line it prints is copied into the scorecard's learn-cycle row.

Scoring, out of 100:
  40  coverage   — issued sub-items the draft also has
  20  precision  — draft sub-items the issued document also has
  20  action     — agreement on Action, over matched items where either side has one
  20  status     — agreement on Status, over matched items where either side has one

Exit codes: 0 = scored (and at or above --min-score, if given), 1 = below --min-score,
2 = bad usage or unreadable input.
"""
import argparse
import bisect
import difflib
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
A_NS = 'http://schemas.openxmlformats.org/drawingml/2006/main'

ITEM_RE = re.compile(r'^(\d+)\.(\d+)\.(\d+)\s*\|(.*)$')
SECTION_RE = re.compile(r'^##\s+(\d+)\.\s+(.+?)\s*$')

# Two texts describing the same outcome rarely match word for word once the supervisor
# has edited them. 0.55 pairs reworded versions of the same item without pairing two
# different items; it was set by checking both failure directions on issued documents.
MATCH_THRESHOLD = 0.55


def w(tag):
    return '{%s}%s' % (W_NS, tag)


def para_text(paragraph):
    return ''.join(node.text or '' for node in paragraph.findall('.//%s' % w('t')))


def numbering(paragraph):
    """Return (ilvl, numId) as strings, or (None, None) when the paragraph has none."""
    num_pr = paragraph.find('./%s/%s' % (w('pPr'), w('numPr')))
    if num_pr is None:
        return None, None
    ilvl = num_pr.find(w('ilvl'))
    num_id = num_pr.find(w('numId'))
    return (ilvl.get(w('val')) if ilvl is not None else None,
            num_id.get(w('val')) if num_id is not None else None)


def style_numbering(styles_root):
    """Map paragraph styleId -> (numId, ilvl) inherited through basedOn, plus the
    default paragraph style. Kept in step with validate.py's copy."""
    declared = {}
    default = None
    for style in styles_root.findall(w('style')):
        if style.get(w('type')) != 'paragraph':
            continue
        sid = style.get(w('styleId'))
        if style.get(w('default')) in ('1', 'true'):
            default = sid
        based = style.find(w('basedOn'))
        num = style.find('./%s/%s/%s' % (w('pPr'), w('numPr'), w('numId')))
        lvl = style.find('./%s/%s/%s' % (w('pPr'), w('numPr'), w('ilvl')))
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


def effective_numbering(paragraph, styles, default_style):
    """(ilvl, numId) the paragraph gets: its own numPr over its style's. Style B section
    titles have no numPr and inherit numId="0" from the 10List style."""
    p_style = paragraph.find('./%s/%s' % (w('pPr'), w('pStyle')))
    num, lvl = styles.get(p_style.get(w('val')) if p_style is not None else default_style,
                          (None, None))
    own_lvl, own_num = numbering(paragraph)
    return (own_lvl if own_lvl is not None else lvl,
            own_num if own_num is not None else num)


# -- where each paragraph sits in its cell -------------------------------------------
# Issued documents pad columns 3 and 4 with blank one-line paragraphs until the owner
# sits beside its item (Style B #10: 11 column-2 paragraphs, 37 side paragraphs), so an
# Action's paragraph index says nothing about the item it faces. Pairing is by height
# instead: each paragraph's top is estimated from its wrapped line count, line spacing
# and before/after spacing, all read from the document and its styles.

# Times New Roman advance widths in 1/1000 em, the same table build_body_xml.py uses
# (draft-checks cannot import from docx-renderer). Unlisted characters: 500.
_TNR = dict(zip(' !"#$%&\'()*+,-./:;<=>?@',
                [250, 333, 408, 500, 500, 833, 778, 333, 333, 333, 500, 564, 250, 333,
                 250, 278, 278, 278, 564, 564, 564, 444, 921]))
_TNR.update(zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ',
                [722, 667, 667, 722, 611, 556, 722, 722, 333, 389, 722, 611, 889, 722,
                 722, 556, 722, 667, 556, 611, 722, 722, 944, 722, 722, 611]))
_TNR.update(zip('abcdefghijklmnopqrstuvwxyz',
                [444, 500, 444, 500, 444, 333, 500, 500, 278, 278, 500, 278, 778, 500,
                 500, 500, 500, 333, 389, 278, 500, 500, 722, 500, 500, 444]))
_TNR.update({'‘': 333, '’': 333, '“': 444, '”': 444, '–': 500, '—': 1000})
# Word's default table cell margins: 108 dxa left and right.
CELL_MARGINS = 216
# Single line spacing as a multiple of the font size, by font. Style B #10's PDF has an
# 11pt Times New Roman line pitch of 12.72pt (1.156). Calibri, the theme font that
# unstyled spacer paragraphs fall back to, carries 0.22 em of line gap on top.
SINGLE_LINE = {'calibri': 1.22}
SINGLE_LINE_DEFAULT = 1.15
# An owner whose estimated position is within this many lines of the boundary between
# two items could belong to either; the result counts those as uncertain.
UNCERTAIN_LINES = 0.5


def wrapped_lines(text, avail_dxa, half_points):
    """Lines `text` wraps to in `avail_dxa` of width (greedy word wrap)."""
    em = half_points * 10
    space = _TNR[' '] * em / 1000.0
    lines, used = 1, 0.0
    for word in text.split():
        width = sum(_TNR.get(ch, 500) for ch in word) * em / 1000.0
        if used and used + space + width > avail_dxa:
            lines, used = lines + 1, width
        else:
            used += (space if used else 0) + width
    return lines


class Layout:
    """Resolves the spacing, font size and indent a paragraph gets: its own pPr/rPr
    first, then its style's basedOn chain, then the document defaults."""

    def __init__(self, styles_root, numbering_root, theme_root=None):
        self.theme = {}
        if theme_root is not None:
            for kind in ('minor', 'major'):
                latin = theme_root.find('.//{%s}%sFont/{%s}latin' % (A_NS, kind, A_NS))
                if latin is not None:
                    self.theme[kind] = latin.get('typeface')
        self.styles = {}
        self.default = None
        for style in styles_root.findall(w('style')):
            if style.get(w('type')) != 'paragraph':
                continue
            sid = style.get(w('styleId'))
            if style.get(w('default')) in ('1', 'true'):
                self.default = sid
            self.styles[sid] = style
        defaults = styles_root.find(w('docDefaults'))
        self.doc_ppr = defaults.find('./%s/%s' % (w('pPrDefault'), w('pPr'))) \
            if defaults is not None else None
        self.doc_rpr = defaults.find('./%s/%s' % (w('rPrDefault'), w('rPr'))) \
            if defaults is not None else None
        self.num_ind = {}
        if numbering_root is not None:
            abstract = {}
            for node in numbering_root.findall(w('abstractNum')):
                for lvl in node.findall(w('lvl')):
                    ind = lvl.find('./%s/%s' % (w('pPr'), w('ind')))
                    if ind is not None:
                        abstract[(node.get(w('abstractNumId')), lvl.get(w('ilvl')))] = ind
            for num in numbering_root.findall(w('num')):
                ref = num.find(w('abstractNumId'))
                for (aid, lvl), ind in abstract.items():
                    if ref is not None and ref.get(w('val')) == aid:
                        self.num_ind[(num.get(w('numId')), lvl)] = ind

    def chain(self, paragraph):
        """The paragraph's pPr, then each style pPr/rPr up the basedOn chain."""
        p_style = paragraph.find('./%s/%s' % (w('pPr'), w('pStyle')))
        sid = p_style.get(w('val')) if p_style is not None else self.default
        seen = []
        while sid in self.styles and sid not in seen:
            seen.append(sid)
            based = self.styles[sid].find(w('basedOn'))
            sid = based.get(w('val')) if based is not None else None
        return [self.styles[sid] for sid in seen]

    def _attr(self, nodes, path, names):
        for node in nodes:
            found = node.find(path) if node is not None else None
            if found is None:
                continue
            for name in names:
                if found.get(w(name)) is not None:
                    return found.get(w(name))
        return None

    def metrics(self, paragraph, numbering_key):
        """(before_pt, after_pt, line_pt, size_half_points, left_indent_dxa)."""
        own = paragraph.find(w('pPr'))
        styles = self.chain(paragraph)
        p_nodes = [own] + [s.find(w('pPr')) for s in styles] + [self.doc_ppr]
        spacing = './%s' % w('spacing')
        before = float(self._attr(p_nodes, spacing, ['before']) or 0) / 20
        after = float(self._attr(p_nodes, spacing, ['after']) or 0) / 20
        line = float(self._attr(p_nodes, spacing, ['line']) or 240)
        rule = self._attr(p_nodes, spacing, ['lineRule']) or 'auto'

        # The first run with text sets the size and font; an empty paragraph takes its
        # paragraph mark's. Either falls back to the style chain, then the defaults.
        runs = [r.find(w('rPr')) for r in paragraph.iter(w('r'))
                if r.find(w('t')) is not None and r.find(w('t')).text]
        r_nodes = (runs[:1] + [own.find(w('rPr')) if own is not None else None]
                   + [s.find(w('rPr')) for s in styles] + [self.doc_rpr])
        size = int(self._attr(r_nodes, './%s' % w('sz'), ['val']) or 20)
        font = self._attr(r_nodes, './%s' % w('rFonts'), ['ascii', 'asciiTheme']) or ''
        if font.startswith(('minor', 'major')):
            font = self.theme.get(font[:5], '')

        single = SINGLE_LINE.get(font.lower(), SINGLE_LINE_DEFAULT) * size / 2.0
        if rule == 'exact':
            line_pt = line / 20
        elif rule == 'atLeast':
            line_pt = max(line / 20, single)
        else:
            line_pt = single * line / 240

        ind = ('./%s' % w('ind'))
        left = self._attr([own], ind, ['left', 'start'])
        if left is None and numbering_key in self.num_ind:
            left = self._attr([self.num_ind[numbering_key]], '.', ['left', 'start'])
        if left is None:
            left = self._attr([s.find(w('pPr')) for s in styles], ind, ['left', 'start'])
        return before, after, line_pt, size, int(float(left or 0))

    def tops(self, cell, styles, default_style):
        """[(top, first_line_middle, line_pt)] for each paragraph of a table cell, in
        points from the top of the cell."""
        width_node = cell.find('./%s/%s' % (w('tcPr'), w('tcW')))
        width = int(width_node.get(w('w'))) if width_node is not None else 0
        y = 0.0
        out = []
        for paragraph in cell.findall(w('p')):
            ilvl, num_id = effective_numbering(paragraph, styles, default_style)
            before, after, line_pt, size, left = self.metrics(
                paragraph, (num_id, ilvl or '0'))
            segments = ['']
            for node in paragraph.iter():
                if node.tag == w('br'):
                    segments.append('')
                elif node.tag == w('t'):
                    segments[-1] += node.text or ''
            lines = sum(wrapped_lines(s, max(width - CELL_MARGINS - left, 1440), size)
                        for s in segments)
            out.append((y, y + before + line_pt / 2, line_pt))
            y += before + lines * line_pt + after
        return out


def side_values(side_cell, starts, layout, styles, default_style):
    """[(column-2 index, value, (index above, index below))] for each non-empty side
    paragraph: the column-2 paragraph its first line sits beside, and the ones it would
    sit beside if the estimate were half a line out either way."""
    def at(y):
        return max(0, bisect.bisect_right(starts, y) - 1)

    out = []
    for paragraph, (_, middle, line_pt) in zip(
            side_cell.findall(w('p')), layout.tops(side_cell, styles, default_style)):
        value = para_text(paragraph).strip()
        if value:
            slack = UNCERTAIN_LINES * line_pt
            out.append((at(middle), value, (at(middle - slack), at(middle + slack))))
    return out


def normalise(text):
    """Lowercase, strip punctuation and collapse whitespace for comparison only."""
    text = text.replace('–', '-').replace('—', '-')
    text = text.replace('’', "'").replace('“', '"').replace('”', '"')
    text = re.sub(r'[^a-z0-9\s\'-]', ' ', text.lower())
    return re.sub(r'\s+', ' ', text).strip()


def read_issued(path):
    """Extract sections and sub-items from an issued .docx.

    Each Action and Status pairs with the column-2 paragraph it sits beside on the page
    (see Layout). An owner beside a spacer or a bullet belongs to the sub-item above it.
    Owners whose estimated position is within half a line of another sub-item are
    counted in 'alignment' as uncertain, so the score can say how far to trust them.
    """
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
        styles_root = ET.fromstring(archive.read('word/styles.xml'))
        names = archive.namelist()
        numbering_root = (ET.fromstring(archive.read('word/numbering.xml'))
                          if 'word/numbering.xml' in names else None)
        theme_root = (ET.fromstring(archive.read('word/theme/theme1.xml'))
                      if 'word/theme/theme1.xml' in names else None)
    styles, default_style = style_numbering(styles_root)
    layout = Layout(styles_root, numbering_root, theme_root)

    body = root.find('.//%s' % w('body'))
    if body is None:
        raise ValueError('no <w:body> in %s' % path)

    sections = []
    items = []
    labels = []
    alignment = {'placed': 0, 'uncertain': 0, 'unplaced': 0}

    for row in body.iter(w('tr')):
        cells = row.findall(w('tc'))
        if len(cells) < 2:
            continue

        content = cells[1].findall(w('p'))
        section_title = None
        row_items = []
        row_labels = []
        # owner[i]: index into row_items of the sub-item column-2 paragraph i belongs
        # to, or None for a title or label (and anything above the first sub-item).
        owner = []

        for paragraph in content:
            text = para_text(paragraph).strip()
            ilvl, num_id = effective_numbering(paragraph, styles, default_style)

            if not text or ilvl == '3':
                # A spacer, or a bullet: drafts carry bullets as "- " lines that
                # read_draft never counts as items. Any Action or Status facing
                # either belongs to the item above.
                owner.append(len(row_items) - 1 if row_items else None)
                continue

            if section_title is None and num_id == '0' and (ilvl in (None, '0')):
                section_title = text
                owner.append(None)
                continue

            if ilvl == '1':
                # A subsection label. The draft carries these as "### N.M" headings, and
                # read_draft only ever returns "N.M.K |" rows as items — so counting a
                # label as an item made a correct draft appear to have dropped one, and
                # capped coverage at around 58% on a document with five of them.
                row_labels.append({'text': text, 'section': section_title})
                owner.append(None)
                continue

            owner.append(len(row_items))
            row_items.append({
                'text': text,
                'level': ilvl,
                'action': '',
                'status': '',
                'section': section_title,
            })

        if content and section_title and row_items:
            starts = [top for top, _, _ in
                      layout.tops(cells[1], styles, default_style)]
            for column, cell_index in (('action', 2), ('status', 3)):
                if len(cells) <= cell_index:
                    continue
                for index, value, (low, high) in side_values(
                        cells[cell_index], starts, layout, styles, default_style):
                    target = owner[index]
                    if target is None:
                        alignment['unplaced'] += 1
                        continue
                    alignment['placed'] += 1
                    if any(owner[i] != target for i in range(low, high + 1)):
                        alignment['uncertain'] += 1
                    # A second owner on the same sub-item faces one of its bullets.
                    if not row_items[target][column]:
                        row_items[target][column] = value

        if section_title:
            sections.append(section_title)
        items.extend(row_items)
        labels.extend(row_labels)

    # The last row is the meetings row: no section title, one sentence about the next
    # meeting. It is not an item and must not count against coverage.
    items = [item for item in items
             if item['section'] and not item['text'].lower().startswith('next meeting')]
    return {'sections': sections, 'items': items, 'subsections': labels,
            'alignment': alignment}


def read_draft(path):
    """Extract sections and sub-items from a draft in the format contract."""
    sections = []
    items = []
    current = None

    for line in path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        section_match = SECTION_RE.match(stripped)
        if section_match:
            current = section_match.group(2)
            sections.append(current)
            continue

        item_match = ITEM_RE.match(stripped)
        if not item_match:
            continue
        parts = re.split(r'(?<!\\)\|', item_match.group(4))
        if len(parts) != 3:
            continue
        items.append({
            'text': parts[0].strip().replace('\\|', '|'),
            'action': parts[1].strip(),
            'status': parts[2].strip(),
            'section': current,
        })

    return {'sections': sections, 'items': items}


def pair_items(issued_items, draft_items):
    """Greedy best-match pairing. Returns (pairs, missing, extra)."""
    remaining = list(range(len(draft_items)))
    pairs = []
    missing = []

    for issued in issued_items:
        best_index = None
        best_ratio = 0.0
        issued_text = normalise(issued['text'])
        for index in remaining:
            ratio = difflib.SequenceMatcher(
                None, issued_text, normalise(draft_items[index]['text'])).ratio()
            if ratio > best_ratio:
                best_ratio, best_index = ratio, index
        if best_index is not None and best_ratio >= MATCH_THRESHOLD:
            remaining.remove(best_index)
            pairs.append((issued, draft_items[best_index], best_ratio))
        else:
            missing.append(issued)

    extra = [draft_items[index] for index in remaining]
    return pairs, missing, extra


def score(issued, draft):
    pairs, missing, extra = pair_items(issued['items'], draft['items'])

    issued_count = len(issued['items'])
    draft_count = len(draft['items'])

    coverage = len(pairs) / issued_count if issued_count else 0.0
    precision = len(pairs) / draft_count if draft_count else 0.0

    # Most sub-items in an issued document carry no Action or Status at all — only the
    # rows that assign something do. Counting blank-against-blank as agreement would
    # bury a real disagreement under ten trivial matches, so a pair is scored only when
    # at least one side has a value. A draft that invents an Action where the issued
    # document has none is a disagreement, and counts.
    def agreement(column):
        scored = [(i, d) for i, d, _ in pairs if i[column] or d[column]]
        if not scored:
            return 1.0, 0, 0
        hits = sum(1 for i, d in scored
                   if normalise(i[column]) == normalise(d[column]))
        return hits / len(scored), hits, len(scored)

    action_rate, _action_hits, action_scored = agreement('action')
    status_rate, _status_hits, status_scored = agreement('status')

    total = (coverage * 40) + (precision * 20) + (action_rate * 20) + (status_rate * 20)

    # The scorecard cells. Agreement over no scored cells is "n/a", not a free 100%,
    # and agreement read from a supervisor's padded layout is marked "approx" when any
    # owner sat within half a line of another item or beside no item at all.
    alignment = issued.get('alignment') or {}
    approx = alignment.get('uncertain', 0) + alignment.get('unplaced', 0) > 0

    def cell(rate, scored):
        if not scored:
            return 'n/a'
        return '%.0f%%%s' % (rate * 100, ' approx' if approx else '')

    return {
        'score': round(total, 1),
        'coverage': round(coverage, 3),
        'precision': round(precision, 3),
        'action_agreement': round(action_rate, 3),
        'status_agreement': round(status_rate, 3),
        'counts': {
            'issued_items': issued_count,
            'draft_items': draft_count,
            'matched': len(pairs),
            'missing': len(missing),
            'extra': len(extra),
            'issued_sections': len(issued['sections']),
            'draft_sections': len(draft['sections']),
            'action_cells_scored': action_scored,
            'status_cells_scored': status_scored,
        },
        'alignment': alignment,
        'scorecard': {
            'score': '%.1f' % total,
            'coverage': '%.0f%%' % (coverage * 100),
            'precision': '%.0f%%' % (precision * 100),
            'action': cell(action_rate, action_scored),
            'status': cell(status_rate, status_scored),
        },
        'missing_items': [item['text'][:100] for item in missing],
        'extra_items': [item['text'][:100] for item in extra],
        'action_mismatches': [
            {'issued': i['action'], 'draft': d['action'], 'item': i['text'][:70]}
            for i, d, _ in pairs if normalise(i['action']) != normalise(d['action'])],
        'status_mismatches': [
            {'issued': i['status'], 'draft': d['status'], 'item': i['text'][:70]}
            for i, d, _ in pairs if normalise(i['status']) != normalise(d['status'])],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Score a draft against the issued document for the same meeting.')
    parser.add_argument('draft', help='pipeline-produced draft (format contract)')
    parser.add_argument('issued', help='supervisor-issued .docx for the same meeting')
    parser.add_argument('--json', dest='json_out', help='write the full result here')
    parser.add_argument('--min-score', type=float,
                        help='exit 1 if the score falls below this')
    parser.add_argument('--quiet', action='store_true', help='summary line only')
    args = parser.parse_args(argv)

    draft_path, issued_path = Path(args.draft), Path(args.issued)
    if not draft_path.is_file():
        sys.exit('error: draft not found: %s' % draft_path)
    if not issued_path.is_file():
        sys.exit('error: issued document not found: %s' % issued_path)

    try:
        issued = read_issued(issued_path)
    except (zipfile.BadZipFile, ET.ParseError, ValueError, KeyError) as error:
        sys.exit('error: could not read %s: %s' % (issued_path, error))

    if not issued['items']:
        # Section titles are found by numId="0" at ilvl 0, on the paragraph or from its
        # style. A house style that marks titles some other way yields no items, and
        # scoring would then report a confident 40/100 for a draft nothing was
        # compared against.
        sys.exit('error: no sub-items extracted from %s — the section titles in this '
                 'document do not carry the numbering pattern score_draft.py looks for, '
                 'so nothing can be compared' % issued_path)

    draft = read_draft(draft_path)
    if not draft['items']:
        sys.exit('error: no sub-items found in %s — is it in the draft format contract?'
                 % draft_path)

    result = score(issued, draft)

    if not args.quiet:
        counts = result['counts']
        print('matched %d of %d issued sub-items (%d extra in the draft)'
              % (counts['matched'], counts['issued_items'], counts['extra']))
        for item in result['missing_items'][:5]:
            print('  missing : %s' % item)
        for item in result['extra_items'][:5]:
            print('  extra   : %s' % item)
        for mismatch in result['action_mismatches'][:5]:
            print('  action  : issued %r, draft %r — %s'
                  % (mismatch['issued'], mismatch['draft'], mismatch['item']))
        for mismatch in result['status_mismatches'][:5]:
            print('  status  : issued %r, draft %r — %s'
                  % (mismatch['issued'], mismatch['draft'], mismatch['item']))
        print('')

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2), encoding='utf-8')

    print('SCORE %.1f/100  (coverage %.0f%%, precision %.0f%%, action %.0f%%, '
          'status %.0f%%)'
          % (result['score'], result['coverage'] * 100, result['precision'] * 100,
             result['action_agreement'] * 100, result['status_agreement'] * 100))

    alignment = result['alignment']
    if alignment.get('uncertain') or alignment.get('unplaced'):
        print('APPROX: Action/Status pairing is estimated from the page layout; %d of %d '
              'owner(s) sit within half a line of another item, %d beside no item'
              % (alignment.get('uncertain', 0), alignment.get('placed', 0),
                 alignment.get('unplaced', 0)))
    cells = result['scorecard']
    print('SCORECARD | %s | %s | %s | %s | %s |'
          % (cells['score'], cells['coverage'], cells['precision'], cells['action'],
             cells['status']))

    if args.min_score is not None and result['score'] < args.min_score:
        print('BELOW BASELINE: %.1f < %.1f' % (result['score'], args.min_score))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
