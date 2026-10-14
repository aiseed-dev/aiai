# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tries aiai on the site with Gemini, for people who sign in: a dialogue
with Gemini that has read one of the guides, today's news made by Gemini
with Google Search from the person's own tastes (as news/SKILL.md says),
three longer jobs from what the person gives (tameshi/kaihatsu.py): the
present state of the apps that do what the person asks the AI again and
again; the problems of those apps (or of the apps the materials name), as
the reference of step 5 of rireki/SKILL.md; and, from a SKILL.md and its
references, the design document and the user manual with a picture per
screen. A dialogue on how those apps could be better can read what the
first job found, and the third job can read what the second made. Gemini
runs on Google Cloud (site/gemini.py). It is mounted at /tameshi by
site/server.py; the screen is /tameshi.html.

People sign in with Apple or Google (the sign-in of moushikomi/server.py).
For reviewers who cannot use those, one test account signs in with an ID
and a password. Each person has a number of uses a day, and everyone
together has a number of Gemini calls a day, so the site is not used up.
What people write is sent to Gemini and is not kept here; only the counts
are kept. Settings come from environment variables, so no secret is in
the repository:

    BASE_URL, RETURN_URLS, GOOGLE_*, APPLE_*    as in moushikomi/server.py
    DB                      the SQLite file (default tameshi.db next to this file)
    TAMESHI_TEST_ID, TAMESHI_TEST_PASSWORD      the test account (both, or neither)
    TAMESHI_CHAT_PER_DAY    turns of the dialogue one person may have a day (default 30)
    TAMESHI_NEWS_PER_DAY    news one person may make a day (default 3)
    TAMESHI_DAY_LIMIT       Gemini calls everyone together may make a day (default 600)
    TAMESHI_SEKKEI_PER_DAY  design jobs one person may start a day (default 1)
    TAMESHI_CHOUSA_PER_DAY  research jobs one person may start a day (default 2)
    TAMESHI_KADAI_PER_DAY   jobs that gather the problems of apps one person may start a day (default 2)
    TAMESHI_JOBS_PER_DAY    jobs everyone together may start a day (default 10; design, research and
                            problems count together)
    TAMESHI_KAIHATSU_EMAILS sign-in emails that may start jobs (space separated); empty
                            means everyone who signs in. The test account always may
    TAMESHI_JOBS            the folder of the jobs' files (default jobs/ next to DB);
                            a job and its files are deleted after 7 days
    TIMEZONE                default Asia/Tokyo
"""
import datetime
import importlib.util
import io
import json
import os
import re
import secrets
import shutil
import sys
import threading
import time
import urllib.parse
import zipfile
import zoneinfo

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# The sign-in is the checked one of moushikomi/server.py, loaded under its own name
_spec = importlib.util.spec_from_file_location("moushikomi_server", os.path.join(ROOT, "moushikomi", "server.py"))
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)

sys.path.insert(0, os.path.join(ROOT, "site"))
import gemini  # noqa: E402

sys.path.insert(0, HERE)
import kaihatsu  # noqa: E402

MESSAGE_CHARS = 4000     # one message in the dialogue
RESEARCH_CHARS = 60000   # what a research job found, read into the dialogue on improving
DIALOGUE_CHARS = 30000   # the whole dialogue sent at once
TASTES_CHARS = 4000      # the person's tastes for the news
FAILED_LOGINS = 50       # wrong test-account passwords accepted a day, before the test login closes

SCHEMA = ms.SIGN_IN_SCHEMA + """
        CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, provider TEXT, sub TEXT, kind TEXT,
            status TEXT, error TEXT, steps TEXT, created REAL, finished REAL);
        CREATE TABLE IF NOT EXISTS uses (day TEXT, provider TEXT, sub TEXT, kind TEXT, n INTEGER,
            PRIMARY KEY (day, provider, sub, kind));
