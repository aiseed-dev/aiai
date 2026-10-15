# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the table conversion of site/app/adoc_md.py. Run: python3 site/test_adoc_md.py"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))
from adoc_md import adoc_to_md  # noqa: E402


class TableTest(unittest.TestCase):
    def test_one_cell_per_line(self):
        src = """[cols="1,1,1,3"]
|===
|プラン |月額(月払い) |月額(年払い) |主な内容

|Free
|$0
|$0
|基本のターミナル機能
|Build
|$20
|$18
|チームで使う
|===
"""
        self.assertEqual(adoc_to_md(src), "\n".join([
            "| プラン | 月額(月払い) | 月額(年払い) | 主な内容 |",
            "|---|---|---|---|",
            "| Free | $0 | $0 | 基本のターミナル機能 |",
            "| Build | $20 | $18 | チームで使う |",
        ]) + "\n")

    def test_rows_on_single_lines(self):
        for head, a, b in (("|a |b", "|1 |2", "|3 |4"), ("| a | b", "| 1 | 2", "| 3 | 4")):
            src = f"|===\n{head}\n\n{a}\n{b}\n|===\n"
            self.assertEqual(adoc_to_md(src), "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n", head)

    def test_continuation_line(self):
        src = '[cols="1,2"]\n|===\n|名前 |説明\n\n|Free\n|最初の行\n続きの行\n|Build\n|別\n|===\n'
        self.assertEqual(adoc_to_md(src), "| 名前 | 説明 |\n|---|---|\n| Free | 最初の行続きの行 |\n| Build | 別 |\n")

    def test_continuation_ascii_words_get_a_space(self):
        src = "|===\n|a |b\n|one two\nthree\n|x\n|===\n"
        self.assertEqual(adoc_to_md(src), "| a | b |\n|---|---|\n| one two three | x |\n")

    def test_star_cols(self):
        src = '[cols="3*"]\n|===\n|a\n|b\n|c\n|1\n|2\n|3\n|===\n'
        self.assertEqual(adoc_to_md(src), "| a | b | c |\n|---|---|---|\n| 1 | 2 | 3 |\n")

    def test_cols_with_options_and_style(self):
        src = '[options="header",cols="2,3a"]\n|===\n|a\n|b\n|1\n|2\n|===\n'
        self.assertEqual(adoc_to_md(src), "| a | b |\n|---|---|\n| 1 | 2 |\n")

    def test_columns_from_first_line_without_cols(self):
        src = "|===\n|a |b\n|1\n|2\n|===\n"
        self.assertEqual(adoc_to_md(src), "| a | b |\n|---|---|\n| 1 | 2 |\n")

    def test_escaped_pipe_stays_in_the_cell(self):
        src = "|===\n|式 |意味\n|a \\| b\n|または\n|===\n"
        self.assertEqual(adoc_to_md(src), "| 式 | 意味 |\n|---|---|\n| a \\| b | または |\n")

    def test_specifiers_do_not_break_parsing(self):
        src = '[cols="1,1"]\n|===\n|a |b\n2+|span\na|x\n|y\n|===\n'
        self.assertEqual(adoc_to_md(src), "| a | b |\n|---|---|\n| span | x |\n| y |  |\n")

    def test_attribute_line_only_applies_to_the_next_table(self):
        src = '[cols="1"]\n|===\n|a\n|===\n\ntext\n\n|===\n|a |b\n|1 |2\n|===\n'
        self.assertEqual(adoc_to_md(src), "| a |\n|---|\n\ntext\n\n| a | b |\n|---|---|\n| 1 | 2 |\n".replace("\n\ntext", "\n\ntext"))


class UrlTest(unittest.TestCase):
    def test_bare_url_before_japanese(self):
        self.assertEqual(adoc_to_md("Warp(https://www.warp.dev/)は、Linux 版もあります。\n"),
                         "Warp([https://www.warp.dev/](https://www.warp.dev/))は、Linux 版もあります。\n")

    def test_bare_url_at_end_of_line_and_before_punctuation(self):
        self.assertEqual(adoc_to_md("見る: https://example.com/a?b=1\n"),
                         "見る: [https://example.com/a?b=1](https://example.com/a?b=1)\n")
        self.assertEqual(adoc_to_md("https://example.com/a。次です\n"),
                         "[https://example.com/a](https://example.com/a)。次です\n")
        self.assertEqual(adoc_to_md("See https://example.com/a.\n"),
                         "See [https://example.com/a](https://example.com/a).\n")
        self.assertEqual(adoc_to_md("a https://example.com/a, b\n"),
                         "a [https://example.com/a](https://example.com/a), b\n")

    def test_url_with_label_is_unchanged(self):
        self.assertEqual(adoc_to_md("https://example.com/x[ページ]を見ます\n"), "[ページ](https://example.com/x)を見ます\n")

    def test_url_in_code_is_left_alone(self):
        self.assertEqual(adoc_to_md("`curl https://example.com/x` を実行\n"), "`curl https://example.com/x` を実行\n")


if __name__ == "__main__":
    unittest.main()
