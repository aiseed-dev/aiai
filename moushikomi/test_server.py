# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tries server.py from sign-in to cancel, against the fake Apple and Google
of fake_id.py (which can also hand out broken id_tokens).

    python test_server.py
"""
import base64
import datetime
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.parse

import jwt
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_id  # noqa: E402
import server  # noqa: E402
from fake_id import code, seen_secrets  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
KOUMOKU = os.path.join(HERE, "取り置き.koumoku.adoc")
SITE = "https://hanako-pan.example/torioki/"

def next_weekday(start, closed=(6, 0)):
    d = start
    while d.weekday() in closed:
        d += datetime.timedelta(days=1)
    return d


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.fake, env = fake_id.start(cls.tmp.name)
        env |= {"BASE_URL": "https://yoyaku.example", "RETURN_URLS": SITE + " hanakopan://signed-in",
                "DB": os.path.join(cls.tmp.name, "t.db"), "SHOP_EMAILS": "Owner@Example.jp"}
        cls.app = server.create_app(KOUMOKU, env)
        cls.c = TestClient(cls.app, follow_redirects=False)

    @classmethod
    def tearDownClass(cls):
        cls.fake.shutdown()
        cls.app.state.db.db.close()
        cls.tmp.cleanup()

    def start(self, provider, next_url=SITE):
        r = self.c.get(f"/login/{provider}", params={"next": next_url})
        self.assertEqual(r.status_code, 303)
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(r.headers["location"]).query))
        return q

    def finish(self, provider, q, c):
        if provider == "apple":
            return self.c.post("/callback/apple", data={"code": c, "state": q["state"]})
        return self.c.get("/callback/google", params={"code": c, "state": q["state"]})

    def sign_in(self, provider, sub, email="", next_url=SITE):
        q = self.start(provider, next_url)
        r = self.finish(provider, q, code(q["nonce"], sub, email))
        self.assertEqual(r.status_code, 303, r.text)
        return self.trade(r, next_url)

    def trade(self, r, next_url=SITE):
        loc = r.headers["location"]
        self.assertTrue(loc.startswith(next_url + ("&" if "?" in next_url else "?") + "code="), loc)
        one = urllib.parse.parse_qs(urllib.parse.urlsplit(loc).query)["code"][0]
        t = self.c.post("/api/session", json={"code": one})
        self.assertEqual(t.status_code, 200, t.text)
        return {"Authorization": "Bearer " + t.json()["token"]}

    def good_request(self, days=1):
        d = next_weekday(datetime.date.today() + datetime.timedelta(days=days))
        return {"values": {"呼び名": "はな", "取りに来る日": d.isoformat()},
                "tables": {"品物": [{"品物": "食パン", "数": "2"}, {"品物": "あんパン", "数": "3"}]}}

    # ---- sign-in ----

    def test_authorize_urls(self):
        a = self.start("apple")
        self.assertEqual(a["response_mode"], "form_post")
        self.assertEqual(a["scope"], "email")
        self.assertEqual(a["redirect_uri"], "https://yoyaku.example/callback/apple")
        g = self.start("google")
        self.assertNotIn("response_mode", g)
        self.assertEqual(g["scope"], "openid email")

    def test_apple_and_google_sign_in(self):
        for p in ("apple", "google"):
            h = self.sign_in(p, f"{p}-user", f"{p}@example.jp")
            me = self.c.get("/api/me", headers=h).json()
            self.assertEqual(me, {"provider": p, "email": f"{p}@example.jp", "shop": False})
        apple_secret = [s for n, s in seen_secrets if n == "apple"][-1]
        self.assertEqual(jwt.get_unverified_header(apple_secret)["alg"], "ES256")

    def test_app_link_return(self):
        self.sign_in("apple", "app-user", next_url="hanakopan://signed-in")

    def test_unknown_return_is_refused(self):
        r = self.c.get("/login/google", params={"next": "https://evil.example/"})
        self.assertEqual(r.status_code, 400)

    def test_state_is_used_once(self):
        q = self.start("google")
        c = code(q["nonce"], "once")
        self.assertEqual(self.finish("google", q, c).status_code, 303)
        self.assertEqual(self.finish("google", q, c).status_code, 400)

    def test_state_of_other_provider_is_refused(self):
        q = self.start("google")
        r = self.c.post("/callback/apple", data={"code": code(q["nonce"], "x"), "state": q["state"]})
        self.assertEqual(r.status_code, 400)

    def test_broken_id_tokens_are_refused(self):
        for bad in ({"override": {"nonce": "other"}}, {"override": {"aud": "someone-else"}},
                    {"override": {"iss": "https://evil.example"}},
                    {"override": {"exp": int(time.time()) - 10}}, {"other_key": True}):
            for p in ("apple", "google"):
                q = self.start(p)
                spec = {"nonce": q["nonce"], "sub": "bad"} | bad
                c = base64.urlsafe_b64encode(json.dumps(spec).encode()).decode()
                self.assertEqual(self.finish(p, q, c).status_code, 400, (p, bad))

    def test_unverified_email_is_not_kept(self):
        q = self.start("google")
        c = code(q["nonce"], "nv", "nv@example.jp", override={"email_verified": False})
        h = self.trade(self.finish("google", q, c))
        self.assertEqual(self.c.get("/api/me", headers=h).json()["email"], "")

    def test_fake_sign_in_page(self):
        # The page people click on when trying fake_id.py by hand
        import html
        import re
        import urllib.request
        for p in ("apple", "google"):
            r = self.c.get(f"/login/{p}", params={"next": SITE})
            with urllib.request.urlopen(r.headers["location"]) as page:
                text = page.read().decode()
            self.assertIn("owner@example.jp", text)
            if p == "apple":
                c = html.unescape(re.search(r'name="code" value="([^"]+)"', text).group(1))
                st = html.unescape(re.search(r'name="state" value="([^"]+)"', text).group(1))
                back = self.c.post("/callback/apple", data={"code": c, "state": st})
            else:
                url = html.unescape(re.search(r'href="([^"]+)"', text).group(1))
                back = self.c.get("/callback/google?" + urllib.parse.urlsplit(url).query)
            self.trade(back)

    # ---- requests ----

    def test_request_cancel_and_shop_view(self):
        h = self.sign_in("apple", "hana", "hana@privaterelay.appleid.com")
        r = self.c.post("/api/requests", headers=h, json=self.good_request() | {"extra": "not kept"})
        self.assertEqual(r.status_code, 200, r.text)
        rid = r.json()["id"]
        mine = self.c.get("/api/requests", headers=h).json()
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["tables"]["品物"][1], {"品物": "あんパン", "数": "3"})
        self.assertNotIn("extra", mine[0])
        # Another person can neither see nor cancel it
        other = self.sign_in("google", "someone", "someone@example.jp")
        self.assertEqual(self.c.get("/api/requests", headers=other).json(), [])
        self.assertEqual(self.c.delete(f"/api/requests/{rid}", headers=other).status_code, 404)
        self.assertEqual(self.c.get("/api/shop/requests", headers=other).status_code, 403)
        # The shop sees it, with the email
        owner = self.sign_in("google", "owner", "owner@example.jp")
        shop = self.c.get("/api/shop/requests", headers=owner).json()
        self.assertIn(rid, [x["id"] for x in shop])
        self.assertEqual([x for x in shop if x["id"] == rid][0]["email"], "hana@privaterelay.appleid.com")
        self.assertEqual(self.c.delete(f"/api/requests/{rid}", headers=h).status_code, 200)
        self.assertEqual(self.c.get("/api/requests", headers=h).json(), [])

    def test_request_rules(self):
        h = self.sign_in("google", "rules", "rules@example.jp")
        today = datetime.date.today()
        closed = today + datetime.timedelta(days=(6 - today.weekday()) % 7 or 7)  # a Sunday ahead
        cases = [
            ({"values": {"呼び名": "", "取りに来る日": ""}, "tables": {}}, "呼び名を書きます"),
            (self.good_request() | {"values": {"呼び名": "a", "取りに来る日": today.isoformat()}}, "取りに来る日は"),
            (self.good_request() | {"values": {"呼び名": "a", "取りに来る日": (today + datetime.timedelta(days=30)).isoformat()}}, "取りに来る日は"),
            (self.good_request() | {"values": {"呼び名": "a", "取りに来る日": closed.isoformat()}}, "休みの日"),
            (self.good_request() | {"tables": {"品物": [{"品物": "ケーキ", "数": "1"}]}}, "どれかを書きます"),
            (self.good_request() | {"tables": {"品物": [{"品物": "食パン", "数": "11"}]}}, "1 から 10"),
            (self.good_request() | {"tables": {"品物": [{"品物": "食パン", "数": "0"}]}}, "1 から 10"),
            (self.good_request() | {"tables": {}}, "品物を 1 つ以上"),
        ]
        for body, word in cases:
            r = self.c.post("/api/requests", headers=h, json=body)
            self.assertEqual(r.status_code, 422, body)
            self.assertTrue(any(word in p for p in r.json()["detail"]), (word, r.json()))

    def test_limit_per_person(self):
        h = self.sign_in("google", "many", "many@example.jp")
        for _ in range(3):
            self.assertEqual(self.c.post("/api/requests", headers=h, json=self.good_request()).status_code, 200)
        r = self.c.post("/api/requests", headers=h, json=self.good_request())
        self.assertEqual(r.status_code, 422)

    def test_past_requests_are_dropped(self):
        h = self.sign_in("google", "past", "past@example.jp")
        self.assertEqual(self.c.post("/api/requests", headers=h, json=self.good_request()).status_code, 200)
        db = self.app.state.db
        db.run("UPDATE requests SET due = '2000-01-01' WHERE sub = 'past'")
        self.app.state.purge(force=True)
        self.assertEqual(self.c.get("/api/requests", headers=h).json(), [])
        self.assertIsNone(db.one("SELECT * FROM requests WHERE sub = 'past'"))

    def test_signed_out(self):
        self.assertEqual(self.c.get("/api/requests").status_code, 401)
        h = self.sign_in("google", "bye")
        self.assertEqual(self.c.post("/api/logout", headers=h).status_code, 200)
        self.assertEqual(self.c.get("/api/requests", headers=h).status_code, 401)

    def test_code_is_used_once(self):
        q = self.start("google")
        loc = self.finish("google", q, code(q["nonce"], "code-once")).headers["location"]
        one = urllib.parse.parse_qs(urllib.parse.urlsplit(loc).query)["code"][0]
        self.assertEqual(self.c.post("/api/session", json={"code": one}).status_code, 200)
        self.assertEqual(self.c.post("/api/session", json={"code": one}).status_code, 400)
        self.assertEqual(self.c.post("/api/session", json={"code": "made-up"}).status_code, 400)

    def test_return_url_with_query(self):
        self.sign_in("google", "q-user", next_url=SITE + "?from=site")

    def test_session_token_is_stored_hashed(self):
        h = self.sign_in("google", "hash")
        token = h["Authorization"][7:]
        self.assertIsNone(self.app.state.db.one("SELECT * FROM sessions WHERE token = ?", (token,)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
