# SPDX-License-Identifier: AGPL-3.0-or-later
"""Serves the aiai site: the hand-written top page at /, the Flet app
(app/main.py) at /app/, and, when SOUDAN_MODELS is set, the second-opinion
server (soudan/server.py) at /soudan/.

    python site/make_assets.py
    python site/server.py [--host 127.0.0.1] [--port 8020]

For the second opinion, set its settings as in soudan/README.md, with
BASE_URL ending in /soudan, and AIAI_SOUDAN, AIAI_SOUDAN_API and AIAI_RETURN
as in app/soudan_view.py. site/try.py runs it all with fake sign-in and models.
"""
import importlib.util
import os
import sys

from fastapi import FastAPI
from fastapi.responses import FileResponse

HERE = os.path.dirname(os.path.abspath(__file__))


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

    # The browser asks again each time, so a changed page or style shows at once
    fresh = {"Cache-Control": "no-cache"}

    @app.get("/")
    def top():
        return FileResponse(os.path.join(HERE, "index.html"), media_type="text/html; charset=utf-8", headers=fresh)

    @app.get("/top.css")
    def css():
        return FileResponse(os.path.join(HERE, "top.css"), media_type="text/css; charset=utf-8", headers=fresh)

    if soudan is not None:
        app.mount("/soudan", soudan)
    app.mount("/app", ft.run(screen, export_asgi_app=True, assets_dir=os.path.join(HERE, "app", "assets")))
    return app


if __name__ == "__main__":
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser(description="aiai のサイトとアプリの画面を出します")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8020)
    a = ap.parse_args()
    soudan = load_soudan().create_app() if os.environ.get("SOUDAN_MODELS") else None
    uvicorn.run(create_app(soudan), host=a.host, port=a.port)
