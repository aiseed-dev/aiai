# SPDX-License-Identifier: AGPL-3.0-or-later
"""A second opinion from another company's AI, for people who make their
job-change advice, resume or business plan with their own AI.

    python server.py [--host 127.0.0.1] [--port 8010]

It is for recruited people only. Research staff make invitation codes
(POST /api/research/invites) and hand one to each person who answered the
call; each code can be used by one person. People sign in with Apple or
Google (the sign-in of moushikomi/server.py), enter their code, agree to the
research use (同意.md), and then keep coming back: each time
they paste a draft with the identifying details taken out, pick one or two
models, and get each model's opinion. They can also note what happened
(applied, interviewed, filed the opening notice). Their record grows in
date order; it is the research material, and they can delete it at any time.

What is checked is written in 観点/*.md (共通.md, plus one file per kind);
the file name is the kind. Settings come from environment variables:

    BASE_URL, RETURN_URLS, GOOGLE_*, APPLE_*    as in moushikomi/server.py
    DB                    the SQLite file (default soudan.db next to this file)
    SOUDAN_MODELS         the models offered, space separated vendor:model,
                          e.g. "anthropic:claude-opus-5-5"
    ANTHROPIC_API_KEY     for the anthropic models
    SOUDAN_PER_DAY        consultations (one per model) one person may make a day (default 10)
    SOUDAN_DAY_LIMIT      model calls everyone together may make a day (default 300); a
                          report calls the model once per item of rireki/SKILL.md, then once more
    RESEARCH_EMAILS       sign-in emails of the research staff, who make invitation
                          codes and read the summary (space separated)
    TIMEZONE              default Asia/Tokyo

Drafts are refused, before any model sees them, when they hold what looks
like an email address, a phone number, a postal code or a 12-digit number
(the shape of the individual number).
"""
import datetime
import hashlib
import importlib.util
import os
import re
import secrets
import threading
import time
import unicodedata
import urllib.parse
import zoneinfo

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

HERE = os.path.dirname(os.path.abspath(__file__))

# The sign-in is the checked one of moushikomi/server.py, loaded under its own name
_spec = importlib.util.spec_from_file_location(
    "moushikomi_server", os.path.join(HERE, "..", "moushikomi", "server.py"))
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)

DRAFT_CHARS = 12000
EVENT_CHARS = 1000
HISTORY = 3  # earlier consultations of the same kind and model given to the model
MATERIAL_CHARS = 80000  # what the app sends for a report: masked messages the person wrote
INVITE_LETTERS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L, so they can be read aloud


def new_invite():
    raw = "".join(secrets.choice(INVITE_LETTERS) for _ in range(8))
    return raw[:4] + "-" + raw[4:]


def invite_key(code):
    """The stored form of an invitation code: typed loosely, kept hashed."""
    plain = re.sub(r"[^A-Z0-9]", "", unicodedata.normalize("NFKC", str(code)).upper())
    return hashlib.sha256(plain.encode()).hexdigest()

SCHEMA = ms.SIGN_IN_SCHEMA + """
        CREATE TABLE IF NOT EXISTS people (provider TEXT, sub TEXT, email TEXT, agreed TEXT,
            agreed_at TEXT, invite TEXT, PRIMARY KEY (provider, sub));
        CREATE TABLE IF NOT EXISTS invites (code TEXT PRIMARY KEY, note TEXT, created TEXT,
            used_at TEXT);
        CREATE TABLE IF NOT EXISTS consults (id TEXT PRIMARY KEY, provider TEXT, sub TEXT,
            kind TEXT, model TEXT, draft TEXT, answer TEXT, in_tokens INTEGER,
            out_tokens INTEGER, rating INTEGER, created TEXT);
        CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, provider TEXT, sub TEXT,
            text TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, provider TEXT, sub TEXT, model TEXT,
            sources TEXT, report TEXT, calls INTEGER, in_tokens INTEGER, out_tokens INTEGER,
            rating INTEGER, created TEXT, status TEXT, done INTEGER, steps INTEGER, error TEXT);
"""

