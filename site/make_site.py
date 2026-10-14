# SPDX-License-Identifier: AGPL-3.0-or-later
"""Builds the aiai web site into site/public/, from what the repository
already holds: the hand-written top page (index.html, with the latest news
put in), one page per skill (each folder's SKILL.md, with a button that
copies it whole and its ZIP), the thinking behind aiai (app/assets/kangaekata.md)
and the news (news/*.adoc, the ones a person has read and committed).
site/server.py serves the folder. Only the standard library is used.

    python site/make_site.py

Markdown and AsciiDoc are read only as far as aiai writes them: headings,
paragraphs, lists, tables, code, bold, links and bare URLs. Links to files in
the repository are shown as plain text, since the site does not carry them.
"""
import html
import json
import os
import re
import shutil

from make_assets import first_paragraph

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "public")

# The order of the guides, and the label each guide's page shows; others come last
STEPS = [("AI の活用法", ["rireki", "website", "moushikomi", "genba", "kaiseki", "kanri", "news"]),
         ("手引き", ["tenshoku", "gakusei", "keikaku"])]
NEWS_ON_TOP = 3
# The fixes Gemini makes by itself on the server (tools/kaiseki_jidou.py), when AIAI_JIDOU names their folder
JIDOU = os.environ.get("AIAI_JIDOU", "")


# ---- reading Markdown -------------------------------------------------------------------


def split_front(text):
    """({front matter}, body) of a SKILL.md."""
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        return {}, text
    head = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
    return {k.strip(): v.strip() for k, v in head.items()}, m.group(2)


def join_lines(lines):
    """Joins wrapped lines: a space only between two ASCII words, as Japanese has none."""
    out = ""
    for line in (x.strip() for x in lines):
        if out and line and out[-1].isascii() and out[-1] not in " (" and line[0].isascii():
            out += " "
        out += line
    return out


URL = re.compile(r"https?://[^\s<>()、。」』）]+[^\s<>()、。」』）.,:;]")


def inline(text):
    """HTML of one line: code, bold, links and bare URLs; everything else escaped."""
    keep = []

    def hold(s):
        keep.append(s)
        return f"\x00{len(keep) - 1}\x00"

    text = re.sub(r"`([^`]+)`", lambda m: hold(f"<code>{html.escape(m[1])}</code>"), text)

    def link(m):
        label, href = m[1], m[2]
        if re.match(r"https?://", href):
            return hold(f'<a href="{html.escape(href)}">{inline(label)}</a>')
        return hold(inline(label))  # a file in the repository: shown as text

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)
    text = URL.sub(lambda m: hold(f'<a href="{html.escape(m[0])}">{html.escape(m[0])}</a>'), text)
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m[1])], text)


LIST_ITEM = re.compile(r"^(\s*)([-*]|\d+\.) (.*)$")


def render_list(lines):
    """HTML of a list block; lines indented under an item belong to it, and
    a deeper list inside an item becomes a nested list."""
    first = LIST_ITEM.match(lines[0])
    indent, tag = len(first[1]), "ol" if first[2][0].isdigit() else "ul"
    items, current = [], None
    for line in lines:
        m = LIST_ITEM.match(line)
        if m and len(m[1]) == indent:
            current = [m[3]]
            items.append(current)
        elif current is not None:
            current.append(line)
    out = []
    for item in items:
        text, rest = [item[0]], []
        for line in item[1:]:
            if rest or LIST_ITEM.match(line):
                rest.append(line)
            else:
                text.append(line)
        inner = inline(join_lines(text))
        if rest:
            inner += render_list([x for x in rest if x.strip()])
        out.append(f"<li>{inner}</li>")
    return f"<{tag}>" + "".join(out) + f"</{tag}>"


def render_table(lines):
    def cells(line):
        return [c.strip() for c in line.strip().strip("|").split("|")]

    head, body = cells(lines[0]), [cells(x) for x in lines[2:]]
    out = ["<div class=\"table\"><table><thead><tr>", *[f"<th>{inline(c)}</th>" for c in head], "</tr></thead><tbody>"]
    for row in body:
        out += ["<tr>", *[f"<td>{inline(c)}</td>" for c in row], "</tr>"]
    return "".join(out + ["</tbody></table></div>"])


FIGURES = os.path.join(HERE, "figures")


def figure(name):
    """A diagram from site/figures/<name>.svg, put in the page as it is (it uses the page's colours)."""
    path = os.path.join(FIGURES, f"{name}.svg")
    return f'<figure class="fig">{read(path)}</figure>' if os.path.exists(path) else ""


def markdown(text):
    """HTML of Markdown as aiai writes it. A line {{fig:name}} puts in a diagram."""
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif m := re.fullmatch(r"\{\{fig:([\w-]+)\}\}", line.strip()):
            out.append(figure(m[1]))
            i += 1
        elif line.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(lines[i + 1:j])) + "</code></pre>")
            i = j + 1
        elif m := re.match(r"(#{1,6}) (.*)", line):
            n, text_ = len(m[1]), m[2].strip()
            # a heading may end in {#name}, which becomes its id, for links to it
            anchor = re.search(r"\s*\{#([\w-]+)\}$", text_)
            if anchor:
                text_ = text_[:anchor.start()]
            out.append(f'<h{n} id="{anchor[1]}">{inline(text_)}</h{n}>' if anchor else f"<h{n}>{inline(text_)}</h{n}>")
            i += 1
        elif line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            out.append(render_table(lines[i:j]))
            i = j
        elif LIST_ITEM.match(line):
            j = i + 1
            while j < len(lines) and (LIST_ITEM.match(lines[j]) or (lines[j].startswith(" ") and lines[j].strip())
                                      or (not lines[j].strip() and j + 1 < len(lines) and lines[j + 1].startswith(" "))):
                j += 1
            out.append(render_list(lines[i:j]))
            i = j
        else:
            j = i
            while (j < len(lines) and lines[j].strip() and not lines[j].startswith(("#", "```", "|"))
                   and not LIST_ITEM.match(lines[j])):
                j += 1
            out.append(f"<p>{inline(join_lines(lines[i:j]))}</p>")
            i = j
    return "\n".join(out)


