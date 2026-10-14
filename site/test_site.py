# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tries site/make_site.py: Markdown, the news adoc and the user manual (AsciiDoc) as
aiai writes them, and a build of the whole site into a temporary folder.

    python site/test_site.py
"""
import json
import os
import re
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

    def test_sources_of_an_article_are_small_lines(self):
        text = "(Rust、https://www.rust-lang.org/ 。Go 、https://go.dev/ )\n\n(補足です)\n\n本文です(https://x.example/)"
        out = make_site.markdown(text, sources=True)
        self.assertIn('<p class="src">(Rust', out)
        self.assertIn("<p>(補足です)</p>", out)
        self.assertIn("<p>本文です(", out)
        self.assertNotIn('class="src"', make_site.markdown(text))

    def test_the_longest_word_of_the_figure_fits_its_box_with_room(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures", "tokui.svg"), encoding="utf-8") as f:
            svg = f.read()
        box = int(re.search(r'<rect x="10" y="98" width="(\d+)"', svg)[1])
        longest = max(len(t) for t in re.findall(r"<text[^>]*>([^<]+)</text>", svg))
        self.assertGreaterEqual(box - longest * 13.5, 30)  # room left and right, at the figure's small size (13.5 px a character)

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


class LeadTest(unittest.TestCase):
    def test_the_first_paragraph_of_a_readme(self):
        import make_assets
        self.assertEqual(make_assets.first_paragraph("# 題\n\nはじめの\n段落です。\n\n次の段落です。\n"), "はじめの段落です。")
        self.assertEqual(make_assets.first_paragraph("# 題\n## 小見出し\n\n本文 `code` です。"), "本文 `code` です。")
        self.assertEqual(make_assets.first_paragraph("# 題\n\n- 箇条から始まる\n"), "")
        self.assertEqual(make_assets.first_paragraph(""), "")


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
        self.assertIn("<sup>[1]</sup>", make_site.adoc_inline("本文です。^[1]^"))


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
                         "kaiseki/index.html", "kaiseki.js", "kaiseki-aiai.js", "sagasu.js", "tsukaikata.html", "tameshi.html",
                         "tsukaikata/manual.pdf", "eizou.html"):
                self.assertTrue(os.path.exists(os.path.join(out, path)), path)
            with open(os.path.join(out, "kiji", "mamoru.html"), encoding="utf-8") as f:  # where an article's claims come from is small and light
                self.assertIn('<p class="src">(', f.read())
            with open(os.path.join(out, "sagasu.json"), encoding="utf-8") as f:
                found = json.load(f)
            # the usage page and the introductions are searched like guides and articles: the first paragraphs, then each section
            for url in ("/tsukaikata.html", "/shoukai/weather.html", "/shoukai/officework.html", "/shoukai/aiai-tools.html"):
                mine = [e for e in found if e["u"].split("#")[0] == url]
                self.assertTrue(any(e["h"] == "" and e["x"] for e in mine), url)
                self.assertTrue(any(e["u"].startswith(url + "#") and e["h"] and e["x"] for e in mine), url)
            self.assertTrue(any(e["u"] == "/tsukaikata.html#tools" and e["h"] == "一緒に使う物" and e["t"] == "使い方" for e in found))
            self.assertFalse(any(e["u"].startswith("/tsukaikata.html") and e["h"] == "知らせが出たとき" for e in found))
            others = [e for e in found if e["u"] == "/tsukaikata.html#s17"][0]  # a table: its cells are apart
            self.assertTrue(others["x"].startswith("手引き 使うとき Web サイトを作る 自分で"), others["x"])
            # the log of fixes opens with the rules of the automatic fixes, with the limits read from tools/kaiseki_jidou.py
            with open(os.path.join(out, "kaiseki", "kiroku.html"), encoding="utf-8") as f:
                kiroku = f.read()
            for text in ("<h2>自動の直しの決まり</h2>", "毎日 0 時 20 分に", "検索の言葉を合うページにつなぐことを 5 まで", "次に読むページの案内を足すことを 3 まで",
                         "短い記事を書くことを 1 までです", "リンクは、このサイトの中だけです", "プログラムが確かめてから使います", "<code>STOP</code>", "<h2>記録</h2>"):
                self.assertIn(text, kiroku)
            self.assertLess(kiroku.index("自動の直しの決まり"), kiroku.index("<h2>記録</h2>"))
            # the button of a guide page copies the skill; what is said under it, and after pressing, are in the words of the flow
            with open(os.path.join(out, "skills", "rireki.html"), encoding="utf-8") as f:
                rireki = f.read()
            self.assertIn('type="button" data-copy="skill-src">スキルをコピー</button>', rireki)
            self.assertIn('<p class="fine">コピーして、ふだん使っている AI のチャットに貼ります。AI に「スキル」として登録しておくこともできます(Claude は ZIP、Gemini は SKILL.md か ZIP)。</p>', rireki)
            self.assertIn("コピーしました。ふだん使っている AI に貼ってください", rireki)
            self.assertNotIn("手引きを写す", rireki)
            self.assertNotIn("「写す」", rireki)
            # a guide page opens with the first paragraph of its README.md; a guide with none keeps its description
            with open(os.path.join(out, "skills", "rireki.html"), encoding="utf-8") as f:
                self.assertIn('<p class="lead">AI とのチャットの履歴から、何度も頼んでいることを見つけます。', f.read())
            with open(os.path.join(out, "skills", "toriooki.html"), encoding="utf-8") as f:  # the sample has no README.md
                self.assertIn('<p class="lead">架空のパン屋「こむぎ堂」の', f.read())
            for name in ("aiai-tools", "officework", "weather"):  # the introductions of what is used with aiai
                with open(os.path.join(out, "shoukai", f"{name}.html"), encoding="utf-8") as f:
                    shoukai = f.read()
                self.assertIn('<ol class="toc">', shoukai)
                self.assertIn("<h1>", shoukai)
                self.assertNotIn("^[", shoukai)
            self.assertFalse(os.path.exists(os.path.join(out, "katsuyou.html")))  # server.py sends it to 使い方
            self.assertFalse(os.path.exists(os.path.join(out, "tameshi.js")))
            with open(os.path.join(out, "tameshi.html"), encoding="utf-8") as f:  # the old page sends # places to the app
                self.assertIn('"/app/tameshi" + (', f.read())
            # the page 使い方 is the short form of the manual: the four sections, the figure, the links to the rest
            with open(os.path.join(out, "tsukaikata.html"), encoding="utf-8") as f:
                usage = f.read()
            for text in ("手引きを AI に読ませる", "アプリを作る流れ", "ほかの手引き", "一緒に使う物", 'id="tools"',
                         'class="nagare"', 'href="/app/"', 'href="/tsukaikata/manual.pdf"'):
                self.assertIn(text, usage)
            # the flow is the top page's, kept in one place: the same steps, the explanations that open, the buttons to the app
            flow_of = lambda t: t[t.index('<div class="nagare">'):t.index("使い始める")]
            with open(os.path.join(out, "index.html"), encoding="utf-8") as f:
                self.assertEqual(flow_of(usage), flow_of(f.read()))
            self.assertNotIn("nagare.svg", usage)
            self.assertNotIn("nagare-foot", usage)
            self.assertEqual(usage.count('class="nagare-try" href="/app/tameshi/'), 5)
            button = '<button class="nagare-try" type="button" data-copy="skill-src" data-said="skill-said" data-fallback="/skills/rireki.html">スキルをコピー</button>'
            self.assertEqual(usage.count(button), 1)  # the same button, with the guide hidden in the page and the script
            self.assertIn('<textarea id="skill-src" hidden>', usage)
            self.assertIn("navigator.clipboard.writeText", usage)
            for text in ("知らせが出たとき", "を使う前に", "<h2 id=\"s13\">8 テストする"):  # the rest of the manual is in the app
                self.assertNotIn(text, usage)
            with open(os.path.join(out, "index.html"), encoding="utf-8") as f:
                top = f.read()
            self.assertIn("/skills/rireki.html", top)  # the button to the guide
            self.assertNotIn("/katsuyou.html", top)
            self.assertIn('href="/tsukaikata.html#tools"', top)
            # the flow: steps 1 to 8, the two questions and the end; no step that is only "作る"
            for text in ("1 AI とのチャットの履歴から、何度も頼むことを見つける", "2 今あるアプリを探す", "不満はあるか", "3 どう良くするかを考える",
                         "4 要望か、自分で作るか", "5 今あるアプリの課題を集める", "6 設計書とマニュアルを作る", "7 実装する",
                         "8 テストする", "直す所はあるか", "使い始める"):
                self.assertIn(text, top)
            self.assertNotIn('nagare-step tsukuru">作る<', top)
            self.assertEqual(top.count('class="nagare-try" href='), 5)  # the five steps Gemini does; the sixth oval is the copy button
            # the head: the name and the theme and no button; the flow's heading; the one main button under the flow; cards
            for text in ("<h1>", "aiai —", "AI 活用法", "AI とのチャットの履歴には、あなたの困りごとや、何度も頼んでいることが書いてあります。",
                         "AI は設計もコードも書けますが、何を作るかは、指示がないと分かりません。",
                         "ふだんの AI にスキルを読ませると、AI が履歴から意図を読み取ります。",
                         "何をアプリにするかを、AI と一緒に考えてみませんか。", "<h2>ほかのページ</h2>",
                         "色の付いた段は、Gemini で試せます"):
                self.assertIn(text, top)
            self.assertNotIn("主役は、あなたの AI", top)
            # the flow follows the head at once: no heading or sentence of its own, but a name for readers of the page's parts
            self.assertIn('<section id="skills" class="path" aria-label="AI に何度も頼むことを、アプリにする流れ">', top)
            self.assertNotIn("<h2>AI に何度も頼む", top)
            self.assertNotIn("設計書とコードは AI が書きます", top)
            self.assertNotIn("section-lead", top)
            self.assertNotIn("flow-guide", top)
            head, rest = top.split('<section id="skills"')
            self.assertNotIn('class="button', head.split("<main>")[1])
            self.assertEqual(top.count('href="/skills/rireki.html">手引きを読んで、始める'), 1)
            self.assertLess(rest.index("色の付いた段は、Gemini で試せます"), rest.index("手引きを読んで、始める"))
            self.assertEqual(top.count('class="card-link"'), 6)
            # the card to the self-fixing site stands where the news card was: the news is in the menu and the footer
            self.assertIn('<a class="card-link" href="/kaiseki/">', top)
            self.assertIn("<strong>読まれ方の記録で、自分で直す</strong><span>Cookie を置かずに記録し、Gemini が毎日サイトを少しずつ直す</span>", top)
            self.assertNotIn('<a class="card-link" href="/news/">', top)
            # step 1 has a button that copies the guide, where the others have "Gemini で試す": the whole SKILL.md is in the page
            self.assertEqual(top.count(button), 1)
            self.assertEqual(top.count('class="nagare-try" type="button"'), 1)
            self.assertIn('<span class="nagare-said" id="skill-said" role="status"></span>', top)
            self.assertIn("右の「スキルをコピー」を押し、ふだん使っている AI のチャットに貼ると、AI があなたに聞きながら、1 から順に進めます。", top)
            hidden = re.search(r'<textarea id="skill-src" hidden>(.*?)</textarea>', top, re.S)[1]
            self.assertIn("name: rireki", hidden)
            self.assertIn("## 手順", hidden)
            self.assertLess(top.index(button), top.index("使い始める"))
            self.assertIn("コピーしました。ふだん使っている AI に貼ってください", top)  # what it says for 2.5 seconds
            self.assertIn("location.href = b.dataset.fallback", top)  # where the clipboard cannot be used, the guide's page opens
            # the end of the flow is an outline, so it is not taken for the button under it
            with open(os.path.join(out, "top.css"), encoding="utf-8") as f:
                end = re.search(r"p\.nagare-step\.tsukuru \{([^}]*)\}", f.read())[1]
            self.assertIn("background: transparent", end)
            self.assertIn("color: var(--accent)", end)
            for href in ("/tsukaikata.html", "/kangaekata.html", "/kiji/", "/news/", "/eizou.html", "/tsukaikata.html#tools", "/kaiseki/", "/sagasu.html"):
                self.assertIn(f'href="{href}"', top)
            self.assertNotIn("<script", top.split('<section id="mokuji"')[1].split("</main>")[0])
            for place in ("chousa", "kaizen", "kadai", "sekkei", "tesuto"):  # the 作る tab of the app, by the field's name
                self.assertIn(f'class="nagare-try" href="/app/tameshi/{place}"', top)
            self.assertNotIn("/tameshi.html", top)
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
            # one footer for every page, with the same links; the menu marks the page that is open
            footer = re.search(r"<footer>.*?</footer>", top, re.S)[0]
            self.assertIn("一緒に使う物</a>", footer)
            self.assertNotIn("aiai-tools", footer)
            pages = {"tsukaikata.html": "/tsukaikata.html", "news/index.html": "/news/", "news/2026-09-30.html": "/news/",
                     "kangaekata.html": "/kangaekata.html", "kiji/index.html": "/kiji/", "sagasu.html": "/sagasu.html",
                     "skills/rireki.html": "", "kaiseki/index.html": ""}
            for path, current in pages.items():
                with open(os.path.join(out, path), encoding="utf-8") as f:
                    text = f.read()
                self.assertEqual(re.search(r"<footer>.*?</footer>", text, re.S)[0], footer, path)
                marked = re.findall(r'<a href="([^"]*)" aria-current="page">', text.split("</nav>")[0])
                self.assertEqual(marked, [current] if current else [], path)
            self.assertNotIn('aria-current', top)
            # a small label that says what the heading says is not put over it
            for path, label in (("tsukaikata.html", "使い方"), ("kiji/index.html", "記事"), ("sagasu.html", "探す"), ("kaiseki/index.html", "読まれ方の記録")):
                with open(os.path.join(out, path), encoding="utf-8") as f:
                    self.assertNotIn(f'<p class="kicker">{label}</p>', f.read(), path)
            # under the steps, the sentence and the button sit in the flow, so they are centred on the column of steps
            self.assertIn('<div class="nagare-foot">', top)
            self.assertLess(top.index('<div class="nagare-foot">'), top.index("</section>", top.index('id="skills"')))
            self.assertNotIn("card-more", top)
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
