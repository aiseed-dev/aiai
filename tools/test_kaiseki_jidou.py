# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tries the checks of tools/kaiseki_jidou.py on what Gemini might answer,
including answers a reader's search words tried to steer.

    python tools/test_kaiseki_jidou.py
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kaiseki_jidou as kj  # noqa: E402

PAGES = [("/skills/rireki.html", "度々聞いていることを、アプリにする"), ("/skills/genba.html", "現場で VLM を使う")]


class CheckTest(unittest.TestCase):
    def test_fixes_within_the_limits_pass(self):
        answer = {"yougo": [{"word": "繰り返し", "page": 0, "mita": "10-12 に 3 回"}],
                  "annai": [{"from": 0, "to": 1, "text": "写真を読む AI も使えます", "mita": "10-12 に 2 回"}],
                  "kiji": [], "kakunin": []}
        yougo, annai, kiji, _ = kj.checked(answer, PAGES, {})
        self.assertEqual(yougo[0]["page"], "/skills/rireki.html")
        self.assertEqual((annai[0]["from"], annai[0]["to"]), ("/skills/rireki.html", "/skills/genba.html"))

    def test_pages_outside_the_list_and_too_many_are_dropped(self):
        answer = {"yougo": [{"word": f"w{i}", "page": 0, "mita": ""} for i in range(9)] + [{"word": "x", "page": 7, "mita": ""}],
                  "annai": [{"from": 0, "to": 0, "text": "同じページ", "mita": ""}, {"from": 0, "to": 9, "text": "無い", "mita": ""}],
                  "kiji": [], "kakunin": []}
        yougo, annai, _, _ = kj.checked(answer, PAGES, {})
        self.assertEqual(len(yougo), kj.MAX_YOUGO)
        self.assertEqual(annai, [])

    def test_an_article_keeps_only_the_sites_own_links(self):
        body = ("詳しくは [手引き](/skills/rireki.html) と [ここ](https://evil.example/x) を見てください。"
                "<script>alert(1)</script> https://evil.example/y も。" + "本文です。" * 30)
        _, _, kiji, _ = kj.checked({"yougo": [], "annai": [], "kakunin": [],
                                    "kiji": [{"title": "<b>題</b>", "subtitle": "", "body": body, "mita": ""}]}, PAGES, {})
        text = kiji[0]["body"]
        self.assertIn("[手引き](https://aiai.aiseed.dev/skills/rireki.html)", text)
        self.assertNotIn("evil.example", text)
        self.assertNotIn("<script>", text)
        self.assertEqual(kiji[0]["title"], "題")

    def test_words_that_are_addresses_or_done_before_are_dropped(self):
        answer = {"yougo": [{"word": "https://evil.example", "page": 0, "mita": ""}, {"word": "前と同じ", "page": 0, "mita": ""}],
                  "annai": [], "kiji": [], "kakunin": []}
        yougo, _, _, _ = kj.checked(answer, PAGES, {"yougo": [{"word": "前と同じ"}]})
        self.assertEqual(yougo, [])

    def test_stop_and_undo(self):
        with tempfile.TemporaryDirectory() as out:
            open(os.path.join(out, "STOP"), "w").close()
            self.assertEqual(kj.run(out, out, os.path.join(out, "none.json")), 0)  # does nothing, calls no AI
            os.remove(os.path.join(out, "STOP"))
            kj.save(os.path.join(out, "yougo.json"), [{"word": "a", "page": "/", "hi": "2026-10-14"},
                                                      {"word": "b", "page": "/", "hi": "2026-10-15"}])
            kj.undo(out, "2026-10-14")
            self.assertEqual([y["word"] for y in kj.load(os.path.join(out, "yougo.json"), [])], ["b"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