# ---- reading the user manual (AsciiDoc) -----------------------------------------------------

ADOC_LINK = re.compile(r"(https?://[^\s\[\]<>]+)\[([^\]]*)\]")
ADOC_ITEM = re.compile(r"^(\*+|\.+) (.*)$")


def adoc_inline(text):
    """HTML of one line of AsciiDoc: `code`, URL[label], bare URLs, *bold*; the rest is escaped."""
    keep = []

    def hold(s):
        keep.append(s)
        return f"\x00{len(keep) - 1}\x00"

    text = re.sub(r"`([^`]+)`", lambda m: hold(f"<code>{html.escape(m[1])}</code>"), text)
    text = re.sub(r"\^([^\s^]+)\^", lambda m: hold(f"<sup>{html.escape(m[1])}</sup>"), text)  # a note's number, ^[1]^
    text = ADOC_LINK.sub(lambda m: hold(f'<a href="{html.escape(m[1])}">{adoc_inline(m[2]) or html.escape(m[1])}</a>'), text)
    text = URL.sub(lambda m: hold(f'<a href="{html.escape(m[0])}">{html.escape(m[0])}</a>'), text)
    text = html.escape(text)
    text = re.sub(r"\*([^*\s][^*]*?)\*", r"<strong>\1</strong>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m[1])], text)


def adoc_list(items):
    """HTML of [(marker, text lines)]: the marker's length is the depth, `.` an ordered list."""
    out, i = [], 0
    tag = "ol" if items[0][0][0] == "." else "ul"
    depth = len(items[0][0])
    while i < len(items):
        marker, lines = items[i]
        i += 1
        j = i
        while j < len(items) and len(items[j][0]) > depth:
            j += 1
        inner = adoc_inline(join_lines(lines))
        if j > i:
            inner += adoc_list(items[i:j])
        out.append(f"<li>{inner}</li>")
        i = j
    return f"<{tag}>" + "".join(out) + f"</{tag}>"


def adoc_table(rows):
    def cells(line):
        return [c.strip() for c in line.strip().lstrip("|").split(" | ")]

    rows = [r for r in rows if r.strip()]
    out = ['<div class="table"><table><thead><tr>', *[f"<th>{adoc_inline(c)}</th>" for c in cells(rows[0])], "</tr></thead><tbody>"]
    for row in rows[1:]:
        out += ["<tr>", *[f"<td>{adoc_inline(c)}</td>" for c in cells(row)], "</tr>"]
    return "".join(out + ["</tbody></table></div>"])


def adoc_blocks(lines, images="images/"):
    """HTML of the blocks of AsciiDoc lines: paragraphs, lists, tables, quotes, code and images.
    The path of an image starts with `images/`, which is put in front of the file's name as `images`."""
    out, i, para, items = [], 0, [], []

    def close():
        if para:
            out.append(f"<p>{adoc_inline(join_lines(para))}</p>")
            para.clear()
        if items:
            out.append(adoc_list(list(items)))
            items.clear()

    while i < len(lines):
        line = lines[i]
        if not line.strip():
            close()
        elif line.startswith("|==="):
            close()
            j = i + 1
            while j < len(lines) and not lines[j].startswith("|==="):
                j += 1
            out.append(adoc_table(lines[i + 1:j]))
            i = j
        elif line.startswith("____"):
            close()
            j = i + 1
            while j < len(lines) and not lines[j].startswith("____"):
                j += 1
            out.append("<blockquote>" + adoc_blocks(lines[i + 1:j], images) + "</blockquote>")
            i = j
        elif line.startswith("----"):
            close()
            j = i + 1
            while j < len(lines) and not lines[j].startswith("----"):
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(lines[i + 1:j])) + "</code></pre>")
            i = j
        elif m := re.fullmatch(r"image::([^\[]+)\[(.*)\]", line.strip()):
            close()
            out.append(f'<figure class="fig"><img src="{html.escape(images + os.path.basename(m[1]))}" alt="{html.escape(m[2])}"></figure>')
        elif re.fullmatch(r"\[.*\]", line.strip()):  # attribute lines such as [cols="1,3"]
            pass
        elif m := ADOC_ITEM.match(line):
            if para:
                close()
            items.append((m[1], [m[2]]))
        elif items and line.startswith(" "):  # a wrapped line of the last item
            items[-1][1].append(line)
        elif line.strip() == "+":
            pass
        else:
            if items:
                close()
            para.append(line)
        i += 1
    close()
    return "\n".join(out)


