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


def write(path, text):
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
    <a href="/katsuyou.html">手引き</a>
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
  <p class="small"><a href="/sagasu.html">探す</a> ・ <a href="/kaiseki/">読まれ方の記録</a> ・ <a href="https://github.com/aiseed-dev/aiai-tools">aiai tools</a></p>
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
            skills[name] = (step_of.get(name, ""), title, front.get("description", ""), raw, body)
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
<p class="kicker">記事</p>
<h1>記事</h1>
<div class="prose"><ul>{"".join(rows)}</ul></div>
</article>""")
    return pages


def search_index(skills, kangaekata, days, articles=()):
    """[{u, t, h, x}] (address, title, heading, text) of the pages and their
    sections, which sagasu.js searches and the server's AI picks from."""
    out = []
    for name, (_, title, description, _, body) in skills.items():
        url = f"/skills/{name}.html"
        out.append({"u": url, "t": title, "h": "", "x": plain(description)})
        out += [{"u": url, "t": title, "h": h, "x": plain(text)} for h, text in sections(body) if h]
    for m in re.finditer(r"^## (.+?) \{#([\w-]+)\}\n(.*?)(?=^## |\Z)", kangaekata, re.M | re.S):
        out.append({"u": f"/kangaekata.html#{m[2]}", "t": "考え方", "h": m[1], "x": plain(m[3])})
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
<p class="kicker">探す</p>
<h1>サイトの中を探す</h1>
<form id="sagasu" class="sagasu" role="search">
  <input type="search" name="q" maxlength="100" placeholder="例: 転職、鳥獣害、サーバーの管理" aria-label="探す言葉">
  <button class="button primary" type="submit">探す</button>
</form>
<div id="sagasu-out" class="prose" aria-live="polite"></div>
</article>
<script src="/sagasu.js" defer></script>"""

def tameshi_page():
    """/tameshi.html: try aiai with Gemini after signing in (tameshi/server.py, at /tameshi)."""
    tastes = html.escape(read(os.path.join(ROOT, "news", "好み.adoc")))
    return f"""<article>
<p class="kicker">試す</p>
<h1>aiai を、Gemini で試す</h1>
<p class="lead">サインインすると、手引きを読ませた Gemini と対話し、今あるアプリを探させ、その不満からどう良くするかを一緒に考え、資料から設計書と利用者マニュアルを作らせ、自分の好みで今日のニュースを作らせることができます。Gemini は Google Cloud で動きます。書いたことは Gemini に送り、このサイトには記録しません。1 日に使える回数があります。</p>
<section id="tameshi-in" class="tameshi-box">
  <h2>サインイン</h2>
  <div class="actions">
    <a class="button primary" id="tameshi-google" hidden>Google でサインイン</a>
    <a class="button" id="tameshi-apple" hidden>Apple でサインイン</a>
  </div>
  <form id="tameshi-test" class="tameshi-test" hidden>
    <p class="fine">審査用のテストアカウント</p>
    <input id="tameshi-id" autocomplete="username" placeholder="ID" aria-label="ID">
    <input id="tameshi-password" type="password" autocomplete="current-password" placeholder="パスワード" aria-label="パスワード">
    <button class="button" type="submit">入る</button>
  </form>
  <p class="fine" id="tameshi-in-note" aria-live="polite"></p>
