# SPDX-License-Identifier: AGPL-3.0-or-later
"""The receiving end of kaiseki (analytics), run on our own server behind Caddy.

Pages send a small record per view and per event (kaiseki.js), with about
what Google Analytics collects: page, title, referrer, campaign (utm_*),
language, time zone, screen, browser, session, and time spent on the page.
A person who accepted the cookie also sends a random ID kept in the site's
own cookie, carried across our own sites by the links between them, so
their visits can be read together; others are counted without an ID. Like
Google Analytics 4, no IP address is stored. When a member signs in, the
member's own server links the ID to the member (POST /v1/link, with a token
only that server holds), so the member's visits stay together across devices
and cleared cookies. A person can read and delete what is kept under their ID.

    KAISEKI_DB=kaiseki.db [KAISEKI_SITES="weather.time-j.net"] \
    KAISEKI_TOKEN=... KAISEKI_LINK_TOKEN=... python server.py --port 8420

Standard library only (Python 3.11+).
"""

import argparse
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

SCHEMA = """
CREATE TABLE IF NOT EXISTS hits (
  ts TEXT NOT NULL,          -- UTC, to the second
  day TEXT NOT NULL,
  site TEXT NOT NULL,        -- host of the page, e.g. weather.time-j.net
  path TEXT NOT NULL,
  event TEXT NOT NULL,       -- view, leave, or a name the page gives
  seconds INTEGER,           -- for leave: seconds the page was in view
  title TEXT NOT NULL,
  referrer TEXT NOT NULL,    -- host only
  utm TEXT NOT NULL,         -- source/medium/campaign/term/content, joined by |
  lang TEXT NOT NULL,
  tz TEXT NOT NULL,
  screen TEXT NOT NULL,      -- e.g. 390x844
  ua TEXT NOT NULL,          -- browser and device, as sent
  sid TEXT,                  -- random ID of the visit (one tab session)
  vid TEXT,                  -- random ID of a person who accepted the cookie, else NULL
  scroll INTEGER,            -- for leave: how far down the page was seen, 0 to 100
  value TEXT                 -- for an event: a short value the page gives (a search word, a missing path)
);
CREATE INDEX IF NOT EXISTS hits_vid ON hits (vid);
CREATE TABLE IF NOT EXISTS links (
  vid TEXT NOT NULL,
  member TEXT NOT NULL,      -- the member's ID in the member system (e.g. PocketBase record id)
  ts TEXT NOT NULL,
  PRIMARY KEY (vid, member)
);
CREATE INDEX IF NOT EXISTS links_member ON links (member);
CREATE INDEX IF NOT EXISTS hits_day ON hits (day, site);
"""

VID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
HOST = re.compile(r"^[a-z0-9.-]{1,253}$")
MAX_BODY = 2048


def now():
    return datetime.now(timezone.utc)


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        # Databases made before scroll and value were added get the columns now
        have = {r[1] for r in self.db.execute("PRAGMA table_info(hits)")}
        for col, kind in (("scroll", "INTEGER"), ("value", "TEXT")):
            if col not in have:
                self.db.execute(f"ALTER TABLE hits ADD COLUMN {col} {kind}")
        self.db.commit()
        self.lock = threading.Lock()

    def add(self, hit):
        t = now()
        cols = ("ts", "day") + FIELDS
        row = (t.isoformat(timespec="seconds"), t.date().isoformat()) + tuple(hit[k] for k in FIELDS)
        with self.lock, self.db:
            self.db.execute(f"INSERT INTO hits ({', '.join(cols)}) VALUES ({', '.join('?' * len(row))})", row)

    def mine(self, vid):
        cols = ("ts",) + FIELDS
        with self.lock:
            rows = self.db.execute(f"SELECT {', '.join(cols)} FROM hits WHERE vid = ? ORDER BY ts", (vid,)).fetchall()
            members = [r[0] for r in self.db.execute("SELECT member FROM links WHERE vid = ?", (vid,))]
        return {"members": members, "hits": [dict(zip(cols, r)) for r in rows]}

    def link(self, vid, member):
        with self.lock, self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO links VALUES (?, ?, ?)", (vid, member, now().isoformat(timespec="seconds"))
            )

    def member(self, member):
        cols = ("ts",) + FIELDS
        with self.lock:
            rows = self.db.execute(
                f"""SELECT {', '.join('h.' + c for c in cols)} FROM hits h JOIN links l ON l.vid = h.vid
                    WHERE l.member = ? ORDER BY h.ts""",
                (member,),
            ).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def forget(self, vid):
        with self.lock, self.db:
            self.db.execute("DELETE FROM links WHERE vid = ?", (vid,))
            return self.db.execute("DELETE FROM hits WHERE vid = ?", (vid,)).rowcount

    def forget_member(self, member):
        """When a member leaves: every ID linked to them, and its records."""
        with self.lock, self.db:
            vids = [r[0] for r in self.db.execute("SELECT vid FROM links WHERE member = ?", (member,))]
            n = 0
            for vid in vids:
                n += self.db.execute("DELETE FROM hits WHERE vid = ?", (vid,)).rowcount
                self.db.execute("DELETE FROM links WHERE vid = ?", (vid,))
            return n

    def report(self, site, start, end):
        with self.lock:
            rows = self.db.execute(
                """SELECT day, path, COUNT(*), COUNT(DISTINCT vid) FROM hits
                   WHERE site = ? AND event = 'view' AND day BETWEEN ? AND ?
                   GROUP BY day, path ORDER BY day, COUNT(*) DESC""",
                (site, start, end),
            ).fetchall()
        return [dict(zip(("day", "path", "views", "people"), r)) for r in rows]


