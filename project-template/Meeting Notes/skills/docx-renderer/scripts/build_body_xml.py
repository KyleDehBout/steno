#!/usr/bin/env python3
"""Deterministic body.xml generator for the DOCX renderer.

Replaces the LLM-authored "read the reference XML docs and write a fresh Python
script from scratch" step. The XML shape is identical every render (fixed by the
branded template); only the meeting content changes, so the generation is a
mechanical tree-walk over the parsed draft.

Inputs:
  <draft.md>       the finalized (Stage 4/5) markdown draft
  <body.xml>       output path
  --constants PATH optional override for the project's constants.json (default:
                   discovered by walking up from the draft to the owning
                   skills/docx-renderer/references/constants.json)

The script parses the draft with the sibling check_draft.parse_draft() and emits
the body XML the manual render process produced for the golden render, except that
the Action/Status paragraphs are padded to stay level with wrapped items. It
assumes the draft already passed check_draft (true by pipeline order) but fails
loudly on unparseable input or missing constants rather than emitting bad XML.

The body.xml it writes ends at the "Prepared by" footer paragraph. The step that
splices body.xml into document.xml preserves the template's <w:sectPr>; this
script does not emit one.
"""
import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DRAFT_CHECK_SCRIPTS = SCRIPT_DIR.parents[1] / 'draft-checks' / 'scripts'
if str(DRAFT_CHECK_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DRAFT_CHECK_SCRIPTS))

try:
    from check_draft import parse_draft, illegal_characters
except ImportError:
    sys.exit("error: [install] cannot import parse_draft() from check_draft.py — "
             "expected it at %s. Run /sync-pipeline to reinstall it." % DRAFT_CHECK_SCRIPTS)

# Every failure message starts with the kind of fault, so render.py and /process-notes
# can route it without parsing prose:
#   [draft]    the draft is at fault; the message names the draft line ("draft line N")
#   [config]   the project's constants.json or template; no pipeline stage can fix it
#   [install]  a pipeline script is missing; /sync-pipeline reinstalls it
#   [input]    the draft file itself is missing
#   [renderer] a bug in this script
CONFIG_FIX = ("re-run setup_docx_renderer.py --force (or correct constants.json by hand)")


class DraftError(ValueError):
    """The draft cannot be rendered; the message names the draft line."""


class ConfigError(ValueError):
    """constants.json is missing a key or holds an unusable value."""


def find_constants(start):
    """Locate the project's constants.json by walking up from the draft.

    The file lives at <project>/skills/docx-renderer/references/constants.json,
    the tree setup_docx_renderer.py wrote it into.
    The first ancestor with that file wins.
    """
    for parent in [start.resolve()] + list(start.resolve().parents):
        candidate = parent / 'skills' / 'docx-renderer' / 'references' / 'constants.json'
        if candidate.is_file():
            return candidate
    return None

# Escapes and typography. Escape & first, then the straight-quote characters the
# manual render scripts converted per each project's reference docs. Content that
# already uses typographic characters passes through unchanged (idempotent).
def esc(text):
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = re.sub(r'"([^"]*)"', '&#x201C;\\1&#x201D;', text)  # paired quotes -> open/close
    text = text.replace('"', '&#x201D;')   # unpaired straight quote -> close quote
    text = text.replace("'", '&#x2019;')   # straight apostrophe -> right single
    text = text.replace('\u2018', '&#x2018;')
    text = text.replace('\u2019', '&#x2019;')
    return text


ORDINAL_SUFFIX_RE = re.compile(r'(\d+)(st|nd|rd|th)\b')

def text_runs(text, normal_rpr, super_rpr):
    """Split text into escaped <w:r> runs, raising date ordinals to superscript.

    A date like "June 19th, 2026" renders as "June 19" + superscript "th" +
    ", 2026" per the footer-and-special reference. Text with no ordinals comes
    back as a single normal run — the common case, and byte-identical to what
    the manual renderers wrote.
    """
    runs = []
    cursor = 0
    for match in ORDINAL_SUFFIX_RE.finditer(text):
        if match.start() > cursor:
            runs.append((normal_rpr, text[cursor:match.start()]))
        runs.append((normal_rpr, match.group(1)))
        runs.append((super_rpr, match.group(2)))
        cursor = match.end()
    if cursor < len(text):
        runs.append((normal_rpr, text[cursor:]))
    if not runs:
        runs.append((normal_rpr, text))
    return runs


