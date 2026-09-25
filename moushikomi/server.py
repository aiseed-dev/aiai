"""Takes requests (a reservation, a booking, an order) from people who sign
in with Apple or Google, keeps only what the item list asks for, and drops
each request once its date has passed.

    python server.py 取り置き.koumoku.adoc [--host 127.0.0.1] [--port 8000]

The item list (.koumoku.adoc, read with tools/todoke.py) says what a request
holds: its items, its tables (.表 / .表の列), and these attributes:

    :期限: 取りに来る日      the date item; the request is dropped after it
    :何日先から: 1           the date may be this many days ahead at the earliest
    :何日先まで: 7           ... and at the latest
    :休みの曜日: 日・月      days the date may not fall on
    :一人あたりの件数: 3      open requests one person may have
    :一つの品物の数まで: 10   the largest 数 in a table row

Settings come from environment variables, so no secret is in the repository:

    BASE_URL              this server as people reach it, e.g. https://yoyaku.example.jp
    RETURN_URLS           where people may be sent back after signing in (prefixes,
                          space separated): the site, and the app's own link
    DB                    the SQLite file (default moushikomi.db next to the item list)
    SHOP_EMAILS           the shop's own sign-in emails (space separated); they see
                          every request
    TIMEZONE              default Asia/Tokyo
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
    APPLE_SERVICES_ID, APPLE_TEAM_ID, APPLE_KEY_ID, APPLE_KEY_FILE (the .p8 key)

Sign-in is OpenID Connect. Both providers are read from their discovery
documents. Apple differs from Google in three ways, all handled here: the
client secret is a JWT this server signs with ES256, the answer comes back
as a POST (form_post), and the name is not asked for (people give a
nickname in the request instead). Only the provider's user id (sub) and the
email it gives are kept.

After signing in, the person is sent back to the return URL with a one-time
code (?code=..., good for one use within a minute). The screen trades it at
POST /api/session for a session token and sends that as
"Authorization: Bearer ...". Codes and tokens are stored hashed.
"""
import datetime
import hashlib
import json
import os
import secrets
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.request
import zoneinfo

import jwt
from fastapi import FastAPI, Form, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import todoke  # noqa: E402

STATE_SECONDS = 600
CODE_SECONDS = 60
SESSION_DAYS = 30
WEEKDAYS = "月火水木金土日"

# ---- the item list ----------------------------------------------------------


class Koumoku:
    """What one kind of request holds, from its .koumoku.adoc."""

    def __init__(self, path):
        doc = todoke.read(path)
        self.title = doc["title"] or ""
        self.attrs = doc["attrs"]
        self.items = todoke.items(doc)
        self.tables = todoke.table_defs(doc)
        self.due = self.attrs.get("期限", "")
        if self.due not in [i["名前"] for i in self.items]:
            raise SystemExit(f":期限: には、書き方が日付の項目の名前を書きます({self.due or '無し'})")

    def num(self, name, default):
        v = self.attrs.get(name, "")
        return int(v) if v.isdigit() else default

    def describe(self):
        return {"title": self.title, "items": self.items, "tables": self.tables,
                "rules": {k: self.attrs[k] for k in self.attrs}}

    def problems(self, values, tables, today):
        """What is wrong with a request, as a list of sentences."""
        out = []
        for it in self.items:
            v = str(values.get(it["名前"], "")).strip()
            if not v:
                if it["必須"] == "必須":
                    out.append(f"{it['名前']}を書きます")
                continue
            if len(v) > 200:
                out.append(f"{it['名前']}は 200 字までです")
            elif (msg := todoke.check(it["書き方"], v)):
                out.append(f"{it['名前']}: {msg}")
        for name, d in self.tables.items():
            rows = tables.get(name) or []
            if not rows and d.get("必須") == "必須":
                out.append(f"{name}を 1 つ以上選びます")
            if len(rows) > 50:
                out.append(f"{name}は 50 行までです")
                continue
            for n, row in enumerate(rows, 1):
                for c in d["列"]:
                    v = str(row.get(c["列"], "")).strip()
                    if not v:
                        if c["必須"] == "必須":
                            out.append(f"{name} {n} 行目: {c['列']}を書きます")
                        continue
                    if (msg := todoke.check(c["書き方"], v)):
                        out.append(f"{name} {n} 行目: {c['列']}: {msg}")
                    elif c["書き方"] == "数":
                        most = self.num("一つの品物の数まで", 99)
                        if not v.isdigit() or not 1 <= int(v) <= most:
                            out.append(f"{name} {n} 行目: {c['列']}は 1 から {most} までです")
        due = str(values.get(self.due, "")).strip()
        if due and not todoke.check("日付", due):
            d = datetime.date.fromisoformat(due)
            first = today + datetime.timedelta(days=self.num("何日先から", 0))
            last = today + datetime.timedelta(days=self.num("何日先まで", 365))
            closed = [w for w in self.attrs.get("休みの曜日", "").split("・") if w]
            if not first <= d <= last:
                out.append(f"{self.due}は {first} から {last} までです")
            elif WEEKDAYS[d.weekday()] in closed:
                out.append(f"{self.due}は休みの日です({'・'.join(closed)}曜日)")
        return out


