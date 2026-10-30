#!/usr/bin/env python3
"""Wrap docs/wiring.html (an Artifact fragment) into a standalone print document.

The artifact platform supplies the <!doctype>/<head>/<body> skeleton at publish
time, so the source file is a fragment. Printing it needs a real document, a
forced light palette (a PDF has no viewer theme), and page-break rules.

It also grows a table of contents. That is built here rather than written into
the source so it cannot go stale: the entries ARE the document's headings, and
a section renamed or added shows up in the TOC on the next build with nothing
to remember. Anchor ids are derived from the heading text the same way, so the
links in the PDF point at whatever the headings currently say.
"""

import pathlib
import re
import sys
import unicodedata

src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "docs/wiring.html")
dst = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "build/wiring-print.html")

frag = src.read_text()
i = frag.index("</style>") + len("</style>")
head, body = frag[:i], frag[i:]


def slug(markup):
    """A stable anchor id from heading text. ASCII-folded, so the em dashes and
    the Greek in headings like "PCB Stage 2 - 5 V in" just drop out."""
    t = re.sub(r"<[^>]+>", "", markup)
    t = t.replace("&nbsp;", " ").replace("&#8217;", "'").replace("&amp;", "&")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower()
    return t or "section"


# One pass, so the TOC comes out in document order and the ids it links to are
# injected by the same match that produced the entry.
HEADINGS = re.compile(
    r'(?P<sec><div class="sechead"><h2)>(?P<sect>.*?)</h2>\s*'
    r'<span class="n">(?P<secn>.*?)</span>'
    r'|(?P<sub><h3 class="sub-h")>(?P<subt>.*?)</h3>',
    re.S,
)


def add_anchors(body):
    """Inject id= on every section and subsection heading, returning the
    rewritten body and a flat list of (level, text, subtitle, slug)."""
    entries, used = [], {}

    def uniq(base):
        used[base] = used.get(base, 0) + 1
        return base if used[base] == 1 else f"{base}-{used[base]}"

    def repl(m):
        if m.group("sec"):
            sid = uniq(slug(m.group("sect")))
            entries.append((2, m.group("sect"), m.group("secn"), sid))
            return (
                f'{m.group("sec")} id="{sid}">{m.group("sect")}</h2>'
                f'<span class="n">{m.group("secn")}</span>'
            )
        sid = uniq(slug(m.group("subt")))
        entries.append((3, m.group("subt"), None, sid))
        return f'{m.group("sub")} id="{sid}">{m.group("subt")}</h3>'

    return HEADINGS.sub(repl, body), entries


def build_toc(entries):
    """Nest the subsections under their section. No page numbers: Chrome's
    print-to-PDF supports neither @page margin boxes nor target-counter(), so
    a number here would be a lie. The entries are links instead."""
    out = ['<nav class="toc">', "<h2>Contents</h2>", "<ol>"]
    open_sub = False
    for level, text, subtitle, sid in entries:
        if level == 2:
            if open_sub:
                out.append("</ul>")
                open_sub = False
            if len(out) > 3:
                out.append("</li>")
            out.append(f'<li><a href="#{sid}">{text}</a> <span class="n">{subtitle}</span>')
        else:
            if not open_sub:
                out.append("<ul>")
                open_sub = True
            out.append(f'<li><a href="#{sid}">{text}</a></li>')
    if open_sub:
        out.append("</ul>")
    out += ["</li>", "</ol>", "</nav>"]
    return "\n".join(out) + "\n\n"


PRINT_CSS = """
<style>
:root, :root[data-theme="dark"] {
  --bg:#FFFFFF; --surface:#FFFFFF; --surface-2:#F4F6F8;
  --ink:#14191E; --ink-2:#414C56; --ink-3:#6B7681; --rule:#C9D1D8;
  --v5:#B8342B; --gnd:#232930; --data:#0B7454; --sw:#23598F;
  --warn:#8A5000; --warn-bg:#FBF2E0; --warn-rule:#D9B06A;
}
@page { size: A4 portrait; margin: 15mm 14mm; }
html, body { background:#FFFFFF; }
.wrap { max-width:none; padding:0; }
.scroll { overflow:visible; }
svg { min-width:0; width:100%; }
.tw { overflow:visible; }
figure, table, .rule-box, .warn { break-inside:avoid; }
tr, ol.steps li { break-inside:avoid; }
.sechead, h1, h2, h3 { break-after:avoid; }
thead { display:table-header-group; }
h1 { font-size:40px; }
body { font-size:11pt; line-height:1.5; }
section { margin-top:26px; }
figcaption, p, ol.steps li { max-width:none; }
.legend { font-size:10px; }

/* Contents. Print-only: on the web the artifact is one scrolling page. */
.toc { break-after:page; margin:34px 0 0; }
.toc h2 { font-size:21px; margin:0 0 14px; padding-bottom:8px;
          border-bottom:1px solid var(--rule); }
.toc ol { list-style:none; margin:0; padding:0; counter-reset:toc;
           column-count:2; column-gap:30px; }
.toc > ol > li { counter-increment:toc; margin:0 0 10px; break-inside:avoid; }
.toc > ol > li > a::before { content:counter(toc) ". "; color:var(--ink-3);
                             font-family:var(--mono); font-weight:400; }
.toc a { color:var(--ink); text-decoration:none; font-weight:600; }
.toc .n { font-family:var(--mono); font-size:9.5px; color:var(--ink-3); }
.toc ul { list-style:none; margin:3px 0 0 26px; padding:0; }
.toc ul li { margin:1px 0; }
.toc ul a { font-weight:400; font-size:10.5pt; color:var(--ink-2); }
</style>
"""

FOOT = """
<p style="margin-top:36px;padding-top:10px;border-top:1px solid var(--rule);
   font-family:var(--mono);font-size:9.5px;color:var(--ink-3)">
  Whack-A-Mole Attack &middot; harness reference &middot;
  values mirrored from firmware/WhackAMole/Config.h
</p>
"""

body = body.rstrip()
assert body.endswith("</div>"), "fragment should end with the wrapper div"

body, entries = add_anchors(body)
assert entries, "no headings found -- has the sechead markup changed?"
body = body.replace("<section>", build_toc(entries) + "<section>", 1)
doc = (
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    + head
    + PRINT_CSS
    + "\n</head>\n<body>\n"
    + body[: -len("</div>")]
    + FOOT
    + "</div>\n</body>\n</html>\n"
)

dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(doc)
secs = sum(1 for e in entries if e[0] == 2)
print(f"{dst} ({len(doc)} bytes) -- TOC: {secs} sections, {len(entries) - secs} subsections")
