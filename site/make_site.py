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
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "public")

# The path a person takes, and the skills on each step; others come last
STEPS = [("知る", ["rireki"]), ("考える", ["tenshoku", "gakusei"]), ("作る", ["genba"]),
         ("始める", ["website", "moushikomi", "keikaku"])]
NEWS_ON_TOP = 3


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


def markdown(text):
    """HTML of Markdown as aiai writes it."""
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(lines[i + 1:j])) + "</code></pre>")
            i = j + 1
        elif m := re.match(r"(#{1,6}) (.*)", line):
            n = len(m[1])
            out.append(f"<h{n}>{inline(m[2].strip())}</h{n}>")
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
</body>
</html>
"""


HEADER = """<header class="bar">
  <a class="logo" href="/"><span class="mark" aria-hidden="true"></span>aiai</a>
  <nav class="menu">
    <a href="/#skills">スキル</a>
    <a href="/#how">使い方</a>
    <a href="/news/">ニュース</a>
    <a href="/kangaekata.html">考え方</a>
  </nav>
  <a class="open" href="/app/">アプリ</a>
</header>"""

FOOTER = """<footer>
  <p><strong>aiai</strong> AI 時代の学び方</p>
  <p class="small">文書は CC BY 4.0、コードは AGPL-3.0-or-later です。見本の人、店、数字は、すべて架空です。このサイトは、国や役所が作った物ではありません。</p>
</footer>"""

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

HOW_TO_LOAD = ("「写す」で写して、ふだん使っている AI のチャットに貼ります。Claude は ZIP を、Gemini は SKILL.md か ZIP を、"
               "スキルとして上げられます。ChatGPT は、スキルが使えるワークスペースで入れます。"
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


def skill_page(name, step, title, description, raw, body):
    return page(title, f"""<article>
<p class="kicker">{html.escape(step) or "スキル"}</p>
<h1>{html.escape(title)}</h1>
<p class="lead">{inline(description)}</p>
<div class="actions">
  <button class="button primary" type="button" data-copy="skill-src">スキルを写す</button>
  <a class="button" href="/skills/{name}.zip" download>ZIP をダウンロード</a>
</div>
<p class="fine">{HOW_TO_LOAD}</p>
<div class="prose">
{markdown(body)}
</div>
<textarea id="skill-src" hidden>{html.escape(raw)}</textarea>
</article>
{COPY_SCRIPT}""", description)


def entry_html(e, level=2):
    tags = "".join(f'<span class="chip">{html.escape(v)}</span>' for v in e["attrs"].values() if v)
    paras = "".join(f'<p class="{"src" if src else ""}">{body}</p>' for src, body in e["paras"])
    return f'<article class="news-entry"><h{level}>{inline(e["heading"])}</h{level}><p class="chips">{tags}</p>{paras}</article>'


def news_pages(days):
    """{path: html} of the news list and one page per day."""
    pages = {}
    rows = []
    for date, title, entries in days:
        items = "".join(f"<li>{inline(e['heading'])}</li>" for e in entries)
        rows.append(f'<section class="news-day"><h2><a href="/news/{date}.html">{html.escape(date)}</a></h2><ul>{items}</ul></section>')
        body = "".join(entry_html(e) for e in entries)
        pages[f"news/{date}.html"] = page(title or f"aiai ニュース {date}", f"""<article>
<p class="kicker"><a href="/news/">aiai ニュース</a></p>
<h1>{html.escape(title or date)}</h1>
<div class="prose">{body}</div>
</article>""")
    pages["news/index.html"] = page("aiai ニュース", f"""<article>
<p class="kicker">ニュース</p>
<h1>aiai ニュース</h1>
<p class="lead">VLM(画像や動画を読む AI)、スマートドア、スマートロック、鳥獣対策のニュースです。AI が下書きを作り、
人が元の記事を読んで確かめてから載せます。出典と確かめた日を付けています。</p>
<div class="prose">{"".join(rows) or "<p>まだありません。</p>"}</div>
</article>""", "VLM、スマートドア、スマートロック、鳥獣対策のニュース")
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


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    days = load_news()
    top = read(os.path.join(HERE, "index.html"))
    if days:
        top = re.sub(r"<!-- news -->.*?<!-- /news -->", lambda m: f"<!-- news -->{latest_news(days)}<!-- /news -->", top, flags=re.S)
    else:  # no news yet: no empty section on the top page
        top = re.sub(r"\s*<!-- news-section -->.*?<!-- /news-section -->", "", top, flags=re.S)
    write(os.path.join(OUT, "index.html"), top)
    shutil.copyfile(os.path.join(HERE, "top.css"), os.path.join(OUT, "top.css"))
    skills = load_skills()
    for name, s in skills.items():
        write(os.path.join(OUT, "skills", f"{name}.html"), skill_page(name, *s))
    kangaekata = read(os.path.join(HERE, "app", "assets", "kangaekata.md"))
    write(os.path.join(OUT, "kangaekata.html"), page("考え方", f"""<article>
<p class="kicker">考え方</p>
<h1>aiai の考え方</h1>
<div class="prose">{markdown(kangaekata)}</div>
</article>""", "AI 時代に、AI を使い込んだ経験をどう活かすか"))
    for path, text in news_pages(days).items():
        write(os.path.join(OUT, path), text)
    print(f"{OUT} に、スキル {len(skills)}、ニュース {len(days)} 日分のページを作りました")


if __name__ == "__main__":
    main()
