# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tries tools/kaiseki_matome.py on a record made by kaiseki/server.py.

    python tools/test_kaiseki_matome.py
"""
import datetime
import os
import sqlite3
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "kaiseki"))
import kaiseki_matome as km  # noqa: E402
import server  # noqa: E402

DAY = datetime.date(2026, 10, 8)


def hit(**kw):
    base = {"site": "aiai.aiseed.dev", "path": "/kangaekata.html", "event": "view", "seconds": None, "scroll": None,
            "value": "", "title": "考え方 — aiai", "referrer": "", "utm": "", "lang": "ja", "tz": "Asia/Tokyo",
            "screen": "390x844", "ua": "test", "sid": None, "vid": None}
    base.update(kw)
    return base


class SummaryTest(unittest.TestCase):
    def test_one_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "k.db")
            store = server.Store(db)
            for h in (hit(referrer="www.google.com"), hit(screen="1920x1080"),
                      hit(event="leave", seconds=40, scroll=95), hit(event="leave", seconds=10, scroll=30),
                      hit(event="section", value="#kiroku 記録"), hit(event="search", value="鳥獣害"),
                      hit(event="search", value="鳥獣害"), hit(event="nohit", value="補助金"),
                      hit(event="notfound", path="/skills/hojokin.html", value="/skills/hojokin.html"), hit(site="example.jp")):
                store.add(h)
            # put every record inside the day, Japan time
            con = sqlite3.connect(db)
            con.execute("UPDATE hits SET ts = '2026-10-08T03:00:00+00:00'")
            con.commit()
            con.close()
            r = km.summary(db, "aiai.aiseed.dev", DAY)
        self.assertEqual(r["views"], 2)
        self.assertEqual(r["phone_share"], 0.5)
        page = r["pages"][0]
        self.assertEqual((page["path"], page["views"], page["seconds"], page["scroll"], page["to_end"]),
                         ("/kangaekata.html", 2, 25, 62, 0.5))
        self.assertEqual(r["sections"]["/kangaekata.html"], [["#kiroku 記録", 1, 0.5]])
        self.assertEqual(r["searches"], [["鳥獣害", 2]])
        self.assertEqual(r["nohit"], [["補助金", 1]])
        self.assertEqual(r["notfound"], [["/skills/hojokin.html", 1]])
        self.assertEqual(r["referrers"], [["www.google.com", 1]])
        text = km.adoc(r)
        self.assertIn("= サイトの読まれ方 2026-10-08", text)
        self.assertIn("- 鳥獣害: 2 回", text)

    def test_the_day_is_japan_time(self):
        self.assertEqual(km.bounds(DAY), ("2026-10-07T15:00:00+00:00", "2026-10-08T15:00:00+00:00"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
