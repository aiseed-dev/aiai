# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tries server.py: sign-in with the fake Google of moushikomi/fake_id.py and
the test account, the dialogue with a guide, the news, the design, research,
problem-gathering and test-procedure jobs from uploaded materials, and the limits,
with a fake Gemini.

    python tameshi/test_server.py
"""
import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.parse
import zipfile

from fastapi.testclient import TestClient

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "moushikomi"))
import fake_id  # noqa: E402
from fake_id import code  # noqa: E402

sys.path.insert(0, HERE)
import kaihatsu  # noqa: E402
import server  # noqa: E402

PAGE = "https://aiai.example/app/tameshi"


class FakeGemini:
    def __init__(self):
        self.seen = []
        self.fail = False  # Gemini that stops a job

    def __call__(self, contents, system="", search=False, schema=None, **more):
        self.seen.append((contents, system, search))
        if self.fail:
            raise server.gemini.GeminiError("Gemini が答えませんでした")
        text = contents[-1]["text"]
        if schema and "screens" in schema["properties"]:
            return json.dumps({"screens": [{"id": "screen-01", "name": "課題一覧", "parts": ["課題一覧", "課題を登録"]}]}), []
        if schema and "test" in schema["properties"]:
            return json.dumps({"report": "== 確かめ\n\n手順にそろっています。", "test": "= テストの手順\n\n== マニュアルの操作の確かめ\n\n直した版。"}), []
        if schema:
            return json.dumps({"report": "== 確かめ\n\n合っています。", "manual": "= 利用者マニュアル\n\nimage::images/screen-01.png[課題一覧]"}), []
        if search and "名前が出ていなければ" in text:  # kadai: which apps
            return "High Climb | https://highclimb.example", []
        if search and "の課題を、Google 検索で" in text:  # kadai: the problems of one app (the same page twice)
            return ("== High Climb\n\n=== 利用者にとっての問題点\n\n. 取り消しは電話だけ。\n\n=== 運営の作りの問題点\n\n. 預かる情報が多い。",
                    [("highclimb.example", "https://highclimb.example/"), ("利用規約", "https://highclimb.example/")])
        if not search and "作るアプリで防ぐことを、adoc の" in text:  # kadai: what to avoid
            return "== 作るアプリで防ぐこと\n\n. 取り消しを、アプリからできるようにする。", []
        if search and "名前 | 公式の URL" in text:
            return "High Climb | https://highclimb.example | 資料に出てくる", []
        if search and "今を、Google 検索で" in text:
            return "== High Climb\n\n課題と記録のアプリです。", [("highclimb.example", "https://highclimb.example/")]
        if search:
            return "= aiai ニュース\n\n== 見出し\n:分野: VLM\n\n本文です。", [("example.jp", "https://example.jp/a")]
        if "テストの手順 docs/test.adoc" in text:
            return "= テストの手順\n\n== マニュアルの操作の確かめ\n\n下書き。", []
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
                     "TAMESHI_NEWS_PER_DAY": "1", "TAMESHI_DAY_LIMIT": "5",
                     "TAMESHI_APPROVED": os.path.join(self.tmp.name, "approved.txt")}
        self.gemini = FakeGemini()
        self.drawn = []
        self.app = server.create_app(self.env, model=self.gemini, draw=lambda p: self.drawn.append(p) or b"\x89PNG fake",
                                     run=lambda fn: fn())
        self.c = TestClient(self.app, follow_redirects=False)

    def tearDown(self):
        self.fake.shutdown()
        self.app.state.db.db.close()
        self.tmp.cleanup()

    def approve(self, *lines):
        """Adds lines to the file of the people the owner approves; the server reads it again each time."""
        with open(self.env["TAMESHI_APPROVED"], "a", encoding="utf-8") as f:
            f.write("".join(line + "\n" for line in lines))

    def google(self, sub, approved=True):
        """Signs in as a person with Google (the verified address is <sub>@example.jp); approved unless said not."""
        email = f"{sub}@example.jp"
        if approved:
            self.approve(f"google:{email}")
        r = self.c.get("/login/google", params={"next": PAGE})
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(r.headers["location"]).query))
        r = self.c.get("/callback/google", params={"code": code(q["nonce"], sub, email, email_verified=True), "state": q["state"]})
        one = urllib.parse.parse_qs(urllib.parse.urlsplit(r.headers["location"]).query)["code"][0]
        return {"Authorization": "Bearer " + self.c.post("/api/session", json={"code": one}).json()["token"]}

    def log_in_test(self, password="kakunin-no-tame"):
        return self.c.post("/api/login", json={"id": "shinsa", "password": password})

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
        # the test account is shared by reviewers, so it has no limit of one person's (a person with Google has: one a day)
        self.assertEqual(self.job(h, "sekkei").status_code, 200)
        g = self.google("u43")
        self.assertEqual(self.job(g, "sekkei").status_code, 200)
        self.assertEqual(self.job(g, "sekkei").status_code, 429)

    def test_research_job_lists_its_sources(self):
        h = self.google("u1")
        r = self.job(h, "chousa", files=[("files", ("SKILL.md", "# 架空のアプリ".encode(), "text/markdown"))])
        self.assertEqual(r.status_code, 200, r.text)
        j = self.c.get(f"/api/jobs/{r.json()['id']}", headers=h).json()
        self.assertEqual(j["status"], "done", j)
        text = self.c.get(f"/api/jobs/{r.json()['id']}/file", params={"path": j["files"][0]}, headers=h).text
        self.assertIn("== High Climb", text)
        self.assertIn("https://highclimb.example/", text)

    def test_searching_from_what_one_asks_again_and_again(self):
        h = self.google("u5")
        r = self.c.post("/api/jobs", data={"kind": "chousa", "note": "毎週、売上の表の集計を頼んでいる"}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        j = self.c.get(f"/api/jobs/{r.json()['id']}", headers=h).json()
        self.assertEqual(j["status"], "done", j)
        first, second = self.gemini.seen[0][0][-1]["text"], self.gemini.seen[1][0][-1]["text"]
        self.assertIn("売上の表の集計", first)
        self.assertNotIn("<資料>", first)
        self.assertIn("(== High Climb)", second)
        # the design and manual still need materials
        self.assertEqual(self.c.post("/api/jobs", data={"kind": "sekkei", "note": "集計"}, headers=h).status_code, 422)

    def test_thinking_how_to_improve_reads_the_research(self):
        h = self.google("u6")
        jid = self.job(h, "chousa", files=[("files", ("SKILL.md", "# 架空のアプリ".encode(), "text/markdown"))]).json()["id"]
        say = {"role": "user", "text": "先週との比べが無いのが不満です"}
        r = self.c.post("/api/kaizen", json={"job": jid, "messages": [say]}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        contents, system, search = self.gemini.seen[-1]
        self.assertIn("== High Climb", system)
        self.assertIn("手順の 3", system)
        self.assertIn("先週との比べ", contents[-1]["text"])
        self.assertFalse(search)
        # another person's research is not theirs to read
        self.assertEqual(self.c.post("/api/kaizen", json={"job": jid, "messages": [say]},
                                     headers=self.google("u7")).status_code, 404)
        # without research it is a dialogue on step 3 alone
        r = self.c.post("/api/kaizen", json={"messages": [say]}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("<調べた結果>", self.gemini.seen[-1][1])

    def test_the_sample_needs_no_upload(self):
        h = self.google("u9")
        r = self.c.post("/api/jobs", data={"kind": "sekkei", "mihon": "1"}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("こむぎ堂", self.gemini.seen[0][0][-1]["text"])

    def assertRefused(self, r, status, detail):
        self.assertEqual((r.status_code, r.json().get("detail")), (status, detail), r.text)

    def restart(self, env=None, **more):
        """The server again on the same files, with other settings or jobs that wait."""
        self.app.state.db.db.close()
        self.app = server.create_app(self.env | (env or {}), model=self.gemini, **more)
        self.c = TestClient(self.app, follow_redirects=False)

    def design_of(self, h):
        """A finished design job of this person, from the sample, for the test procedure to read."""
        r = self.c.post("/api/jobs", data={"kind": "sekkei", "mihon": "1"}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.c.get(f"/api/jobs/{r.json()['id']}", headers=h).json()["status"], "done")
        return r.json()["id"]

    def search_of(self, h):
        """A finished research job of this person, for the problems job to read."""
        r = self.job(h, "chousa", files=[("files", ("SKILL.md", "# 架空のアプリ".encode(), "text/markdown"))])
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    def test_gathering_the_problems_of_the_apps_that_were_found(self):
        h = self.google("u10")
        found = self.search_of(h)
        before = len(self.gemini.seen)
        r = self.c.post("/api/jobs", data={"kind": "kadai", "research": found, "name": "Toriooki",
                                           "note": "取り消しがアプリでできない"}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        j = self.c.get(f"/api/jobs/{r.json()['id']}", headers=h).json()
        self.assertEqual(j["status"], "done", j)
        # the name, lowercased, names the reference of step 5
        self.assertEqual(j["files"], ["references/toriooki-analysis.adoc"])
        self.assertEqual([x["name"] for x in j["steps"]],
                         ["課題を調べるアプリを決める", "課題を調べる: High Climb", "防ぐことをまとめる"])
        text = self.c.get(f"/api/jobs/{r.json()['id']}/file", params={"path": j["files"][0]}, headers=h).text
        self.assertTrue(text.startswith("= toriooki の今あるアプリの課題\n"), text)
        for want in ("== High Climb", "=== 利用者にとっての問題点", "=== 運営の作りの問題点", "== 作るアプリで防ぐこと",
                     "== 読んだ資料", "https://highclimb.example/"):
            self.assertIn(want, text)
        self.assertEqual(text.count("* https://highclimb.example/["), 1)  # a page read twice is listed once
        # the first request has what the search found and the person's own words; Google Search is on for the
        # first two steps and off for the last
        asks = self.gemini.seen[before:]
        self.assertEqual([a[2] for a in asks], [True, True, False])
        self.assertIn("課題と記録のアプリです。", asks[0][0][-1]["text"])
        self.assertIn("取り消しがアプリでできない", asks[0][0][-1]["text"])
        self.assertEqual(asks[0][1], kaihatsu.RULES)
        # the app's name is in the request, not the place for it
        self.assertIn("「High Climb」(https://highclimb.example)の課題を", asks[1][0][-1]["text"])
        self.assertIn("(== High Climb)", asks[1][0][-1]["text"])
        self.assertIn("=== 利用者にとっての問題点", asks[2][0][-1]["text"])
        for contents, _, _ in asks:
            self.assertNotRegex(contents[-1]["text"], r"\{(who|name|url|app)\}")
        # it is a job in the list, and in its ZIP
        self.assertEqual([x["kind"] for x in self.c.get("/api/jobs", headers=h).json()["jobs"]], ["kadai", "chousa"])
        z = zipfile.ZipFile(io.BytesIO(self.c.get(f"/api/jobs/{r.json()['id']}/zip", headers=h).content))
        self.assertEqual(z.namelist(), ["references/toriooki-analysis.adoc"])

    def test_gathering_the_problems_from_the_sample_or_from_materials(self):
        h = self.google("u11")
        before = len(self.gemini.seen)
        r = self.c.post("/api/jobs", data={"kind": "kadai", "mihon": "1"}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        # no name given: the name: of the SKILL.md in the sample
        self.assertEqual(self.c.get(f"/api/jobs/{r.json()['id']}", headers=h).json()["files"],
                         ["references/toriooki-analysis.adoc"])
        first = self.gemini.seen[before][0][-1]["text"]
        self.assertIn("こむぎ堂", first)
        self.assertNotIn("<調べた結果>", first)
        # materials alone, with a SKILL.md that names the app
        r = self.job(h, "kadai", files=[("files", ("mirai.zip", materials_zip(), "application/zip"))])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.c.get(f"/api/jobs/{r.json()['id']}", headers=h).json()["files"], ["references/app-analysis.adoc"])

    def test_gathering_the_problems_needs_something_to_read_and_a_usable_name(self):
        h = self.google("u12")
        # no search chosen, no materials, no sample: the note alone is not enough
        r = self.c.post("/api/jobs", data={"kind": "kadai", "note": "不満です"}, headers=h)
        self.assertRefused(r, 422, "読ませる結果を選ぶか、資料を選んでください")
        # the name is letters, digits and hyphens, 40 at most (capitals are lowered)
        for bad in ("to_riooki", "とりおき", "a" * 41, "../x", "to riooki"):
            with self.subTest(name=bad):
                r = self.c.post("/api/jobs", data={"kind": "kadai", "mihon": "1", "name": bad}, headers=h)
                self.assertRefused(r, 422, "名前は英数字とハイフンで、40 字までで書いてください")
        r = self.c.post("/api/jobs", data={"kind": "kadai", "mihon": "1", "name": "A" * 40}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.c.get(f"/api/jobs/{r.json()['id']}", headers=h).json()["files"],
                         ["references/" + "a" * 40 + "-analysis.adoc"])
        # none of the refusals used up a try: the one job did
        self.assertEqual(self.c.get("/api/me", headers=h).json()["left"]["kadai"], 1)

    def test_only_a_finished_search_of_ones_own_can_be_read(self):
        h = self.google("u13")
        mine = self.search_of(h)
        sent = {"kind": "kadai", "mihon": "1", "research": mine}
        # another person's search is no search at all
        self.assertEqual(self.c.post("/api/jobs", data=sent, headers=self.google("u14")).status_code, 404)
        self.assertEqual(self.c.post("/api/jobs", data=sent | {"research": "nai"}, headers=h).status_code, 404)
        # a job that is not a search
        gathered = self.c.post("/api/jobs", data={"kind": "kadai", "mihon": "1"}, headers=h).json()["id"]
        r = self.c.post("/api/jobs", data=sent | {"research": gathered}, headers=h)
        self.assertRefused(r, 422, "読ませられるのは、できあがった「今あるアプリを探す」の結果です")
        # a search that is not finished
        self.restart(run=lambda fn: None)
        waiting = self.c.post("/api/jobs", data={"kind": "chousa", "note": "毎週の集計"}, headers=h).json()["id"]
        self.assertEqual(self.c.get(f"/api/jobs/{waiting}", headers=h).json()["status"], "waiting")
        r = self.c.post("/api/jobs", data=sent | {"research": waiting}, headers=h)
        self.assertRefused(r, 422, "読ませられるのは、できあがった「今あるアプリを探す」の結果です")

    def test_the_design_job_reads_the_problems_that_were_gathered(self):
        h = self.google("u15")
        gathered = self.c.post("/api/jobs", data={"kind": "kadai", "mihon": "1"}, headers=h).json()["id"]
        skill = [("files", ("SKILL.md", "# 架空のアプリ".encode(), "text/markdown"))]
        before = len(self.gemini.seen)
        r = self.c.post("/api/jobs", data={"kind": "sekkei", "kadai": gathered}, files=skill, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.c.get(f"/api/jobs/{r.json()['id']}", headers=h).json()["status"], "done")
        # the request that writes the design has the SKILL.md and the reference, by the name of its path
        sent = self.gemini.seen[before][0][-1]["text"]
        self.assertIn("設計書 docs/design.adoc", sent)
        self.assertIn("# 架空のアプリ", sent)
        self.assertIn('<ファイル name="references/toriooki-analysis.adoc">', sent)
        self.assertIn("== 作るアプリで防ぐこと", sent)
        self.assertIn("取り消しを、アプリからできるようにする。", sent)

    def test_the_problems_document_is_titled_without_the_fallback_name(self):
        h = self.google("u10b")
        found = self.search_of(h)
        # no name given and no SKILL.md among the materials: the file is named app, the document is not
        r = self.c.post("/api/jobs", data={"kind": "kadai", "research": found}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        j = self.c.get(f"/api/jobs/{r.json()['id']}", headers=h).json()
        self.assertEqual(j["files"], ["references/app-analysis.adoc"])
        text = self.c.get(f"/api/jobs/{r.json()['id']}/file", params={"path": j["files"][0]}, headers=h).text
        self.assertTrue(text.startswith("= 今あるアプリの課題\n"), text)
        # a name given, or found in a SKILL.md, titles it
        skill = [("files", ("SKILL.md", b"---\nname: toriooki\n---\n# x", "text/markdown"))]
        r = self.c.post("/api/jobs", data={"kind": "kadai", "research": found}, files=skill, headers=h)
        j = self.c.get(f"/api/jobs/{r.json()['id']}", headers=h).json()
        text = self.c.get(f"/api/jobs/{r.json()['id']}/file", params={"path": j["files"][0]}, headers=h).text
        self.assertTrue(text.startswith("= toriooki の今あるアプリの課題\n"), text)

    def test_the_design_job_needs_materials_even_with_the_problems(self):
        h = self.google("u16")
        gathered = self.c.post("/api/jobs", data={"kind": "kadai", "mihon": "1"}, headers=h).json()["id"]
        # the problems alone are not enough: the SKILL.md is what says what to make
        r = self.c.post("/api/jobs", data={"kind": "sekkei", "kadai": gathered}, headers=h)
        self.assertRefused(r, 422, "SKILL.md と参考の資料を選んでください")
        r = self.c.post("/api/jobs", data={"kind": "sekkei"}, headers=h)
        self.assertRefused(r, 422, "SKILL.md と参考の資料を選んでください")
        # another person's problems are no problems at all
        skill = [("files", ("SKILL.md", "# 架空のアプリ".encode(), "text/markdown"))]
        self.assertEqual(self.c.post("/api/jobs", data={"kind": "sekkei", "kadai": gathered}, files=skill,
                                     headers=self.google("u17")).status_code, 404)
        # a job that does not gather problems
        search = self.search_of(h)
        r = self.c.post("/api/jobs", data={"kind": "sekkei", "kadai": search}, files=skill, headers=h)
        self.assertRefused(r, 422, "読ませられるのは、できあがった「今あるアプリの課題を集める」の資料です")
        # none of this used the day's design job
        self.assertEqual(self.c.get("/api/me", headers=h).json()["left"]["sekkei"], 1)

    def test_the_refusals_of_a_job_say_what_is_missing(self):
        h = self.google("u18")
        r = self.c.post("/api/jobs", data={"kind": "chousa"}, headers=h)
        self.assertRefused(r, 422, "何度も頼んでいることを書くか、資料を選んでください")
        # materials that cannot be read are another matter
        r = self.job(h, "chousa", files=[("files", ("a.sh", b"x", "text/plain"))])
        self.assertRefused(r, 422, "資料が入っていません(.md、.adoc、.txt か、それを入れた ZIP)")
        self.assertEqual(self.c.post("/api/jobs", data={"kind": "nani"}, headers=h).json()["detail"], "何をするかを選んでください")

    def test_the_counts_and_the_limits_include_the_problems_job(self):
        h = self.google("u19")
        left = self.c.get("/api/me", headers=h).json()["left"]
        self.assertEqual(left, {"chat": 3, "news": 1, "sekkei": 1, "chousa": 2, "kadai": 2, "tesuto": 2})
        for n in (1, 0):
            self.assertEqual(self.c.post("/api/jobs", data={"kind": "kadai", "mihon": "1"}, headers=h).status_code, 200)
            self.assertEqual(self.c.get("/api/me", headers=h).json()["left"]["kadai"], n)
        r = self.c.post("/api/jobs", data={"kind": "kadai", "mihon": "1"}, headers=h)
        self.assertRefused(r, 429, "今日の分(2 回)は使い終わりました。明日またどうぞ")
        # the limit is one person's: another person's own is not used
        self.assertEqual(self.c.post("/api/jobs", data={"kind": "kadai", "mihon": "1"}, headers=self.google("u20")).status_code, 200)

    def test_the_day_counts_the_problems_job_among_all_the_jobs(self):
        self.restart(env={"TAMESHI_JOBS_PER_DAY": "2"}, run=lambda fn: fn())
        self.assertEqual(self.c.post("/api/jobs", data={"kind": "kadai", "mihon": "1"}, headers=self.google("u21")).status_code, 200)
        self.assertEqual(self.c.post("/api/jobs", data={"kind": "kadai", "mihon": "1"}, headers=self.google("u22")).status_code, 200)
        r = self.c.post("/api/jobs", data={"kind": "chousa", "mihon": "1"}, headers=self.google("u23"))
        self.assertRefused(r, 429, "今日の受け付けは終わりました。明日またどうぞ")
        # the dialogue is not a job
        self.assertEqual(self.chat(self.google("u23")).status_code, 200)

    def test_the_test_procedure_reads_the_design_and_the_manual(self):
        h = self.google("u30")
        designed = self.design_of(h)
        before = len(self.gemini.seen)
        r = self.c.post("/api/jobs", data={"kind": "tesuto", "sekkei": designed, "note": "スマートフォンで使う"}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        j = self.c.get(f"/api/jobs/{r.json()['id']}", headers=h).json()
        self.assertEqual(j["status"], "done", j)
        self.assertEqual(j["files"], ["docs/test-kakunin.adoc", "docs/test.adoc"])
        self.assertEqual([x["name"] for x in j["steps"]], ["テストの手順を書く", "設計書とマニュアルと照らし合わせる"])
        # the first request has the design, the manual and the check of the job that was chosen, and the note
        sent = self.gemini.seen[before][0][-1]["text"]
        for name in ("docs/design.adoc", "docs/manual.adoc", "docs/kakunin.adoc"):
            self.assertIn(f'<ファイル name="{name}">', sent)
        self.assertIn("課題一覧: 課題を登録", sent)
        self.assertIn("= 利用者マニュアル", sent)
        self.assertIn("スマートフォンで使う", sent)
        # the result is what the check wrote, and the record of the check
        get = lambda path: self.c.get(f"/api/jobs/{r.json()['id']}/file", params={"path": path}, headers=h).text
        self.assertIn("直した版。", get("docs/test.adoc"))
        self.assertEqual(get("docs/test-kakunin.adoc").splitlines()[0], "= テストの手順の確かめ")
        self.assertEqual(len(self.drawn), 1)  # no picture was drawn for the test procedure (the one of the design)

    def test_the_test_procedure_reads_materials_too(self):
        h = self.google("u31")
        files = [("files", ("design.adoc", "= 設計書\n\n== 画面".encode(), "text/plain")),
                 ("files", ("manual.adoc", "= 利用者マニュアル".encode(), "text/plain"))]
        r = self.job(h, "tesuto", files=files)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.c.get(f"/api/jobs/{r.json()['id']}", headers=h).json()["status"], "done")
        self.assertIn('<ファイル name="design.adoc">', self.gemini.seen[-2][0][-1]["text"])

    def test_the_test_procedure_needs_the_design_and_one_of_ones_own(self):
        h = self.google("u32")
        designed = self.design_of(h)
        r = self.c.post("/api/jobs", data={"kind": "tesuto"}, headers=h)
        self.assertRefused(r, 422, "読ませる設計書とマニュアルを選ぶか、資料を選んでください")
        # the sample is not read for this job
        r = self.c.post("/api/jobs", data={"kind": "tesuto", "mihon": "1"}, headers=h)
        self.assertRefused(r, 422, "読ませる設計書とマニュアルを選ぶか、資料を選んでください")
        # another person's design is no design at all
        self.assertEqual(self.c.post("/api/jobs", data={"kind": "tesuto", "sekkei": designed}, headers=self.google("u33")).status_code, 404)
        # a job that is not a design
        search = self.search_of(h)
        r = self.c.post("/api/jobs", data={"kind": "tesuto", "sekkei": search}, headers=h)
        self.assertRefused(r, 422, "読ませられるのは、できあがった「設計書とマニュアルを作る」の結果です")
        # none of this used the day's test procedures
        self.assertEqual(self.c.get("/api/me", headers=h).json()["left"]["tesuto"], 2)

    def test_the_test_procedure_has_its_own_limit(self):
        h = self.google("u34")
        designed = self.design_of(h)
        for n in (1, 0):
            self.assertEqual(self.c.post("/api/jobs", data={"kind": "tesuto", "sekkei": designed}, headers=h).status_code, 200)
            self.assertEqual(self.c.get("/api/me", headers=h).json()["left"]["tesuto"], n)
        r = self.c.post("/api/jobs", data={"kind": "tesuto", "sekkei": designed}, headers=h)
        self.assertRefused(r, 429, "今日の分(2 回)は使い終わりました。明日またどうぞ")

    def test_a_job_that_stops_is_not_counted_against_the_person(self):
        h = self.google("u35")
        self.gemini.fail = True
        r = self.c.post("/api/jobs", data={"kind": "sekkei", "mihon": "1"}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        j = self.c.get(f"/api/jobs/{r.json()['id']}", headers=h).json()
        self.assertEqual((j["status"], j["error"]), ("error", "Gemini が答えませんでした"))
        self.assertEqual(self.c.get("/api/me", headers=h).json()["left"]["sekkei"], 1)  # given back; one a day
        self.gemini.fail = False
        r = self.c.post("/api/jobs", data={"kind": "sekkei", "mihon": "1"}, headers=h)
        self.assertEqual(self.c.get(f"/api/jobs/{r.json()['id']}", headers=h).json()["status"], "done")
        self.assertEqual(self.c.get("/api/me", headers=h).json()["left"]["sekkei"], 0)
        self.assertEqual(self.c.post("/api/jobs", data={"kind": "sekkei", "mihon": "1"}, headers=h).status_code, 429)

    def test_a_stopped_job_counts_among_all_the_jobs_of_the_day(self):
        self.restart(env={"TAMESHI_JOBS_PER_DAY": "2"}, run=lambda fn: fn())
        h = self.google("u36")
        self.gemini.fail = True
        for _ in range(2):  # each is given back to the person, so the person can ask again
            self.assertEqual(self.c.post("/api/jobs", data={"kind": "chousa", "mihon": "1"}, headers=h).status_code, 200)
        self.assertEqual(self.c.get("/api/me", headers=h).json()["left"]["chousa"], 2)
        # but the day's number of jobs has run out
        r = self.c.post("/api/jobs", data={"kind": "chousa", "mihon": "1"}, headers=h)
        self.assertRefused(r, 429, "今日の受け付けは終わりました。明日またどうぞ")

    def reviewer(self):
        return {"Authorization": "Bearer " + self.log_in_test().json()["token"]}

    def test_the_test_account_has_no_limit_of_one_person(self):
        # the reviewers share it: one of them using it must not shut the others out
        self.restart(env={"TAMESHI_DAY_LIMIT": "100"}, run=lambda fn: fn())
        t = self.reviewer()
        for _ in range(5):  # one person may talk 3 times a day
            self.assertEqual(self.chat(t).status_code, 200)
        for _ in range(2):  # and may ask for one design a day
            self.assertEqual(self.c.post("/api/jobs", data={"kind": "sekkei", "mihon": "1"}, headers=t).status_code, 200)
        g = self.google("u40")
        self.assertEqual(self.c.post("/api/jobs", data={"kind": "sekkei", "mihon": "1"}, headers=g).status_code, 200)
        self.assertEqual(self.c.post("/api/jobs", data={"kind": "sekkei", "mihon": "1"}, headers=g).status_code, 429)

    def test_the_test_account_is_shown_what_is_left_of_everyone_s_limits(self):
        t = self.reviewer()  # a day's limit of 5 Gemini calls in all (setUp)
        left = self.c.get("/api/me", headers=t).json()["left"]
        self.assertEqual(set(left.values()), {5})
        r = self.chat(t)
        self.assertEqual(r.json()["left"], 4)
        self.assertEqual(set(self.c.get("/api/me", headers=t).json()["left"].values()), {4})
        for _ in range(3):
            self.assertEqual(self.chat(t).status_code, 200)
        self.assertEqual(self.c.get("/api/me", headers=t).json()["left"]["chat"], 1)
        self.assertEqual(self.chat(t).json()["left"], 0)
        r = self.chat(t)
        self.assertRefused(r, 429, "今日の受け付けは終わりました。明日またどうぞ")
        # a person who signed in with Google still has a limit of one's own, and is shown it
        self.assertEqual(self.c.get("/api/me", headers=self.google("u41")).json()["left"]["chat"], 3)

    def test_the_test_account_is_limited_by_the_jobs_of_everyone(self):
        self.restart(env={"TAMESHI_DAY_LIMIT": "100", "TAMESHI_JOBS_PER_DAY": "2"}, run=lambda fn: fn())
        t = self.reviewer()
        self.assertEqual(self.c.get("/api/me", headers=t).json()["left"]["sekkei"], 2)
        for left in (1, 0):
            self.assertEqual(self.c.post("/api/jobs", data={"kind": "chousa", "mihon": "1"}, headers=t).status_code, 200)
            self.assertEqual(self.c.get("/api/me", headers=t).json()["left"]["sekkei"], left)
        r = self.c.post("/api/jobs", data={"kind": "chousa", "mihon": "1"}, headers=t)
        self.assertRefused(r, 429, "今日の受け付けは終わりました。明日またどうぞ")
        # the dialogue is not a job
        self.assertEqual(self.chat(t).status_code, 200)

    def test_the_test_account_s_jobs_are_kept_longer(self):
        t, g = self.reviewer(), self.google("u42")
        ids = {w: self.c.post("/api/jobs", data={"kind": "chousa", "mihon": "1"}, headers=h).json()["id"] for w, h in (("test", t), ("google", g))}

        def age(who, days):
            self.app.state.db.run("UPDATE jobs SET created = ? WHERE id = ?", (time.time() - days * 86400, ids[who]))

        def shown(who, h):
            return self.c.get(f"/api/jobs/{ids[who]}", headers=h).status_code, os.path.isdir(os.path.join(self.tmp.name, "jobs", ids[who]))

        self.assertEqual((shown("test", t), shown("google", g)), ((200, True), (200, True)))
        age("test", 8), age("google", 8)  # a person's job goes after 7 days, the test account's does not
        self.restart(run=lambda fn: fn())
        self.assertEqual((shown("test", t), shown("google", g)), ((200, True), (404, False)))
        age("test", 59)
        self.restart(run=lambda fn: fn())
        self.assertEqual(shown("test", t), (200, True))
        age("test", 61)  # 60 days is the default
        self.restart(run=lambda fn: fn())
        self.assertEqual(shown("test", t), (404, False))

    def test_the_days_the_test_account_s_jobs_are_kept_can_be_set(self):
        t = self.reviewer()
        jid = self.c.post("/api/jobs", data={"kind": "chousa", "mihon": "1"}, headers=t).json()["id"]
        self.app.state.db.run("UPDATE jobs SET created = ? WHERE id = ?", (time.time() - 20 * 86400, jid))
        self.restart(env={"TAMESHI_TEST_KEEP_DAYS": "30"}, run=lambda fn: fn())
        self.assertEqual(self.c.get(f"/api/jobs/{jid}", headers=t).status_code, 200)
        self.restart(env={"TAMESHI_TEST_KEEP_DAYS": "10"}, run=lambda fn: fn())
        self.assertEqual(self.c.get(f"/api/jobs/{jid}", headers=t).status_code, 404)

    # ---- registering with an ID and a password, and the owner's approval ----------------------------------

    def register(self, uid="taro", password="himitsu-no-pass"):
        return self.c.post("/api/register", json={"id": uid, "password": password})

    def local(self, uid="taro", password="himitsu-no-pass"):
        r = self.register(uid, password)
        self.assertEqual(r.status_code, 200, r.text)
        return {"Authorization": "Bearer " + r.json()["token"]}

    def test_anyone_may_register_and_is_signed_in_at_once(self):
        h = self.local()
        me = self.c.get("/api/me", headers=h).json()
        self.assertEqual((me["provider"], me["id"], me["email"], me["approved"], me["kaihatsu"]), ("local", "taro", "", False, False))
        # the ID is put in small letters
        self.assertEqual(self.c.get("/api/me", headers=self.local("Hanako-2")).json()["id"], "hanako-2")

    def test_the_form_of_an_id_and_of_a_password(self):
        for uid in ("ab", "x" * 33, "ta ro", "taro!", "たろう", ""):
            r = self.register(uid)
            self.assertRefused(r, 422, "ID は、3〜32 字の、小文字の英数字と - _ で書いてください")
        for password in ("1234567", "x" * 73, ""):
            self.assertRefused(self.register("taro", password), 422, "パスワードは、8 字以上、72 字までで書いてください")
        self.assertEqual(self.register("a-b_c").status_code, 200)  # - and _ are allowed
        self.assertEqual(self.register("x" * 32, "y" * 72).status_code, 200)  # the longest

    def test_an_id_that_is_used_cannot_be_registered_again(self):
        self.local("taro")
        self.assertRefused(self.register("taro", "another-pass"), 409, "この ID は使われています")
        self.assertRefused(self.register("TARO", "another-pass"), 409, "この ID は使われています")
        # nor the ID of the test account
        self.assertRefused(self.register("shinsa", "another-pass"), 409, "この ID は使われています")

    def test_only_so_many_may_register_a_day(self):
        self.restart(env={"TAMESHI_REGISTER_PER_DAY": "2"}, run=lambda fn: fn())
        self.local("one")
        self.local("two")
        self.assertRefused(self.register("three"), 429, "今日の登録は終わりました。明日またどうぞ")
        # an ID that is used is told so, and a wrong form is, before the number is looked at
        self.assertRefused(self.register("one"), 409, "この ID は使われています")
        self.assertRefused(self.register("x"), 422, "ID は、3〜32 字の、小文字の英数字と - _ で書いてください")

    def test_the_password_is_not_kept_only_its_salted_hash(self):
        self.local("taro", "himitsu-no-pass")
        self.local("jiro", "himitsu-no-pass")
        rows = {r["id"]: r for r in self.app.state.db.all("SELECT * FROM users")}
        for row in rows.values():
            self.assertNotIn("himitsu-no-pass", [row[k] for k in row.keys()])
            self.assertEqual(len(row["salt"]), 32)
            self.assertEqual(row["hash"], server.hash_password("himitsu-no-pass", row["salt"]))
        # the same password gives another value for another person, by the salt
        self.assertNotEqual(rows["taro"]["hash"], rows["jiro"]["hash"])
        self.assertEqual(server.PBKDF2_ROUNDS, 600_000)

    def test_a_registered_person_signs_in_with_the_id_and_the_password(self):
        self.local("taro", "himitsu-no-pass")
        r = self.c.post("/api/login", json={"id": "taro", "password": "himitsu-no-pass"})
        self.assertEqual(r.status_code, 200, r.text)
        me = self.c.get("/api/me", headers={"Authorization": "Bearer " + r.json()["token"]}).json()
        self.assertEqual((me["provider"], me["id"]), ("local", "taro"))
        self.assertEqual(self.c.post("/api/login", json={"id": "TARO", "password": "himitsu-no-pass"}).status_code, 200)
        for body in ({"id": "taro", "password": "chigau-pass"}, {"id": "nobody", "password": "himitsu-no-pass"}, {"id": "taro"}, {}):
            self.assertRefused(self.c.post("/api/login", json=body), 401, "ID かパスワードが違います")
        # the test account comes in by the same way
        self.assertEqual(self.log_in_test().status_code, 200)
        self.assertEqual(self.c.get("/api/me", headers={"Authorization": "Bearer " + self.log_in_test().json()["token"]}).json()["provider"], "test")

    def test_an_id_is_shut_for_the_day_after_too_many_wrong_passwords(self):
        from unittest import mock
        self.local("taro", "himitsu-no-pass")
        with mock.patch.object(server, "FAILED_LOGINS", 2):
            for _ in range(2):
                self.assertEqual(self.c.post("/api/login", json={"id": "taro", "password": "chigau-pass"}).status_code, 401)
            # shut: even the right password does not come in, today
            self.assertRefused(self.c.post("/api/login", json={"id": "taro", "password": "himitsu-no-pass"}), 429, "今日は、この ID では入れません")
            # an ID counts by itself: another ID, and the test account, are not shut
            self.local("jiro", "himitsu-no-pass")
            self.assertEqual(self.c.post("/api/login", json={"id": "jiro", "password": "himitsu-no-pass"}).status_code, 200)
            self.assertEqual(self.log_in_test().status_code, 200)
            # an ID that does not exist is counted too
            for _ in range(2):
                self.c.post("/api/login", json={"id": "nobody", "password": "x"})
            self.assertEqual(self.c.post("/api/login", json={"id": "nobody", "password": "x"}).status_code, 429)
            # the test account is shut the same way
            for _ in range(2):
                self.log_in_test("chigau")
            self.assertRefused(self.log_in_test(), 429, "今日は、この ID では入れません")

    def test_a_person_who_is_not_approved_may_not_ask_gemini(self):
        h = self.local("taro")
        before = len(self.gemini.seen)
        refused = "承認されるまで、Gemini には頼めません"
        self.assertRefused(self.chat(h), 403, refused)
        self.assertRefused(self.c.post("/api/news", json={"tastes": "VLM"}, headers=h), 403, refused)
        self.assertRefused(self.c.post("/api/kaizen", json={"messages": [{"role": "user", "text": "困っています"}]}, headers=h), 403, refused)
        self.assertRefused(self.c.post("/api/jobs", data={"kind": "chousa", "mihon": "1"}, headers=h), 403, refused)
        self.assertEqual(len(self.gemini.seen), before)  # Gemini was not called, and nothing was counted
        self.assertEqual(self.c.get("/api/me", headers=h).json()["left"]["chat"], 3)
        # what is not a way to Gemini is open to them: reading the jobs (none), the list, the information
        self.assertEqual(self.c.get("/api/jobs", headers=h).json(), {"jobs": []})
        # a way that does not exist is told first (422) before the approval (403)
        self.assertRefused(self.c.post("/api/jobs", data={"kind": "nani"}, headers=h), 422, "何をするかを選んでください")

    def test_the_approved_file_counts_at_once_and_is_read_each_time(self):
        h = self.local("taro")
        self.assertEqual(self.chat(h).status_code, 403)
        self.approve("# the owner's file", "", "  LOCAL:Taro  # a comment")  # lines are not case-sensitive, and may have comments
        self.assertEqual(self.chat(h).status_code, 200)  # no restart
        me = self.c.get("/api/me", headers=h).json()
        self.assertEqual((me["approved"], me["kaihatsu"]), (True, True))
        self.assertEqual(self.c.post("/api/jobs", data={"kind": "chousa", "mihon": "1"}, headers=h).status_code, 200)  # an approved person may ask for jobs
        with open(self.env["TAMESHI_APPROVED"], "w", encoding="utf-8") as f:  # the owner takes the line away
            f.write("")
        self.assertEqual(self.chat(h).status_code, 403)
        os.remove(self.env["TAMESHI_APPROVED"])  # no file at all: nobody but the test account
        self.assertEqual(self.chat(h).status_code, 403)
        self.assertEqual(self.chat({"Authorization": "Bearer " + self.log_in_test().json()["token"]}).status_code, 200)

    def test_google_people_are_approved_by_their_verified_address(self):
        h = self.google("u50", approved=False)
        self.assertEqual(self.chat(h).status_code, 403)
        self.approve("google:u50@example.jp")
        self.assertEqual(self.chat(h).status_code, 200)
        self.assertEqual(self.chat(self.google("u51", approved=False)).status_code, 403)
        # the approval of the same name for another provider does not count
        self.approve("apple:u51@example.jp", "local:u51")
        self.assertEqual(self.chat(self.google("u51", approved=False)).status_code, 403)

    def test_the_test_account_is_always_approved(self):
        t = {"Authorization": "Bearer " + self.log_in_test().json()["token"]}
        self.assertEqual(self.c.get("/api/me", headers=t).json()["approved"], True)
        self.assertEqual(self.chat(t).status_code, 200)

    def test_the_owner_s_list_shows_who_registered_and_who_is_approved(self):
        self.local("taro")
        self.local("jiro")
        self.google("u60")  # approved by the helper
        self.c.get("/api/me", headers=self.google("u61", approved=False))  # the first use of a session leaves a line of the person
        self.c.get("/api/me", headers=self.google("u60"))
        self.approve("local:jiro")
        lines = server.users_report(self.env["DB"], self.env["TAMESHI_APPROVED"])
        table = [x.split("\t") for x in lines]
        self.assertEqual(table[0], ["名前", "種類", "登録した日", "承認", "approved.txt に足す行"])
        by = {row[0]: row for row in table[1:]}
        self.assertEqual((by["taro"][1], by["taro"][3], by["taro"][4]), ("local", "未承認", "local:taro"))
        self.assertEqual((by["jiro"][1], by["jiro"][3]), ("local", "承認済み"))
        self.assertEqual((by["u60@example.jp"][1], by["u60@example.jp"][3], by["u60@example.jp"][4]), ("google", "承認済み", "google:u60@example.jp"))
        self.assertEqual((by["u61@example.jp"][3], by["u61@example.jp"][4]), ("未承認", "google:u61@example.jp"))
        self.assertRegex(by["taro"][2], r"^\d{4}-\d{2}-\d{2}$")
        # the command prints the same, from the files the server uses
        import subprocess
        out = subprocess.run([sys.executable, os.path.join(HERE, "server.py"), "users"], capture_output=True, text=True, timeout=60,
                             env=dict(os.environ, DB=self.env["DB"], TAMESHI_APPROVED=self.env["TAMESHI_APPROVED"]))
        self.assertEqual(out.returncode, 0, out.stderr[-300:])
        self.assertEqual(out.stdout.strip().splitlines(), lines)

    def test_the_name_of_the_app_falls_back_to_the_skill_md(self):
        m = server.materials_of
        self.assertEqual(server.skill_name(m([("toriooki/SKILL.md", b"---\nname: Toriooki\n---\n# x")])), "toriooki")
        self.assertEqual(server.skill_name(m([("SKILL.md", b"---\r\nname: 'my-app'\r\n---\r\n# x")])), "my-app")
        self.assertEqual(server.skill_name(m([("SKILL.md", "---\nname: 取り置き\n---\n".encode())])), "app")
        self.assertEqual(server.skill_name(m([("notes.md", b"---\nname: x\n---\n")])), "app")
        self.assertEqual(server.skill_name(m([("SKILL.md", b"# no front matter")])), "app")
        self.assertEqual(server.skill_name(""), "app")

    def test_jobs_are_only_for_the_owner_and_the_allowed(self):
        h = self.google("u1")
        jid = self.job(h, "chousa", files=[("files", ("SKILL.md", "# 架空".encode(), "text/markdown"))]).json()["id"]
        other = self.google("u2")
        self.assertEqual(self.c.get(f"/api/jobs/{jid}", headers=other).status_code, 404)
        self.assertEqual(self.job(h, "sekkei", files=[("files", ("a.sh", b"x", "text/plain"))]).status_code, 422)
        # a person the owner has not approved may not start a job
        self.assertRefused(self.job(self.google("u3", approved=False), "chousa"), 403, "承認されるまで、Gemini には頼めません")


if __name__ == "__main__":
    unittest.main(verbosity=2)