def read_adoc(text, images="images/"):
    """(title, [section]) of an AsciiDoc document. A section is a dict of its level (2 for ==, 3 for ===),
    its heading, its id (a [[id]] line above it, or s1, s2, ...) and its HTML (up to the next heading).
    The first section is the text before the first heading, at level 0. The attribute lines (:x:) are not read."""
    title, sections, body, head, anchor = "", [], [], {"level": 0, "title": "", "id": ""}, ""

    def close():
        sections.append(head | {"html": adoc_blocks(body, images)})
        body.clear()

    for line in text.splitlines():
        if re.match(r"^:[^:\s][^:]*:", line):
            continue
        if m := re.fullmatch(r"\[\[([\w-]+)\]\]", line.strip()):
            anchor = m[1]
        elif m := re.match(r"^(={1,3}) (.*)$", line):
            if len(m[1]) == 1:
                title = m[2].strip()
            else:
                close()
                head = {"level": len(m[1]), "title": m[2].strip(), "id": anchor or f"s{len(sections)}"}
                anchor = ""
        else:
            body.append(line)
    close()
    return title, sections


SHOUKAI = os.path.join(ROOT, "shoukai")  # introductions of what is used with aiai: shoukai/<name>.adoc
MANUAL = os.path.join(ROOT, "tameshi", "docs", "manual.adoc")
USAGE_SECTIONS = ("手引きを AI に読ませる", "アプリを作る流れ", "ほかの手引き", "一緒に使う物")


def usage_sections(text):
    """[intro, section, ...] of the manual that the page 使い方 shows: what is before its first heading, and the
    sections USAGE_SECTIONS with their subsections."""
    _, sections = read_adoc(text, "/tsukaikata/images/")
    chosen, on = [sections[0]], False
    for sec in sections[1:]:
        if sec["level"] == 2:
            on = sec["title"] in USAGE_SECTIONS
        if on:
            chosen.append(sec)
    return chosen


def flow_html():
    """The flow of the top page (site/index.html, between <!-- flow --> and <!-- /flow -->), without the note and the
    button under its steps: the page 使い方 shows the same flow, so it is kept in one place."""
    m = re.search(r"<!-- flow -->\s*(.*?)\s*<!-- /flow -->", read(os.path.join(HERE, "index.html")), re.S)
    return re.sub(r'\s*<div class="nagare-foot">.*?</div>\s*</div>\s*$', "\n    </div>", m[1], flags=re.S)


def usage_page(text):
    """The page 使い方: the short form of the user manual. Only its first paragraphs and the sections
    USAGE_SECTIONS (with their subsections) are on it; the whole manual is in the app, and a PDF."""
    sections = usage_sections(text)
    chosen = sections[1:]
    toc = '<ol class="toc">' + "".join(f'<li><a href="#{x["id"]}">{adoc_inline(x["title"])}</a></li>'
                                       for x in chosen if x["level"] == 2) + "</ol>"
    body = "\n".join(f'<h{x["level"]} id="{x["id"]}">{adoc_inline(x["title"])}</h{x["level"]}>\n{x["html"]}' for x in chosen)
    # on the web the figure of the flow is the flow of the top page (the PDF and the app keep the picture)
    body = re.sub(r'<figure class="fig"><img src="/tsukaikata/images/nagare\.svg"[^>]*></figure>', lambda m: flow_html(), body)
    return f"""<article class="tsukaikata">
<h1>使い方</h1>
{toc}
<div class="prose">
{sections[0]["html"]}
{body}
<p>くわしい使い方は、<a href="/app/">アプリの「使い方」</a>と、<a href="/tsukaikata/manual.pdf">利用者マニュアルの PDF</a> にあります。</p>
</div>
</article>"""


def load_shoukai(folder=SHOUKAI):
    """[(name, title, sections)] of shoukai/<name>.adoc, each read as the manual is read."""
    out = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if name.endswith(".adoc"):
                title, sections = read_adoc(read(os.path.join(folder, name)))
                out.append((name[:-5], title, sections))
    return out


def shoukai_pages(items):
    """{shoukai/<name>.html: page} of each introduction: its title, a list of its sections, and the text.
    A folder or a file that is not there gives no page."""
    pages = {}
    for name, title, sections in items:
        toc = '<ol class="toc">' + "".join(f'<li><a href="#{x["id"]}">{adoc_inline(x["title"])}</a></li>'
                                           for x in sections[1:] if x["level"] == 2) + "</ol>"
        body = "\n".join(f'<h{x["level"]} id="{x["id"]}">{adoc_inline(x["title"])}</h{x["level"]}>\n{x["html"]}' for x in sections[1:])
        pages[f"shoukai/{name}.html"] = page(title, f"""<article class="shoukai">
<p class="kicker">一緒に使う物</p>
<h1>{adoc_inline(title)}</h1>
{toc}
<div class="prose">
{sections[0]["html"]}
{body}
</div>
</article>""", f"{title}の紹介")
    return pages


# ---- reading the news -------------------------------------------------------------------


def read_news(text):
    """(title, date, [entries]) of one day's news adoc; an entry is a dict of
    its heading, its attributes (分野, 国・地域) and its paragraphs as HTML."""
    title, date, entries, attrs, para = "", "", [], {}, []

    def close():
        if para and entries:
            # A line ending in " +" ends a line in the page too (the sources are written so)
            groups, cur = [], []
            for x in para:
                if x.endswith(" +"):
                    groups.append(cur + [x[:-2]])
                    cur = []
                else:
                    cur.append(x)
            groups += [cur] if cur else []
            body = "<br>".join(inline(join_lines(g)) for g in groups)
            entries[-1]["paras"].append((para[0].startswith("出典"), body))
        para.clear()

    for line in text.splitlines():
        if line.startswith("== "):
            close()
            entries.append({"heading": line[3:].strip(), "attrs": {}, "paras": []})
        elif line.startswith("= "):
            title = line[2:].strip()
        elif m := re.match(r":([^:]+): ?(.*)", line):
            if entries:
                entries[-1]["attrs"][m[1]] = m[2].strip()
            else:
                attrs[m[1]] = m[2].strip()
        elif not line.strip():
            close()
        else:
            para.append(line.rstrip())
    close()
    return title, attrs.get("日付", ""), entries


