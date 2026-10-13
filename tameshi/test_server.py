# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tries server.py: sign-in with the fake Google of moushikomi/fake_id.py and
the test account, the dialogue with a guide, the news, and the limits, with
a fake Gemini.

    python tameshi/test_server.py
"""
import os
import sys
import tempfile
import unittest
import urllib.parse

from fastapi.testclient import TestClient

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "moushikomi"))
import fake_id  # noqa: E402
from fake_id import code  # noqa: E402

sys.path.insert(0, HERE)
import server  # noqa: E402

PAGE = "https://aiai.example/tameshi.html"


class FakeGemini:
    def __init__(self):
        self.seen = []

    def __call__(self, contents, system="", search=False):
        self.seen.append((contents, system, search))
        if search:
            return "= aiai ニュース\n\n== 見出し\n:分野: VLM\n\n本文です。", [("example.jp", "https://example.jp/a")]
        return f"答え #{len(self.seen)}", []


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fake, self.env = fake_id.start(self.tmp.name)
        self.env |= {"BASE_URL": "https://aiai.example/tameshi", "RETURN_URLS": PAGE,
                     "DB": os.path.join(self.tmp.name, "t.db"), "TAMESHI_TEST_ID": "shinsa",
                     "TAMESHI_TEST_PASSWORD": "kakunin-no-tame", "TAMESHI_CHAT_PER_DAY": "3",
                     "TAMESHI_NEWS_PER_DAY": "1", "TAMESHI_DAY_LIMIT": "5"}
        self.gemini = FakeGemini()
        self.app = server.create_app(self.env, model=self.gemini)
        self.c = TestClient(self.app, follow_redirects=False)

    def tearDown(self):
        self.fake.shutdown()
        self.app.state.db.db.close()
        self.tmp.cleanup()

    def google(self, sub):
        r = self.c.get("/login/google", params={"next": PAGE})
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(r.headers["location"]).query))
        r = self.c.get("/callback/google", params={"code": code(q["nonce"], sub, ""), "state": q["state"]})
        one = urllib.parse.parse_qs(urllib.parse.urlsplit(r.headers["location"]).query)["code"][0]
        return {"Authorization": "Bearer " + self.c.post("/api/session", json={"code": one}).json()["token"]}

    def log_in_test(self, password="kakunin-no-tame"):
        return self.c.post("/api/test-login", json={"id": "shinsa", "password": password})

    def chat(self, h, text="始めたいです", guide="rireki"):
        return self.c.post("/api/chat", json={"guide": guide, "messages": [{"role": "user", "text": text}]}, headers=h)

    def test_info_lists_the_guides(self):
        info = self.c.get("/api/info").json()
        names = {g["name"] for g in info["guides"]}
        self.assertTrue({"rireki", "news", "kaiseki"} <= names)
        self.assertTrue(info["test_login"])

    def test_nothing_without_signing_in(self):
        self.assertEqual(self.chat({}).status_code, 401)
        self.assertEqual(self.c.post("/api/news", json={"tastes": "VLM"}).status_code, 401)

    def test_the_test_account(self):
        self.assertEqual(self.log_in_test("chigau").status_code, 401)
        r = self.log_in_test()
        self.assertEqual(r.status_code, 200, r.text)
        h = {"Authorization": "Bearer " + r.json()["token"]}
        self.assertEqual(self.c.get("/api/me", headers=h).json()["provider"], "test")

    def test_dialogue_reads_the_guide(self):
        h = self.google("u1")
        r = self.chat(h)
        self.assertEqual(r.status_code, 200, r.text)
        contents, system, search = self.gemini.seen[-1]
        self.assertIn("度々聞いていることを、アプリにする", system)
        self.assertFalse(search)
        self.assertEqual(r.json()["left"], 2)
        self.assertEqual(self.chat(h, guide="nai").status_code, 422)

    def test_news_searches_and_lists_its_sources(self):
        h = self.google("u1")
        r = self.c.post("/api/news", json={"tastes": "= 好み\n\n== 分野\n\n=== VLM\n"}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(self.gemini.seen[-1][2])
        self.assertIn("https://example.jp/a", r.json()["adoc"])
        self.assertEqual(self.c.post("/api/news", json={"tastes": "VLM"}, headers=h).status_code, 429)

    def test_limits_per_person_and_per_day(self):
        h = self.google("u1")
        for _ in range(3):
            self.assertEqual(self.chat(h).status_code, 200)
        self.assertEqual(self.chat(h).status_code, 429)
        g = self.google("u2")
        self.assertEqual(self.chat(g).status_code, 200)
        self.assertEqual(self.c.post("/api/news", json={"tastes": "VLM"}, headers=g).status_code, 200)
        # five calls today in all: the day's limit
        self.assertEqual(self.chat(g).status_code, 429)
        self.assertEqual(len(self.gemini.seen), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
