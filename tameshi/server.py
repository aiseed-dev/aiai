# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tries aiai on the site with Gemini, for people who sign in: a dialogue
with Gemini that has read one of the guides, and today's news made by
Gemini with Google Search from the person's own tastes (as news/SKILL.md
says). Gemini runs on Google Cloud (site/gemini.py). It is mounted at
/tameshi by site/server.py; the screen is /tameshi.html.

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
    TIMEZONE                default Asia/Tokyo
"""
import datetime
import importlib.util
import os
import re
import secrets
import sys
import time
import urllib.parse
import zoneinfo

from fastapi import FastAPI, Header, HTTPException, Request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# The sign-in is the checked one of moushikomi/server.py, loaded under its own name
_spec = importlib.util.spec_from_file_location("moushikomi_server", os.path.join(ROOT, "moushikomi", "server.py"))
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)

sys.path.insert(0, os.path.join(ROOT, "site"))
import gemini  # noqa: E402

MESSAGE_CHARS = 4000     # one message in the dialogue
DIALOGUE_CHARS = 30000   # the whole dialogue sent at once
TASTES_CHARS = 4000      # the person's tastes for the news
FAILED_LOGINS = 50       # wrong test-account passwords accepted a day, before the test login closes

SCHEMA = ms.SIGN_IN_SCHEMA + """
        CREATE TABLE IF NOT EXISTS uses (day TEXT, provider TEXT, sub TEXT, kind TEXT, n INTEGER,
            PRIMARY KEY (day, provider, sub, kind));
"""

CHAT_RULES = """あなたは、aiai のサイト(https://aiai.aiseed.dev/)の上で、下の手引きを読んで、この人と対話します。
手引きの「守ること」と「手順」のとおりに進めます。1 回の答えは短くし、この人に 1 つずつ聞きながら進めます。
この人が持っていない道具(ファイルを読む、コマンドを動かす)が要る所は、この人が自分の AI か PC でする形にします。
サイトは、この対話を記録しません。続きは、この人がふだん使っている AI で、同じ手引きを読ませて進められます。

<手引き>
{guide}
</手引き>"""

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


def create_app(env=None, providers=None, model=None):
    """model(contents, system=..., search=...) -> (text, sources); Gemini unless given."""
    env = dict(os.environ if env is None else env)
    base = env["BASE_URL"].rstrip("/")
    returns = env.get("RETURN_URLS", "").split()
    tz = zoneinfo.ZoneInfo(env.get("TIMEZONE", "Asia/Tokyo"))
    db = ms.Store(env.get("DB") or os.path.join(HERE, "tameshi.db"), SCHEMA)
    provs = providers if providers is not None else ms.providers_from(env)
    ask = model or gemini.generate
    test_id, test_password = env.get("TAMESHI_TEST_ID", ""), env.get("TAMESHI_TEST_PASSWORD", "")
    per_day = {"chat": int(env.get("TAMESHI_CHAT_PER_DAY", "30")), "news": int(env.get("TAMESHI_NEWS_PER_DAY", "3"))}
    day_limit = int(env.get("TAMESHI_DAY_LIMIT", "600"))
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
        if everyone >= day_limit:
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

    @app.get("/api/me")
    def me(authorization: str = Header("")):
        s = person(authorization)
        return {"provider": s["provider"], "email": s["email"],
                "left": {k: per_day[k] - used(s["provider"], s["sub"], k) for k in per_day}}

    @app.post("/api/chat")
    async def chat(request: Request, authorization: str = Header("")):
        s = person(authorization)
        b = await body_of(request)
        name = str(b.get("guide", ""))
        if name not in all_guides:
            raise HTTPException(422, "手引きを選んでください")
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
        left = take(s, "chat")
        try:
            text, _ = ask(contents, system=CHAT_RULES.format(guide=all_guides[name][1]), search=False)
        except gemini.GeminiError as e:
            raise HTTPException(502, str(e))
        return {"text": text, "left": left}

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