"""

CHAT_RULES = """あなたは、aiai のサイト(https://aiai.aiseed.dev/)の上で、下の手引きを読んで、この人と対話します。
手引きの「守ること」と「手順」のとおりに進めます。1 回の答えは短くし、この人に 1 つずつ聞きながら進めます。
答えは、Markdown の記号(** や #)を使わず、普通の文で書きます。画面は、書いた文をそのまま見せます。
この人が持っていない道具(ファイルを読む、コマンドを動かす)が要る所は、この人が自分の AI か PC でする形にします。
サイトは、この対話を記録しません。続きは、この人がふだん使っている AI で、同じ手引きを読ませて進められます。

<手引き>
{guide}
</手引き>"""

KAIZEN_RULES = CHAT_RULES + """

いまは、手順の 3(今あるアプリに不満な所があれば、どう良くすればよいかを本人と考える)から始めます。
この人は、最初に、使ったアプリと、困った場面と、困ったことを書きます。どのアプリの、どの場面で、
何が困るのかが具体的でない所は、1 つずつ聞いて具体的にします。不満が具体的になるまでは、良くする案を
出しません。具体的になったら、どうなればよいのかを、この人の言葉にします。良くする所がそろったら、
手順の 4(開発者に要望を書くか、自分で作るか)を、この人が決めるための材料を短くまとめます。{research}"""

KAIZEN_RESEARCH = """

下は、手順の 2 で、Gemini が Google 検索で今あるアプリを調べた結果です。ここに書いてあることを材料にし、
書いていないことは推測しません。

<調べた結果>
{text}
</調べた結果>"""

NEWS_REQUEST = """今日は {today} です。下の手引きと、この人の好みに従って、今日のニュースを adoc で 1 つ書いてください。
Google 検索で、今日と前の数日の記事を探します。見つけた記事に書いてあることだけを書き、推測で書きません。
出典には、記事の題、媒体、日付を書きます。URL は、こちらで調べた物を下に足すので、書かなくてかまいません。
答えは adoc の本文だけにします。

<好み>
{tastes}
</好み>"""


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def without_front(text):
    return re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S).strip()


def guides(root=ROOT):
    """{name: (title, text)} of every SKILL.md in the repository."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in ("site", "public"))
        if "SKILL.md" in filenames:
            text = read(os.path.join(dirpath, "SKILL.md"))
            m = re.search(r"^# (.+)$", text, re.M)
            out[os.path.basename(dirpath)] = (m[1].strip() if m else os.path.basename(dirpath), without_front(text))
    return out


JOB_KINDS = ("sekkei", "chousa", "kadai")  # the longer jobs; they share the day's limit for jobs
MATERIAL_EXTS = (".md", ".adoc", ".txt")
MATERIAL_BYTES = 2_000_000     # all the files of one job, unpacked
MATERIAL_FILES = 50
JOB_DAYS = 7
MIHON = os.path.join(ROOT, "hackathon", "mihon")  # a made-up sample of materials
# the front matter of a SKILL.md among the materials of materials_of(), and the name: in it
SKILL_FRONT = re.compile(r'<ファイル name="(?:[^"\n]*/)?SKILL\.md">\n---\r?\n(.*?)\r?\n---', re.S)
SKILL_NAME = re.compile(r"""^name:[ \t]*["']?([^\s"']+)["']?[ \t]*\r?$""", re.M)


def materials_of(uploads):
    """The text of the materials: [(name, bytes)] of the uploaded files, a ZIP opened
    in memory. Only Markdown, AsciiDoc and plain text are read; nothing is written."""
    found, total = [], 0
    for name, data in uploads:
        if name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    for info in z.infolist():
                        if (not info.is_dir() and info.filename.lower().endswith(MATERIAL_EXTS)
                                and ".." not in info.filename and info.file_size <= MATERIAL_BYTES):
                            found.append((info.filename, z.read(info)))
            except zipfile.BadZipFile:
                raise HTTPException(422, f"{name} を開けませんでした")
        elif name.lower().endswith(MATERIAL_EXTS):
            found.append((name, data))
    if not found:
        raise HTTPException(422, "資料が入っていません(.md、.adoc、.txt か、それを入れた ZIP)")
    parts = []
    for name, data in found[:MATERIAL_FILES]:
        total += len(data)
        if total > MATERIAL_BYTES:
            raise HTTPException(422, "資料が大きすぎます(2 MB まで)")
        parts.append(f'<ファイル name="{name}">\n{data.decode("utf-8", errors="replace")}\n</ファイル>')
    return "\n\n".join(parts)


def skill_name(materials):
    """The name: in the front matter of a SKILL.md among the materials, when it can name a
    file; app when there is none."""
    for m in SKILL_FRONT.finditer(materials):
        n = SKILL_NAME.search(m[1])
        if n and kaihatsu.NAME.fullmatch(n[1].lower()):
            return n[1].lower()
    return "app"


def create_app(env=None, providers=None, model=None, draw=None, run=None):
    """model(contents, system=..., search=..., **more) -> (text, sources), and
    draw(prompt) -> PNG bytes: Gemini unless given. run(fn) starts a job; a
    thread unless given (the tests run it at once)."""
    env = dict(os.environ if env is None else env)
    base = env["BASE_URL"].rstrip("/")
    returns = env.get("RETURN_URLS", "").split()
    tz = zoneinfo.ZoneInfo(env.get("TIMEZONE", "Asia/Tokyo"))
    db = ms.Store(env.get("DB") or os.path.join(HERE, "tameshi.db"), SCHEMA)
    provs = providers if providers is not None else ms.providers_from(env)
    ask = model or gemini.generate
    test_id, test_password = env.get("TAMESHI_TEST_ID", ""), env.get("TAMESHI_TEST_PASSWORD", "")
    per_day = {"chat": int(env.get("TAMESHI_CHAT_PER_DAY", "30")), "news": int(env.get("TAMESHI_NEWS_PER_DAY", "3")),
               "sekkei": int(env.get("TAMESHI_SEKKEI_PER_DAY", "1")), "chousa": int(env.get("TAMESHI_CHOUSA_PER_DAY", "2")),
               "kadai": int(env.get("TAMESHI_KADAI_PER_DAY", "2"))}
    day_limit = int(env.get("TAMESHI_DAY_LIMIT", "600"))
    jobs_per_day = int(env.get("TAMESHI_JOBS_PER_DAY", "10"))
    makers = {e.lower() for e in env.get("TAMESHI_KAIHATSU_EMAILS", "").split()}
    jobs_dir = env.get("TAMESHI_JOBS") or os.path.join(os.path.dirname(os.path.abspath(env.get("DB") or os.path.join(HERE, "tameshi.db"))), "jobs")
    paint = draw or gemini.image
    slots = threading.BoundedSemaphore(2)  # jobs that call Gemini at the same time

    def start_thread(fn):
        def go():
            with slots:
                fn()
        threading.Thread(target=go, daemon=True).start()
    start = run or start_thread
    all_guides = guides()
    news_guide = without_front(read(os.path.join(ROOT, "news", "SKILL.md"))).split("\n## 使い方")[0]
    last_purge = [0.0]

    def today():
        return datetime.datetime.now(tz).date().isoformat()

    def purge():
        t = time.time()
        if t - last_purge[0] >= 60:
            last_purge[0] = t
            ms.purge_sign_in(db, t)
            for row in db.all("SELECT id FROM jobs WHERE created < ?", (t - JOB_DAYS * 86400,)):
                shutil.rmtree(os.path.join(jobs_dir, row["id"]), ignore_errors=True)
                db.run("DELETE FROM jobs WHERE id = ?", (row["id"],))

    app = FastAPI(title="aiai を試す", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db = db
    person = ms.sign_in(app, db, provs, base, returns, purge)

    def used(provider, sub, kind):
        row = db.one("SELECT n FROM uses WHERE day = ? AND provider = ? AND sub = ? AND kind = ?",
                     (today(), provider, sub, kind))
        return row["n"] if row else 0

    def take(s, kind):
        """Counts one use before Gemini is called, or refuses when a limit is reached."""
        if used(s["provider"], s["sub"], kind) >= per_day[kind]:
            raise HTTPException(429, f"今日の分({per_day[kind]} 回)は使い終わりました。明日またどうぞ")
        everyone = db.one("SELECT COALESCE(SUM(n), 0) FROM uses WHERE day = ? AND provider != '-'", (today(),))[0]
        marks = ", ".join("?" * len(JOB_KINDS))
        jobs = db.one(f"SELECT COALESCE(SUM(n), 0) FROM uses WHERE day = ? AND kind IN ({marks})", (today(), *JOB_KINDS))[0]
        if everyone >= day_limit or (kind in JOB_KINDS and jobs >= jobs_per_day):
            raise HTTPException(429, "今日の受け付けは終わりました。明日またどうぞ")
        db.run("INSERT INTO uses VALUES (?, ?, ?, ?, 1) ON CONFLICT (day, provider, sub, kind) DO UPDATE SET n = n + 1",
               (today(), s["provider"], s["sub"], kind))
        return per_day[kind] - used(s["provider"], s["sub"], kind)

    async def body_of(request):
        try:
            b = await request.json()
        except ValueError:
            raise HTTPException(400, "中身を読めませんでした")
        if not isinstance(b, dict):
            raise HTTPException(400, "中身を読めませんでした")
        return b

    @app.get("/api/info")
    def info():
        return {"guides": [{"name": n, "title": t} for n, (t, _) in sorted(all_guides.items())],
                "per_day": per_day, "providers": sorted(provs), "test_login": bool(test_id and test_password)}

    @app.post("/api/test-login")
    async def test_login(request: Request):
        b = await body_of(request)
        if not (test_id and test_password):
            raise HTTPException(404, "テストアカウントはありません")
        failed = db.one("SELECT n FROM uses WHERE day = ? AND provider = '-' AND sub = '-' AND kind = 'failed'",
                        (today(),))
        if failed and failed["n"] >= FAILED_LOGINS:
            raise HTTPException(429, "今日は、テストアカウントでは入れません")
        if not (secrets.compare_digest(str(b.get("id", "")), test_id)
                and secrets.compare_digest(str(b.get("password", "")), test_password)):
            db.run("INSERT INTO uses VALUES (?, '-', '-', 'failed', 1) ON CONFLICT (day, provider, sub, kind) "
                   "DO UPDATE SET n = n + 1", (today(),))
            time.sleep(1)
            raise HTTPException(401, "ID かパスワードが違います")
        token = secrets.token_urlsafe(32)
        db.run("INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
               (ms.digest(token), "test", test_id, "", time.time() + ms.SESSION_DAYS * 86400))
        return {"token": token}

    def may_make(s):
        return s["provider"] == "test" or not makers or (s["email"] or "").lower() in makers

    @app.get("/api/me")
    def me(authorization: str = Header("")):
        s = person(authorization)
        return {"provider": s["provider"], "email": s["email"], "kaihatsu": may_make(s),
                "left": {k: per_day[k] - used(s["provider"], s["sub"], k) for k in per_day}}

    # ---- the longer jobs: design and manual, and the present state of related apps ----

    def job_row(jid, s):
        row = db.one("SELECT * FROM jobs WHERE id = ? AND provider = ? AND sub = ?", (jid, s["provider"], s["sub"]))
        if not row:
            raise HTTPException(404, "その仕事はありません")
        return row

    def job_files(jid):
        folder = os.path.join(jobs_dir, jid)
        out = []
        for dirpath, _, names in os.walk(folder):
            out += [os.path.relpath(os.path.join(dirpath, n), folder) for n in names]
        return sorted(out)

    def research_of(jid, s):
        """What a finished research job (chousa) of this person's found, as text: its chousa/*.adoc."""
        row = job_row(jid, s)
        folder = os.path.join(jobs_dir, row["id"], "chousa")
        if row["kind"] != "chousa" or row["status"] != "done" or not os.path.isdir(folder):
            raise HTTPException(422, "読ませられるのは、できあがった「今あるアプリを探す」の結果です")
        text = "\n\n".join(read(os.path.join(folder, n)) for n in sorted(os.listdir(folder)) if n.endswith(".adoc"))
        return text[:RESEARCH_CHARS]

    def problems_of(jid, s):
        """The references (references/*.adoc) of a finished job that gathers problems (kadai) of this
        person's: [(path, bytes)]."""
        row = job_row(jid, s)
        if row["kind"] != "kadai" or row["status"] != "done":
            raise HTTPException(422, "読ませられるのは、できあがった「今あるアプリの課題を集める」の資料です")
        out = []
        for path in job_files(jid):
            if os.path.dirname(path) == "references" and path.endswith(".adoc"):
                with open(os.path.join(jobs_dir, jid, path), "rb") as f:
                    out.append((path, f.read()))
        return out

    @app.post("/api/jobs")
    async def new_job(kind: str = Form(...), note: str = Form(""), mihon: str = Form(""), research: str = Form(""),
                      name: str = Form(""), kadai: str = Form(""),
                      files: list[UploadFile] | None = File(None), authorization: str = Header("")):
        s = person(authorization)
        if kind not in JOB_KINDS:
            raise HTTPException(422, "何をするかを選んでください")
        if not may_make(s):
            raise HTTPException(403, "この機能は、使える人を決めています")
        # the search whose result kadai reads, and the problems whose references sekkei reads
        found = research_of(research, s) if kind == "kadai" and research else ""
        kept = problems_of(kadai, s) if kind == "sekkei" and kadai else []
        name = name.strip().lower()
        if kind == "kadai" and name and not kaihatsu.NAME.fullmatch(name):
            raise HTTPException(422, "名前は英数字とハイフンで、40 字までで書いてください")
        uploads = []
        if mihon == "1":
            # the made-up sample of the repository (hackathon/mihon), for reviewers and first tries
            for dirpath, _, names in os.walk(MIHON):
                for n in sorted(names):
                    with open(os.path.join(dirpath, n), "rb") as f:
                        uploads.append((os.path.relpath(os.path.join(dirpath, n), MIHON), f.read()))
        for f in (files or [])[:MATERIAL_FILES]:
            data = await f.read(MATERIAL_BYTES + 1)
            if len(data) > MATERIAL_BYTES:
                raise HTTPException(422, "資料が大きすぎます(2 MB まで)")
            uploads.append((os.path.basename(f.filename or "資料"), data))
        if kind == "chousa" and not uploads and not note.strip():
            raise HTTPException(422, "何度も頼んでいることを書くか、資料を選んでください")
        if kind == "kadai" and not uploads and not research:
            raise HTTPException(422, "読ませる結果を選ぶか、資料を選んでください")
        if kind == "sekkei" and not uploads:
            raise HTTPException(422, "SKILL.md と参考の資料を選ぶか、見本で試してください")
        uploads += [(f"references/{os.path.basename(path)}", data) for path, data in kept]
        # what the person asks the AI again and again, or the search chosen, needs no materials
        materials = materials_of(uploads) if uploads else ""
        if kind == "kadai" and not name:
            name = skill_name(materials)
        take(s, kind)
        jid = secrets.token_urlsafe(12)
        folder = os.path.join(jobs_dir, jid)
        os.makedirs(folder, exist_ok=True)
        db.run("INSERT INTO jobs VALUES (?, ?, ?, ?, 'waiting', '', '[]', ?, NULL)",
               (jid, s["provider"], s["sub"], kind, time.time()))
        steps = []

        def step(name):
            now = time.time()
            if steps:
                steps[-1]["seconds"] = round(now - steps[-1].pop("at"))
            steps.append({"name": name, "at": now})
            db.run("UPDATE jobs SET status = 'running', steps = ? WHERE id = ?",
                   (json.dumps([{k: v for k, v in x.items() if k != "at"} for x in steps], ensure_ascii=False), jid))

        def work():
            try:
                if kind == "sekkei":
                    kaihatsu.sekkei(materials, note[:2000], folder, ask, paint, step)
                elif kind == "kadai":
                    kaihatsu.kadai(found, materials, note[:2000], name, folder, ask, step)
                else:
                    kaihatsu.chousa(materials, note[:2000], folder, ask, step)
                status, error = "done", ""
            except gemini.GeminiError as e:
                status, error = "error", str(e)
            except (ValueError, KeyError, OSError):
                status, error = "error", "途中で止まりました。もう一度試してください"
            if steps and "at" in steps[-1]:
                steps[-1]["seconds"] = round(time.time() - steps[-1].pop("at"))
            db.run("UPDATE jobs SET status = ?, error = ?, steps = ?, finished = ? WHERE id = ?",
                   (status, error, json.dumps(steps, ensure_ascii=False), time.time(), jid))
        start(work)
        return {"id": jid}

    @app.get("/api/jobs")
    def my_jobs(authorization: str = Header("")):
        s = person(authorization)
        rows = db.all("SELECT id, kind, status, created FROM jobs WHERE provider = ? AND sub = ? ORDER BY created DESC",
                      (s["provider"], s["sub"]))
        return {"jobs": [{"id": r["id"], "kind": r["kind"], "status": r["status"],
                          "created": datetime.datetime.fromtimestamp(r["created"], tz).isoformat(timespec="minutes")}
                         for r in rows]}

    @app.get("/api/jobs/{jid}")
    def job(jid: str, authorization: str = Header("")):
        row = job_row(jid, person(authorization))
        return {"id": jid, "kind": row["kind"], "status": row["status"], "error": row["error"],
                "steps": json.loads(row["steps"] or "[]"), "files": job_files(jid) if row["status"] == "done" else []}

    @app.get("/api/jobs/{jid}/file")
    def job_file(jid: str, path: str, authorization: str = Header("")):
        job_row(jid, person(authorization))
        if path not in job_files(jid):
            raise HTTPException(404, "そのファイルはありません")
        with open(os.path.join(jobs_dir, jid, path), "rb") as f:
            data = f.read()
        kind = "image/png" if path.endswith(".png") else "text/plain; charset=utf-8"
        return Response(data, media_type=kind, headers={"X-Content-Type-Options": "nosniff",
                                                        "Content-Security-Policy": "default-src 'none'"})

    @app.get("/api/jobs/{jid}/zip")
    def job_zip(jid: str, authorization: str = Header("")):
        row = job_row(jid, person(authorization))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for path in job_files(jid):
                z.write(os.path.join(jobs_dir, jid, path), path)
        name = f"aiai-{row['kind']}-{jid[:6]}.zip"
        return Response(buf.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    def dialogue_of(b):
        """The messages of a dialogue, checked: the person's turn last, none too long."""
        msgs = b.get("messages")
        if (not isinstance(msgs, list) or not msgs or not all(isinstance(m, dict) for m in msgs)
                or msgs[-1].get("role") != "user"):
            raise HTTPException(422, "書いたことが届きませんでした")
        contents = [{"role": "model" if m.get("role") == "model" else "user", "text": str(m.get("text", ""))[:MESSAGE_CHARS]}
                    for m in msgs]
        if not contents[-1]["text"].strip():
            raise HTTPException(422, "何か書いてください")
        if sum(len(c["text"]) for c in contents) > DIALOGUE_CHARS:
            raise HTTPException(422, "対話が長くなりました。続きは、ふだん使っている AI で進めてください")
        return contents

    def answer(s, contents, system):
        left = take(s, "chat")
        try:
            text, _ = ask(contents, system=system, search=False)
        except gemini.GeminiError as e:
            raise HTTPException(502, str(e))
        return {"text": text, "left": left}

    @app.post("/api/chat")
    async def chat(request: Request, authorization: str = Header("")):
        s = person(authorization)
        b = await body_of(request)
        name = str(b.get("guide", ""))
        if name not in all_guides:
            raise HTTPException(422, "手引きを選んでください")
        return answer(s, dialogue_of(b), CHAT_RULES.format(guide=all_guides[name][1]))

    @app.post("/api/kaizen")
    async def kaizen(request: Request, authorization: str = Header("")):
        """Step 3 of rireki/SKILL.md: how the apps there are could be better, as a
        dialogue, reading what a research job of this person's found when one is chosen."""
        s = person(authorization)
        b = await body_of(request)
        contents = dialogue_of(b)
        research = ""
        if b.get("job"):
            research = KAIZEN_RESEARCH.format(text=research_of(str(b["job"]), s))
        if "rireki" not in all_guides:
            raise HTTPException(404, "手引きが見つかりません")
        return answer(s, contents, KAIZEN_RULES.format(guide=all_guides["rireki"][1], research=research))

    @app.post("/api/news")
    async def news(request: Request, authorization: str = Header("")):
        s = person(authorization)
        b = await body_of(request)
        tastes = str(b.get("tastes", "")).strip()
        if not tastes:
            raise HTTPException(422, "好みを書いてください")
        if len(tastes) > TASTES_CHARS:
            raise HTTPException(422, f"好みは {TASTES_CHARS} 字までです")
        left = take(s, "news")
        prompt = NEWS_REQUEST.format(today=today(), tastes=tastes)
        try:
            text, sources = ask([{"role": "user", "text": prompt}], system=news_guide, search=True)
        except gemini.GeminiError as e:
            raise HTTPException(502, str(e))
        text = re.sub(r"\A```\w*\n|\n```\s*\Z", "", text.strip())
        if sources:
            text += "\n\n== Gemini が Google 検索で読んだ資料\n\n" + "\n".join(
                f"- {t or urllib.parse.urlsplit(u).netloc}: {u}" for t, u in sources) + "\n"
        return {"adoc": text, "sources": [{"title": t, "url": u} for t, u in sources], "left": left}

    return app
