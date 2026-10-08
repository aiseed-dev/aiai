# SPDX-License-Identifier: AGPL-3.0-or-later
"""Has an AI's CLI fix aiai's site from the record of how it is read: it
reads the last days' summaries (tools/kaiseki_matome.py writes them on the
server; the app's 解析 tab brings them to ~/aiai-server/kaiseki), the log of
earlier fixes (kaiseki/kiroku.adoc) and the pages' sources, checks whether
the earlier fixes worked, fixes pages, writes missing ones, and adds what it
did to the log. It works on a branch of its own, kaiseki/YYYY-MM-DD, and
commits there; the person reads the diff and merges it, or drops it.

    python kaiseki/naosu.py --ai claude|gemini|codex [--days 7] [--records ~/aiai-server/kaiseki]
    python kaiseki/naosu.py --prompt-only          # the request alone, to paste into any AI
    python kaiseki/naosu.py --merge kaiseki/2026-10-09 | --drop kaiseki/2026-10-09

Only the standard library is used.
"""
import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "news"))
from tsukuru import CLIS, MODEL_FLAG  # noqa: E402  (the same way of running each CLI)

TZ = zoneinfo.ZoneInfo("Asia/Tokyo")
RECORDS = os.path.join(os.path.expanduser("~"), "aiai-server", "kaiseki")
LOG = os.path.join(HERE, "kiroku.adoc")
# Where each page of the site comes from
SOURCES = """- / : site/index.html(手で書いた HTML。帯や段の文を直す)
- /kangaekata.html : site/app/assets/kangaekata.md(節は「## 見出し {#id}」、図は {{fig:名前}} で site/figures/名前.svg)
- /skills/名前.html : 名前/SKILL.md(人が見るのは、説明、「手順」の各段の最初の文、「項目」の名前。全文は畳んである)
- /news/ : news/*.adoc(ニュースは直さない)
- /sagasu.html、/kaiseki/、404 : site/make_site.py の中の文
- 新しい手引き: 新しいフォルダーの SKILL.md(ほかの SKILL.md と同じ形)
- 新しい考え方の節: kangaekata.md に「## 見出し {#id}」で足す"""


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def records(folder, days):
    """The last days' summaries (adoc), oldest first."""
    if not os.path.isdir(folder):
        return []
    names = sorted(f for f in os.listdir(folder) if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.adoc", f))[-days:]
    return [read(os.path.join(folder, f)) for f in names]


def guide():
    text = read(os.path.join(HERE, "SKILL.md"))
    return re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S).strip()


def request(today, recs):
    log = read(LOG) if os.path.exists(LOG) else "(まだありません)"
    return f"""今日は {today.isoformat()} です。aiai のサイト(https://aiai.aiseed.dev/)を、読まれ方の記録から直してください。
このリポジトリの中で作業します。質問はせず、最後まで進めてください。コミットはしません(後で、まとめてします)。

次の順に進めます。
1. 直し方の記録(kaiseki/kiroku.adoc)の前の直しについて、直した日より後の記録と比べ、効いたかを、その節の
   「確かめたこと:」に書きます。比べる記録がまだ無ければ、そのままにします
2. 下の記録から、直す所と、足りないページを決めます。手引きの「手順」の 4 の順に見ます。記録の数が少なければ、
   直すのは 1 つか 2 つにします。直す理由が記録に無ければ、何も直しません
3. ページの元のファイルを直し、足りないページを書きます。リポジトリの CLAUDE.md の書き方を守ります
   (です・ます、出典と確かめた日、余計な注意書きを書かない、ページは短く、詳しいことは手引きに)
4. 直したことを、kaiseki/kiroku.adoc の終わりに足します。直し 1 つにつき 1 つの節で、次の形です。
   == {today.isoformat()} 直したページ
   :ページ: /kangaekata.html#kiroku
   見たこと: 記録の数(どの日の、何が、いくつ)
   直したこと: 何をどう直したか
   確かめたこと: (次に回したときに書く)
   kiroku.adoc が無ければ、1 行目を「= aiai のサイトの直し方の記録」にして作ります
5. 最後に、直したファイルの名前と、直したことを 1 行ずつ答えます

<手引き>
{guide()}
</手引き>

<ページの元>
{SOURCES}
</ページの元>

<直し方の記録>
{log.strip()}
</直し方の記録>

<読まれ方の記録(古い日から)>
{chr(10).join(recs) if recs else "(まだありません)"}
</読まれ方の記録>
"""


