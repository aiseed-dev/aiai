# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tries server.py: sign-in with the fake Google of moushikomi/fake_id.py and
the test account, the dialogue with a guide, the news, the design and research
jobs from uploaded materials, and the limits, with a fake Gemini.

    python tameshi/test_server.py
"""
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.parse
import zipfile

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

    def __call__(self, contents, system="", search=False, schema=None, **more):
        self.seen.append((contents, system, search))
        text = contents[-1]["text"]
        if schema and "screens" in schema["properties"]:
            return json.dumps({"screens": [{"id": "screen-01", "name": "課題一覧", "parts": ["課題一覧", "課題を登録"]}]}), []
        if schema:
            return json.dumps({"report": "== 確かめ\n\n合っています。", "manual": "= 利用者マニュアル\n\nimage::images/screen-01.png[課題一覧]"}), []
        if search and "名前 | 公式の URL" in text:
            return "High Climb | https://highclimb.example | 資料に出てくる", []
        if search and "今を、Google 検索で" in text:
            return "== High Climb\n\n課題と記録のアプリです。", [("highclimb.example", "https://highclimb.example/")]
        if search:
            return "= aiai ニュース\n\n== 見出し\n:分野: VLM\n\n本文です。", [("example.jp", "https://example.jp/a")]
        if "設計書 docs/design.adoc" in text:
            return "= 設計書\n\n== 画面\n\n課題一覧: 課題を登録", []
        return f"答え #{len(self.seen)}", []


def materials_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("app/SKILL.md", "---\nname: app\n---\n\n# 架空のアプリ\n\n課題と記録のアプリを作る。")
        z.writestr("app/references/a.adoc", "= 架空の調べ")
        z.writestr("app/run.sh", "echo 読まない")
        z.writestr("../outside.md", "読まない")
    return buf.getvalue()


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fake, self.env = fake_id.start(self.tmp.name)
        self.env |= {"BASE_URL": "https://aiai.example/tameshi", "RETURN_URLS": PAGE,
                     "DB": os.path.join(self.tmp.name, "t.db"), "TAMESHI_TEST_ID": "shinsa",
                     "TAMESHI_TEST_PASSWORD": "kakunin-no-tame", "TAMESHI_CHAT_PER_DAY": "3",
                     "TAMESHI_NEWS_PER_DAY": "1", "TAMESHI_DAY_LIMIT": "5"}
        self.gemini = FakeGemini()
        self.drawn = []
        self.app = server.create_app(self.env, model=self.gemini, draw=lambda p: self.drawn.append(p) or b"\x89PNG fake",
                                     run=lambda fn: fn())
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


    def job(self, h, kind, files=None, note=""):
        files = files or [("files", ("mirai.zip", materials_zip(), "application/zip"))]
        return self.c.post("/api/jobs", data={"kind": kind, "note": note}, files=files, headers=h)

    def test_design_job_writes_the_documents_and_the_pictures(self):
        h = {"Authorization": "Bearer " + self.log_in_test().json()["token"]}
        r = self.job(h, "sekkei")
        self.assertEqual(r.status_code, 200, r.text)
        j = self.c.get(f"/api/jobs/{r.json()['id']}", headers=h).json()
        self.assertEqual(j["status"], "done", j)
        self.assertEqual(j["files"], ["docs/design.adoc", "docs/images/screen-01.png", "docs/kakunin.adoc", "docs/manual.adoc"])
        self.assertIn("課題一覧", self.drawn[0])
        # what Gemini read: the Markdown and AsciiDoc of the ZIP, not the script, not a path outside it
        sent = self.gemini.seen[0][0][-1]["text"]
        self.assertIn("架空のアプリ", sent)
        self.assertNotIn("echo", sent)
        self.assertNotIn("outside", sent)
        pic = self.c.get(f"/api/jobs/{r.json()['id']}/file", params={"path": "docs/images/screen-01.png"}, headers=h)
        self.assertEqual(pic.headers["content-type"], "image/png")
        self.assertEqual(self.c.get(f"/api/jobs/{r.json()['id']}/file", params={"path": "../../t.db"}, headers=h).status_code, 404)
        z = zipfile.ZipFile(io.BytesIO(self.c.get(f"/api/jobs/{r.json()['id']}/zip", headers=h).content))
        self.assertIn("docs/manual.adoc", z.namelist())
        # one a day
        self.assertEqual(self.job(h, "sekkei").status_code, 429)

    def test_research_job_lists_its_sources(self):
        h = self.google("u1")
        r = self.job(h, "chousa", files=[("files", ("SKILL.md", "# 架空のアプリ".encode(), "text/markdown"))])
        self.assertEqual(r.status_code, 200, r.text)
        j = self.c.get(f"/api/jobs/{r.json()['id']}", headers=h).json()
        self.assertEqual(j["status"], "done", j)
        text = self.c.get(f"/api/jobs/{r.json()['id']}/file", params={"path": j["files"][0]}, headers=h).text
        self.assertIn("== High Climb", text)
        self.assertIn("https://highclimb.example/", text)

    def test_jobs_are_only_for_the_owner_and_the_allowed(self):
        h = self.google("u1")
        jid = self.job(h, "chousa", files=[("files", ("SKILL.md", "# 架空".encode(), "text/markdown"))]).json()["id"]
        other = self.google("u2")
        self.assertEqual(self.c.get(f"/api/jobs/{jid}", headers=other).status_code, 404)
        self.assertEqual(self.job(h, "sekkei", files=[("files", ("a.sh", b"x", "text/plain"))]).status_code, 422)
        self.app.state.db.db.close()
        self.app = server.create_app(self.env | {"TAMESHI_KAIHATSU_EMAILS": "maker@example.jp"}, model=self.gemini,
                                     run=lambda fn: fn())
        self.c = TestClient(self.app, follow_redirects=False)
        self.assertEqual(self.job(self.google("u3"), "chousa").status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