def load_news(folder=os.path.join(ROOT, "news")):
    """[(date, title, entries)] of news/YYYY-MM-DD.adoc, newest first."""
    days = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder), reverse=True):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.adoc", name):
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    title, date, entries = read_news(f.read())
                days.append((date or name[:10], title, entries))
    return days


# ---- the pages ----------------------------------------------------------------------------


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def current_menu(path):
    """The address of the menu item of the page that is open (the path under public/), or ''."""
    rel = os.path.relpath(path, OUT)
    for prefix, href in (("tsukaikata.html", "/tsukaikata.html"), ("news/", "/news/"), ("kangaekata.html", "/kangaekata.html"),
                         ("kiji/", "/kiji/"), ("sagasu.html", "/sagasu.html")):
        if rel == prefix or (prefix.endswith("/") and rel.startswith(prefix)):
            return href
    return ""


def write(path, text):
    href = current_menu(path)
    if href:  # the menu shows which of its pages is open
        text = re.sub(rf'(<nav class="menu">.*?)<a href="{re.escape(href)}">', lambda m: m[1] + f'<a href="{href}" aria-current="page">',
                      text, count=1, flags=re.S)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


ICON = re.search(r'<link rel="icon"[^>]*>', read(os.path.join(HERE, "index.html")))[0]


def page(title, body, description=""):
    """One page with the site's header, footer and icon (the top page's)."""
    desc = (f'<meta name="description" content="{html.escape(description)}">\n'
            f'<meta property="og:description" content="{html.escape(description)}">\n') if description else ""
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} — aiai</title>
<meta property="og:title" content="{html.escape(title)} — aiai">
<meta property="og:locale" content="ja_JP">
{desc}{ICON}
<link rel="stylesheet" href="/top.css">
</head>
<body>
{HEADER}
<main class="doc">
{body}
</main>
{FOOTER}
{KAISEKI_TAGS}
</body>
</html>
"""


HEADER = """<header class="bar">
  <a class="logo" href="/"><span class="mark" aria-hidden="true"></span>aiai</a>
  <nav class="menu">
    <a href="/tsukaikata.html">使い方</a>
    <a href="/news/">ニュース</a>
    <a href="/kangaekata.html">考え方</a>
    <a href="/kiji/">記事</a>
    <a href="/sagasu.html">探す</a>
  </nav>
  <a class="open" href="/app/">アプリ</a>
</header>"""

FOOTER = """<footer>
  <p><strong>aiai</strong> AI 時代の AI 活用法</p>
  <p class="small"><a href="/tsukaikata.html">使い方</a> ・ <a href="/news/">ニュース</a> ・ <a href="/kangaekata.html">考え方</a> ・ <a href="/kiji/">記事</a> ・ <a href="/sagasu.html">探す</a> ・ <a href="/tsukaikata.html#tools">一緒に使う物</a> ・ <a href="/kaiseki/">読まれ方の記録</a></p>
  <p class="small">文書は CC BY 4.0、コードは AGPL-3.0-or-later です。見本の人、店、数字は、すべて架空です。このサイトは、国や役所が作った物ではありません。</p>
</footer>"""

# The record of how the pages are read (kaiseki/): no cookie and no ID, sent to
# this site's own server, with aiai's events (kaiseki-aiai.js) on top
KAISEKI_TAGS = """<script src="/kaiseki.js" data-to="/kaiseki" data-ask="no" defer></script>
<script src="/kaiseki-aiai.js" defer></script>"""

COPY_SCRIPT = """<script>
document.querySelectorAll("[data-copy]").forEach(function (b) {
  b.addEventListener("click", function () {
    var text = document.getElementById(b.dataset.copy).value;
    navigator.clipboard.writeText(text).then(function () {
      var was = b.textContent;
      b.textContent = "写しました。あなたの AI に貼ってください";
      setTimeout(function () { b.textContent = was; }, 2500);
    });
  });
});
</script>"""


HOW_TO_LOAD = ("「写す」で写して、ふだん使っている AI のチャットに貼ります。貼るほかに、AI に「スキル」として登録しておくこともできます。"
               "Claude は ZIP を、Gemini は SKILL.md か ZIP を上げます。ChatGPT は、スキルが使えるワークスペースで入れます。"
               "Microsoft 365 Copilot は、企業用の場合は、管理者に言ってもらってください。")


def load_skills():
    """{name: (step, title, description, raw text, body)} of every SKILL.md; the
    name is the folder's, as the ZIP at /skills/<name>.zip uses it."""
    step_of = {n: s for s, names in STEPS for n in names}
    skills = {}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in ("site", "public"))
        if "SKILL.md" in filenames:
            name = os.path.basename(dirpath)
            raw = read(os.path.join(dirpath, "SKILL.md"))
            front, body = split_front(raw)
            m = re.search(r"^# (.+)$", body, re.M)
            title = m[1].strip() if m else name
            body = body[:m.start()] + body[m.end():] if m else body
            # the lead is the first paragraph of the guide's README.md, written for people; the description of the
            # SKILL.md is for the AI that chooses a guide, so it is used only when there is no README
            readme = os.path.join(dirpath, "README.md")
            lead = first_paragraph(read(readme)) if os.path.exists(readme) else ""
            skills[name] = (step_of.get(name, ""), title, lead or front.get("description", ""), raw, body)
    order = [n for _, names in STEPS for n in names]
    return dict(sorted(skills.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else len(order)))


