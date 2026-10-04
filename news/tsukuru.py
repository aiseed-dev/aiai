# SPDX-License-Identifier: AGPL-3.0-or-later
"""Has an AI's CLI write today's news draft, news/YYYY-MM-DD.adoc, by the
guide (SKILL.md) and the person's tastes (好み.adoc).

    python news/tsukuru.py --ai claude|gemini|codex [--date YYYY-MM-DD] [--model NAME]
    python news/tsukuru.py --prompt-only          # the request alone, to paste into any AI

The request holds the guide, the tastes and the headings of the last days
(so the same event is not written twice), and asks for the one file. The
CLI runs without asking: Claude Code with web tools allowed and edits
accepted, Gemini CLI with edits approved, Codex with web search and
workspace writes. Afterwards the file is checked for the shape the site
reads (title, date, headings, 分野, sources with a checked-on date).
Only the standard library is used.
"""
import argparse
import datetime
import os
import re
import subprocess
import sys
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TZ = zoneinfo.ZoneInfo("Asia/Tokyo")
DAYS_BACK = 7

# How each CLI runs once, without asking. {prompt} is the request.
CLIS = {
    "claude": ["claude", "-p", "{prompt}", "--permission-mode", "acceptEdits",
               "--allowedTools", "WebSearch", "WebFetch", "Read", "Write", "Edit", "Glob", "Grep"],
    "gemini": ["gemini", "-p", "{prompt}", "--approval-mode", "auto_edit"],
    "codex": ["codex", "exec", "--search", "--sandbox", "workspace-write", "{prompt}"],
}
MODEL_FLAG = {"claude": "--model", "gemini": "--model", "codex": "--model"}


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def guide():
    """The guide without its front matter and its 使い方 section."""
    text = read(os.path.join(HERE, "SKILL.md"))
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    return text.split("\n## 使い方")[0].strip()


def recent_headings(today, days=DAYS_BACK):
    """[(date, heading)] of the last days' files, newest first."""
    out = []
    for n in range(1, days + 1):
        d = (today - datetime.timedelta(days=n)).isoformat()
        p = os.path.join(HERE, f"{d}.adoc")
        if os.path.exists(p):
            out += [(d, m[1]) for m in re.finditer(r"^== (.+)$", read(p), re.M)]
    return out


def request(today):
    """The request for one day's file."""
    tastes = read(os.path.join(HERE, "好み.adoc"))
    seen = recent_headings(today)
    before = ("\n".join(f"- {d} {h}" for d, h in seen) or "(まだありません)")
    target = f"news/{today.isoformat()}.adoc"
    return f"""今日は {today.isoformat()} です。次の手引きと好みに従って、今日のニュースの adoc を 1 つ、`{target}` に書いてください。
質問はせず、最後まで進めてください。ファイルを書くほかには、何も作らず、何も変えません。
どの分野にも書く物が無ければ、ファイルを作らず、その旨だけを答えてください。

<手引き>
{guide()}
</手引き>

<好み>
{tastes.strip()}
</好み>

<前の数日に書いた見出し>
{before}
</前の数日に書いた見出し>
"""


def check(path):
    """Problems in the file's shape, as the site reads it; [] when none."""
    if not os.path.exists(path):
        return ["ファイルがありません"]
    text = read(path)
    problems = []
    if not re.search(r"^= .+", text, re.M):
        problems.append("1 行目の「= 題」がありません")
    if not re.search(r"^:日付: \d{4}-\d{2}-\d{2}", text, re.M):
        problems.append("「:日付:」がありません")
    entries = re.split(r"^== ", text, flags=re.M)[1:]
    if not entries:
        problems.append("「== 見出し」が 1 つもありません")
    for e in entries:
        head = e.splitlines()[0]
        if not re.search(r"^:分野: .+", e, re.M):
            problems.append(f"「{head}」に :分野: がありません")
        if "出典:" not in e:
            problems.append(f"「{head}」に出典がありません")
        elif not re.search(r"出典:.*https?://.*に確かめました", e):
            problems.append(f"「{head}」の出典に URL か確かめた日がありません")
    return problems


def run(ai, prompt, model=None):
    cmd = [prompt if a == "{prompt}" else a for a in CLIS[ai]]
    if model:
        cmd += [MODEL_FLAG[ai], model]
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)  # so Claude Code runs even from inside a Claude Code session
    return subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser(description="AI の CLI に、今日のニュースの下書きを書かせます")
    ap.add_argument("--ai", choices=sorted(CLIS), help="動かす CLI")
    ap.add_argument("--date", help="YYYY-MM-DD(既定は今日、日本時間)")
    ap.add_argument("--model", help="その CLI に渡すモデルの名前")
    ap.add_argument("--prompt-only", action="store_true", help="頼み文だけを出す")
    a = ap.parse_args()
    today = datetime.date.fromisoformat(a.date) if a.date else datetime.datetime.now(TZ).date()
    prompt = request(today)
    if a.prompt_only:
        print(prompt)
        return 0
    if not a.ai:
        ap.error("--ai か --prompt-only を付けてください")
    target = os.path.join(HERE, f"{today.isoformat()}.adoc")
    if os.path.exists(target):
        print(f"{os.path.relpath(target, ROOT)} はもうあります。消すか、--date で別の日にしてください")
        return 1
    print(f"{a.ai} に、{today.isoformat()} の下書きを頼みます(数分かかります)")
    r = run(a.ai, prompt, a.model)
    tail = (r.stdout or "").strip().splitlines()[-12:]
    if tail:
        print("--- " + a.ai + " の答え(終わりの部分)")
        print("\n".join(tail))
    if r.returncode != 0:
        print(f"--- {a.ai} が {r.returncode} で終わりました")
        if r.stderr:
            print(r.stderr.strip()[-2000:])
    problems = check(target)
    if problems == ["ファイルがありません"]:
        print("下書きはできませんでした(書く物が無かったか、途中で止まりました)")
        return 1
    rel = os.path.relpath(target, ROOT)
    if problems:
        print(f"{rel} はできましたが、直す所があります:")
        for p in problems:
            print(f"  - {p}")
    else:
        n = len(re.findall(r"^== ", read(target), re.M))
        print(f"{rel} に {n} 件できました。読んで直してから、コミットしてください")
    return 0


if __name__ == "__main__":
    sys.exit(main())