</section>
<div id="tameshi-use" hidden>
  <p class="fine"><span id="tameshi-who"></span> ・ <span id="tameshi-left"></span> ・ <button type="button" class="linkish" id="tameshi-out">サインアウト</button></p>
  <section class="tameshi-box">
    <h2>手引きを読ませた Gemini と対話する</h2>
    <label class="tameshi-pick">手引き <select id="tameshi-guide"></select></label>
    <div id="tameshi-log" class="tameshi-log" aria-live="polite"></div>
    <form id="tameshi-chat" class="sagasu">
      <textarea id="tameshi-say" rows="2" maxlength="4000" placeholder="例: 始めたいです" aria-label="書くこと"></textarea>
      <button class="button primary" type="submit">送る</button>
    </form>
    <p class="fine" id="tameshi-chat-note" aria-live="polite"></p>
  </section>
  <section class="tameshi-box">
    <h2>今日のニュースを作らせる</h2>
    <p class="fine">分野、地域、件数、扱わない物を書きます。下は aiai のニュースの好みです。書き替えて使えます。</p>
    <form id="tameshi-news">
      <textarea id="tameshi-tastes" rows="10" maxlength="4000" aria-label="好み">{tastes}</textarea>
      <button class="button primary" type="submit">作る</button>
    </form>
    <p class="fine" id="tameshi-news-note" aria-live="polite"></p>
    <div id="tameshi-news-out" hidden>
      <pre id="tameshi-news-text"></pre>
      <button type="button" class="button" id="tameshi-copy">写す</button>
    </div>
  </section>
  <div id="tameshi-kaihatsu">
  <section class="tameshi-box" id="chousa">
    <h2>今あるアプリを探す</h2>
    <p class="fine">AI に何度も頼んでいることを書くと、Gemini が、似たアプリを Google 検索で 3 つまで選び、公式サイト、ストアの説明、利用規約、料金のページを読んで、機能、料金、問題点を、出典を付けてまとめます。SKILL.md や参考の資料(.md、.adoc、.txt か、それを入れた ZIP)も足せます。数分かかります。作った物は 7 日で消します。</p>
    <form class="tameshi-form" data-kind="chousa">
      <label class="tameshi-pick">何度も頼んでいること <textarea name="note" rows="3" maxlength="2000" placeholder="例: 毎週、売上の表を渡して、品目ごとの集計と先週との比べを頼んでいる"></textarea></label>
      <label class="tameshi-pick">資料(なくてもかまいません) <input type="file" name="files" multiple accept=".md,.adoc,.txt,.zip"></label>
      <div class="actions">
        <button class="button primary" type="submit">探す</button>
      </div>
      <p class="fine">架空の見本(パン屋の取り置きのアプリ)でも試せます。
        <button class="linkish" type="submit" data-mihon="1">見本で探す</button> ・
        <a href="https://github.com/aiseed-dev/aiai/tree/main/hackathon/mihon">見本を見る</a></p>
    </form>
    <p class="fine tameshi-job-note" aria-live="polite"></p>
    <div class="tameshi-jobs"></div>
  </section>
  <section class="tameshi-box" id="kaizen">
    <h2>どう良くするかを考える</h2>
    <p class="fine">今あるアプリを使ってみて、不満な所を具体的に書きます。どのアプリの、どの場面で、何が困るのかが分からないと、Gemini も一緒に考えられません。Gemini は、手引き「度々聞いていることを、アプリにする」の手順 3 に沿って、聞きながら、どうなればよいかを一緒に考えます。上の「今あるアプリを探す」の結果を読ませることもできます。対話は記録しません。</p>
    <form id="kaizen-start" class="kaizen-start">
      <label class="tameshi-pick">読ませる結果 <select id="kaizen-job"><option value="">読ませない</option></select></label>
      <label class="tameshi-pick">使ったアプリ <input id="kaizen-app" maxlength="200" placeholder="例: 集計のアプリ"></label>
      <label class="tameshi-pick">困った場面と、困ったこと <textarea id="kaizen-fuman" rows="3" maxlength="2000" required placeholder="例: 毎週、売上の表を渡して集計させている。前の週の表が残らないので、先週との比べを毎回自分で作っている"></textarea></label>
      <label class="tameshi-pick">どうなればよいか(分かれば) <textarea id="kaizen-hoshii" rows="2" maxlength="1000" placeholder="例: 先週の表を残し、比べた表も一緒に出してほしい"></textarea></label>
      <button class="button primary" type="submit">考える</button>
    </form>
    <div id="kaizen-talk" hidden>
      <div id="kaizen-log" class="tameshi-log" aria-live="polite"></div>
      <form id="kaizen-chat" class="sagasu">
        <textarea id="kaizen-say" rows="2" maxlength="4000" aria-label="書くこと"></textarea>
        <button class="button primary" type="submit">送る</button>
      </form>
      <button type="button" class="linkish" id="kaizen-again">初めから</button>
    </div>
    <p class="fine" id="kaizen-note" aria-live="polite"></p>
  </section>
  <section class="tameshi-box" id="kadai">
    <h2>今あるアプリの課題を集める</h2>
    <p class="fine">「今あるアプリを探す」の結果か、渡した資料に出てくるアプリについて、使う人にとっての問題点と、運営の作りの問題点を、Gemini が Google 検索で公式サイトや利用規約などを読んで、出典を付けてまとめます。アプリの名前が出てこなければ、似たことをしているアプリを探してから調べます。できる物は、手引きの手順 5 の資料(references/&lt;名前&gt;-analysis.adoc)です。数分かかります。作った物は 7 日で消します。</p>
    <form class="tameshi-form" data-kind="kadai">
      <label class="tameshi-pick">読ませる結果 <select name="research"><option value="">読ませない</option></select></label>
      <label class="tameshi-pick">作るアプリの名前(英数字とハイフン。資料のファイルの名前に使います) <input name="name" autocomplete="off" autocapitalize="none" placeholder="例: toriooki"></label>
      <label class="tameshi-pick">3 で分かった不満(あれば) <textarea name="note" rows="3" maxlength="2000" placeholder="例: 前の週の表が残らないので、先週との比べを毎回自分で作っている"></textarea></label>
      <label class="tameshi-pick">資料(なくてもかまいません) <input type="file" name="files" multiple accept=".md,.adoc,.txt,.zip"></label>
      <div class="actions">
        <button class="button primary" type="submit">集める</button>
      </div>
      <p class="fine">架空の見本(パン屋の取り置きのアプリ)でも試せます。
        <button class="linkish" type="submit" data-mihon="1">見本で集める</button> ・
        <a href="https://github.com/aiseed-dev/aiai/tree/main/hackathon/mihon">見本を見る</a></p>
    </form>
    <p class="fine tameshi-job-note" aria-live="polite"></p>
    <div class="tameshi-jobs"></div>
  </section>
  <section class="tameshi-box" id="sekkei">
    <h2>設計書と利用者マニュアルを作る</h2>
    <p class="fine">作るアプリの SKILL.md と参考の資料(.md、.adoc、.txt か、それを入れた ZIP)を渡します。SKILL.md は、手引き「度々聞いていることを、アプリにする」の「アプリの SKILL.md の形」に沿って、自分の AI と書きます。上の「今あるアプリの課題を集める」の資料も読ませられます。Gemini 4 Argon が設計書と利用者マニュアルを書き、画面の絵を Nano Banana が描き、最後に 2 つを照らし合わせます。数分かかります。作った物は 7 日で消します。</p>
    <form class="tameshi-form" data-kind="sekkei">
      <label class="tameshi-pick">読ませる課題の資料 <select name="kadai"><option value="">読ませない</option></select></label>
      <label class="tameshi-pick">資料 <input type="file" name="files" multiple accept=".md,.adoc,.txt,.zip"></label>
      <textarea name="note" rows="2" maxlength="2000" placeholder="足したいこと(なくてもかまいません)" aria-label="足したいこと"></textarea>
      <div class="actions">
        <button class="button primary" type="submit">設計書とマニュアルを作る</button>
      </div>
      <p class="fine">資料が手元に無ければ、架空の見本(パン屋の取り置きのアプリ)で試せます。
        <button class="linkish" type="submit" data-mihon="1">見本で設計書とマニュアルを作る</button> ・
        <a href="https://github.com/aiseed-dev/aiai/tree/main/hackathon/mihon">見本を見る</a></p>
    </form>
    <p class="fine tameshi-job-note" aria-live="polite"></p>
    <div class="tameshi-jobs"></div>
  </section>
  </div>
