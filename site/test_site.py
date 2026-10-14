# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tries site/make_site.py: Markdown, the news adoc and the user manual (AsciiDoc) as
aiai writes them, and a build of the whole site into a temporary folder.

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


ADOC = """= 題
:日付: 2026-10-14

はじめの
文です。`code <x>` と https://example.jp/[リンク] と *太字* です。

[[ankaa]]
== 第 1 節

. 1 つ目の
  続き
. 2 つ目
** 入れ子

____
引用です
____

image::images/zu.svg[図の説明]

[cols="1,2"]
|===
| 段 | すること

| 1 見つける | 履歴から
|===

=== 小節

----
x < y
----
"""


class AdocTest(unittest.TestCase):
    def test_the_manual_subset(self):
        title, sections = make_site.read_adoc(ADOC, "/i/")
        self.assertEqual(title, "題")
        self.assertEqual([(x["level"], x["title"], x["id"]) for x in sections],
                         [(0, "", ""), (2, "第 1 節", "ankaa"), (3, "小節", "s2")])
        self.assertIn("<p>はじめの文です。<code>code &lt;x&gt;</code> と", sections[0]["html"])
        self.assertIn('<a href="https://example.jp/">リンク</a>', sections[0]["html"])
        self.assertIn("<strong>太字</strong>", sections[0]["html"])
        body = sections[1]["html"]
        self.assertIn("<ol><li>1 つ目の続き</li><li>2 つ目<ul><li>入れ子</li></ul></li></ol>", body)
        self.assertIn("<blockquote><p>引用です</p></blockquote>", body)
        self.assertIn('<img src="/i/zu.svg" alt="図の説明">', body)
        self.assertIn("<th>段</th><th>すること</th>", body)
        self.assertIn("<td>1 見つける</td><td>履歴から</td>", body)
        self.assertIn("<pre><code>x &lt; y</code></pre>", sections[2]["html"])


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
                         "kaiseki/index.html", "kaiseki.js", "kaiseki-aiai.js", "sagasu.js", "tsukaikata.html",
                         "tsukaikata/images/nagare.svg", "tsukaikata/manual.pdf", "eizou.html"):
                self.assertTrue(os.path.exists(os.path.join(out, path)), path)
            self.assertFalse(os.path.exists(os.path.join(out, "katsuyou.html")))  # server.py sends it to 使い方
            # the page 使い方 is the short form of the manual: the four sections, the figure, the links to the rest
            with open(os.path.join(out, "tsukaikata.html"), encoding="utf-8") as f:
                usage = f.read()
            for text in ("手引きを AI に読ませる", "アプリを作る流れ", "ほかの手引き", "一緒に使う物", 'id="tools"',
                         "/tsukaikata/images/nagare.svg", 'href="/app/"', 'href="/tsukaikata/manual.pdf"'):
                self.assertIn(text, usage)
            for text in ("知らせが出たとき", "を使う前に", "<h2 id=\"s13\">8 テストする"):  # the rest of the manual is in the app
                self.assertNotIn(text, usage)
            with open(os.path.join(out, "index.html"), encoding="utf-8") as f:
                top = f.read()
            self.assertIn("度々聞いていることを、アプリにする", top)
            self.assertNotIn("/katsuyou.html", top)
            self.assertIn('href="/tsukaikata.html#tools"', top)
            # the flow: steps 1 to 8, the two questions and the end; no step that is only "作る"
            for text in ("1 何度も頼むことを見つける", "2 今あるアプリを探す", "不満はあるか", "3 どう良くするかを考える",
                         "4 要望か、自分で作るか", "5 今あるアプリの課題を集める", "6 設計書とマニュアルを作る", "7 実装する",
                         "8 テストする", "直す所はあるか", "使い始める"):
                self.assertIn(text, top)
            self.assertNotIn('nagare-step tsukuru">作る<', top)
            self.assertEqual(top.count('class="nagare-try"'), 5)
            with open(os.path.join(out, "news", "index.html"), encoding="utf-8") as f:
                self.assertIn("架空の見出し", f.read())
            with open(os.path.join(out, "skills", "rireki.html"), encoding="utf-8") as f:
                skill = f.read()
            self.assertIn("/skills/rireki.zip", skill)
            self.assertIn("name: rireki", skill)  # the whole SKILL.md, for the copy button
            # every page sends its record to this site's own server, with no cookie
            for text in (top, skill, usage):
                self.assertIn('data-to="/kaiseki" data-ask="no"', text)
                self.assertNotIn("/katsuyou.html", text)
            with open(os.path.join(out, "sagasu.json"), encoding="utf-8") as f:
                index = json.load(f)
            self.assertIn({"u": "/news/2026-09-30.html", "t": "ニュース 2026-09-30"},
                          [{"u": e["u"], "t": e["t"]} for e in index])
            self.assertTrue(any(e["u"].startswith("/kangaekata.html#") and e["h"] for e in index))
            self.assertTrue(all({"u", "t", "h", "x"} <= set(e) <= {"u", "t", "h", "x", "k"} for e in index))



class JidouTest(unittest.TestCase):
    """The site with the fixes Gemini made by itself (tools/kaiseki_jidou.py) in AIAI_JIDOU."""

    def test_the_fixes_show_on_the_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            jidou = os.path.join(tmp, "jidou")
            os.makedirs(os.path.join(jidou, "kiji"))
            with open(os.path.join(jidou, "yougo.json"), "w", encoding="utf-8") as f:
                json.dump([{"word": "くりかえし", "page": "/skills/rireki.html", "hi": "2026-10-14"}], f)
            with open(os.path.join(jidou, "annai.json"), "w", encoding="utf-8") as f:
                json.dump([{"from": "/skills/rireki.html", "to": "/skills/genba.html", "text": "写真も読ませられます",
                            "hi": "2026-10-14"}], f)
            with open(os.path.join(jidou, "kiji", "jidou-2026-10-14-1.md"), "w", encoding="utf-8") as f:
                f.write("# 架空の記事\n\n記録から\n\n本文です。\n")
            with open(os.path.join(jidou, "kiroku.adoc"), "w", encoding="utf-8") as f:
                f.write("= 記録\n\n== 2026-10-14 検索の言葉「くりかえし」\n:ページ: /skills/rireki.html\n:種類: 自動\n"
                        "見たこと: 架空\n直したこと: つないだ\n")
            out = os.path.join(tmp, "public")
            make_site.OUT, make_site.JIDOU = out, jidou
            try:
                make_site.main()
            finally:
                make_site.JIDOU = ""

            def page(path):
                with open(os.path.join(out, path), encoding="utf-8") as f:
                    return f.read()
            self.assertIn('class="annai"', page("skills/rireki.html"))
            self.assertIn("写真も読ませられます", page("skills/rireki.html"))
            self.assertIn("Gemini が自動で書きました", page("kiji/jidou-2026-10-14-1.html"))
            self.assertIn("Gemini が自動で", page("kaiseki/kiroku.html"))
            index = json.loads(page("sagasu.json"))
            self.assertIn("くりかえし", [e.get("k", "") for e in index if e["u"] == "/skills/rireki.html"][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
