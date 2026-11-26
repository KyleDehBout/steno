"""Replace the body of an unpacked document.xml with a generated body.xml.

Usage: splice_body.py <document.xml> <body.xml>

Everything between the <w:body> open tag and the template's final <w:sectPr> is
replaced by body.xml, inserted verbatim: build_body_xml.py has already escaped the
draft's text. The root element, its namespace declarations and the <w:sectPr> (which
carries the header and footer references) are kept byte for byte. Works on bytes, so
the template's own line endings survive too.
"""
import re
import sys

BODY_OPEN_RE = re.compile(rb'<w:body(?:\s[^>]*)?>')


def splice(document, body):
    """document.xml bytes with its body content replaced by body bytes."""
    m = BODY_OPEN_RE.search(document)
    if not m:
        raise ValueError("no <w:body> in document.xml")
    body_close = document.rfind(b'</w:body>')
    if body_close == -1:
        raise ValueError("no </w:body> in document.xml")
    sect_start = document.rfind(b'<w:sectPr', m.end(), body_close)
    if sect_start == -1:
        raise ValueError("no <w:sectPr> in the template body — header/footer "
                         "references would be lost")
    return document[:m.end()] + body + document[sect_start:]


def main():
    if len(sys.argv) != 3:
        print("Usage: splice_body.py <document.xml> <body.xml>")
        sys.exit(1)
    doc_path, body_path = sys.argv[1], sys.argv[2]
    try:
        with open(doc_path, 'rb') as fh:
            document = fh.read()
        with open(body_path, 'rb') as fh:
            body = fh.read()
        spliced = splice(document, body)
        with open(doc_path, 'wb') as fh:
            fh.write(spliced)
    except (OSError, ValueError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    print(f"OK: body spliced into {doc_path}")


if __name__ == "__main__":
    main()