</div>
</article>
<script src="/tameshi.js" defer></script>"""


NOT_FOUND = """<article>
<div data-notfound hidden></div>
<h1>このページは見つかりません</h1>
<p><a href="/sagasu.html">サイトの中を探す</a>か、<a href="/">トップページ</a>から開いてください。</p>
</article>"""

KAISEKI_PAGE = """<article>
<p class="kicker">読まれ方の記録</p>
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
    write(os.path.join(OUT, "index.html"), top.replace("</body>", KAISEKI_TAGS + "\n</body>"))
    shutil.copyfile(os.path.join(HERE, "top.css"), os.path.join(OUT, "top.css"))
    for src, name in ((os.path.join(ROOT, "kaiseki", "kaiseki.js"), "kaiseki.js"),
                      (os.path.join(HERE, "kaiseki-aiai.js"), "kaiseki-aiai.js"), (os.path.join(HERE, "sagasu.js"), "sagasu.js"),
                      (os.path.join(HERE, "tameshi.js"), "tameshi.js")):
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
    write(os.path.join(OUT, "tameshi.html"), page("Gemini で試す", tameshi_page(), "手引きを読ませた Gemini と対話し、好みでニュースを作らせる"))
    # the pages the top page's table of contents leads to (hand-written, as the top page is)
    for name, title, desc in (("katsuyou", "AI 時代の AI 活用法", "AI の使い方と、それぞれの手引き"),
                              ("tsukaikata", "使い方", "手引きをあなたの AI に読ませる方法と、対話の例"),
                              ("eizou", "写真や映像を読む AI", "畑のカメラの映像を AI が読み、記録する例")):
        write(os.path.join(OUT, f"{name}.html"), page(title, read(os.path.join(HERE, f"{name}.html")), desc))
    write(os.path.join(OUT, "kaiseki", "index.html"), page("読まれ方の記録", KAISEKI_PAGE, "aiai のサイトが記録する物と送り先"))
    write(os.path.join(OUT, "kaiseki", "kiroku.html"), page("直し方の記録", kiroku_page(), "読まれ方の記録から、aiai のサイトをどう直したか"))
    write(os.path.join(OUT, "sagasu.json"), json.dumps(search_index(skills, kangaekata, days, articles), ensure_ascii=False))
    print(f"{OUT} に、スキル {len(skills)}、ニュース {len(days)} 日分のページを作りました")


if __name__ == "__main__":
    main()
