# SPDX-License-Identifier: AGPL-3.0-or-later
"""python kaiseki/test_server.py  (standard library only)"""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
import server  # noqa: E402

VID = "0f8c6c6e-3d3a-4b8e-9a51-1c2d3e4f5a6b"
VID2 = "1a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d"
VID3 = "2b3c4d5e-6f7a-4b2c-9d3e-4f5a6b7c8d9e"
SID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


class Kaiseki(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.srv = server.serve(0, os.path.join(self.dir.name, "k.db"), {"weather.time-j.net"}, "report-secret", "link-secret")
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.dir.cleanup()

    def call(self, method, path, data=None, token="", origin=""):
        req = urllib.request.Request(self.base + path, method=method)
        if data is not None:
            req.data = json.dumps(data).encode()
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        if origin:
            req.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(req) as r:
                body = r.read()
                return r.status, (json.loads(body) if body else None), r.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null"), e.headers

    def hit(self, **kw):
        d = {"site": "weather.time-j.net", "path": "/point/44132", "title": "東京", "referrer": "www.google.com",
             "utm": "", "lang": "ja", "tz": "Asia/Tokyo", "screen": "390x844", "ua": "Mozilla/5.0", "sid": SID}
        d.update(kw)
        return self.call("POST", "/v1/hit", d, origin="https://weather.time-j.net")

    def test_views_are_kept_with_the_fields_and_without_an_address(self):
        status, _, headers = self.hit(vid=VID)
        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "https://weather.time-j.net")
        _, mine, _ = self.call("GET", f"/v1/mine?vid={VID}")
        h = mine["hits"][0]
        self.assertEqual((h["site"], h["path"], h["event"], h["referrer"], h["lang"], h["screen"], h["sid"]),
                         ("weather.time-j.net", "/point/44132", "view", "www.google.com", "ja", "390x844", SID))
        self.assertNotIn("ip", h)

    def test_hits_from_other_sites_or_broken_bodies_are_dropped(self):
        self.hit(site="evil.example.jp", vid=VID)
        self.hit(path="no-slash", vid=VID)
        self.hit(event="DROP TABLE", vid=VID)
        self.call("POST", "/v1/hit", ["not", "a", "dict"])
        _, mine, _ = self.call("GET", f"/v1/mine?vid={VID}")
        self.assertEqual(mine["hits"], [])

    def test_without_consent_the_view_is_counted_without_an_id(self):
        self.hit(vid="")
        self.hit(vid="not-a-uuid")
        _, rep, _ = self.call("GET", "/v1/report?site=weather.time-j.net&from=2000-01-01&to=2999-12-31", token="report-secret")
        self.assertEqual(rep["rows"][0]["views"], 2)
        self.assertEqual(rep["rows"][0]["people"], 0)

    def test_leave_keeps_the_seconds_and_events_are_named(self):
        self.hit(vid=VID, event="leave", seconds=42)
        self.hit(vid=VID, event="signup")
        _, mine, _ = self.call("GET", f"/v1/mine?vid={VID}")
        self.assertEqual([(h["event"], h["seconds"]) for h in mine["hits"]], [("leave", 42), ("signup", None)])

    def test_leave_keeps_how_far_down_and_events_keep_a_short_value(self):
        self.hit(vid=VID, event="leave", seconds=10, scroll=75)
        self.hit(vid=VID, event="leave", seconds=10, scroll=150)
        self.hit(vid=VID, event="search", value="雨 " * 80)
        self.hit(vid=VID, value="views have no value")
        _, mine, _ = self.call("GET", f"/v1/mine?vid={VID}")
        self.assertEqual([(h["scroll"], h["value"]) for h in mine["hits"]],
                         [(75, ""), (None, ""), (None, ("雨 " * 80)[:100]), (None, "")])

    def test_a_database_made_before_scroll_and_value_gets_the_columns(self):
        import sqlite3
        path = os.path.join(self.dir.name, "old.db")
        old = sqlite3.connect(path)
        # The table as it was on deb2 before 2026-10-08
        old.execute("CREATE TABLE hits (ts TEXT NOT NULL, day TEXT NOT NULL, site TEXT NOT NULL, path TEXT NOT NULL, "
                    "event TEXT NOT NULL, seconds INTEGER, title TEXT NOT NULL, referrer TEXT NOT NULL, "
                    "utm TEXT NOT NULL, lang TEXT NOT NULL, tz TEXT NOT NULL, screen TEXT NOT NULL, ua TEXT NOT NULL, "
                    "sid TEXT, vid TEXT)")
        old.execute("INSERT INTO hits VALUES ('2026-10-07T00:00:00', '2026-10-07', 'weather.time-j.net', '/', 'view', "
                    "NULL, '', '', '', 'ja', '', '', '', NULL, ?)", (VID,))
        old.commit()
        old.close()
        store = server.Store(path)
        store.add(server.clean_hit(json.dumps({"site": "weather.time-j.net", "path": "/", "event": "leave",
                                               "scroll": 40, "vid": VID}), {"weather.time-j.net"}))
        self.assertEqual([(h["event"], h["scroll"]) for h in store.mine(VID)["hits"]], [("view", None), ("leave", 40)])

    def test_link_needs_the_member_systems_token(self):
        self.hit(vid=VID)
        self.assertEqual(self.call("POST", "/v1/link", {"vid": VID, "member": "m1"})[0], 403)
        self.assertEqual(self.call("POST", "/v1/link", {"vid": VID, "member": "m1"}, token="report-secret")[0], 403)
        self.assertEqual(self.call("POST", "/v1/link", {"vid": VID, "member": "m1"}, token="link-secret")[0], 204)
        _, mine, _ = self.call("GET", f"/v1/mine?vid={VID}")
        self.assertEqual(mine["members"], ["m1"])

    def test_a_member_reads_together_across_devices(self):
        self.hit(vid=VID, path="/point/1")
        self.hit(vid=VID2, path="/point/2")
        self.hit(vid=VID3, path="/point/3")
        for v in (VID, VID2):
            self.call("POST", "/v1/link", {"vid": v, "member": "m1"}, token="link-secret")
        self.call("POST", "/v1/link", {"vid": VID3, "member": "m9"}, token="link-secret")
        self.assertEqual(self.call("GET", "/v1/member?member=m1")[0], 403)
        _, got, _ = self.call("GET", "/v1/member?member=m1", token="report-secret")
        self.assertEqual(sorted(h["path"] for h in got["hits"]), ["/point/1", "/point/2"])

    def test_a_person_forgets_their_id_and_a_member_who_leaves_is_forgotten(self):
        self.hit(vid=VID)
        self.hit(vid=VID2)
        self.call("POST", "/v1/link", {"vid": VID2, "member": "m2"}, token="link-secret")
        self.call("POST", "/v1/link", {"vid": VID, "member": "m3"}, token="link-secret")
        self.assertEqual(self.call("POST", "/v1/forget", {"vid": VID})[1], {"deleted": 1})
        self.assertEqual(self.call("GET", "/v1/member?member=m3", token="report-secret")[1], {"hits": []})
        self.assertEqual(self.call("GET", f"/v1/mine?vid={VID}")[1], {"members": [], "hits": []})
        self.assertEqual(self.call("POST", "/v1/forget-member", {"member": "m2"})[0], 403)
        self.assertEqual(self.call("POST", "/v1/forget-member", {"member": "m2"}, token="link-secret")[1], {"deleted": 1})
        self.assertEqual(self.call("GET", f"/v1/mine?vid={VID2}")[1], {"members": [], "hits": []})

    def test_only_https_pages_of_the_sites_and_the_extra_origins_may_read(self):
        self.assertEqual(self.hit(vid=VID)[2]["Access-Control-Allow-Origin"], "https://weather.time-j.net")
        status, _, headers = self.call("GET", f"/v1/mine?vid={VID}", origin="http://127.0.0.1:8001")
        self.assertIsNone(headers["Access-Control-Allow-Origin"])
        local = server.serve(0, os.path.join(self.dir.name, "l.db"), {"weather.time-j.net"}, "", "",
                             extra_origins=["http://127.0.0.1:8001"])
        threading.Thread(target=local.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{local.server_address[1]}/v1/mine?vid={VID}")
            req.add_header("Origin", "http://127.0.0.1:8001")
            with urllib.request.urlopen(req) as r:
                self.assertEqual(r.headers["Access-Control-Allow-Origin"], "http://127.0.0.1:8001")
        finally:
            local.shutdown()
            local.server_close()

    def test_with_no_sites_listed_any_https_site_is_counted_as_its_own_origin(self):
        anyw = server.serve(0, os.path.join(self.dir.name, "a.db"), set(), "report-secret", "")
        threading.Thread(target=anyw.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{anyw.server_address[1]}"

        def post(site, origin):
            req = urllib.request.Request(base + "/v1/hit", method="POST",
                                         data=json.dumps({"site": site, "path": "/", "vid": VID}).encode())
            if origin:
                req.add_header("Origin", origin)
            with urllib.request.urlopen(req) as r:
                return r.headers.get("Access-Control-Allow-Origin")
        try:
            self.assertEqual(post("shop.example.jp", "https://shop.example.jp"), "https://shop.example.jp")
            post("weather.time-j.net", "https://shop.example.jp")  # a page naming another site
            post("shop.example.jp", "http://shop.example.jp")      # not HTTPS
            post("shop.example.jp", "")                            # no Origin
            with urllib.request.urlopen(f"{base}/v1/mine?vid={VID}") as r:
                hits = json.loads(r.read())["hits"]
            self.assertEqual([h["site"] for h in hits], ["shop.example.jp"])
        finally:
            anyw.shutdown()
            anyw.server_close()

    def test_report_needs_its_token(self):
        self.assertEqual(self.call("GET", "/v1/report?site=weather.time-j.net")[0], 403)


if __name__ == "__main__":
    unittest.main()
