# SPDX-License-Identifier: AGPL-3.0-or-later
"""Serves the aiai site: the pages built into public/ by make_site.py (the
top page, the skills, the thinking, the news) at /, each skill's ZIP at
/skills/<name>.zip, the site search's AI at /api/sagasu (AIAI_SAGASU=vertex),
the Flet app (app/main.py) at /app/, and, when SOUDAN_MODELS is set, the second-opinion server (soudan/server.py) at /soudan/.

    python site/make_assets.py
    python site/make_site.py
    python site/server.py [--host 127.0.0.1] [--port 8020]

For the second opinion, set its settings as in soudan/README.md, with
BASE_URL ending in /soudan, and AIAI_SOUDAN, AIAI_SOUDAN_API and AIAI_RETURN
as in app/soudan_view.py. site/try.py runs it all with fake sign-in and models.
"""
import importlib.util
import io
import json
import re
import threading
import time
import urllib.error
import urllib.request
import zipfile
import os
import sys

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def skill_zip(name, root=False):
    """A ZIP of one skill: <name>/SKILL.md as Claude and Gemini take it, or
    SKILL.md at the top (root=True) as Microsoft 365 Copilot takes it."""
    if not re.fullmatch(r"[a-z0-9-]+", name):
        return None
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "site")
        if os.path.basename(dirpath) == name and "SKILL.md" in filenames:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(os.path.join(dirpath, "SKILL.md"), "SKILL.md" if root else f"{name}/SKILL.md")
            return buf.getvalue()
    return None


class Sagasu:
    """The AI of the site search: given the words a reader searched, it picks
    the pages that fit from the search index (public/sagasu.json) and writes no
    answer. Gemini 3.8 Flash on Google Cloud (Vertex AI), called by REST with
    the VM's service account, so no key is kept; set AIAI_SAGASU=vertex to use
    it. Elsewhere, and when a limit is reached, it picks nothing and the page
    shows only the pages with the words in them. Searches are not logged here;
    the page records them (kaiseki)."""

    MODEL = "gemini-3.8-flash"
    PER_MINUTE, PER_DAY = 30, 3000
    META = "http://metadata.google.internal/computeMetadata/v1/"

    def __init__(self, index_path, on=os.environ.get("AIAI_SAGASU") == "vertex"):
        self.index_path, self.on = index_path, on
        self.lock = threading.Lock()
        self.cache, self.calls, self.token = {}, [], (None, 0)
        self.index, self.mtime = [], 0

    def entries(self):
        m = os.path.getmtime(self.index_path)
        if m != self.mtime:
            with open(self.index_path, encoding="utf-8") as f:
                self.index, self.mtime = json.load(f), m
            self.cache.clear()
        return self.index

    def meta(self, path):
        req = urllib.request.Request(self.META + path, headers={"Metadata-Flavor": "Google"})
        return urllib.request.urlopen(req, timeout=5).read().decode()

    def bearer(self):
        tok, until = self.token
        if not tok or time.time() > until - 60:
            d = json.loads(self.meta("instance/service-accounts/default/token"))
            tok, until = d["access_token"], time.time() + d["expires_in"]
            self.token = (tok, until)
        return tok

    def allowed(self):
        now = time.time()
        self.calls = [t for t in self.calls if now - t < 86400]
        if len(self.calls) >= self.PER_DAY or sum(now - t < 60 for t in self.calls) >= self.PER_MINUTE:
            return False
        self.calls.append(now)
        return True

    def pick(self, q):
        q = " ".join(str(q).split())[:100]
        if not q or not self.on:
            return []
        with self.lock:
            index = self.entries()
            if q in self.cache:
                return self.cache[q]
            if not self.allowed():
                return []
        pages = "\n".join(f"{i}\t{e['t']}\t{e['h']}\t{e['x']}" for i, e in enumerate(index))
        prompt = (
            "aiai のサイトの中を探す人が、次の言葉で探しました。下の目録(番号、題、見出し、中身の始め)から、"
            "その人が読みたいページを、合う順に 5 つまで選んでください。言葉が同じでなくても、探している"
            "ことに合えば選びます。合う物が無ければ、選びません。答えは JSON だけで、"
            '{"hits": [番号, ...]} の形にしてください。\n\n'
            f"探した言葉: {q}\n\n目録:\n{pages}"
        )
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 2048, "responseMimeType": "application/json"}}
        try:
            project = self.meta("project/project-id")
            url = (f"https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/"
                   f"publishers/google/models/{self.MODEL}:generateContent")
            req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
                "Authorization": f"Bearer {self.bearer()}", "Content-Type": "application/json"})
            res = json.load(urllib.request.urlopen(req, timeout=30))
            parts = res.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            m = re.search(r"\{.*\}", text, re.S)
            hits = [i for i in json.loads(m[0]).get("hits", []) if isinstance(i, int) and 0 <= i < len(index)][:5] if m else []
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            return []
        with self.lock:
            if len(self.cache) > 1000:
                self.cache.clear()
            self.cache[q] = hits
        return hits


def load_soudan():
    """soudan/server.py, under its own name (this file is server.py too)."""
    spec = importlib.util.spec_from_file_location("soudan_server", os.path.join(HERE, "..", "soudan", "server.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def create_app(soudan=None):
    import flet as ft

    sys.path.insert(0, os.path.join(HERE, "app"))
    from main import main as screen

    app = FastAPI(title="aiai", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/skills/{name}.zip")
    def skill(name: str, request: Request):
        data = skill_zip(name, root=request.query_params.get("for") == "m365")
        if data is None:
            raise HTTPException(404, "そのスキルはありません")
        return Response(data, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'})

    sagasu = Sagasu(os.path.join(HERE, "public", "sagasu.json"))

    @app.post("/api/sagasu")
    def search(body: dict = Body(default={})):  # a plain def: FastAPI runs it in a thread
        return {"hits": sagasu.pick(body.get("q", ""))}

    if soudan is not None:
        app.mount("/soudan", soudan)
    app.mount("/app", ft.run(screen, export_asgi_app=True, assets_dir=os.path.join(HERE, "app", "assets")))
    app.mount("/", Pages(directory=os.path.join(HERE, "public"), html=True))
    return app


class Pages(StaticFiles):
    """The built pages; the browser asks again each time, so a changed page or
    style shows at once (it still gets "not modified" when nothing changed)."""

    def file_response(self, *args, **kwargs):
        r = super().file_response(*args, **kwargs)
        r.headers["Cache-Control"] = "no-cache"
        return r


if __name__ == "__main__":
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser(description="aiai のサイトとアプリの画面を出します")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8020)
    a = ap.parse_args()
    soudan = load_soudan().create_app() if os.environ.get("SOUDAN_MODELS") else None
    uvicorn.run(create_app(soudan), host=a.host, port=a.port)
