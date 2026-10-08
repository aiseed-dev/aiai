# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tries site/make_site.py: Markdown and the news adoc as aiai writes them,
and a build of the whole site into a temporary folder.

    python site/test_site.py
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_site  # noqa: E402


class MarkdownTest(unittest.TestCase):
    def test_wrapped_japanese_lines_join_without_a_space(self):
        self.assertEqual(make_site.markdown("決めるのは\n本人です。"), "<p>決めるのは本人です。</p>")
        self.assertEqual(make_site.markdown("Claude and\nGemini"), "<p>Claude and Gemini</p>")

    def test_lists_with_wrapped_and_nested_items(self):
        out = make_site.markdown("1. **長所**: 強み\n   - 読む物: 対話\n   - 書き方: 3 つまで\n2. 次")
        self.assertEqual(out, "<ol><li><strong>長所</strong>: 強み<ul><li>読む物: 対話</li><li>書き方: 3 つまで</li></ul>"
                              "</li><li>次</li></ol>")
        self.assertEqual(make_site.markdown("- 一つ目の\n  続き\n- 二つ目"), "<ul><li>一つ目の続き</li><li>二つ目</li></ul>")

    def test_links_urls_code_and_escaping(self):
        out = make_site.markdown("[説明](https://example.jp/a) と [ファイル](../genba/) と `<x>` と https://example.jp/b 、<b>")
        self.assertIn('<a href="https://example.jp/a">説明</a>', out)
        self.assertNotIn("../genba/", out)
        self.assertIn("<code>&lt;x&gt;</code>", out)
        self.assertIn('<a href="https://example.jp/b">https://example.jp/b</a>', out)
        self.assertIn("&lt;b&gt;", out)

    def test_table_and_code_block(self):
        out = make_site.markdown("| a | b |\n|---|---|\n| 1 | 2 |\n\n```\nx < y\n```")
        self.assertIn("<th>a</th>", out)
        self.assertIn("<td>2</td>", out)
        self.assertIn("<pre><code>x &lt; y</code></pre>", out)


NEWS = """= aiai ニュース 2026-09-30
:日付: 2026-09-30

== 架空の見出し
:分野: 鳥獣対策
:国・地域: 日本

何があったかを、
2 文で書きます。

出典: 架空の資料、https://example.jp/a 、2026-09-30 に確かめました +
出典: 架空の資料 2、https://example.jp/b 、2026-09-30 に確かめました
"""


class NewsTest(unittest.TestCase):
    def test_one_day(self):
        title, date, entries = make_site.read_news(NEWS)
        self.assertEqual((title, date, len(entries)), ("aiai ニュース 2026-09-30", "2026-09-30", 1))
        e = entries[0]
        self.assertEqual(e["attrs"], {"分野": "鳥獣対策", "国・地域": "日本"})
        self.assertEqual(e["paras"][0], (False, "何があったかを、2 文で書きます。"))
        src, body = e["paras"][1]
        self.assertTrue(src)
        self.assertEqual(body.count("<br>"), 1)
        self.assertIn('<a href="https://example.jp/b">', body)


class BuildTest(unittest.TestCase):
    def test_the_whole_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            news = os.path.join(tmp, "news")
            os.makedirs(news)
            with open(os.path.join(news, "2026-09-30.adoc"), "w", encoding="utf-8") as f:
                f.write(NEWS)
            out = os.path.join(tmp, "public")
            make_site.OUT = out
            days = make_site.load_news(news)
            make_site.load_news = lambda folder=None: days
            make_site.main()
            for path in ("index.html", "top.css", "kangaekata.html", "news/index.html", "news/2026-09-30.html",
                         "skills/rireki.html", "skills/keikaku.html", "sagasu.html", "sagasu.json", "404.html",
                         "kaiseki/index.html", "kaiseki.js", "kaiseki-aiai.js", "sagasu.js"):
                self.assertTrue(os.path.exists(os.path.join(out, path)), path)
            with open(os.path.join(out, "index.html"), encoding="utf-8") as f:
                top = f.read()
            self.assertIn("架空の見出し", top)
            with open(os.path.join(out, "skills", "rireki.html"), encoding="utf-8") as f:
                skill = f.read()
            self.assertIn("/skills/rireki.zip", skill)
            self.assertIn("name: rireki", skill)  # the whole SKILL.md, for the copy button
            # every page sends its record to this site's own server, with no cookie
            for text in (top, skill):
                self.assertIn('data-to="/kaiseki" data-ask="no"', text)
            with open(os.path.join(out, "sagasu.json"), encoding="utf-8") as f:
                index = json.load(f)
            self.assertIn({"u": "/news/2026-09-30.html", "t": "ニュース 2026-09-30"},
                          [{"u": e["u"], "t": e["t"]} for e in index])
            self.assertTrue(any(e["u"].startswith("/kangaekata.html#") and e["h"] for e in index))
            self.assertTrue(all(set(e) == {"u", "t", "h", "x"} for e in index))


if __name__ == "__main__":
    unittest.main(verbosity=2)