# ---- sign-in providers --------------------------------------------------------


class Provider:
    def __init__(self, name, issuer, client_id, scope, form_post):
        self.name, self.issuer, self.client_id = name, issuer.rstrip("/"), client_id
        self.scope, self.form_post = scope, form_post
        self._conf = None
        self._jwks = None

    def conf(self):
        if self._conf is None:
            with urllib.request.urlopen(self.issuer + "/.well-known/openid-configuration", timeout=10) as r:
                self._conf = json.load(r)
            if self._conf.get("issuer", "").rstrip("/") != self.issuer:
                raise RuntimeError(f"{self.name}: discovery issuer does not match")
            self._jwks = jwt.PyJWKClient(self._conf["jwks_uri"])
        return self._conf

    def authorize_url(self, redirect_uri, state, nonce):
        q = {"response_type": "code", "client_id": self.client_id, "redirect_uri": redirect_uri,
             "scope": self.scope, "state": state, "nonce": nonce}
        if self.form_post:
            q["response_mode"] = "form_post"
        return self.conf()["authorization_endpoint"] + "?" + urllib.parse.urlencode(q)

    def client_secret(self):
        raise NotImplementedError

    def exchange(self, code, redirect_uri):
        body = urllib.parse.urlencode({
            "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
            "client_id": self.client_id, "client_secret": self.client_secret()}).encode()
        req = urllib.request.Request(self.conf()["token_endpoint"], data=body,
                                     headers={"Content-Type": "application/x-www-form-urlencoded",
                                              "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)["id_token"]

    def verify(self, id_token, nonce):
        """The claims of an id_token, after checking signature, iss, aud, exp and nonce."""
        self.conf()
        key = self._jwks.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(id_token, key.key, algorithms=["RS256"], audience=self.client_id,
                            issuer=self.issuer, options={"require": ["exp", "iat", "sub", "iss", "aud"]})
        if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise jwt.InvalidTokenError("nonce does not match")
        return claims


class Google(Provider):
    def __init__(self, env):
        super().__init__("google", env.get("GOOGLE_ISSUER", "https://accounts.google.com"),
                         env["GOOGLE_CLIENT_ID"], "openid email", form_post=False)
        self.secret = env["GOOGLE_CLIENT_SECRET"]

    def client_secret(self):
        return self.secret


class Apple(Provider):
    def __init__(self, env):
        super().__init__("apple", env.get("APPLE_ISSUER", "https://appleid.apple.com"),
                         env["APPLE_SERVICES_ID"], "email", form_post=True)
        self.team, self.key_id = env["APPLE_TEAM_ID"], env["APPLE_KEY_ID"]
        with open(env["APPLE_KEY_FILE"], encoding="utf-8") as f:
            self.key = f.read()

    def client_secret(self):
        # Apple asks for a JWT signed with the .p8 key (ES256); a short one is made per exchange
        now = int(time.time())
        return jwt.encode({"iss": self.team, "iat": now, "exp": now + 300, "aud": self.issuer,
                           "sub": self.client_id}, self.key, algorithm="ES256",
                          headers={"kid": self.key_id})


def providers_from(env):
    out = {}
    if env.get("GOOGLE_CLIENT_ID"):
        out["google"] = Google(env)
    if env.get("APPLE_SERVICES_ID"):
        out["apple"] = Apple(env)
    return out


# ---- storage ------------------------------------------------------------------


class Store:
    """One SQLite connection shared by the app's threads, one statement at a time."""

    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.db.executescript(SCHEMA)

    def one(self, sql, args=()):
        with self.lock:
            return self.db.execute(sql, args).fetchone()

    def all(self, sql, args=()):
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    def run(self, sql, args=()):
        with self.lock:
            return self.db.execute(sql, args).rowcount


SCHEMA = """
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS states (state TEXT PRIMARY KEY, provider TEXT, nonce TEXT,
            next TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS codes (code TEXT PRIMARY KEY, provider TEXT, sub TEXT,
            email TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, provider TEXT, sub TEXT,
            email TEXT, expires REAL);
        CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, provider TEXT, sub TEXT,
            email TEXT, due TEXT, body TEXT, created TEXT);
"""


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


# ---- the web app -----------------------------------------------------------------


def create_app(koumoku, env=None, providers=None):
    env = dict(os.environ if env is None else env)
    form = Koumoku(koumoku)
    base = env["BASE_URL"].rstrip("/")
    returns = env.get("RETURN_URLS", "").split()
    shop = {e.lower() for e in env.get("SHOP_EMAILS", "").split()}
    tz = zoneinfo.ZoneInfo(env.get("TIMEZONE", "Asia/Tokyo"))
    db = Store(env.get("DB") or os.path.join(os.path.dirname(os.path.abspath(koumoku)), "moushikomi.db"))
    provs = providers if providers is not None else providers_from(env)
    last_purge = [0.0]

    def today():
        return datetime.datetime.now(tz).date()

    def purge(force=False):
        # Drop what is no longer needed: past-due requests, old sign-in states, ended sessions
        now = time.time()
        if not force and now - last_purge[0] < 60:
            return
        last_purge[0] = now
        db.run("DELETE FROM requests WHERE due < ?", (today().isoformat(),))
        db.run("DELETE FROM states WHERE created < ?", (now - STATE_SECONDS,))
        db.run("DELETE FROM codes WHERE created < ?", (now - CODE_SECONDS,))
        db.run("DELETE FROM sessions WHERE expires < ?", (now,))

    def allowed_return(url):
        return any(url.startswith(p) for p in returns)

    def person(authorization):
        purge()
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "サインインしてください")
        row = db.one("SELECT * FROM sessions WHERE token = ? AND expires > ?",
                     (digest(authorization[7:]), time.time()))
        if not row:
            raise HTTPException(401, "サインインしてください")
        return row

    app = FastAPI(title=form.title, docs_url=None, redoc_url=None, openapi_url=None)
    origins = sorted({"{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(u)) for u in returns
                      if u.startswith("https://") or u.startswith("http://")})
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["Authorization", "Content-Type"])

    @app.get("/login/{name}")
    def login(name: str, next: str):
        p = provs.get(name)
        if not p:
            raise HTTPException(404, "この方法ではサインインできません")
        if not allowed_return(next):
            raise HTTPException(400, "戻り先が登録されていません")
        purge()
        # The state is kept on the server, not in a cookie: Apple's answer is a cross-site POST
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        db.run("INSERT INTO states VALUES (?, ?, ?, ?, ?)", (state, name, nonce, next, time.time()))
        return RedirectResponse(p.authorize_url(f"{base}/callback/{name}", state, nonce), 303)

    def finish(name, code, state):
        # A state is used once: it is deleted as it is read
        row = db.one("DELETE FROM states WHERE state = ? AND provider = ? AND created > ? RETURNING *",
                     (state or "", name, time.time() - STATE_SECONDS))
        if not row or not code:
            raise HTTPException(400, "サインインをやり直してください")
        p = provs[name]
        try:
            claims = p.verify(p.exchange(code, f"{base}/callback/{name}"), row["nonce"])
        except Exception:
            raise HTTPException(400, "サインインを確かめられませんでした")
        verified = claims.get("email_verified") in (True, "true")
        email = claims.get("email", "") if verified else ""
        # The screen gets a one-time code, not the session token, in its URL
        one = secrets.token_urlsafe(32)
        db.run("INSERT INTO codes VALUES (?, ?, ?, ?, ?)", (digest(one), name, claims["sub"], email, time.time()))
        sep = "&" if "?" in row["next"] else "?"
        return RedirectResponse(row["next"] + sep + urllib.parse.urlencode({"code": one}), 303)

    @app.get("/callback/google")
    def callback_google(code: str = "", state: str = ""):
        return finish("google", code, state)

    @app.post("/callback/apple")
    def callback_apple(code: str = Form(""), state: str = Form("")):
        return finish("apple", code, state)

    @app.post("/api/session")
    async def session(request: Request):
        try:
            one = str((await request.json()).get("code", ""))
        except (ValueError, AttributeError):
            one = ""
        row = db.one("DELETE FROM codes WHERE code = ? AND created > ? RETURNING *",
                     (digest(one), time.time() - CODE_SECONDS))
        if not row:
            raise HTTPException(400, "サインインをやり直してください")
        token = secrets.token_urlsafe(32)
        db.run("INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
               (digest(token), row["provider"], row["sub"], row["email"], time.time() + SESSION_DAYS * 86400))
        return {"token": token}

    @app.get("/api/form")
    def get_form():
        return form.describe() | {"providers": sorted(provs)}

    @app.get("/api/me")
    def me(authorization: str = Header("")):
        s = person(authorization)
        return {"provider": s["provider"], "email": s["email"], "shop": s["email"].lower() in shop}

    def as_dict(r, with_email=False):
        d = {"id": r["id"], "due": r["due"], "created": r["created"], **json.loads(r["body"])}
        if with_email:
            d["email"] = r["email"]
        return d

    @app.get("/api/requests")
    def mine(authorization: str = Header("")):
        s = person(authorization)
        rows = db.all("SELECT * FROM requests WHERE provider = ? AND sub = ? ORDER BY due",
                      (s["provider"], s["sub"]))
        return [as_dict(r) for r in rows]

    @app.post("/api/requests")
    async def add(request: Request, authorization: str = Header("")):
        s = person(authorization)
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "中身を読めませんでした")
        values = body.get("values") if isinstance(body.get("values"), dict) else {}
        tables = body.get("tables") if isinstance(body.get("tables"), dict) else {}
        # Keep only what the item list names; anything else is not stored
        values = {i["名前"]: str(values.get(i["名前"], "")).strip() for i in form.items}
        tables = {n: [{c["列"]: str(r.get(c["列"], "")).strip() for c in d["列"]}
                      for r in (tables.get(n) or []) if isinstance(r, dict)]
                  for n, d in form.tables.items()}
        problems = form.problems(values, tables, today())
        count = db.one("SELECT COUNT(*) FROM requests WHERE provider = ? AND sub = ?",
                       (s["provider"], s["sub"]))[0]
        if count >= form.num("一人あたりの件数", 10):
            problems.append(f"一人あたり {form.num('一人あたりの件数', 10)} 件までです")
        if problems:
            raise HTTPException(422, problems)
        rid = secrets.token_urlsafe(12)
        db.run("INSERT INTO requests VALUES (?, ?, ?, ?, ?, ?, ?)",
               (rid, s["provider"], s["sub"], s["email"], values[form.due],
                json.dumps({"values": values, "tables": tables}, ensure_ascii=False),
                datetime.datetime.now(tz).isoformat(timespec="seconds")))
        return {"id": rid}

    @app.delete("/api/requests/{rid}")
    def cancel(rid: str, authorization: str = Header("")):
        s = person(authorization)
        n = db.run("DELETE FROM requests WHERE id = ? AND provider = ? AND sub = ?",
                   (rid, s["provider"], s["sub"]))
        if not n:
            raise HTTPException(404, "見つかりません")
        return {"ok": True}

    @app.get("/api/shop/requests")
    def shop_list(authorization: str = Header("")):
        s = person(authorization)
        if not s["email"] or s["email"].lower() not in shop:
            raise HTTPException(403, "店の人だけが見られます")
        rows = db.all("SELECT * FROM requests ORDER BY due, created")
        return [as_dict(r, with_email=True) for r in rows]

    @app.post("/api/logout")
    def logout(authorization: str = Header("")):
        s = person(authorization)
        db.run("DELETE FROM sessions WHERE token = ?", (s["token"],))
        return {"ok": True}

    app.state.db, app.state.form, app.state.purge = db, form, purge
    return app


def mount_screen(app, base):
    """Serve the Flet screen (app/main.py) at /app/, next to the API."""
    import flet as ft

    os.environ.setdefault("MOUSHIKOMI_SERVER", base)
    os.environ.setdefault("MOUSHIKOMI_RETURN", base + "/app/")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))
    from main import main as screen

    app.mount("/app", ft.run(screen, export_asgi_app=True))


if __name__ == "__main__":
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser(description="Apple か Google でサインインした人から申し込みを受けます")
    ap.add_argument("koumoku", help="申し込みの項目(.koumoku.adoc)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-screen", action="store_true", help="画面(/app/)を出さず、API だけにします")
    a = ap.parse_args()
    web = create_app(a.koumoku)
    if not a.no_screen:
        mount_screen(web, os.environ["BASE_URL"].rstrip("/"))
    uvicorn.run(web, host=a.host, port=a.port)