def sections(body):
    """[(heading, text)] of a guide's "## " sections; the heading is "" before the first."""
    parts = re.split(r"^## (.+)$", body, flags=re.M)
    out = [("", parts[0])]
    for i in range(1, len(parts), 2):
        out.append((parts[i].strip(), parts[i + 1]))
    return out


def first_sentence_block(step):
    """A step's own text: its first line and the wrapped lines under it, not the
    sub-bullets, code or commands that follow (those are for the AI)."""
    lines = step.splitlines()
    keep = [lines[0]]
    for line in lines[1:]:
        if not line.strip() or not line.startswith(" ") or re.match(r"\s+([-*]|\d+\.|```)", line):
            break
        keep.append(line)
    text = join_lines(keep)
    # the first sentence says what the step is; the rest is how, which is for the AI
    m = re.match(r"(.*?。)", text)
    return m[1] if m and len(text) > 60 else text


def for_people(body):
    """The parts of a guide a person wants to see: the steps, and the names of the
    items when there is an item list. The rest is written for the AI."""
    out = []
    for heading, text in sections(body):
        if heading.startswith("項目"):
            names = re.findall(r"^\d+\. \*\*(.+?)\*\*", text, re.M)
            if names:
                out.append(f"<h2>できる項目</h2><ol class=\"items\">" + "".join(f"<li>{inline(n)}</li>" for n in names) + "</ol>")
        elif "手順" in heading:
            steps = [m[1] for m in re.finditer(r"^\d+\. (.+?)(?=^\d+\. |\Z)", text, re.M | re.S)]
            if steps:
                out.append("<h2>あなたの AI は、こう進めます</h2><ol class=\"flow\">" + "".join(f"<li>{inline(first_sentence_block(s))}</li>" for s in steps) + "</ol>")
    return "\n".join(out)


def skill_page(name, step, title, description, raw, body):
    return page(title, f"""<article>
<p class="kicker">{html.escape(step) or "手引き"}</p>
<h1>{html.escape(title)}</h1>
<p class="lead">{inline(description)}</p>
<div class="actions">
  <button class="button primary" type="button" data-copy="skill-src">手引きを写す</button>
  <a class="button" href="/skills/{name}.zip" download>ZIP をダウンロード</a>
</div>
<p class="fine">写して、ふだん使っている AI のチャットに貼ります。AI に「スキル」として登録しておくこともできます(Claude は ZIP、Gemini は SKILL.md か ZIP)。</p>
<div class="prose people">
{for_people(body)}
</div>
<details class="full">
<summary>手引きの全文(あなたの AI が読む物)</summary>
<div class="prose">
{markdown(body)}
</div>
</details>
<textarea id="skill-src" hidden>{html.escape(raw)}</textarea>
{annai_html(f"/skills/{name}.html")}
</article>
{COPY_SCRIPT}""", description)


def entry_html(e, level=2):
    tags = "".join(f'<span class="chip">{html.escape(v)}</span>' for v in e["attrs"].values() if v)
    paras = "".join(f'<p class="{"src" if src else ""}">{body}</p>' for src, body in e["paras"])
    return f'<article class="news-entry"><h{level}>{inline(e["heading"])}</h{level}><p class="chips">{tags}</p>{paras}</article>'


FILTER_SCRIPT = """<script>
/* The reader picks the areas they want; the choice is kept in this browser. */
(function () {
  var bar = document.getElementById("areas");
  if (!bar) return;
  var key = "aiai.news.areas", picked = {};
  try { (JSON.parse(localStorage.getItem(key) || "[]")).forEach(function (a) { picked[a] = true; }); } catch (e) {}
  function apply() {
    var any = Object.keys(picked).some(function (a) { return picked[a]; });
    bar.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-pressed", picked[b.dataset.area] ? "true" : "false"); });
    document.querySelectorAll("[data-area]").forEach(function (el) {
      if (el.tagName === "BUTTON") return;
      el.hidden = any && !picked[el.dataset.area];
    });
    document.querySelectorAll(".news-day").forEach(function (d) {
      d.hidden = !Array.prototype.some.call(d.querySelectorAll("li"), function (li) { return !li.hidden; });
    });
    try { localStorage.setItem(key, JSON.stringify(Object.keys(picked).filter(function (a) { return picked[a]; }))); } catch (e) {}
  }
  bar.addEventListener("click", function (ev) {
    var b = ev.target.closest("button");
    if (!b) return;
    picked[b.dataset.area] = !picked[b.dataset.area];
    apply();
  });
  apply();
})();
</script>"""