def w_run(text, rpr, preserve=False):
    space = ' xml:space="preserve"' if preserve else ''
    return '<w:r><w:rPr>%s</w:rPr><w:t%s>%s</w:t></w:r>' % (rpr, space, esc(text))


# Times New Roman advance widths in 1/1000 em (the standard Times-Roman metrics).
# Used only to count how many lines a column-2 paragraph wraps to, so the Action and
# Status paragraphs facing it can be made exactly as tall. Unlisted characters: 500.
_TNR = dict(zip(' !"#$%&\'()*+,-./:;<=>?@',
                [250, 333, 408, 500, 500, 833, 778, 333, 333, 333, 500, 564, 250, 333,
                 250, 278, 278, 278, 564, 564, 564, 444, 921]))
_TNR.update(zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ',
                [722, 667, 667, 722, 611, 556, 722, 722, 333, 389, 722, 611, 889, 722,
                 722, 556, 722, 667, 556, 611, 722, 722, 944, 722, 722, 611]))
_TNR.update(zip('abcdefghijklmnopqrstuvwxyz',
                [444, 500, 444, 500, 444, 333, 500, 500, 278, 278, 500, 278, 778, 500,
                 500, 500, 500, 333, 389, 278, 500, 500, 722, 500, 500, 444]))
_TNR.update({'‘': 333, '’': 333, '“': 444, '”': 444,
             '–': 500, '—': 1000})
# Word's default table cell margins: 108 dxa left and right.
CELL_MARGINS = 216


def wrapped_lines(text, avail_dxa, sz_half_points):
    """Estimate how many lines `text` wraps to in `avail_dxa` of width (greedy word wrap)."""
    em = int(sz_half_points) * 10  # dxa per em: half-points x 10
    space = _TNR[' '] * em / 1000.0
    lines, used = 1, 0.0
    for word in text.split():
        width = sum(_TNR.get(ch, 500) for ch in word) * em / 1000.0
        if used and used + space + width > avail_dxa:
            lines, used = lines + 1, width
        else:
            used += (space if used else 0) + width
    return lines


class Constraints:
    """Wraps constants.json with loud failure on any missing key."""

    def __init__(self, data, source):
        self.data = data
        self.source = source

    def req(self, key):
        if key not in self.data:
            raise ConfigError(
                "constants %s is missing required key %r — %s"
                % (self.source, key, CONFIG_FIX))
        return self.data[key]

    def req_int(self, key):
        """A required constant that must be a whole number (a DXA or half-point value)."""
        value = self.req(key)
        try:
            int(value)
        except (TypeError, ValueError):
            raise ConfigError(
                "constants %s key %r must be a whole number, found %r — %s"
                % (self.source, key, value, CONFIG_FIX))
        return value

    def get(self, key, default=None):
        return self.data.get(key, default)


