# SPDX-License-Identifier: AGPL-3.0-or-later
"""Serves the aiai site: the hand-written top page at /, and the Flet app
(app/main.py) at /app/.

    python site/make_assets.py
    python site/server.py [--host 127.0.0.1] [--port 8020]
"""
import os
import sys

from fastapi import FastAPI
from fastapi.responses import FileResponse

HERE = os.path.dirname(os.path.abspath(__file__))


def create_app():
    import flet as ft

    sys.path.insert(0, os.path.join(HERE, "app"))
    from main import main as screen

    app = FastAPI(title="aiai", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/")
    def top():
        return FileResponse(os.path.join(HERE, "index.html"), media_type="text/html; charset=utf-8")

    @app.get("/top.css")
    def css():
        return FileResponse(os.path.join(HERE, "top.css"), media_type="text/css; charset=utf-8")

    app.mount("/app", ft.run(screen, export_asgi_app=True, assets_dir=os.path.join(HERE, "app", "assets")))
    return app


if __name__ == "__main__":
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser(description="aiai のサイトとアプリの画面を出します")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8020)
    a = ap.parse_args()
    uvicorn.run(create_app(), host=a.host, port=a.port)