def news_pages(days):
    """{path: html} of the news list and one page per day. The list can be
    narrowed to the areas the reader picks."""
    pages = {}
    rows, areas = [], []
    for date, title, entries in days:
        items = []
        for e in entries:
            area = e["attrs"].get("分野", "")
            if area and area not in areas:
                areas.append(area)
            items.append(f'<li data-area="{html.escape(area)}"><span class="chip">{html.escape(area)}</span>{inline(e["heading"])}</li>')
        rows.append(f'<section class="news-day"><h2><a href="/news/{date}.html">{html.escape(date)}</a></h2><ul>{"".join(items)}</ul></section>')
        body = "".join(entry_html(e) for e in entries)
        pages[f"news/{date}.html"] = page(title or f"aiai ニュース {date}", f"""<article>
<p class="kicker"><a href="/news/">aiai ニュース</a></p>
<h1>{html.escape(title or date)}</h1>
<div class="prose">{body}</div>
</article>""")
    buttons = "".join(f'<button type="button" data-area="{html.escape(a)}" aria-pressed="false">{html.escape(a)}</button>' for a in areas)
    picker = f'<p class="areas-head">読みたい分野だけにする</p><div class="areas" id="areas">{buttons}</div>' if len(areas) > 1 else ""
    pages["news/index.html"] = page("aiai ニュース", f"""<article>
<p class="kicker">ニュース</p>
<h1>aiai ニュース</h1>
<p class="lead">VLM(画像や動画を読む AI)と、VLM をこれから使える建物の機器と鳥獣対策のニュースです。</p>
<p class="own-news">自分の分野のニュースは、自分の AI に作らせることができます。<a href="/skills/news.html">ニュースを作る手引き</a></p>
{picker}
<div class="prose">{"".join(rows) or "<p>まだありません。</p>"}</div>
</article>
{FILTER_SCRIPT}""", "VLM と、VLM を使える建物の機器と鳥獣対策のニュース")
    return pages


def latest_news(days, n=NEWS_ON_TOP):
    """The top page's list of the newest entries."""
    items = []
    for date, _, entries in days:
        for e in entries:
            if len(items) < n:
                area = e["attrs"].get("分野", "")
                items.append(f'<li><a href="/news/{date}.html"><span class="date">{date}</span>'
                             f'<span class="chip">{html.escape(area)}</span>{inline(e["heading"])}</a></li>')
    return "<ul class=\"news-list\">" + "".join(items) + "</ul>" if items else "<p>まだありません。</p>"


