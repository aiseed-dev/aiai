# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tries what site/server.py and site/app/main.py give the app's page (skipped without Flet and FastAPI):

    python site/test_app.py
"""
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

try:
    import fastapi  # noqa: F401
    import flet_web  # noqa: F401
except ImportError:
    flet_web = None


@unittest.skipUnless(flet_web, "Flet or FastAPI is not installed")
class AppPageTest(unittest.TestCase):
    def test_the_page_is_called_aiai_while_the_app_loads(self):
        spec = importlib.util.spec_from_file_location("site_server", os.path.join(HERE, "server.py"))
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        with tempfile.TemporaryDirectory() as tmp:
            server.brand_index(tmp)
            with open(os.path.join(tmp, "index.html"), encoding="utf-8") as f:
                text = f.read()
        self.assertIn("<title>aiai</title>", text)
        self.assertNotIn("<title>Flet</title>", text)
        self.assertIn("<!-- fletAppConfig -->", text)  # Flet still puts its settings in

    def test_the_images_of_the_loading_screen_are_aiai_s(self):
        for path in ("favicon.png", "icons/loading-animation.png", "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon-192.png"):
            full = os.path.join(HERE, "app", "assets", path)
            self.assertTrue(os.path.exists(full), path)
            with open(full, "rb") as f:
                self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n", path)


@unittest.skipUnless(flet_web, "Flet or FastAPI is not installed")
class SecurityHeadersTest(unittest.TestCase):
    def test_every_answer_carries_the_headers_whichever_app_gives_it(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        spec = importlib.util.spec_from_file_location("site_server2", os.path.join(HERE, "server.py"))
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        os.makedirs(os.path.join(HERE, "public"), exist_ok=True)  # the folder the pages are served from (made by make_site.py)
        inner = FastAPI()

        @inner.get("/api/info")
        def info():
            return {"ok": True}

        @inner.get("/api/file")
        def file():  # an answer that has a header of ours already is not given it twice
            from fastapi.responses import Response
            return Response(b"x", headers={"X-Content-Type-Options": "nosniff"})

        c = TestClient(server.create_app(tameshi=inner), follow_redirects=False)
        for path in ("/katsuyou.html", "/app/", "/tameshi/api/info", "/tameshi/api/file", "/no-such-page"):
            r = c.get(path)
            self.assertEqual(r.headers["strict-transport-security"], "max-age=31536000", path)
            self.assertEqual(r.headers["x-content-type-options"], "nosniff", path)
            self.assertEqual(r.headers["referrer-policy"], "strict-origin-when-cross-origin", path)
            self.assertEqual(r.headers["x-frame-options"], "SAMEORIGIN", path)
            self.assertEqual(r.headers["permissions-policy"], "camera=(), microphone=(), geolocation=()", path)
            self.assertNotIn("includesubdomains", r.headers["strict-transport-security"].lower())
        self.assertEqual(c.get("/tameshi/api/file").headers.get_list("x-content-type-options"), ["nosniff"])
        self.assertEqual(c.get("/tameshi/api/info").json(), {"ok": True})  # the apps still answer as before
        self.assertEqual(c.get("/katsuyou.html").status_code, 301)
        self.assertEqual(c.get("/app/").status_code, 200)


class MainTextTest(unittest.TestCase):
    def test_the_first_tab_and_its_head_say_guide(self):
        with open(os.path.join(HERE, "app", "main.py"), encoding="utf-8") as f:
            main = f.read()
        self.assertIn('label="手引き"', main)
        self.assertIn("手引きを写して、ふだん使っている AI に貼ると", main)
        self.assertIn('("1", "手引きを選ぶ")', main)
        self.assertIn("MAX_WIDTH = 960", main)


if __name__ == "__main__":
    unittest.main(verbosity=2)