FIELDS = ("site", "path", "event", "seconds", "title", "referrer", "utm", "lang", "tz", "screen", "ua", "sid", "vid",
          "scroll", "value")
EVENT = re.compile(r"^[a-z0-9_]{1,40}$")


def text(d, key, limit):
    return str(d.get(key, ""))[:limit]


def clean_hit(body, sites, origin=""):
    """The record to keep, or None if the body is not one we accept.

    With sites listed, only those sites are kept. With none listed, any HTTPS
    site is kept, but only when the browser's Origin is that same site, so a
    page cannot count itself as another site.
    """
    try:
        d = json.loads(body)
    except ValueError:
        return None
    if not isinstance(d, dict):
        return None
    site, path = text(d, "site", 253).lower(), text(d, "path", 301)
    event = text(d, "event", 41) or "view"
    allowed = site in sites if sites else (HOST.match(site) and origin == f"https://{site}")
    if not allowed or not path.startswith("/") or len(path) > 300 or not EVENT.match(event):
        return None
    ref = text(d, "referrer", 253).lower()
    def number(key, top):
        try:
            n = int(d.get(key)) if event == "leave" else None
        except (TypeError, ValueError):
            return None
        return n if n is None or 0 <= n <= top else None

    seconds, scroll = number("seconds", 86400), number("scroll", 100)
    ids = {k: text(d, k, 36).lower() for k in ("sid", "vid")}
    return {
        "site": site,
        "path": path,
        "event": event,
        "seconds": seconds,
        "scroll": scroll,
        "value": text(d, "value", 100) if event not in ("view", "leave") else "",
        "title": text(d, "title", 200),
        "referrer": ref if HOST.match(ref) and ref != site else "",
        "utm": text(d, "utm", 300),
        "lang": text(d, "lang", 35),
        "tz": text(d, "tz", 64),
        "screen": text(d, "screen", 20) if re.match(r"^\d{1,5}x\d{1,5}$", text(d, "screen", 20)) else "",
        "ua": text(d, "ua", 300),
        "sid": ids["sid"] if VID.match(ids["sid"]) else None,
        "vid": ids["vid"] if VID.match(ids["vid"]) else None,
    }


MEMBER = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def make_handler(store, sites, token, link_token="", extra_origins=()):
    # Pages are served over HTTPS; extra origins (KAISEKI_ORIGINS) are for trying it on one's own PC
    origins = {f"https://{s}" for s in sites} | set(extra_origins)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # no access log: it would hold IP addresses
            pass

        def cors(self):
            origin = self.headers.get("Origin", "")
            if origin in origins or (not sites and origin.startswith("https://")):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")

        def reply(self, status, data=None):
            body = b"" if data is None else json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.cors()
            if data is not None:
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(n) if 0 < n <= MAX_BODY else None

        def has(self, secret):
            return bool(secret) and self.headers.get("Authorization") == f"Bearer {secret}"

        def do_OPTIONS(self):
            self.send_response(204)
            self.cors()
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_POST(self):
            path = urlsplit(self.path).path
            body = self.body()
            if path == "/v1/hit":
                hit = clean_hit(body or b"", sites, self.headers.get("Origin", ""))
                if hit:
                    store.add(hit)
                return self.reply(204)
            try:
                d = json.loads(body or b"{}")
                d = d if isinstance(d, dict) else {}
            except ValueError:
                d = {}
            vid, member = str(d.get("vid", "")).lower(), str(d.get("member", ""))
            if path == "/v1/forget":
                if not VID.match(vid):
                    return self.reply(400, {"error": "vid"})
                return self.reply(200, {"deleted": store.forget(vid)})
            if path in ("/v1/link", "/v1/forget-member"):
                # Only the member system's server holds this token
                if not self.has(link_token):
                    return self.reply(403, {"error": "token"})
                if not MEMBER.match(member) or (path == "/v1/link" and not VID.match(vid)):
                    return self.reply(400, {"error": "member or vid"})
                if path == "/v1/link":
                    store.link(vid, member)
                    return self.reply(204)
                return self.reply(200, {"deleted": store.forget_member(member)})
            self.reply(404, {"error": "not found"})

        def do_GET(self):
            url = urlsplit(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path == "/v1/mine":
                vid = q.get("vid", "").lower()
                if not VID.match(vid):
                    return self.reply(400, {"error": "vid"})
                return self.reply(200, store.mine(vid))
            if url.path in ("/v1/report", "/v1/member"):
                if not self.has(token):
                    return self.reply(403, {"error": "token"})
                if url.path == "/v1/member":
                    m = q.get("member", "")
                    return self.reply(200, {"hits": store.member(m) if MEMBER.match(m) else []})
                today = now().date().isoformat()
                return self.reply(200, {"rows": store.report(q.get("site", ""), q.get("from", today), q.get("to", today))})
            self.reply(404, {"error": "not found"})

    return Handler


def serve(port, db, sites, token, link_token="", host="127.0.0.1", extra_origins=()):
    return ThreadingHTTPServer((host, port), make_handler(Store(db), sites, token, link_token, extra_origins))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8420)
    a = p.parse_args()
    # Empty: any HTTPS site may send. Listed: only those sites
    sites = {s.strip().lower() for s in os.environ.get("KAISEKI_SITES", "").split() if s.strip()}
    serve(
        a.port,
        os.environ.get("KAISEKI_DB", "kaiseki.db"),
        sites,
        os.environ.get("KAISEKI_TOKEN", ""),
        os.environ.get("KAISEKI_LINK_TOKEN", ""),
        extra_origins=os.environ.get("KAISEKI_ORIGINS", "").split(),
    ).serve_forever()