def run(ai, prompt, model=None):
    cmd = [prompt if a == "{prompt}" else a for a in CLIS[ai]]
    if model:
        cmd += [MODEL_FLAG[ai], model]
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)  # so Claude Code runs even from inside a Claude Code session
    return subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True)


def fix(ai, model, days, folder):
    today = datetime.datetime.now(TZ).date()
    recs = records(folder, days)
    if not recs:
        print(f"{folder} に読まれ方の記録がありません。アプリの「解析」のタブで、サーバーから取り込んでください")
        return 1
    if git("status", "--porcelain"):
        print("まだコミットしていない変更があります。コミットするか片付けてから、もう一度動かしてください")
        return 1
    if not shutil.which(CLIS[ai][0]):
        print(f"{CLIS[ai][0]} が見つかりません")
        return 1
    base = git("rev-parse", "--abbrev-ref", "HEAD")
    branch = f"kaiseki/{today.isoformat()}"
    if git("rev-parse", "--verify", "--quiet", branch, check=False):
        print(f"枝 {branch} はもうあります。取り込むか捨ててから、もう一度動かしてください")
        return 1
    git("switch", "-c", branch)
    before = read(LOG) if os.path.exists(LOG) else ""
    print(f"{ai} に、{len(recs)} 日分の記録から直すよう頼みます(数分かかります)。枝は {branch} です")
    r = run(ai, request(today, recs), model)
    tail = (r.stdout or "").strip().splitlines()[-15:]
    if tail:
        print(f"--- {ai} の答え(終わりの部分)\n" + "\n".join(tail))
    if r.returncode != 0 and r.stderr:
        print(r.stderr.strip()[-1500:])
    changed = [line[3:] for line in git("status", "--porcelain").splitlines()]
    if not changed:
        git("switch", base)
        git("branch", "-D", branch)
        print("直す所はありませんでした")
        return 0
    after = read(LOG) if os.path.exists(LOG) else ""
    notes = [h for h in re.findall(r"^== (.+)$", after, re.M) if h not in re.findall(r"^== (.+)$", before, re.M)]
    test = subprocess.run([sys.executable, os.path.join(ROOT, "site", "test_site.py")], cwd=ROOT, text=True, capture_output=True)
    if test.returncode != 0:
        print("--- サイトを作る確かめが通りません。差分を読んで直してから取り込んでください\n" + test.stderr.strip()[-1500:])
    git("add", "--", *changed)
    git("commit", "-m", f"Site: fixes from the record of how it is read, {today.isoformat()}\n\n"
        + "\n".join(f"- {n}" for n in notes) + "\n\nWritten by " + ai + " with kaiseki/naosu.py.")
    git("switch", base)
    print(f"--- {branch} にコミットしました。直したファイル:")
    print(git("diff", "--stat", f"{base}...{branch}"))
    print(f"差分を読んで、python kaiseki/naosu.py --merge {branch} で取り込むか、--drop {branch} で捨ててください")
    return 0


def main():
    ap = argparse.ArgumentParser(description="読まれ方の記録から、AI の CLI にサイトを直させます")
    ap.add_argument("--ai", choices=sorted(CLIS), help="動かす CLI")
    ap.add_argument("--model", help="その CLI に渡すモデルの名前")
    ap.add_argument("--days", type=int, default=7, help="読ませる記録の日数(既定 7)")
    ap.add_argument("--records", default=RECORDS, help=f"読まれ方の記録のフォルダー(既定 {RECORDS})")
    ap.add_argument("--prompt-only", action="store_true", help="頼み文だけを出す")
    ap.add_argument("--merge", metavar="BRANCH", help="AI が直した枝を、今の枝に取り込む")
    ap.add_argument("--drop", metavar="BRANCH", help="AI が直した枝を捨てる")
    a = ap.parse_args()
    for name in (a.merge, a.drop):
        if name and not re.fullmatch(r"kaiseki/\d{4}-\d{2}-\d{2}", name):
            ap.error("枝の名前は kaiseki/YYYY-MM-DD です")
    if a.merge:
        git("merge", "--ff-only", a.merge)
        git("branch", "-d", a.merge)
        print(f"{a.merge} を取り込みました。サイトに載せるのは、いつもの手順です")
        return 0
    if a.drop:
        git("branch", "-D", a.drop)
        print(f"{a.drop} を捨てました")
        return 0
    if a.prompt_only:
        print(request(datetime.datetime.now(TZ).date(), records(a.records, a.days)))
        return 0
    if not a.ai:
        ap.error("--ai か --prompt-only を付けてください")
    return fix(a.ai, a.model, a.days, a.records)


if __name__ == "__main__":
    sys.exit(main())
