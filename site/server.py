# SPDX-License-Identifier: AGPL-3.0-or-later
"""Serves the aiai site: the pages built into public/ by make_site.py (the
top page, the skills, the thinking, the news) at /, each skill's ZIP at
/skills/<name>.zip, the Flet app (app/main.py) at /app/, and, when
SOUDAN_MODELS is set, the second-opinion server (soudan/server.py) at /soudan/.

    python site/make_assets.py
    python site/make_site.py
    python site/server.py [--host 127.0.0.1] [--port 8020]

For the second opinion, set its settings as in soudan/README.md, with
BASE_URL ending in /soudan, and AIAI_SOUDAN, AIAI_SOUDAN_API and AIAI_RETURN
as in app/soudan_view.py. site/try.py runs it all with fake sign-in and models.
"""
import importlib.util
import io
import re
import zipfile
import os
import sys

from fastapi import FastAPI, HTTPException, Request
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
