"""Builds a small website from adoc pages, with Python's standard library only.

    python build.py サイトのフォルダー [--data Webサイト.sheet.adoc] [--out 出力先]

The folder holds:

    Webサイト.sheet.adoc  the public facts, made by tools/todoke.py from 事業.sheet.adoc
                         (or --data); {屋号} in a page becomes its value
    pages/*.adoc         one page each; index.adoc is the top page
    news/*.adoc          news; the newest come first, :日付: sets the date
    images/              pictures used by image::
    style.css            the look

It reads a plain part of AsciiDoc: the title and attributes, == and ===
headings, paragraphs (a line ending in " +" breaks), * and . lists,
|=== tables, image::, *bold*, link:…[…], https://…[…], mailto:…[…],
and // comments. `news::[5]` lists the newest five news items.
`contact::[]` puts the contact form; functions/api/contact.js receives it
on Cloudflare Pages and keeps each message in R2. A page with
`:turnstile: サイトキー` also shows Cloudflare Turnstile on the form.
"""
import datetime
import html
import os
import re
import shutil
import sys

# ---- reading --------------------------------------------------------------


def read_doc(path):
    """(title, attrs, body lines) of an adoc file."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    title, attrs, i = None, {}, 0
    while i < len(lines) and lines[i].strip():
        s = lines[i].strip()
        if s.startswith("= "):
            title = s[2:].strip()
        elif m := re.match(r"^:([^:]+):\s*(.*)$", s):
            attrs[m.group(1)] = m.group(2)
        elif not s.startswith("//"):
            break
        i += 1
    return title, attrs, lines[i:]


def data_of(path):
    """{name: value} from the two-column tables of a .sheet.adoc."""
    out = {}
    if not os.path.exists(path):
        return out
    _, attrs, body = read_doc(path)
    out.update(attrs)
    in_table, last = False, None
    for line in body:
        s = line.rstrip()
        if s == "|===":
            in_table, last = not in_table, None
        elif in_table and s.startswith("|"):
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", s)[1:]]
            if len(cells) >= 2:
                out[cells[0]] = re.sub(r"\s*\+$", "", cells[1])
                last = cells[0]
        elif in_table and s.strip() and last:
            out[last] = out[last] + "\n" + re.sub(r"\s*\+$", "", s.strip())
    return out


# ---- writing HTML -----------------------------------------------------------


def inline(text):
    """Escape, then turn the inline marks into HTML."""
    t = html.escape(text, quote=False)

    def link(m):
        target, label = m.group(1), m.group(2) or m.group(1)
        return f'<a href="{html.escape(target)}">{label}</a>'

    t = re.sub(r"link:([^\s\[]+)\[([^\]]*)\]", link, t)
    t = re.sub(r"(?<![\"=])((?:https?://|mailto:)[^\s\[<]+)\[([^\]]*)\]", link, t)
    t = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<strong>\1</strong>", t)
    return t


def fill(text, data, missing):
    def one(m):
        name = m.group(1)
        if name in data:
            return data[name]
        missing.add(name)
        return m.group(0)

    return re.sub(r"\{([^{}\s]+)\}", one, text)


def contact_form(page, sitekey):
    ts = ""
    if sitekey:
        ts = (f'<div class="cf-turnstile" data-sitekey="{html.escape(sitekey)}"></div>'
              '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>')
    return f"""<p id="sent" class="notice">お問い合わせを受け取りました。ありがとうございました。</p>