# ---- identifying details --------------------------------------------------------

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
POSTAL = re.compile(r"(?<![\d-])\d{3}-\d{4}(?![\d-])|〒\s*\d{7}(?!\d)")
PHONE = re.compile(r"(?<![\d-])\+?\d[\d-]{8,15}\d(?![\d-])")
NUMBER12 = re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)")


def identifiers(text):
    """The kinds of identifying details the text seems to hold, by name."""
    t = unicodedata.normalize("NFKC", text)
    found = []
    if EMAIL.search(t):
        found.append("メールアドレス")
    if POSTAL.search(t):
        found.append("郵便番号")
    for m in PHONE.finditer(t):
        digits = re.sub(r"\D", "", m.group())
        if (digits.startswith("0") and len(digits) in (10, 11)) or digits.startswith("81"):
            found.append("電話番号")
            break
    if NUMBER12.search(t):
        found.append("12 桁の数字(個人番号の形)")
    return found


# ---- what is checked ----------------------------------------------------------------


def read_kanten(folder):
    """{kind: (title, text)} from 観点/*.md, and the common part from 共通.md."""
    common, kinds = "", {}
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".md"):
            continue
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            text = f.read().strip()
        if name == "共通.md":
            common = text
        else:
            first = text.splitlines()[0].lstrip("# ").strip()
            kinds[name[:-3]] = (first, text)
    return common, kinds


# ---- the report: items from rireki/SKILL.md --------------------------------------------


