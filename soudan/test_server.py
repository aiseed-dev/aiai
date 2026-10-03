# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tries server.py from sign-in to deleting one's record, against the fake
Apple and Google of moushikomi/fake_id.py and two fake models.

    python test_server.py
"""
import os
import sys
import tempfile
import time
import unittest
import urllib.parse

from fastapi.testclient import TestClient

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "moushikomi"))
import fake_id  # noqa: E402
from fake_id import code  # noqa: E402

sys.path.insert(0, HERE)
import server  # noqa: E402

SITE = "https://soudan.example/app/"


class FakeModel:
    """Answers with what it was given, so the tests can see the messages."""

    def __init__(self, name, fail=None):
        self.name, self.fail, self.seen = name, fail, []
        self.fail_at, self.drop_at = None, None  # the call that is refused / that does not connect

    def answer(self, system, messages):
        self.seen.append((system, messages))
        if self.fail or len(self.seen) == self.fail_at:
            raise self.fail or server.ModelError("このモデルは、この相談に答えませんでした")
        if len(self.seen) == self.drop_at:
            raise ConnectionError("dropped")
        return f"{self.name} の答え #{len(self.seen)}", 100, 20


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fake, self.env = fake_id.start(self.tmp.name)
        self.env |= {"BASE_URL": "https://soudan.example", "RETURN_URLS": SITE,
                     "DB": os.path.join(self.tmp.name, "t.db"), "RESEARCH_EMAILS": "Owner@Example.jp",
                     "SOUDAN_PER_DAY": "4", "SOUDAN_DAY_LIMIT": "30"}
        self.start()

    def start(self, **over):
        self.a, self.b = FakeModel("A"), FakeModel("B")
        self.app = server.create_app(self.env | over, models={"a:one": self.a, "b:two": self.b})
        self.c = TestClient(self.app, follow_redirects=False)

    def tearDown(self):
        self.fake.shutdown()
        self.app.state.db.db.close()
        self.tmp.cleanup()

    def sign_in(self, sub, email="", agree=True, invite=None):
        r = self.c.get("/login/google", params={"next": SITE})
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(r.headers["location"]).query))
        r = self.c.get("/callback/google", params={"code": code(q["nonce"], sub, email), "state": q["state"]})
        one = urllib.parse.parse_qs(urllib.parse.urlsplit(r.headers["location"]).query)["code"][0]
        h = {"Authorization": "Bearer " + self.c.post("/api/session", json={"code": one}).json()["token"]}
        if agree:
            invite = invite or self.app.state.make_invites(1)[0]
            v = self.c.get("/api/info").json()["consent_version"]
            r = self.c.post("/api/agree", json={"version": v, "code": invite}, headers=h)
            self.assertEqual(r.status_code, 200, r.text)
        return h

    def ask(self, h, draft="長所は、粘り強く確かめることです。", kind="転職", models=("a:one",)):
        return self.c.post("/api/consults", json={"kind": kind, "draft": draft, "models": list(models)},
                           headers=h)

    def test_info_lists_kinds_and_models(self):
        info = self.c.get("/api/info").json()
        self.assertEqual({k["name"] for k in info["kinds"]}, {"自分を知る", "転職", "学び", "履歴書", "企画書"})
        self.assertEqual(info["models"], ["a:one", "b:two"])
        self.assertIn("研究", info["consent"])

    def test_consent_is_needed_first(self):
        h = self.sign_in("hana", agree=False)
        self.assertEqual(self.ask(h).status_code, 403)
        code = self.app.state.make_invites(1)[0]
        self.assertEqual(self.c.post("/api/agree", json={"version": "old", "code": code}, headers=h).status_code, 409)
        self.assertFalse(self.c.get("/api/me", headers=h).json()["agreed"])

    def test_only_invited_people_join(self):
        v = self.c.get("/api/info").json()["consent_version"]
        h = self.sign_in("hana", agree=False)
        self.assertEqual(self.c.post("/api/agree", json={"version": v}, headers=h).status_code, 403)
        self.assertEqual(self.c.post("/api/agree", json={"version": v, "code": "ABCD-EFGH"}, headers=h).status_code, 403)
        code = self.app.state.make_invites(1)[0]
        # Typed loosely: lower case, no dash, full-width letters
        loose = code.replace("-", "").lower()
        self.assertEqual(self.c.post("/api/agree", json={"version": v, "code": loose}, headers=h).status_code, 200)
        me = self.c.get("/api/me", headers=h).json()
        self.assertTrue(me["invited"] and me["agreed"])
        # A code is used once
        t = self.sign_in("taro", agree=False)
        self.assertEqual(self.c.post("/api/agree", json={"version": v, "code": code}, headers=t).status_code, 403)
        self.assertEqual(self.ask(t).status_code, 403)

    def test_staff_make_invites(self):
        h = self.sign_in("hana")
        self.assertEqual(self.c.post("/api/research/invites", json={"count": 2}, headers=h).status_code, 403)
        o = self.sign_in("owner", "owner@example.jp")
        r = self.c.post("/api/research/invites", json={"count": 2, "note": "10 月の募集"}, headers=o)
        self.assertEqual(r.status_code, 200, r.text)
        codes = r.json()["codes"]
        self.assertEqual(len(set(codes)), 2)
        self.assertEqual(self.c.post("/api/research/invites", json={"count": 0}, headers=o).status_code, 422)
        self.sign_in("jiro", invite=codes[0])
        s = self.c.get("/api/research/summary", headers=o).json()
        self.assertEqual((s["invites_used"], s["people"]), (3, 3))

    def test_two_models_answer_and_the_record_grows(self):
        h = self.sign_in("hana")
        r = self.ask(h, models=("a:one", "b:two"))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([x["answer"] for x in r.json()], ["A の答え #1", "B の答え #1"])
        system, messages = self.a.seen[0]
        self.assertIn("セカンドオピニオン", system)
        self.assertIn("# 転職の考え", system)
        self.assertTrue(messages[-1]["content"].endswith("長所は、粘り強く確かめることです。"))
        self.assertEqual(self.c.post("/api/events", json={"text": "製造業の会社に応募した"}, headers=h).status_code, 200)
        # The next consultation carries the earlier one and the events
        self.ask(h, draft="面接で何を話すか考えました。")
        _, messages = self.a.seen[-1]
        self.assertEqual([m["role"] for m in messages], ["user", "assistant", "user"])
        self.assertIn("製造業の会社に応募した", messages[-1]["content"])
        rec = self.c.get("/api/record", headers=h).json()
        self.assertEqual([x["type"] for x in rec], ["consult", "consult", "event", "consult"])

    def test_identifying_details_never_reach_a_model(self):
        h = self.sign_in("hana")
        for draft, kind in [("連絡は hana@example.jp へ", "メールアドレス"), ("電話 090-1234-5678", "電話番号"),
                            ("〒100-0001 の近く", "郵便番号"), ("番号 1234 5678 9012", "12 桁の数字"),
                            ("電話 ０３－１２３４－５６７８", "電話番号")]:
            r = self.ask(h, draft=draft)
            self.assertEqual(r.status_code, 422, draft)
            self.assertIn(kind, r.text)
        self.assertEqual(self.a.seen, [])
        self.assertEqual(self.c.post("/api/events", json={"text": "hana@example.jp に返事"}, headers=h).status_code, 422)
        # Dates and money are not mistaken for them
        self.assertEqual(self.ask(h, draft="2026-10-02 に 120,000 円で始めます").status_code, 200)

    def test_choices_are_checked(self):
        h = self.sign_in("hana")
        self.assertEqual(self.ask(h, kind="占い").status_code, 422)
        self.assertEqual(self.ask(h, models=()).status_code, 422)
        self.assertEqual(self.ask(h, models=("c:three",)).status_code, 422)
        self.assertEqual(self.ask(h, models=("a:one", "a:one")).status_code, 422)
        self.assertEqual(self.ask(h, draft="").status_code, 422)
        self.assertEqual(self.ask(h, draft="あ" * 12001).status_code, 422)

    def test_limits_per_person_and_per_day(self):
        self.start(SOUDAN_DAY_LIMIT="6")
        h = self.sign_in("hana")
        self.assertEqual(self.ask(h, models=("a:one", "b:two")).status_code, 200)
        self.assertEqual(self.ask(h, models=("a:one", "b:two")).status_code, 200)
        self.assertEqual(self.ask(h).status_code, 429)
        t = self.sign_in("taro")
        self.assertEqual(self.ask(t, models=("a:one", "b:two")).status_code, 200)
        self.assertEqual(self.ask(t).status_code, 429)  # everyone's limit of 6

    def test_a_failing_model_is_reported_and_not_stored(self):
        self.b.fail = server.ModelError("このモデルは、この相談に答えませんでした")
        h = self.sign_in("hana")
        r = self.ask(h, models=("a:one", "b:two")).json()
        self.assertIn("answer", r[0])
        self.assertEqual(r[1]["error"], "このモデルは、この相談に答えませんでした")
        self.assertEqual(len(self.c.get("/api/record", headers=h).json()), 1)

    def test_others_cannot_see_or_rate(self):
        h, t = self.sign_in("hana"), self.sign_in("taro")
        cid = self.ask(h).json()[0]["id"]
        self.assertEqual(self.c.get("/api/record", headers=t).json(), [])
        self.assertEqual(self.c.post(f"/api/consults/{cid}/rating", json={"rating": 5}, headers=t).status_code, 404)
        self.assertEqual(self.c.post(f"/api/consults/{cid}/rating", json={"rating": 9}, headers=h).status_code, 422)
        self.assertEqual(self.c.post(f"/api/consults/{cid}/rating", json={"rating": 4}, headers=h).status_code, 200)
        self.assertEqual(self.c.get("/api/record", headers=h).json()[0]["rating"], 4)

    def test_research_summary_has_no_text(self):
        h = self.sign_in("hana")
        cid = self.ask(h, models=("a:one", "b:two")).json()[0]["id"]
        self.c.post(f"/api/consults/{cid}/rating", json={"rating": 5}, headers=h)
        self.assertEqual(self.c.get("/api/research/summary", headers=h).status_code, 403)
        o = self.sign_in("owner", "owner@example.jp")
        s = self.c.get("/api/research/summary", headers=o).json()
        self.assertEqual(s["people"], 2)
        a = [x for x in s["by_model"] if x["model"] == "a:one"][0]
        self.assertEqual((a["consults"], a["rated"], a["rating"]), (1, 1, 5.0))
        self.assertNotIn("粘り強く", str(s))

    def report(self, h, material="[2026-09-01] 畑の写真から病気の見当を付けるアプリを作りたい", model="a:one"):
        return self.c.post("/api/reports", json={"model": model, "material": material, "sources": "Claude Code 3 件"},
                           headers=h)

    def finished(self, h, rid):
        """The report once its thread is done (the fake models answer at once)."""
        for _ in range(100):
            r = self.c.get(f"/api/reports/{rid}", headers=h).json()
            if r["status"] != "running":
                return r
            time.sleep(0.05)
        self.fail("the report did not finish")

    def test_report_runs_the_agent_one_item_at_a_time(self):
        h = self.sign_in("hana")
        self.c.post("/api/events", json={"text": "農業法人の見学に申し込んだ"}, headers=h)
        r = self.report(h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["steps"], 13)
        r = self.finished(h, r.json()["id"])
        self.assertEqual((r["status"], r["done"], r["error"]), ("done", 13, None))
        prompts = [m[-1]["content"] for _, m in self.a.seen]
        self.assertIn("本人と AI の対話", self.a.seen[0][0])
        # 1. 長所: the dialogue and its own lines, nothing else
        self.assertIn("「1. 長所」", prompts[0])
        self.assertIn("書き方: 3 つまで", prompts[0])
        self.assertIn("畑の写真", prompts[0])
        self.assertNotIn("農業法人の見学", prompts[0])
        # 7. いまの AI での頼み方: only the result of 6
        self.assertIn("「7. いまの AI での頼み方」", prompts[6])
        self.assertIn("A の答え #6", prompts[6])
        self.assertNotIn("A の答え #1\n", prompts[6])
        self.assertNotIn("畑の写真", prompts[6])
        # 10. 長所が生きる仕事: the results of 1 to 5 and the events
        self.assertIn("A の答え #5", prompts[9])
        self.assertNotIn("A の答え #6", prompts[9])
        self.assertIn("農業法人の見学", prompts[9])
        # the summary reads every item, and the report is put together in order
        self.assertIn("## 12. 次の行動", prompts[12])
        self.assertTrue(r["report"].startswith("# 報告書\n\n## 要約\n\nA の答え #13"))
        self.assertLess(r["report"].index("## 1. 長所\n\nA の答え #1\n"), r["report"].index("## 12. 次の行動\n\nA の答え #12"))
        rec = self.c.get("/api/record", headers=h).json()
        self.assertEqual([x["type"] for x in rec], ["event", "report"])
        self.assertEqual(rec[1]["report"], r["report"])

    def test_report_checks(self):
        h = self.sign_in("hana")
        self.assertEqual(self.report(h, material="").status_code, 422)
        self.assertEqual(self.report(h, model="c:three").status_code, 422)
        self.assertEqual(self.report(h, material="連絡は hana@example.jp").status_code, 422)
        self.assertEqual(self.report(h, material="あ" * 80001).status_code, 422)
        self.assertEqual(self.a.seen, [])
        self.assertEqual(self.c.get("/api/reports/nothing", headers=h).status_code, 404)

    def test_report_limits(self):
        self.start(SOUDAN_DAY_LIMIT="20")
        h = self.sign_in("hana")
        first = self.report(h)
        self.assertEqual(first.status_code, 200)
        self.finished(h, first.json()["id"])
        self.assertEqual(self.ask(h).status_code, 200)   # a report is not one of the person's consultations
        t = self.sign_in("taro")
        self.assertEqual(self.report(t).status_code, 429)  # 13 + 1 + 13 is over everyone's 20 calls
        self.assertEqual(self.ask(t).status_code, 200)

    def test_a_report_that_stops_early_keeps_its_items(self):
        h = self.sign_in("hana")
        self.a.fail_at = 4
        r = self.finished(h, self.report(h).json()["id"])
        self.assertEqual((r["status"], r["done"]), ("failed", 3))
        self.assertEqual(r["error"], "このモデルは、この相談に答えませんでした")
        self.assertIn("## 3. 繰り返し興味を持っていること\n\nA の答え #3", r["report"])
        self.assertNotIn("要約", r["report"])
        self.assertNotIn("## 4.", r["report"])
        self.assertEqual(len(self.a.seen), 4)  # a refusal is not tried again

    def test_a_connection_failure_is_tried_once_more(self):
        h = self.sign_in("hana")
        self.a.drop_at = 2
        r = self.finished(h, self.report(h).json()["id"])
        self.assertEqual((r["status"], r["done"]), ("done", 13))
        self.assertEqual(len(self.a.seen), 14)

    def test_deleting_the_record(self):
        h = self.sign_in("hana")
        self.ask(h)
        self.c.post("/api/events", json={"text": "応募した"}, headers=h)
        self.finished(h, self.report(h).json()["id"])
        self.assertEqual(self.c.delete("/api/record", headers=h).status_code, 200)
        db = self.app.state.db
        for table in ("consults", "events", "reports", "people", "sessions"):
            self.assertEqual(db.one(f"SELECT COUNT(*) FROM {table}")[0], 0, table)
        self.assertEqual(self.c.get("/api/me", headers=h).status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
