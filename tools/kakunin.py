# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lists the sources the documents rest on, and which ones need checking again.

    python tools/kakunin.py [--days 180] [--fetch] [--out 確認の結果.md]

Every fact in this repository comes with its source (a URL) and the day it
was checked ("2026-09-25 に確かめました"). This reads the .md and .adoc files
git tracks, pairs each URL with the check date of its section (the text
between two headings; the file's latest date when the section has none), and
lists:

    old       checked more than --days days ago
    no date   no check date in the section or the file
    broken    with --fetch: the page did not open (an error, or 4xx/5xx)
    moved     with --fetch: the page now answers from another address

The report holds only public URLs and file names, so it can be pasted into
an issue as it is. It exits with 1 when something needs checking, so a
scheduled job can tell. Only the standard library is used.
"""
import argparse
import collections
import datetime
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

URL = re.compile(r"https?://[^\s)(<>\"'`、。,|\]]+")
CHECKED = re.compile(r"(\d{4}-\d{2}-\d{2}) に確かめ")
HEADING = re.compile(r"^(#{1,6} |={1,6} |\.[^\s.])")
# Addresses in examples and settings, and links to our own repositories: not sources
SKIP = re.compile(r"://(127\.0\.0\.1|localhost|[^/]*\.example(\.|/|$)|[^/]*example\.(jp|com)"
                  r"|github\.com/aiseed-dev/|[^/]*[^\x00-\x7f])")


def tracked_docs():
    out = subprocess.run(["git", "ls-files", "-z", "*.md", "*.adoc"], capture_output=True, check=True)
    return [p for p in out.stdout.decode().split("\0") if p]


def sources(path):
    """[(url, section heading, check date or None)] of one file."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    sections, head, body = [], path, []
    for line in lines:
        if HEADING.match(line) and body:
            sections.append((head, body))
            head, body = line.strip(), []
        elif HEADING.match(line):
            head = line.strip()
        else:
            body.append(line)
    sections.append((head, body))
    file_dates = CHECKED.findall("\n".join(lines))
    file_date = max(file_dates) if file_dates else None
    out = []
    for head, body in sections:
        text = "\n".join(body)
        dates = CHECKED.findall(text)
        date = max(dates) if dates else file_date
        for u in URL.findall(text):
            u = u.rstrip(".")
            if not SKIP.search(u):
                out.append((u, head, date))
    return out


def fetch(url):
    """(status, final url) of opening a page; status is a number or an error.

    A DOI always leads on to the publisher, and many publishers turn scripts
    away, so a DOI is asked of the DOI system itself: does the number exist."""
    if url.startswith(("https://doi.org/", "http://doi.org/")):
        doi = url.split("doi.org/", 1)[1]
        try:
            with urllib.request.urlopen(f"https://doi.org/api/handles/{doi}", timeout=20) as r:
                code = json.load(r).get("responseCode")
        except urllib.error.HTTPError as e:
            return e.code, url
        except Exception as e:
            return type(e).__name__, url
        return (200 if code == 1 else f"DOI が見つからない({code})"), url
    req = urllib.request.Request(url, headers={"User-Agent": "aiai-kakunin/1 (checking sources)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, url
    except Exception as e:  # network errors: the reason is the report
        return type(e).__name__, url


def moved(url, final):
    """Whether the page answered from another place (a query added on the way is not a move)."""
    a, b = urllib.parse.urlsplit(url), urllib.parse.urlsplit(final)
    return (a.netloc.lower(), a.path.rstrip("/")) != (b.netloc.lower(), b.path.rstrip("/"))


def main():
    ap = argparse.ArgumentParser(description="出典の URL と確かめた日を集め、確かめ直す物を出します")
    ap.add_argument("--days", type=int, default=180, help="これより前に確かめた物を「古い」とします(既定 180 日)")
    ap.add_argument("--fetch", action="store_true", help="それぞれの URL を開いて、開けるかを見ます")
    ap.add_argument("--out", help="結果を Markdown で書くファイル(Issue に貼れます)")
    a = ap.parse_args()

    today = datetime.date.today()
    found = collections.defaultdict(list)  # url -> [(file, heading, date)]
    for path in tracked_docs():
        for url, head, date in sources(path):
            found[url].append((path, head, date))

    rows = []
    for url, places in sorted(found.items()):
        dates = [d for _, _, d in places if d]
        date = min(dates) if dates else None
        marks = []
        if date is None:
            marks.append("日付なし")
        elif (today - datetime.date.fromisoformat(date)).days > a.days:
            marks.append("古い")
        if a.fetch:
            status, final = fetch(url)
            if not isinstance(status, int) or status >= 400:
                marks.append(f"開けない({status})")
            elif moved(url, final):
                marks.append(f"移った({final})")
        rows.append((url, date, marks, sorted({p for p, _, _ in places})))

    need = [r for r in rows if r[2]]
    lines = [f"# 出典の確認({today})", "",
             f"出典の URL は {len(rows)} 件で、確かめ直す物は {len(need)} 件です"
             f"(古い: {a.days} 日より前に確かめた物{'、開けるかも見ました' if a.fetch else ''})。", ""]
    if need:
        lines += ["| 出典 | 確かめた日 | 見る所 | 書いてあるファイル |", "|---|---|---|---|"]
        lines += [f"| {u} | {d or '-'} | {'、'.join(m)} | {'、'.join(ps)} |" for u, d, m, ps in need]
    text = "\n".join(lines) + "\n"
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"{a.out} に書きました")
    print(text, end="")
    return 1 if need else 0


if __name__ == "__main__":
    sys.exit(main())
