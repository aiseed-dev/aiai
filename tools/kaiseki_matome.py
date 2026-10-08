# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sums up one day of the record that kaiseki keeps of how a site is read
(kaiseki/server.py writes it into SQLite): page by page, how many views, how
long and how far down people read, which section headings they reached,
which full texts they opened, which guides they copied, where they went
next, what they searched for in the site, and which pages were not found.
Writes the day (Japan time) as YYYY-MM-DD.adoc and .json into a folder, as
tools/kougeki.py does, so the record grows day by day; the aiai app's 解析
tab brings the folder to the person's PC and has their AI fix the pages.
Only totals go into the summary, no ID of anyone. Standard library only.

    python3 tools/kaiseki_matome.py --db ~/aiai-server/kaiseki/kaiseki.db --site aiai.aiseed.dev \\
        --out ~/aiai-server/kaiseki [--day 2026-10-08] [--ai haiku]

With --ai haiku, Claude Haiku 5.5 on Google Cloud (Vertex AI, with the
machine's service account, so no key is kept) reads the day next to the
earlier days and writes a short note: what people were looking for, where
they stopped reading, and which pages are missing. A page left more than
once (switching tabs) sends more than one leave, and each counts.
"""
import argparse
import collections
import datetime
import json
import os
import re
import sqlite3
import statistics
import sys
import urllib.error
import urllib.request
import zoneinfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kougeki import metadata  # noqa: E402

TOKYO = zoneinfo.ZoneInfo("Asia/Tokyo")
TOP = 20


def bounds(day):
    """The UTC times, as kaiseki writes them, of the start and end of a day in Japan."""
    start = datetime.datetime.combine(day, datetime.time(), TOKYO).astimezone(datetime.timezone.utc)
    end = start + datetime.timedelta(days=1)
    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")


def summary(db, site, day):
    start, end = bounds(day)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute("SELECT path, event, seconds, scroll, value, title, referrer, utm, screen FROM hits "
                       "WHERE site = ? AND ts >= ? AND ts < ? ORDER BY ts", (site, start, end)).fetchall()
    con.close()
    views, titles, secs, scrolls = collections.Counter(), {}, collections.defaultdict(list), collections.defaultdict(list)
    events = collections.defaultdict(collections.Counter)
    refs, utms, phones = collections.Counter(), collections.Counter(), 0
    for path, event, seconds, scroll, value, title, ref, utm, screen in rows:
        if event == "view":
            views[path] += 1
            titles.setdefault(path, title)
            refs[ref] += bool(ref)
            utms[utm] += bool(utm)
            w = int(screen.split("x")[0]) if re.match(r"\d+x", screen or "") else 0
            phones += 0 < w < 768
        elif event == "leave":
            if seconds is not None:
                secs[path].append(seconds)
            if scroll is not None:
                scrolls[path].append(scroll)
        else:
            events[event][(path, value or "")] += 1

    def med(xs):
        return round(statistics.median(xs)) if xs else None

    pages = [{"path": p, "title": titles.get(p, ""), "views": n, "seconds": med(secs[p]), "scroll": med(scrolls[p]),
              "to_end": round(sum(s >= 90 for s in scrolls[p]) / len(scrolls[p]), 2) if scrolls[p] else None}
             for p, n in views.most_common()]
    sections = {}
    for (path, value), n in events["section"].most_common():
        sections.setdefault(path, []).append([value, n, round(n / views[path], 2) if views[path] else None])

    def top(name):
        return [[p, v, n] for (p, v), n in events[name].most_common(TOP)]

    def words(name):
        c = collections.Counter()
        for (_, v), n in events[name].items():
            c[v] += n
        return [[v, n] for v, n in c.most_common(TOP)]

    total = sum(views.values())
    return {
        "day": day.isoformat(), "site": site,
        "when": datetime.datetime.now(TOKYO).isoformat(timespec="seconds"),
        "views": total, "phone_share": round(phones / total, 2) if total else None,
        "pages": pages, "sections": sections,
        "opens": top("open"), "uses": top("use"), "links": top("link"), "outs": top("out"),
        "notfound": words("notfound"), "searches": words("search"), "nohit": words("nohit"),
        "referrers": [[h, n] for h, n in refs.most_common(TOP) if h],
        "utm": [[u, n] for u, n in utms.most_common(TOP) if u],
    }


def adoc(r):
    lines = [f"= サイトの読まれ方 {r['day']}", f":日付: {r['day']}", f":サイト: {r['site']}", f":日時: {r['when']}", "",
             f"表示: {r['views']} 回。" + (f"画面の幅がスマートフォンの物: {round(r['phone_share'] * 100)}%。" if r["phone_share"] is not None else ""),
             "", "== ページ", ""]
    for p in r["pages"]:
        how = []
        if p["seconds"] is not None:
            how.append(f"見ていた時間の中ほど {p['seconds']} 秒")
        if p["scroll"] is not None:
            how.append(f"下へ見た所の中ほど {p['scroll']}%、終わりまで見た割合 {round(p['to_end'] * 100)}%")
        lines.append(f"- {p['path']}({p['title']}): {p['views']} 回" + (f"。{'、'.join(how)}" if how else ""))
    if r["sections"]:
        lines += ["", "== 読んだ見出し(表示のうち、たどり着いた割合)", ""]
        for path, items in r["sections"].items():
            lines.append(f"{path}:")
            lines += [f"- {v}: {n} 回" + (f"({round(s * 100)}%)" if s is not None else "") for v, n, s in items]
    for key, head in (("opens", "開いた全文"), ("uses", "写した、ダウンロードした手引き"), ("links", "次に開いたページ"), ("outs", "外へのリンク")):
        if r[key]:
            lines += ["", f"== {head}", ""] + [f"- {p} → {v}: {n} 回" for p, v, n in r[key]]
    for key, head in (("searches", "探した言葉"), ("nohit", "探して見つからなかった言葉"), ("notfound", "見つからなかったページ"),
                      ("referrers", "来た元"), ("utm", "キャンペーン(utm)")):
        if r[key]:
            lines += ["", f"== {head}", ""] + [f"- {v}: {n} 回" for v, n in r[key]]
    if r.get("ai"):
        lines += ["", f"== AI の所見({r['ai']['model']})", "", r["ai"]["text"] or f"(読めませんでした: {r['ai'].get('error', '')})"]
    return "\n".join(lines) + "\n"


def ask_haiku(prompt, model="claude-haiku-5-5"):
    """Claude's answer through Vertex AI, with the machine's service account."""
    project = metadata("project/project-id")
    token = json.loads(metadata("instance/service-accounts/default/token"))["access_token"]
    url = (f"https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/"
           f"publishers/anthropic/models/{model}:rawPredict")
    body = {"anthropic_version": "vertex-2023-10-16", "max_tokens": 4000, "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        answer = json.load(resp)
    return "".join(c.get("text", "") for c in answer.get("content", []) if c.get("type") == "text").strip()


def earlier(folder, today, n=7):
    """The earlier days' adoc in the folder, newest first."""
    out = []
    if os.path.isdir(folder):
        for f in sorted(os.listdir(folder), reverse=True):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.adoc", f) and f[:10] < today and len(out) < n:
                with open(os.path.join(folder, f), encoding="utf-8") as fh:
                    out.append(fh.read())
    return out


def ai_note(r, folder):
    before = earlier(folder, r["day"])
    prompt = ("あなたは、サイトの読まれ方の記録を読み、ページを直す人に渡す所見を書く係です。"
              "次の今日の記録と前の日の記録を読んで、日本語の「です・ます」の説明文で、次の 3 つを短く書いてください。\n"
              "1. 読む人が探している物: 探した言葉、見つからなかった言葉とページを、同じことを探している物どうしでまとめる\n"
              "2. 直す候補: 多くの人が読むのをやめる見出しやページ、よく開かれる全文、終わりまで読まれないページ\n"
              "3. 足りないページの候補: 探しても見つからなかった物から、作るとよいページ\n"
              "記録にある数だけを使い、推測で書きません。数が少ないときは、少ないと書きます。\n\n"
              f"<今日の記録>\n{adoc(r)}\n</今日の記録>\n\n<前の日>\n" + ("\n".join(before) or "(まだありません)") + "\n</前の日>\n")
    try:
        return {"model": "claude-haiku-5-5", "text": ask_haiku(prompt) or "(答えがありませんでした)"}
    except (OSError, ValueError, KeyError, urllib.error.URLError) as e:
        detail = getattr(e, "read", lambda: b"")()
        return {"model": "claude-haiku-5-5", "text": "", "error": (detail.decode("utf-8", errors="replace") if detail else str(e))[:300]}


def main():
    ap = argparse.ArgumentParser(description="サイトの読まれ方の記録を、1 日分まとめます")
    ap.add_argument("--db", required=True, help="kaiseki の SQLite のファイル")
    ap.add_argument("--site", required=True, help="まとめるサイトのホスト(例: aiai.aiseed.dev)")
    ap.add_argument("--day", help="まとめる日(日本時間)。既定は昨日")
    ap.add_argument("--out", help="この日の記録(adoc と json)を書くフォルダー。無ければ adoc を出すだけ")
    ap.add_argument("--ai", choices=["haiku"], help="Claude Haiku 5.5(Google Cloud)に読ませて、所見を足す")
    a = ap.parse_args()
    day = datetime.date.fromisoformat(a.day) if a.day else datetime.datetime.now(TOKYO).date() - datetime.timedelta(days=1)
    r = summary(os.path.expanduser(a.db), a.site, day)
    if a.ai:
        r["ai"] = ai_note(r, a.out or "")
    if not a.out:
        print(adoc(r), end="")
        return
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, f"{r['day']}.json"), "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    with open(os.path.join(a.out, f"{r['day']}.adoc"), "w", encoding="utf-8") as f:
        f.write(adoc(r))
    print(f"{a.out} に {r['day']} の記録を書きました(表示 {r['views']} 回)")


if __name__ == "__main__":
    main()