def build_body(draft, c):
    parts = []

    header = draft.get('header', {})
    title_sz = c.req('title_sz')
    title_sz_cs = c.req('title_sz_cs')
    title_lang = c.req('title_lang')
    title_line = c.req('title_line')

    title_rpr = ('<w:b/><w:bCs/><w:sz w:val="%s"/><w:szCs w:val="%s"/>'
                 '<w:lang w:val="%s"/>' % (title_sz, title_sz_cs, title_lang))

    def title_para(text=None):
        # Empty title paragraph used as the opening blank and is the same rPr
        # with no <w:r> child; a content paragraph appends the run.
        para = ('<w:p><w:pPr><w:spacing w:after="0" w:line="%s" w:lineRule="auto"/>'
                '<w:jc w:val="center"/><w:rPr>%s</w:rPr></w:pPr>' % (title_line, title_rpr))
        if text is None:
            return para + '</w:p>'
        return para + w_run(text, title_rpr) + '</w:p>'

    # -- title block ---------------------------------------------------------
    parts.append(title_para())                          # opening empty
    parts.append(title_para(header.get('TITLE', '')))
    parts.append(title_para('Held on'))
    parts.append(title_para(header.get('HELD ON', '')))
    parts.append(title_para(header.get('TIME', '')))

    # -- attendees -----------------------------------------------------------
    att_font = c.req('att_font')
    att_sz = c.req('att_sz')
    att_sz_cs = c.req('att_sz_cs')
    att_lang = c.req('att_lang')
    att_line = c.req('att_line')
    att_tab_company = c.req('att_tab_company')
    att_tab_position = c.req('att_tab_position')

    att_rpr = ('<w:rFonts w:ascii="%s" w:hAnsi="%s"/><w:sz w:val="%s"/>'
               '<w:szCs w:val="%s"/><w:lang w:val="%s"/>'
               % (att_font, att_font, att_sz, att_sz_cs, att_lang))
    att_bold_rpr = ('<w:rFonts w:ascii="%s" w:hAnsi="%s"/><w:b/><w:bCs/>'
                    '<w:sz w:val="%s"/><w:szCs w:val="%s"/><w:lang w:val="%s"/>'
                    % (att_font, att_font, att_sz, att_sz_cs, att_lang))

    def att_empty():
        return ('<w:p><w:pPr><w:spacing w:after="0" w:line="%s" w:lineRule="auto"/>'
                '<w:rPr>%s</w:rPr></w:pPr></w:p>' % (att_line, att_rpr))

    def att_label():
        return ('<w:p><w:pPr><w:spacing w:after="0" w:line="%s" w:lineRule="auto"/>'
                '<w:rPr>%s</w:rPr></w:pPr><w:r><w:rPr>%s</w:rPr>'
                '<w:t>Attendees:</w:t></w:r></w:p>' % (att_line, att_bold_rpr, att_bold_rpr))

    def att_row(fields):
        cells = ''
        for i, value in enumerate(fields):
            if i:
                cells += '<w:tab/>'
            cells += '<w:t>%s</w:t>' % esc(value)
        return ('<w:p><w:pPr><w:tabs><w:tab w:val="left" w:pos="0"/>'
                '<w:tab w:val="left" w:pos="%s"/><w:tab w:val="left" w:pos="%s"/>'
                '</w:tabs><w:spacing w:after="0" w:line="%s" w:lineRule="auto"/>'
                '<w:rPr>%s</w:rPr></w:pPr><w:r><w:rPr>%s</w:rPr>%s</w:r></w:p>'
                % (att_tab_company, att_tab_position, att_line, att_rpr, att_rpr, cells))

    parts.append(att_empty())
    parts.append(att_empty())
    parts.append(att_label())
    for row in draft.get('attendees', []):
        fields = row.get('fields', [])
        # Never drop or truncate an attendee: a row that is not exactly
        # Name / Organisation / Title stops the render.
        if len(fields) != 3:
            raise DraftError(
                "draft line %s: attendee row needs exactly 3 fields (Name / "
                "Organisation / Title) separated by tabs, found %d: %r"
                % (row.get('line', '?'), len(fields), row.get('raw', '')[:60]))
        parts.append(att_row(fields))
    parts.append(att_empty())
    parts.append(att_empty())

    # -- table ---------------------------------------------------------------
    tbl_total_w = c.req('tbl_total_w')
    col_widths = c.req('col_widths')
    if not isinstance(col_widths, list) or len(col_widths) < 4:
        raise ConfigError(
            "constants %s must define col_widths as a list of 4 DXA strings — %s"
            % (c.source, CONFIG_FIX))
    for width in col_widths[:4]:
        try:
            int(width)
        except (TypeError, ValueError):
            raise ConfigError(
                "constants %s col_widths must be whole numbers, found %r — %s"
                % (c.source, width, CONFIG_FIX))
    col1_w, col2_w, col3_w, col4_w = (str(x) for x in col_widths[:4])

    tbl_look = ('<w:tblLook w:val="%s" w:firstRow="%s" w:lastRow="%s" '
                'w:firstColumn="%s" w:lastColumn="%s" w:noHBand="%s" w:noVBand="%s"/>'
                % (c.req('tbl_look_val'), c.req('tbl_look_first_row'),
                   c.req('tbl_look_last_row'), c.req('tbl_look_first_col'),
                   c.req('tbl_look_last_col'), c.req('tbl_look_no_hband'),
                   c.req('tbl_look_no_vband')))

    num_id = c.req('num_id')
    col1_style = c.req('col1_style')
    col2_style_l0 = c.req('col2_style_l0')
    col2_style_l2 = c.req('col2_style_l2')
    col2_style_l3 = c.req('col2_style_l3')
    l2_left = c.req_int('l2_left')
    l2_hanging = c.req_int('l2_hanging')
    l3_left = c.req_int('l3_left')
    l3_hanging = c.req_int('l3_hanging')
    tbl_font = c.req('tbl_font')
    tbl_sz = c.req_int('tbl_sz')
    tbl_lang = c.req('tbl_lang')
    header_row_h = c.req('header_row_h')
    meetings_row_h = c.req('meetings_row_h')
    title_bold = c.get('title_bold', '1')

    tbl_rpr = ('<w:rFonts w:ascii="%s" w:hAnsi="%s"/><w:sz w:val="%s"/>'
               '<w:szCs w:val="%s"/><w:lang w:val="%s"/>'
               % (tbl_font, tbl_font, tbl_sz, tbl_sz, tbl_lang))
    tbl_bold_rpr = ('<w:rFonts w:ascii="%s" w:hAnsi="%s"/><w:b/><w:bCs/>'
                    '<w:sz w:val="%s"/><w:szCs w:val="%s"/><w:lang w:val="%s"/>'
                    % (tbl_font, tbl_font, tbl_sz, tbl_sz, tbl_lang))

    border = '<w:tcBorders><w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/></w:tcBorders>'

    empty_title_run_rpr = '<w:szCs w:val="%s"/><w:lang w:val="%s"/>' % (tbl_sz, tbl_lang)
    title_run_rpr = ((('<w:b/><w:bCs/>' if title_bold == '1' else '')
                      + empty_title_run_rpr))
    sub_run_rpr = '<w:i/><w:iCs/><w:szCs w:val="%s"/><w:lang w:val="%s"/>' % (tbl_sz, tbl_lang)
    item_run_rpr = '<w:lang w:val="%s"/>' % tbl_lang
    sub_rpr = '<w:vertAlign w:val="superscript"/><w:lang w:val="%s"/>' % tbl_lang

    heading_spacing = '<w:spacing w:line="240" w:lineRule="auto"/>'
    item_spacing = '<w:spacing w:after="240" w:line="240" w:lineRule="auto"/>'

    def col2_section_title(text):
        return ('<w:p><w:pPr><w:pStyle w:val="%s"/><w:numPr><w:ilvl w:val="0"/>'
                '<w:numId w:val="0"/></w:numPr>%s'
                '<w:rPr>%s</w:rPr></w:pPr>%s%s'
                % (col2_style_l0, heading_spacing, empty_title_run_rpr,
                   w_run(text, title_run_rpr), '</w:p>'))

    def col2_subsection(text):
        body = ''.join(w_run(t, rpr) for rpr, t in text_runs(text, sub_run_rpr, sub_rpr))
        return ('<w:p><w:pPr><w:pStyle w:val="%s"/><w:numPr><w:ilvl w:val="1"/>'
                '<w:numId w:val="%s"/></w:numPr>%s</w:pPr>%s'
                % (col2_style_l2, num_id, heading_spacing, body)) + '</w:p>'

    def col2_item(text, ilvl, ind_left, ind_hanging, pstyle):
        body = ''.join(w_run(t, rpr) for rpr, t in text_runs(text, item_run_rpr, sub_rpr))
        return ('<w:p><w:pPr><w:pStyle w:val="%s"/><w:numPr><w:ilvl w:val="%s"/>'
                '<w:numId w:val="%s"/></w:numPr>%s'
                '<w:ind w:left="%s" w:hanging="%s"/><w:rPr><w:bCs w:val="0"/></w:rPr>'
                '</w:pPr>%s'
                % (pstyle, ilvl, num_id, item_spacing, ind_left, ind_hanging, body)) + '</w:p>'

    # Each Action/Status paragraph mirrors the column-2 paragraph it faces: same style
    # (numbering suppressed) so it inherits the same before/after spacing from the
    # template, same explicit spacing, and as many lines tall (line breaks) as that
    # paragraph wraps to. One-line side paragraphs facing wrapped items drifted up and
    # put each owner beside the item above its own (M13).
    col2_text_w = int(col2_w) - CELL_MARGINS
    heading_indent = int(l2_left) - int(l2_hanging)

    def face(pstyle, spacing, text, indent):
        return pstyle, spacing, wrapped_lines(text, col2_text_w - int(indent), tbl_sz)

    def col1_counter():
        return ('<w:tc><w:tcPr><w:tcW w:w="%s" w:type="dxa"/>%s</w:tcPr>'
                '<w:p><w:pPr><w:pStyle w:val="%s"/><w:numPr><w:ilvl w:val="0"/>'
                '<w:numId w:val="%s"/></w:numPr>'
                '<w:spacing w:line="240" w:lineRule="auto"/></w:pPr></w:p></w:tc>'
                % (col1_w, border, col1_style, num_id))

    def side_cell(width, values, faces):
        paragraphs = []
        for value, (pstyle, spacing, lines) in zip(values, faces):
            runs = ('<w:r><w:rPr>%s</w:rPr><w:t>%s</w:t></w:r>' % (tbl_rpr, esc(value))
                    if value else '')
            if lines > 1:
                runs += '<w:r><w:rPr>%s</w:rPr>%s</w:r>' % (tbl_rpr, '<w:br/>' * (lines - 1))
            paragraphs.append(
                '<w:p><w:pPr><w:pStyle w:val="%s"/><w:numPr><w:ilvl w:val="0"/>'
                '<w:numId w:val="0"/></w:numPr>%s<w:ind w:left="0" w:hanging="0"/>'
                '<w:jc w:val="center"/><w:rPr>%s</w:rPr></w:pPr>%s</w:p>'
                % (pstyle, spacing, tbl_rpr, runs))
        return ('<w:tc><w:tcPr><w:tcW w:w="%s" w:type="dxa"/>%s</w:tcPr>%s</w:tc>'
                % (width, border, ''.join(paragraphs)))

    def header_cell(width, text, bold=False):
        rpr = tbl_bold_rpr if bold else tbl_rpr
        if text is None:
            return ('<w:tc><w:tcPr><w:tcW w:w="%s" w:type="dxa"/></w:tcPr>'
                    '<w:p><w:pPr><w:spacing w:after="0"/><w:jc w:val="center"/></w:pPr></w:p></w:tc>'
                    % width)
        return ('<w:tc><w:tcPr><w:tcW w:w="%s" w:type="dxa"/></w:tcPr>'
                '<w:p><w:pPr><w:spacing w:after="0"/><w:jc w:val="center"/>'
                '<w:rPr>%s</w:rPr></w:pPr><w:r><w:rPr>%s</w:rPr><w:t>%s</w:t></w:r></w:p></w:tc>'
                % (width, rpr, rpr, esc(text)))

    header_text = c.get('tbl_header_text', c.req('project_name'))

    tbl = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>'
           '<w:tblW w:w="%s" w:type="dxa"/>%s</w:tblPr>'
           '<w:tblGrid><w:gridCol w:w="%s"/><w:gridCol w:w="%s"/>'
           '<w:gridCol w:w="%s"/><w:gridCol w:w="%s"/></w:tblGrid>'
           % (tbl_total_w, tbl_look, col1_w, col2_w, col3_w, col4_w)]

    tbl.append('<w:tr><w:trPr><w:trHeight w:val="%s"/></w:trPr>'
               % header_row_h)
    tbl.append(header_cell(col1_w, None))
    tbl.append(header_cell(col2_w, header_text, bold=True))
    tbl.append(header_cell(col3_w, 'Action', bold=True))
    tbl.append(header_cell(col4_w, 'Status', bold=True))
    tbl.append('</w:tr>')

    def append_item(col2, col3, col4, faces, item):
        col2.append(col2_item(item.get('text', ''), 2,
                              l2_left, l2_hanging, col2_style_l2))
        col3.append(item.get('action', ''))
        col4.append(item.get('status', ''))
        faces.append(face(col2_style_l2, item_spacing, item.get('text', ''), l2_left))
        for bullet in item.get('bullets', []):
            col2.append(col2_item(bullet.get('text', ''), 3,
                                  l3_left, l3_hanging, col2_style_l3))
            # A plain bullet has no cells; a dependent follow-up may carry its own.
            col3.append(bullet.get('action', ''))
            col4.append(bullet.get('status', ''))
            faces.append(face(col2_style_l3, item_spacing, bullet.get('text', ''), l3_left))

    for section in draft.get('sections', []):
        col2 = []
        col3 = []
        col4 = []
        faces = []

        col2.append(col2_section_title(section.get('title', '')))
        col3.append('')
        col4.append('')
        faces.append(face(col2_style_l0, heading_spacing, section.get('title', ''),
                          heading_indent))

        placed = set()
        for subsection in section.get('subsections', []):
            col2.append(col2_subsection(subsection.get('label', '')))
            col3.append('')
            col4.append('')
            faces.append(face(col2_style_l2, heading_spacing, subsection.get('label', ''),
                              heading_indent))
            for item in section.get('items', []):
                if tuple(item.get('num', ())[:2]) == tuple(subsection.get('num', ())):
                    placed.add(id(item))
                    append_item(col2, col3, col4, faces, item)

        for item in section.get('items', []):
            if id(item) not in placed:
                # Item whose subsection number has no heading — emit it directly
                # under the section title so its content is never dropped.
                append_item(col2, col3, col4, faces, item)

        tbl.append('<w:tr>' + col1_counter()
                   + ('<w:tc><w:tcPr><w:tcW w:w="%s" w:type="dxa"/>%s</w:tcPr>%s</w:tc>'
                      % (col2_w, border, ''.join(col2)))
                   + side_cell(col3_w, col3, faces)
                   + side_cell(col4_w, col4, faces)
                   + '</w:tr>')

    # -- meetings row ---------------------------------------------------------
    meetings = draft.get('meetings') or ''
    mtg_rpr = tbl_bold_rpr
    mtg_side = ('<w:tc><w:tcPr><w:tcW w:w="%s" w:type="dxa"/></w:tcPr>'
                '<w:p><w:pPr><w:spacing w:after="0"/></w:pPr></w:p></w:tc>')
    mtg_col2_title = ('<w:tc><w:tcPr><w:tcW w:w="%s" w:type="dxa"/></w:tcPr>'
                      '<w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/>'
                      '<w:rPr>%s</w:rPr></w:pPr><w:r><w:rPr>%s</w:rPr>'
                      '<w:t>MEETINGS</w:t></w:r></w:p>'
                      % (col2_w, mtg_rpr, mtg_rpr))
    mtg_col2_date = ('<w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/>'
                     '<w:rPr>%s</w:rPr></w:pPr>%s</w:p></w:tc>'
                     % (mtg_rpr, ''.join(
                         w_run(t, rpr)
                         for rpr, t in text_runs(
                             meetings, mtg_rpr,
                             '<w:vertAlign w:val="superscript"/><w:lang w:val="%s"/>'
                             % tbl_lang))))
    tbl.append('<w:tr><w:trPr><w:trHeight w:val="%s"/></w:trPr>'
               % meetings_row_h)
    tbl.append(mtg_side % col1_w)
    tbl.append(mtg_col2_title + mtg_col2_date)
    tbl.append(mtg_side % col3_w)
    tbl.append(mtg_side % col4_w)
    tbl.append('</w:tr>')
    tbl.append('</w:tbl>')
    parts.append(''.join(tbl))

    # -- footer ---------------------------------------------------------------
    footer_spacing = c.req('footer_spacing_before')
    footer_sz = c.req('footer_sz')
    footer_sz_cs = c.req('footer_sz_cs')
    footer_lang = c.req('footer_lang')
    footer_font = c.req('footer_font')
    org_name = c.req('org_name')
    org_suffix = c.req('org_suffix')
    org_color = c.req('org_color')

    footer_rpr = ('<w:rFonts w:ascii="%s" w:hAnsi="%s"/><w:sz w:val="%s"/>'
                  '<w:szCs w:val="%s"/><w:lang w:val="%s"/>'
                  % (footer_font, footer_font, footer_sz, footer_sz_cs, footer_lang))
    footer_bold_rpr = ('<w:rFonts w:ascii="%s" w:hAnsi="%s"/><w:b/><w:bCs/>'
                       '<w:color w:val="%s"/><w:sz w:val="%s"/><w:szCs w:val="%s"/>'
                       '<w:lang w:val="%s"/>'
                       % (footer_font, footer_font, org_color, footer_sz,
                          footer_sz_cs, footer_lang))

    parts.append(
        '<w:p><w:pPr><w:spacing w:before="%s"/><w:rPr>%s</w:rPr></w:pPr>'
        '%s%s%s</w:p>'
        % (footer_spacing, footer_rpr,
           w_run('Prepared by: ', footer_rpr, preserve=True),
           w_run(org_name, footer_bold_rpr),
           w_run(org_suffix, footer_rpr, preserve=True)))

    return ''.join(parts)