def plain(text, limit=160):
    """Text of Markdown or HTML without its marks, cut to a short line, for the search index."""
    text = re.sub(r"\{\{fig:[\w-]+\}\}|\s*\{#[\w-]+\}", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>|[*`|#>]", "", text)
    text = join_lines([x.strip(" -") for x in text.splitlines() if x.strip()])
    return text[:limit]


def jidou(name, default):
    """One of the files of the automatic fixes, or default when there are none."""
    try:
        with open(os.path.join(JIDOU, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def load_kiji(folder=os.path.join(ROOT, "kiji")):
    """[(slug, title, subtitle, body, auto)] of the articles, kiji/*.md and those Gemini
    wrote by itself (auto), newest name first. An article starts with "# title" and a
    one-line subtitle."""
    found = []
    for where, auto in ((folder, False), (os.path.join(JIDOU, "kiji") if JIDOU else "", True)):
        if where and os.path.isdir(where):
            found += [(name, os.path.join(where, name), auto) for name in os.listdir(where) if name.endswith(".md")]
    out = []
    for name, path, auto in sorted(found, reverse=True):
        text = read(path)
        m = re.match(r"# (.+)\n+(.+)\n", text)
        out.append((name[:-3], m[1].strip(), m[2].strip(), text[m.end():], auto) if m
                   else (name[:-3], name[:-3], "", text, auto))
    return out


def annai_html(url):
    """The lines Gemini added at the end of this page, pointing to pages readers went on to."""
    items = [a for a in jidou("annai.json", []) if a.get("from") == url]
    if not items:
        return ""
    lis = "".join(f'<li><a href="{html.escape(a["to"])}">{html.escape(a["text"])}</a></li>' for a in items)
    return f'<aside class="annai"><p class="annai-head">次に読む</p><ul>{lis}</ul></aside>'


AUTO_NOTE = ('<p class="fine">この記事は、読まれ方の記録から、Gemini が自動で書きました'
             '(<a href="/kaiseki/kiroku.html">直し方の記録</a>)。</p>')


def kiji_pages(articles):
    """{path: html} of one page per article and their list at /kiji/."""
    pages, rows = {}, []
    for slug, title, sub, body, auto in articles:
        pages[f"kiji/{slug}.html"] = page(title, f"""<article>
<p class="kicker"><a href="/kiji/">記事</a></p>
<h1>{html.escape(title)}</h1>
<p class="lead">{inline(sub)}</p>
{AUTO_NOTE if auto else ""}
<div class="prose">{markdown(body)}</div>
{annai_html(f"/kiji/{slug}.html")}
</article>""", sub)
        rows.append(f'<li><a href="/kiji/{slug}.html">{html.escape(title)}</a><br><span class="fine">{inline(sub)}</span></li>')
    if rows:
        pages["kiji/index.html"] = page("記事", f"""<article>
<h1>記事</h1>
<div class="prose"><ul>{"".join(rows)}</ul></div>
</article>""")
    return pages


def adoc_entries(url, title, sections):
    """[{u, t, h, x}] of a page made from AsciiDoc: its first paragraphs (no heading), then each section,
    whose address is <page>#<id of the section>."""
    def text(html_):  # the end of a cell, an item or a paragraph is a space, so words of two cells do not run together
        return plain(re.sub(r"</(td|th|li|p|blockquote)>", " ", html_))

    return [{"u": url, "t": title, "h": "", "x": text(sections[0]["html"])}] + [
        {"u": f"{url}#{x['id']}", "t": title, "h": x["title"], "x": text(x["html"])} for x in sections[1:]]


def search_index(skills, kangaekata, days, articles=(), pages=()):
    """[{u, t, h, x}] (address, title, heading, text) of the pages and their
    sections, which sagasu.js searches and the server's AI picks from. pages is
    [(address, title, sections)] of the pages made from AsciiDoc: 使い方 and the introductions."""
    out = []
    for name, (_, title, description, _, body) in skills.items():
        url = f"/skills/{name}.html"
        out.append({"u": url, "t": title, "h": "", "x": plain(description)})
        out += [{"u": url, "t": title, "h": h, "x": plain(text)} for h, text in sections(body) if h]
    for m in re.finditer(r"^## (.+?) \{#([\w-]+)\}\n(.*?)(?=^## |\Z)", kangaekata, re.M | re.S):
        out.append({"u": f"/kangaekata.html#{m[2]}", "t": "考え方", "h": m[1], "x": plain(m[3])})
    for url, title, parts in pages:
        out += adoc_entries(url, title, parts)
    for date, _, entries in days:
        for e in entries:
            text = " ".join(body for src, body in e["paras"] if not src)
            out.append({"u": f"/news/{date}.html", "t": f"ニュース {date}", "h": e["heading"], "x": plain(text)})
    # words Gemini tied to a page (tools/kaiseki_jidou.py), so the search finds it by them
    words = {}
    for y in jidou("yougo.json", []):
        words.setdefault(y.get("page", ""), []).append(y.get("word", ""))
    for slug, title, sub, body, _ in articles:
        url = f"/kiji/{slug}.html"
        out.append({"u": url, "t": title, "h": "", "x": plain(sub)})
        out += [{"u": url, "t": title, "h": h, "x": plain(text)} for h, text in sections(body) if h]
    for e in out:
        page_url = e["u"].split("#")[0]
        if page_url in words:
            e["k"] = " ".join(words.pop(page_url))
    return out


SEARCH_PAGE = """<article>
<h1>サイトの中を探す</h1>
<form id="sagasu" class="sagasu" role="search">
  <input type="search" name="q" maxlength="100" placeholder="例: 転職、鳥獣害、サーバーの管理" aria-label="探す言葉">
  <button class="button primary" type="submit">探す</button>
</form>
<div id="sagasu-out" class="prose" aria-live="polite"></div>
</article>
<script src="/sagasu.js" defer></script>"""

# /tameshi.html was the page of the 作る tab before the tab was in the app. The address after the # does not
# reach the server, so this page reads it and sends the person to the same place in the app.
TAMESHI_MOVED = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>作る — aiai</title>
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="3; url=/app/tameshi">
<script>
  var place = location.hash.slice(1);
  location.replace("/app/tameshi" + (/^[a-z]+$/.test(place) ? "/" + place : ""));
</script>
</head>
<body>
<p>アプリの「作る」に移ります。移らないときは、<a href="/app/tameshi">こちら</a>を開いてください。</p>
</body>
</html>
"""


NOT_FOUND = """<article>
<div data-notfound hidden></div>
<h1>このページは見つかりません</h1>
<p><a href="/sagasu.html">サイトの中を探す</a>か、<a href="/">トップページ</a>から開いてください。</p>
</article>"""

KAISEKI_PAGE = """<article>
<h1>読まれ方の記録</h1>
<div class="prose">
<p>このサイトは、読む人がどこで読み、何を探しているかを記録します。その記録を AI に読ませ、ページを直し、足りないページを作ります。</p>
<h2>記録する物</h2>
<ul>
<li>見たページと題、来た元のサイト、言語、時間帯、画面の大きさ、ブラウザー</li>
<li>ページを見ていた時間と、どこまで下へ見たか</li>
<li>読んだ見出し、開いた全文、押したリンク、写したりダウンロードしたりした手引き</li>
<li>このサイトの中で探した言葉と、見つからなかったページ</li>
</ul>
<h2>送り先</h2>
<p>このサイトのサーバー(<code>https://aiai.aiseed.dev/kaiseki/v1/</code>)です。Cookie に番号は置かず、IP アドレスは記録しません。探した言葉は、合うページを選ぶために、Google Cloud の Gemini 3.8 Flash にも渡します。</p>
<p>仕組みのコードは、aiai のリポジトリの <code>kaiseki/</code> にあります(AGPL-3.0-or-later)。記録を読んで何を直したかは、<a href="/kaiseki/kiroku.html">直し方の記録</a>にあります。</p>
</div>
</article>"""


def kiroku_page(path=os.path.join(ROOT, "kaiseki", "kiroku.adoc")):
    """The log of the fixes made from the record, newest first: those the owner's AI
    made (kaiseki/kiroku.adoc, which kaiseki/naosu.py adds to) and those Gemini made
    by itself (kiroku.adoc in AIAI_JIDOU): page, what was seen, what was done, and
    whether it worked."""
    entries = []
    for p in (path, os.path.join(JIDOU, "kiroku.adoc") if JIDOU else ""):
        if not p or not os.path.exists(p):
            continue
        for part in re.split(r"^== ", read(p), flags=re.M)[1:]:
            lines = part.splitlines()
            fields, cur = {}, None
            for line in lines[1:]:
                if m := re.match(r":(ページ|種類): ?(.*)", line):
                    fields[m[1]] = m[2].strip()
                elif m := re.match(r"(見たこと|直したこと|確かめたこと): ?(.*)", line):
                    cur = m[1]
                    fields[cur] = m[2].strip()
                elif cur and line.strip():
                    fields[cur] = join_lines([fields[cur], line.strip()])
            entries.append((lines[0].strip(), fields))
    items = []
    for n, (head, f) in sorted(enumerate(entries), key=lambda x: (x[1][0][:10], x[0]), reverse=True):
        where = f.get("ページ", "")
        link = f' <a href="{html.escape(where)}">{html.escape(where)}</a>' if where.startswith("/") else ""
        who = "Gemini が自動で" if f.get("種類") == "自動" else "AI が直し、人が取り込んだ"
        rows = "".join(f"<dt>{k}</dt><dd>{inline(f[k])}</dd>" for k in ("見たこと", "直したこと", "確かめたこと") if f.get(k))
        items.append(f'<section class="kiroku-entry"><h2>{inline(head)}</h2><p class="fine">{who}{link}</p><dl>{rows}</dl></section>')
    return f"""<article>
<p class="kicker"><a href="/kaiseki/">読まれ方の記録</a></p>
<h1>直し方の記録</h1>
<p class="lead">読まれ方の記録を AI に読ませて、ページをどう直したか、直した後にどうなったかです。</p>
<div class="prose">{"".join(items) or "<p>まだありません。</p>"}</div>
</article>"""


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    days = load_news()
    top = read(os.path.join(HERE, "index.html"))
    if days:
        top = re.sub(r"<!-- news -->.*?<!-- /news -->", lambda m: f"<!-- news -->{latest_news(days)}<!-- /news -->", top, flags=re.S)
    else:  # no news yet: no empty section on the top page
        top = re.sub(r"\s*<!-- news-section -->.*?<!-- /news-section -->", "", top, flags=re.S)
    top = re.sub(r"<footer>.*?</footer>", lambda m: FOOTER, top, count=1, flags=re.S)  # one footer for all the pages
    write(os.path.join(OUT, "index.html"), top.replace("</body>", KAISEKI_TAGS + "\n</body>"))
    shutil.copyfile(os.path.join(HERE, "top.css"), os.path.join(OUT, "top.css"))
    for src, name in ((os.path.join(ROOT, "kaiseki", "kaiseki.js"), "kaiseki.js"),
                      (os.path.join(HERE, "kaiseki-aiai.js"), "kaiseki-aiai.js"), (os.path.join(HERE, "sagasu.js"), "sagasu.js")):
        shutil.copyfile(src, os.path.join(OUT, name))
    skills = load_skills()
    for name, s in skills.items():
        write(os.path.join(OUT, "skills", f"{name}.html"), skill_page(name, *s))
    kangaekata = read(os.path.join(HERE, "app", "assets", "kangaekata.md"))
    # Every section gets an id, so the list at the top can jump to it (a long page on a phone)
    heads = []
    def with_id(m):
        n = len(heads) + 1
        anchor = re.search(r"\s*\{#([\w-]+)\}$", m[1])
        name = anchor[1] if anchor else f"k{n}"
        text_ = m[1][:anchor.start()] if anchor else m[1]
        heads.append((name, text_.strip()))
        return f"## {text_.strip()} {{#{name}}}"
    kangaekata = re.sub(r"^## (.+)$", with_id, kangaekata, flags=re.M)
    toc = "<ol class=\"toc\">" + "".join(f'<li><a href="#{name}">{inline(text_)}</a></li>' for name, text_ in heads) + "</ol>"
    write(os.path.join(OUT, "kangaekata.html"), page("考え方", f"""<article>
<p class="kicker">考え方</p>
<h1>aiai の考え方</h1>
{toc}
<div class="prose">{markdown(kangaekata)}</div>
{annai_html("/kangaekata.html")}
</article>""", "AI 時代に、AI を使い込んだ経験をどう活かすか"))
    for path, text in news_pages(days).items():
        write(os.path.join(OUT, path), text)
    articles = load_kiji()
    for path, text in kiji_pages(articles).items():
        write(os.path.join(OUT, path), text)
    write(os.path.join(OUT, "sagasu.html"), page("探す", SEARCH_PAGE, "aiai のサイトの中を探す"))
    write(os.path.join(OUT, "404.html"), page("見つかりません", NOT_FOUND))
    write(os.path.join(OUT, "tameshi.html"), TAMESHI_MOVED)
    # the pages the top page's table of contents leads to (hand-written, as the top page is)
    write(os.path.join(OUT, "eizou.html"), page("写真や映像を読む AI", read(os.path.join(HERE, "eizou.html")),
                                                 "畑のカメラの映像を AI が読み、記録する例"))
    # the usage page is the short form of the user manual; its PDF is copied beside it (the flow is the top page's)
    write(os.path.join(OUT, "tsukaikata.html"), page("使い方", usage_page(read(MANUAL)), "手引きを AI に読ませる方法と、アプリを作る流れ"))
    docs = os.path.dirname(MANUAL)
    shoukai = load_shoukai()
    for path, text in shoukai_pages(shoukai).items():
        write(os.path.join(OUT, path), text)
    if os.path.exists(os.path.join(docs, "manual.pdf")):
        os.makedirs(os.path.join(OUT, "tsukaikata"), exist_ok=True)
        shutil.copyfile(os.path.join(docs, "manual.pdf"), os.path.join(OUT, "tsukaikata", "manual.pdf"))
    write(os.path.join(OUT, "kaiseki", "index.html"), page("読まれ方の記録", KAISEKI_PAGE, "aiai のサイトが記録する物と送り先"))
    write(os.path.join(OUT, "kaiseki", "kiroku.html"), page("直し方の記録", kiroku_page(), "読まれ方の記録から、aiai のサイトをどう直したか"))
    write(os.path.join(OUT, "sagasu.json"), json.dumps(search_index(
        skills, kangaekata, days, articles,
        [("/tsukaikata.html", "使い方", usage_sections(read(MANUAL)))] + [(f"/shoukai/{n}.html", t, s) for n, t, s in shoukai]), ensure_ascii=False))
    print(f"{OUT} に、スキル {len(skills)}、ニュース {len(days)} 日分のページを作りました")


if __name__ == "__main__":
    main()