def read_rireki(path):
    """(rules, items) from rireki/SKILL.md: its 守ること and 項目 sections.

    Each item is a dict: number, group, name, what (its one line), the lines under
    it by their label (読む物, 見る所, 書き方), and from 読む物: dialogue (whether it
    reads the dialogue), events (the person's events) and uses (the numbers of the
    items whose results it reads)."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    rules = re.search(r"## 守ること\n(.*?)\n## ", text, re.S).group(1).strip()
    part = re.search(r"## 項目\n(.*?)\n## ", text, re.S).group(1)
    items = []
    for block in re.split(r"\n### ", "\n" + part)[1:]:
        group, _, body = block.partition("\n")
        for m in re.finditer(r"^(\d+)\. \*\*(.+?)\*\*: (.+)\n((?:[ ]+- .+\n?)*)", body, re.M):
            item = {"number": int(m[1]), "group": group.strip(), "name": m[2], "what": m[3].strip()}
            item |= dict(re.findall(r"^[ ]+- (.+?): (.+)$", m[4], re.M))
            reads = item.get("読む物", "")
            uses = set()
            for a, b in re.findall(r"(\d+)(?:〜(\d+))?", reads.split("の結果")[0] if "の結果" in reads else ""):
                uses |= set(range(int(a), int(b or a) + 1))
            item |= {"dialogue": "対話" in reads, "events": "出来事" in reads, "uses": sorted(uses)}
            items.append(item)
    return rules, items


# ---- models ----------------------------------------------------------------------------


class ModelError(Exception):
    """The model gave no usable answer; the message is shown to the person."""


class Anthropic:
    vendor = "anthropic"

    def __init__(self, model, env):
        import anthropic

        self.model = model
        self.client = anthropic.Anthropic(api_key=env["ANTHROPIC_API_KEY"])

    def answer(self, system, messages):
        r = self.client.messages.create(model=self.model, max_tokens=16000, system=system,
                                        messages=messages)
        if r.stop_reason == "refusal":
            raise ModelError("このモデルは、この相談に答えませんでした")
        text = "".join(b.text for b in r.content if b.type == "text").strip()
        if not text:
            raise ModelError("このモデルから答えが返りませんでした")
        return text, r.usage.input_tokens, r.usage.output_tokens


VENDORS = {"anthropic": Anthropic}


def models_from(env):
    out = {}
    for spec in env.get("SOUDAN_MODELS", "").split():
        vendor, _, model = spec.partition(":")
        if vendor not in VENDORS:
            raise RuntimeError(f"{vendor}: この会社のモデルは、まだ使えません")
        out[spec] = VENDORS[vendor](model, env)
    return out


# ---- the web app ------------------------------------------------------------------------


def create_app(env=None, providers=None, models=None):
    env = dict(os.environ if env is None else env)
    base = env["BASE_URL"].rstrip("/")
    returns = env.get("RETURN_URLS", "").split()
    research = {e.lower() for e in env.get("RESEARCH_EMAILS", "").split()}
    per_day = int(env.get("SOUDAN_PER_DAY", "10"))
    day_limit = int(env.get("SOUDAN_DAY_LIMIT", "300"))
    tz = zoneinfo.ZoneInfo(env.get("TIMEZONE", "Asia/Tokyo"))
    db = ms.Store(env.get("DB") or os.path.join(HERE, "soudan.db"), SCHEMA)
    provs = providers if providers is not None else ms.providers_from(env)
    mods = models if models is not None else models_from(env)
    common, kinds = read_kanten(os.path.join(HERE, "観点"))
    rireki_rules, rireki_items = read_rireki(os.path.join(HERE, "..", "rireki", "SKILL.md"))
    with open(os.path.join(HERE, "同意.md"), encoding="utf-8") as f:
        consent = f.read().strip()
    consent_version = hashlib.sha256(consent.encode()).hexdigest()[:12]
    last_purge = [0.0]

    def now():
        return datetime.datetime.now(tz)

    def purge(force=False):
        t = time.time()
        if not force and t - last_purge[0] < 60:
            return
        last_purge[0] = t
        ms.purge_sign_in(db, t)

    app = FastAPI(title="aiai セカンドオピニオン", docs_url=None, redoc_url=None, openapi_url=None)
    origins = sorted({"{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(u)) for u in returns
                      if u.startswith("https://") or u.startswith("http://")})
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["Authorization", "Content-Type"])
    person = ms.sign_in(app, db, provs, base, returns, purge)

    def joined(s):
        """(invited, agreed to the current text) of a signed-in person."""
        row = db.one("SELECT agreed, invite FROM people WHERE provider = ? AND sub = ?", (s["provider"], s["sub"]))
        return (bool(row) and bool(row["invite"]), bool(row) and row["agreed"] == consent_version)

    def member(authorization):
        s = person(authorization)
        invited, ok = joined(s)
        if not invited:
            raise HTTPException(403, "セカンドオピニオンは、募集に応じた人だけが使えます。招待の番号が要ります")
        if not ok:
            raise HTTPException(403, "使い始める前に、記録を残すことと研究に使うことへの同意が要ります")
        return s

    def staff(authorization):
        s = person(authorization)
        if not s["email"] or s["email"].lower() not in research:
            raise HTTPException(403, "研究の係の人だけが使えます")
        return s

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
        return {"kinds": [{"name": k, "title": v[0]} for k, v in kinds.items()],
                "models": sorted(mods), "consent": consent, "consent_version": consent_version,
                "per_day": per_day, "providers": sorted(provs)}

    @app.get("/api/me")
    def me(authorization: str = Header("")):
        s = person(authorization)
        invited, ok = joined(s)
        return {"provider": s["provider"], "email": s["email"], "invited": invited, "agreed": ok,
                "research": bool(s["email"]) and s["email"].lower() in research}

    @app.post("/api/agree")
    async def agree(request: Request, authorization: str = Header("")):
        s = person(authorization)
        b = await body_of(request)
        if b.get("version") != consent_version:
            raise HTTPException(409, "同意の文が変わりました。読み直してください")
        invited, _ = joined(s)
        key = None
        if not invited:
            # A code is used once: it is marked as it is taken
            key = invite_key(b.get("code", ""))
            if not db.run("UPDATE invites SET used_at = ? WHERE code = ? AND used_at IS NULL",
                          (now().isoformat(timespec="microseconds"), key)):
                raise HTTPException(403, "招待の番号が違うか、もう使われています")
        db.run("INSERT INTO people VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (provider, sub) DO UPDATE SET "
               "email = excluded.email, agreed = excluded.agreed, agreed_at = excluded.agreed_at, "
               "invite = COALESCE(people.invite, excluded.invite)",
               (s["provider"], s["sub"], s["email"], consent_version, now().isoformat(timespec="microseconds"), key))
        return {"ok": True}

    @app.get("/api/record")
    def record(authorization: str = Header("")):
        s = member(authorization)
        key = (s["provider"], s["sub"])
        consults = [{"type": "consult", "id": r["id"], "kind": r["kind"], "model": r["model"],
                     "draft": r["draft"], "answer": r["answer"], "rating": r["rating"],
                     "created": r["created"]}
                    for r in db.all("SELECT * FROM consults WHERE provider = ? AND sub = ?", key)]
        events = [{"type": "event", "id": r["id"], "text": r["text"], "created": r["created"]}
                  for r in db.all("SELECT * FROM events WHERE provider = ? AND sub = ?", key)]
        reports = [report_of(r) | {"type": "report", "sources": r["sources"], "rating": r["rating"],
                                   "created": r["created"]}
                   for r in db.all("SELECT * FROM reports WHERE provider = ? AND sub = ?", key)]
        return sorted(consults + events + reports, key=lambda x: x["created"])

    def messages_for(s, kind, model, draft):
        key = (s["provider"], s["sub"])
        earlier = db.all("SELECT draft, answer FROM consults WHERE provider = ? AND sub = ? AND kind = ? "
                         "AND model = ? ORDER BY created DESC LIMIT ?", (*key, kind, model, HISTORY))
        out = []
        for r in reversed(earlier):
            out += [{"role": "user", "content": r["draft"]}, {"role": "assistant", "content": r["answer"]}]
        events = db.all("SELECT text, created FROM events WHERE provider = ? AND sub = ? ORDER BY created",
                        key)
        lines = [f"- {r['created'][:10]} {r['text']}" for r in events]
        head = ("これまでの出来事(本人が書いた物):\n" + "\n".join(lines) + "\n\n") if lines else ""
        out.append({"role": "user", "content": head + "今回の下書き:\n" + draft})
        return out

    def today(key):
        day = now().date().isoformat()
        return ("provider = ? AND sub = ? AND ", (*key, day)) if key else ("", (day,))

    def consults_today(key):
        who, args = today(key)
        return db.one(f"SELECT COUNT(*) FROM consults WHERE {who}created >= ?", args)[0]

    def calls_today():
        """Everyone's model calls today: one per consultation, and each report's steps."""
        who, args = today(None)
        reports = db.one(f"SELECT COALESCE(SUM(calls), 0) FROM reports WHERE {who}created >= ?", args)[0]
        return consults_today(None) + reports

    @app.post("/api/consults")
    async def consult(request: Request, authorization: str = Header("")):
        s = member(authorization)
        b = await body_of(request)
        kind, draft = str(b.get("kind", "")), str(b.get("draft", "")).strip()
        chosen = b.get("models") if isinstance(b.get("models"), list) else []
        problems = []
        if kind not in kinds:
            problems.append("相談の種類を選んでください")
        if not draft:
            problems.append("下書きを貼ってください")
        elif len(draft) > DRAFT_CHARS:
            problems.append(f"下書きは {DRAFT_CHARS} 字までです")
        if not chosen or len(chosen) > 2 or len(set(chosen)) != len(chosen) or any(m not in mods for m in chosen):
            problems.append("モデルを 1 つか 2 つ選んでください")
        found = identifiers(draft)
        if found:
            problems.append("次の物が入っているようです。除いてから送ってください: " + "、".join(found))
        if problems:
            raise HTTPException(422, problems)
        key = (s["provider"], s["sub"])
        if consults_today(key) + len(chosen) > per_day:
            raise HTTPException(429, f"相談は、一人 1 日 {per_day} 回までです")
        if calls_today() + len(chosen) > day_limit:
            raise HTTPException(429, "今日の相談の受け付けは終わりました。明日またどうぞ")
        system = common + "\n\n" + kinds[kind][1]
        out = []
        for m in chosen:
            try:
                text, tin, tout = mods[m].answer(system, messages_for(s, kind, m, draft))
            except ModelError as e:
                out.append({"model": m, "error": str(e)})
                continue
            except Exception:
                out.append({"model": m, "error": "このモデルに、いまはつながりませんでした"})
                continue
            cid = secrets.token_urlsafe(12)
            db.run("INSERT INTO consults VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (cid, *key, kind, m, draft, text, tin, tout, None, now().isoformat(timespec="microseconds")))
            out.append({"model": m, "id": cid, "answer": text})
        return out

    def report_steps(material, events):
        """The agent's steps: one per item of rireki/SKILL.md, in order, then a summary.

        A model gives better answers to small, exact requests, so each step asks
        for one item with that item's lines (読む物, 見る所, 書き方), and hands it only
        what its 読む物 names: the dialogue, the results of earlier items, the
        person's events. Each step is a function of the texts done so far that
        returns the prompt; assemble(done) makes the report."""
        system = ("あなたは、aiai のアプリの報告書のエージェントです。次の決まりを守ります。\n\n" + rireki_rules +
                  "\n\n資料は、本人と AI の対話を、日付付きで並べた物です。「AI:」は AI の答えの初め、"
                  "「あなた:」は本人がそれを受けて書いたことです。AI の答えを受けて本人がどう返したか"
                  "(問い直した、断った、確かめた、直した)から読み取ります。「AI:」の [ ] の中は、答えた AI の"
                  "モデルの名前です。過去の AI には十分に答えられなかった物もあるので、AI の答えが足りなかった"
                  "場面での本人の問い直しや断りを、本人の短所と取り違えません。足りなかったやり取りは、改善の提案の"
                  "材料にします。識別情報に見える物は伏せてあります。日本語の、主語と述語のそろった「です・ます」の"
                  "説明文で書きます。頼まれた 1 つの項目だけを、見出しを付けずに書きます。")
        lines = [f"- {r['created'][:10]} {r['text']}" for r in events]
        happened = "\n".join(lines) or "(まだありません)"
        by_number = {it["number"]: n for n, it in enumerate(rireki_items)}

        def step(item):
            def prompt(done):
                parts = []
                if item["dialogue"]:
                    parts.append(f"<資料>\n{material}\n</資料>")
                for u in item["uses"]:
                    if by_number.get(u, len(done)) < len(done):
                        used = rireki_items[by_number[u]]
                        parts.append(f"<{u}. {used['name']}>\n{done[by_number[u]]}\n</{u}. {used['name']}>")
                if item["events"]:
                    parts.append(f"<本人が書いた出来事>\n{happened}\n</本人が書いた出来事>")
                ask = [f"項目「{item['number']}. {item['name']}」を書いてください。", f"この項目: {item['what']}"]
                ask += [f"{k}: {item[k]}" for k in ("見る所", "書き方") if k in item]
                ask.append("根拠は「〇月ごろの、〇〇についてのやり取り」のように書きます。根拠の無いことは書きません。")
                return "\n\n".join(parts + ["\n".join(ask)])
            return prompt

        def sections(done):
            return "\n\n".join(f"## {it['number']}. {it['name']}\n\n{text.strip()}" for it, text in zip(rireki_items, done))

        summary = (lambda done: f"<報告書>\n{sections(done)}\n</報告書>\n\nこの報告書の初めに置く要約を、3 行で書いてください。"
                   "1 行目は長所と得意な分野、2 行目は AI の使い方で改善できること、3 行目はいちばん先にする行動です。"
                   "報告書に無いことは書きません。")

        def assemble(done):
            """The report from what is done so far: the summary comes last, so a report
            that stopped early has the items it got and no summary."""
            items = done[:len(rireki_items)]
            head = f"## 要約\n\n{done[-1].strip()}\n\n" if len(done) > len(rireki_items) else ""
            return f"# 報告書\n\n{head}{sections(items)}\n" if items else ""

        return system, [step(it) for it in rireki_items] + [summary], assemble

    def report_of(r):
        return {"id": r["id"], "model": r["model"], "status": r["status"], "done": r["done"],
                "steps": r["steps"], "report": r["report"], "error": r["error"]}

    def run_report(rid, model, system, steps, assemble):
        """Runs the agent's steps in a thread, keeping each finished item in the row, so
        the app can show how far it is and a report that stops early keeps its items.
        A connection failure is tried once more; a refusal stops the report."""
        done, tin, tout = [], 0, 0
        error = None
        for step in steps:
            prompt = step(done)
            for attempt in (1, 2):
                error = None
                try:
                    text, i, o = mods[model].answer(system, [{"role": "user", "content": prompt}])
                    break
                except ModelError as e:
                    error = str(e)
                    break
                except Exception:
                    error = "このモデルに、いまはつながりませんでした"
            if error:
                break
            done.append(text)
            tin, tout = tin + i, tout + o
            db.run("UPDATE reports SET report = ?, done = ?, in_tokens = ?, out_tokens = ? WHERE id = ?",
                   (assemble(done), len(done), tin, tout, rid))
        db.run("UPDATE reports SET status = ?, calls = ?, error = ? WHERE id = ?",
               ("failed" if error else "done", len(done), error, rid))

    @app.post("/api/reports")
    async def report(request: Request, authorization: str = Header("")):
        s = member(authorization)
        b = await body_of(request)
        model, material = str(b.get("model", "")), str(b.get("material", "")).strip()
        sources = str(b.get("sources", ""))[:500]
        problems = []
        if model not in mods:
            problems.append("モデルを 1 つ選んでください")
        if not material:
            problems.append("読み込んだ記録がありません")
        elif len(material) > MATERIAL_CHARS:
            problems.append(f"記録は {MATERIAL_CHARS} 字までです")
        found = identifiers(material)
        if found:
            problems.append("次の物が入っているようです。伏せてから送ってください: " + "、".join(found))
        if problems:
            raise HTTPException(422, problems)
        key = (s["provider"], s["sub"])
        system, steps, assemble = report_steps(material, db.all(
            "SELECT text, created FROM events WHERE provider = ? AND sub = ? ORDER BY created", key))
        if calls_today() + len(steps) > day_limit:
            raise HTTPException(429, "今日の受け付けは終わりました。明日またどうぞ")
        if db.one("SELECT COUNT(*) FROM reports WHERE provider = ? AND sub = ? AND status = 'running'", key)[0]:
            raise HTTPException(409, ["前の報告書を、まだ作っています"])
        rid = secrets.token_urlsafe(12)
        # The steps are counted as calls from the start, so the day's limit holds while it runs
        db.run("INSERT INTO reports VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (rid, *key, model, sources, "", len(steps), 0, 0, None,
                now().isoformat(timespec="microseconds"), "running", 0, len(steps), None))
        threading.Thread(target=run_report, args=(rid, model, system, steps, assemble), daemon=True).start()
        return report_of(db.one("SELECT * FROM reports WHERE id = ?", (rid,)))

    @app.get("/api/reports/{rid}")
    def report_progress(rid: str, authorization: str = Header("")):
        s = member(authorization)
        r = db.one("SELECT * FROM reports WHERE id = ? AND provider = ? AND sub = ?", (rid, s["provider"], s["sub"]))
        if not r:
            raise HTTPException(404, ["その報告書はありません"])
        return report_of(r)

    @app.post("/api/consults/{cid}/rating")
    async def rate(cid: str, request: Request, authorization: str = Header("")):
        s = member(authorization)
        rating = (await body_of(request)).get("rating")
        if rating not in (1, 2, 3, 4, 5):
            raise HTTPException(422, ["1 から 5 で付けてください"])
        if not db.run("UPDATE consults SET rating = ? WHERE id = ? AND provider = ? AND sub = ?",
                      (rating, cid, s["provider"], s["sub"])):
            raise HTTPException(404, "見つかりません")
        return {"ok": True}

    @app.post("/api/events")
    async def add_event(request: Request, authorization: str = Header("")):
        s = member(authorization)
        text = str((await body_of(request)).get("text", "")).strip()
        problems = []
        if not text:
            problems.append("出来事を書いてください")
        elif len(text) > EVENT_CHARS:
            problems.append(f"出来事は {EVENT_CHARS} 字までです")
        found = identifiers(text)
        if found:
            problems.append("次の物が入っているようです。除いてから送ってください: " + "、".join(found))
        if problems:
            raise HTTPException(422, problems)
        eid = secrets.token_urlsafe(12)
        db.run("INSERT INTO events VALUES (?, ?, ?, ?, ?)",
               (eid, s["provider"], s["sub"], text, now().isoformat(timespec="microseconds")))
        return {"id": eid}

    @app.delete("/api/record")
    def forget(authorization: str = Header("")):
        s = person(authorization)
        key = (s["provider"], s["sub"])
        for table in ("consults", "events", "reports", "people", "sessions"):
            db.run(f"DELETE FROM {table} WHERE provider = ? AND sub = ?", key)
        return {"ok": True}

    def make_invites(count, note=""):
        codes = [new_invite() for _ in range(count)]
        for c in codes:
            db.run("INSERT INTO invites VALUES (?, ?, ?, NULL)", (invite_key(c), note, now().isoformat(timespec="microseconds")))
        return codes

    @app.post("/api/research/invites")
    async def invites(request: Request, authorization: str = Header("")):
        staff(authorization)
        b = await body_of(request)
        count = b.get("count")
        if not isinstance(count, int) or not 1 <= count <= 100:
            raise HTTPException(422, ["1 から 100 までの数を選んでください"])
        return {"codes": make_invites(count, str(b.get("note", ""))[:200])}

    @app.get("/api/research/summary")
    def summary(authorization: str = Header("")):
        staff(authorization)
        by_model = [dict(r) for r in db.all(
            "SELECT model, kind, COUNT(*) AS consults, AVG(in_tokens) AS in_tokens, "
            "AVG(out_tokens) AS out_tokens, COUNT(rating) AS rated, AVG(rating) AS rating "
            "FROM consults GROUP BY model, kind ORDER BY model, kind")]
        return {"invites": db.one("SELECT COUNT(*) FROM invites")[0],
                "invites_used": db.one("SELECT COUNT(*) FROM invites WHERE used_at IS NOT NULL")[0],
                "people": db.one("SELECT COUNT(*) FROM people WHERE agreed = ?", (consent_version,))[0],
                "events": db.one("SELECT COUNT(*) FROM events")[0], "by_model": by_model,
                "reports": [dict(r) for r in db.all(
                    "SELECT model, COUNT(*) AS reports, AVG(in_tokens) AS in_tokens, AVG(out_tokens) AS out_tokens "
                    "FROM reports GROUP BY model ORDER BY model")]}

    app.state.db, app.state.purge, app.state.make_invites = db, purge, make_invites
    return app


if __name__ == "__main__":
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser(description="ほかの会社の AI のセカンドオピニオンを返します")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8010)
    a = ap.parse_args()
    uvicorn.run(create_app(), host=a.host, port=a.port)