<p id="error" class="notice">送れませんでした。お返事の先とお問い合わせの中身を書いて、もう一度お送りください。</p>
<form class="contact" method="post" action="/api/contact">
<input type="hidden" name="page" value="/{html.escape(page)}">
<label>お返事の先(メールか電話)<input name="reply" maxlength="200" required></label>
<label>お問い合わせの中身<textarea name="message" rows="6" maxlength="5000" required></textarea></label>
<label class="hp" aria-hidden="true">Web サイト<input name="website" tabindex="-1" autocomplete="off"></label>
{ts}<button type="submit">送る</button>
</form>"""


def block_html(lines, data, missing, news_items, page="", sitekey=""):
    out, para, lst = [], [], None

    def flush():
        nonlocal para, lst
        if para:
            text = " ".join(para)
            text = text.replace(" +\x00", "<br>\n")
            out.append(f"<p>{text}</p>")
            para = []
        if lst:
            tag, items = lst
            out.append(f"<{tag}>" + "".join(f"<li>{x}</li>" for x in items) + f"</{tag}>")
            lst = None

    i = 0
    while i < len(lines):
        raw = fill(lines[i], data, missing)
        s = raw.strip()
        i += 1
        if s.startswith("//"):
            continue
        if not s:
            flush()
            continue
        if m := re.match(r"^(={2,3}) (.+)$", s):
            flush()
            n = len(m.group(1))
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
        elif m := re.match(r"^image::([^\[]+)\[([^\]]*)\]$", s):
            flush()
            out.append(f'<figure><img src="{html.escape(m.group(1))}" alt="{html.escape(m.group(2))}"></figure>')
        elif m := re.match(r"^news::\[(\d*)\]$", s):
            flush()
            n = int(m.group(1) or 0) or len(news_items)
            out.append(news_list(news_items[:n]))
        elif s == "contact::[]":
            flush()
            out.append(contact_form(page, sitekey))
        elif s == "|===":
            flush()
            rows, header = [], None
            while i < len(lines) and lines[i].strip() != "|===":
                r = fill(lines[i], data, missing).strip()
                i += 1
                if r.startswith("|"):
                    rows.append([inline(c.strip()) for c in re.split(r"(?<!\\)\|", r)[1:]])
                elif not r and len(rows) == 1:
                    header = rows.pop()
                elif r and rows:
                    rows[-1][-1] += "<br>" + inline(r)
            i += 1
            t = "<table>"
            if header:
                t += "<thead><tr>" + "".join(f"<th>{c}</th>" for c in header) + "</tr></thead>"
            t += "<tbody>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table>"
            out.append(t)
        elif m := re.match(r"^([*.]) (.+)$", s):
            if para:
                flush()
            tag = "ul" if m.group(1) == "*" else "ol"
            if not lst or lst[0] != tag:
                flush()
                lst = (tag, [])
            lst[1].append(inline(m.group(2)))
        else:
            if lst:
                flush()
            brk = s.endswith(" +")
            text = inline(s[:-2].rstrip() if brk else s)
            para.append(text + (" +\x00" if brk else ""))
    flush()
    return "\n".join(out)


def news_list(items):
    if not items:
        return "<p>お知らせはまだありません。</p>"
    rows = "".join(
        f'<li><time datetime="{d}">{d}</time> <a href="{href}">{html.escape(t)}</a></li>'
        for d, t, href in items
    )
    return f'<ul class="news">{rows}</ul>'


def page_html(title, body, data, nav, here, depth, description):
    up = "../" * depth
    site = html.escape(data.get("屋号", ""))
    current = ' aria-current="page"'
    links = "".join(
        f'<a href="{up}{href}"{current if href == here else ""}>{html.escape(t)}</a>'
        for t, href in nav
    )
    foot = [site]
    for k in ("住所", "電話", "営業時間", "定休日"):
        if data.get(k):
            foot.append(f"{k}: {html.escape(data[k])}")
    head_title = site if title == site or not title else f"{html.escape(title)} | {site}"
    desc = f'<meta name="description" content="{html.escape(description)}">' if description else ""
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{head_title}</title>
{desc}
<link rel="stylesheet" href="{up}style.css">
</head>
<body>
<header><a class="site" href="{up}index.html">{site}</a><nav>{links}</nav></header>
<main>
<h1>{html.escape(title or site)}</h1>
{body}
</main>
<footer>{"<br>".join(foot)}<br><small>© {datetime.date.today().year} {site}</small></footer>
</body>
</html>
"""


# ---- building ---------------------------------------------------------------


def build(src, out, data_path=None):
    data = data_of(data_path or os.path.join(src, "Webサイト.sheet.adoc"))
    pages_dir, news_dir = os.path.join(src, "pages"), os.path.join(src, "news")
    pages = []
    for name in sorted(os.listdir(pages_dir)):
        if name.endswith(".adoc"):
            title, attrs, body = read_doc(os.path.join(pages_dir, name))
            pages.append((name[:-5] + ".html", title, attrs, body))
    # The top page first, then by :順番:
    pages.sort(key=lambda p: (p[0] != "index.html", int(p[2].get("順番", 99)), p[0]))
    news = []
    if os.path.isdir(news_dir):
        for name in os.listdir(news_dir):
            if name.endswith(".adoc"):
                title, attrs, body = read_doc(os.path.join(news_dir, name))
                date = attrs.get("日付", name[:10])
                news.append((date, title, attrs, body, "news/" + name[:-5] + ".html"))
    news.sort(key=lambda n: n[0], reverse=True)
    items = [(d, t, href) for d, t, _, _, href in news]
    nav = [(fill(p[2].get("メニュー", p[1] or ""), data, set()), p[0]) for p in pages]
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "news"))
    missing = set()
    for href, title, attrs, body in pages:
        title = fill(title or "", data, missing)
        text = block_html(body, data, missing, items, href, attrs.get("turnstile", ""))
        with open(os.path.join(out, href), "w", encoding="utf-8") as f:
            f.write(page_html(title, text, data, nav, href, 0, fill(attrs.get("description", ""), data, missing)))
    for date, title, attrs, body, href in news:
        text = f'<p><time datetime="{date}">{date}</time></p>' + block_html(body, data, missing, items)
        with open(os.path.join(out, href), "w", encoding="utf-8") as f:
            f.write(page_html(fill(title or "", data, missing), text, data, nav, href, 1, ""))
    for extra in ("style.css", "images", "CNAME"):
        p = os.path.join(src, extra)
        if os.path.isdir(p):
            shutil.copytree(p, os.path.join(out, extra))
        elif os.path.exists(p):
            shutil.copyfile(p, os.path.join(out, extra))
    if os.path.isdir(os.path.join(src, "functions")):
        # Only /api/* runs the functions; the pages stay free static files
        with open(os.path.join(out, "_routes.json"), "w", encoding="utf-8") as f:
            f.write('{"version": 1, "include": ["/api/*"], "exclude": []}\n')
    print(f"{out} に {len(pages)} ページとお知らせ {len(news)} 件を書きました")
    if missing:
        print(f"データに無い名前: {'、'.join(sorted(missing))}")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="adoc のページから Web サイトを作ります")
    ap.add_argument("folder", help="サイトのフォルダー")
    ap.add_argument("--data", help="公開する事業のデータ(既定はフォルダーの中の Webサイト.sheet.adoc)")
    ap.add_argument("--out", help="出力先(既定はフォルダーの中の _site)")
    a = ap.parse_args()
    build(a.folder, a.out or os.path.join(a.folder, "_site"), a.data)
