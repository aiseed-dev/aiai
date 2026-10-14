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


WAKU_PAGES = [("/skills/a.html", "A"), ("/skills/b.html", "B"), ("/skills/c.html", "C"),
              ("/shoukai/x.html", "X"), ("/shoukai/y.html", "Y"), ("/kiji/k.html", "K"), ("/news/2026-10-14.html", "N")]


class WakuTest(unittest.TestCase):
    def choose(self, page, clicks=None, views=None, shown=None):
        return kj.choose_waku(page, WAKU_PAGES, clicks or {}, views or {}, shown or {})

    def test_most_pressed_then_most_viewed_then_path(self):
        cards = self.choose("/kiji/k.html", clicks={("/kiji/k.html", "/skills/b.html"): 3},
                            views={"/skills/c.html": 9, "/shoukai/y.html": 5})
        self.assertEqual(cards[:2], ["/skills/b.html", "/shoukai/y.html"])  # 1st guide, 2nd introduction
        self.assertEqual(self.choose("/kiji/k.html")[:2], ["/skills/a.html", "/shoukai/x.html"])  # by path when equal

    def test_the_more_pressed_of_the_first_two_goes_first(self):
        cards = self.choose("/kiji/k.html", clicks={("/kiji/k.html", "/shoukai/x.html"): 4, ("/kiji/k.html", "/skills/a.html"): 1})
        self.assertEqual(cards[:2], ["/shoukai/x.html", "/skills/a.html"])

    def test_the_third_is_the_one_shown_on_the_fewest_days(self):
        cards = self.choose("/kiji/k.html", shown={"/skills/b.html": 2, "/skills/c.html": 1, "/shoukai/y.html": 3})
        self.assertEqual(len(cards), 3)
        self.assertEqual(cards[2], "/skills/c.html")  # b: 2, c: 1, y: 3, and a and x are the 1st and 2nd

    def test_the_open_page_is_left_out_and_there_are_three_at_most(self):
        cards = self.choose("/skills/a.html")
        self.assertNotIn("/skills/a.html", cards)
        self.assertEqual(len(cards), 3)
        self.assertTrue(all(c.startswith(("/skills/", "/shoukai/")) for c in cards))

    def test_a_day_is_chosen_from_the_summaries_and_undone(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec, out = os.path.join(tmp, "rec"), os.path.join(tmp, "out")
            os.makedirs(rec)
            os.makedirs(out)
            self.assertEqual(kj.waku_step(rec, out, WAKU_PAGES, "2026-10-14"), "")  # no record: nothing chosen
            kj.save(os.path.join(rec, "2026-10-13.json"),
                    {"pages": [{"path": "/skills/b.html", "views": 5}], "moves": [["/kiji/k.html", "/skills/b.html", 2, 1]]})
            kj.waku_step(rec, out, WAKU_PAGES, "2026-10-14")
            waku = kj.load(os.path.join(out, "waku.json"), {})
            self.assertEqual(waku["/kiji/k.html"][0], "/skills/b.html")
            self.assertNotIn("/", waku)  # the top page has no frame
            self.assertIn("「あわせて読む」を選び直した", kj.read(os.path.join(out, "kiroku.adoc")))
            kj.waku_step(rec, out, WAKU_PAGES, "2026-10-15")
            self.assertEqual(sorted(kj.load(os.path.join(out, "waku-history.json"), {})), ["2026-10-14", "2026-10-15"])
            kj.undo(out, "2026-10-15")
            self.assertEqual(sorted(kj.load(os.path.join(out, "waku-history.json"), {})), ["2026-10-14"])
            self.assertEqual(kj.load(os.path.join(out, "waku.json"), {}), waku)

    def test_only_a_change_of_the_first_or_second_is_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec, out = os.path.join(tmp, "rec"), os.path.join(tmp, "out")
            os.makedirs(rec)
            os.makedirs(out)
            kj.save(os.path.join(rec, "2026-10-13.json"), {"pages": [], "moves": []})
            kj.waku_step(rec, out, WAKU_PAGES, "2026-10-14")
            kj.save(os.path.join(rec, "2026-10-14.json"), {"pages": [], "moves": [["/kiji/k.html", "/skills/c.html", 4, 0]]})
            text = kj.waku_step(rec, out, WAKU_PAGES, "2026-10-15")
            self.assertEqual(text.count("の変更"), 1)  # only /kiji/k.html
            self.assertIn(":ページ: /kiji/k.html", text)
            self.assertIn("/skills/c.html", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