# Characters XML 1.0 forbids. One in the draft makes document.xml unparseable, and
# validate.py would then report a column in document.xml that no stage can act on.
# The rule is check_draft's, so Stage 4.5 catches the same characters first.
def check_characters(text):
    """Raise DraftError naming the first draft line holding a character Word cannot store.

    Runs on the raw text before parse_draft(), which would otherwise report the
    fragments a form feed leaves as format errors instead."""
    for number, char, context in illegal_characters(text):
        raise DraftError(
            "draft line %d: character U+%04X cannot go into a Word document (an "
            "invisible control or non-character) — delete it. It follows %r"
            % (number, ord(char), context))


def draft_errors_message(errors):
    """One message for parse errors, naming the draft line of each (up to five)."""
    shown = ['draft line %s: [%s] %s' % (f.line or '?', f.code, f.message)
             for f in errors[:5]]
    more = ' (+%d more)' % (len(errors) - 5) if len(errors) > 5 else ''
    return ("%d format error(s) — build_body_xml.py renders only drafts that pass "
            "check_draft: %s%s" % (len(errors), '; '.join(shown), more))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate body.xml for a finalized meeting-notes draft.")
    parser.add_argument('draft', help="finalized draft markdown path")
    parser.add_argument('output', help="where to write body.xml")
    parser.add_argument('--constants',
                        help="path to constants.json (default: auto-discovered)")
    args = parser.parse_args(argv)

    draft_path = Path(args.draft)
    if not draft_path.is_file():
        sys.exit("error: [input] draft not found: %s" % draft_path)

    constants_path = (Path(args.constants) if args.constants else None)
    if constants_path is None:
        constants_path = find_constants(draft_path)
    if constants_path is None or not constants_path.is_file():
        sys.exit("error: [config] constants.json not found — expected it at "
                 "<project>/skills/docx-renderer/references/constants.json. "
                 "Run setup_docx_renderer.py --force to create it.")

    try:
        constants = Constraints(json.loads(constants_path.read_text(encoding='utf-8')),
                                str(constants_path))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        sys.exit("error: [config] %s is not valid JSON: %s — %s"
                 % (constants_path, e, CONFIG_FIX))
    if not isinstance(constants.data, dict):
        sys.exit("error: [config] %s must hold a JSON object — %s"
                 % (constants_path, CONFIG_FIX))

    raw = draft_path.read_bytes()
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as e:
        sys.exit("error: [draft] draft line %d: bytes that are not UTF-8 text (byte 0x%02X) "
                 "— retype the characters on that line"
                 % (raw[:e.start].count(b'\n') + 1, raw[e.start]))

    try:
        check_characters(text)
    except DraftError as e:
        sys.exit("error: [draft] %s" % e)

    draft, findings = parse_draft(text)
    errors = [f for f in findings if f.level == 'ERROR']
    if errors:
        sys.exit("error: [draft] %s" % draft_errors_message(errors))

    try:
        body = build_body(draft, constants)
    except DraftError as e:
        sys.exit("error: [draft] %s" % e)
    except ConfigError as e:
        sys.exit("error: [config] %s" % e)
    except Exception as e:  # anything else is a bug here, not in the draft
        sys.exit("error: [renderer] build_body_xml.py crashed: %s: %s — a renderer bug, "
                 "not a draft or config problem" % (type(e).__name__, e))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding='utf-8')
    print("body XML written to %s (%d bytes)" % (out_path, len(body)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
