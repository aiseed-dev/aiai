# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tries app/kiroku.py on made-up records in the shapes of Claude Code (the
shape checked on a real record), and of JSON exports and other tools (made
up, to try the general walk).

    python site/test_kiroku.py
"""
import json
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))
import kiroku  # noqa: E402

CLAUDE_CODE = [
    {"type": "user", "timestamp": "2026-09-01T10:00:00Z",
     "message": {"role": "user", "content": "畑の写真から病気の見当を付けるアプリを作りたい"}},
    {"type": "assistant", "timestamp": "2026-09-01T10:00:05Z",
     "message": {"role": "assistant", "model": "claude-test-1", "content": [{"type": "text", "text": "いいですね"}]}},
    {"type": "user", "timestamp": "2026-09-01T10:01:00Z",
     "message": {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]}},
    {"type": "user", "isMeta": True, "message": {"role": "user", "content": "<command-name>/model</command-name>"}},
    {"type": "user", "timestamp": "2026-09-02T09:00:00Z",
     "message": {"role": "user", "content": [{"type": "text", "text": "連絡は hana@example.jp か 090-1234-5678 へ"}]}},
]

EXPORT_TREE = [{"title": "架空の会話", "mapping": {
    "a": {"message": {"author": {"role": "user"}, "create_time": 1788000000,
                      "content": {"parts": ["自然農法で土のりん酸を使う順番を考えています"]}}},
    "b": {"message": {"author": {"role": "assistant"}, "content": {"parts": ["順番はこうです"]}}}}}]

EXPORT_LIST = [{"name": "架空", "chat_messages": [
    {"sender": "human", "created_at": "2026-08-20T12:00:00Z", "text": "パンの取り置きの仕組みを考えています"},
    {"sender": "assistant", "text": "どんな項目ですか"}]}]


class KirokuTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        p = os.path.join(self.tmp.name, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_claude_code_keeps_only_what_the_person_typed(self):
        p = self.write(".claude/projects/x/s.jsonl", "\n".join(json.dumps(o, ensure_ascii=False) for o in CLAUDE_CODE))
        turns = kiroku.read_file(p)
        self.assertEqual([(d, who) for d, who, _ in turns],
                         [("2026-09-01", "user"), ("2026-09-01", "ai"), ("2026-09-02", "user")])
        self.assertIn("畑の写真", turns[0][2])
        self.assertEqual(turns[1][2], "[claude-test-1] いいですね")

    def test_tool_records_are_found(self):
        self.write(".claude/projects/x/s.jsonl", "{}")
        self.write(".codex/history.jsonl", "{}")
        self.write(".gemini/tmp/abc/chats/one.json", "{}")
        self.assertEqual(sorted(kiroku.tool_records(self.tmp.name)), ["Claude Code", "Codex", "Gemini CLI"])

    def test_export_zip_in_two_shapes(self):
        z = os.path.join(self.tmp.name, "export.zip")
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("conversations.json", json.dumps(EXPORT_TREE, ensure_ascii=False))
            f.writestr("other/conversations.json", json.dumps(EXPORT_LIST, ensure_ascii=False))
            f.writestr("chat.html", "<p>読まない</p>")
        texts = sorted(t for _, who, t in kiroku.read_zip(z) if who == "user")
        self.assertEqual(len(texts), 2)
        self.assertTrue(any("りん酸" in t for t in texts) and any("取り置き" in t for t in texts))

    def test_unreadable_zip_gives_nothing(self):
        z = os.path.join(self.tmp.name, "html.zip")
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("MyActivity.html", "<p>読めない形</p>")
        self.assertEqual(kiroku.read_zip(z), [])

    def test_material_masks_and_spreads(self):
        msgs = [("2026-09-02", "user", "連絡は hana@example.jp か 090-1234-5678 へ、鍵は sk-abcdefghijklmnopqrstuv です")]
        m = kiroku.material(msgs)
        for secret in ("hana@example.jp", "090-1234-5678", "sk-abcdefghijklmnopqrstuv"):
            self.assertNotIn(secret, m)
        many = [(f"2026-09-{d:02d}", "user", f"{d} 日目の長めの相談です。" * 20) for d in range(1, 29)]
        m = kiroku.material(many, limit=3000)
        self.assertLessEqual(len(m), 3000 + 700)
        self.assertIn("2026-09-01", m)

    def test_csv_with_a_prompt_column(self):
        p = self.write("copilot.csv", "Date,Prompt,Response\n2026-09-10T08:00:00,会議のメモを整理して,はい\n")
        self.assertEqual(kiroku.read_file(p), [("2026-09-10", "user", "会議のメモを整理して"), ("2026-09-10", "ai", "はい")])
        q = self.write("other.csv", "a,b\n1,2\n")
        self.assertEqual(kiroku.read_file(q), [])

    def test_material_keeps_the_dialogue(self):
        turns = [("2026-09-01", "user", "畑の写真から病気を見分けるアプリを作りたいです"),
                 ("2026-09-01", "ai", "まず学習用の写真を千枚集めましょう"),
                 ("2026-09-01", "user", "千枚は無理です。手元の三十枚で、人が確かめる形にしたいです")]
        m = kiroku.material(turns)
        self.assertIn("AI: まず学習用の写真", m)
        self.assertLess(m.index("AI: まず"), m.index("あなた: 千枚は無理"))

    def test_handout_has_the_skill_then_the_dialogue(self):
        skill = "---\nname: rireki\n---\n\n# 自分を知る\n\n## 項目\n\n1. **長所**: 強み\n\n## 使い方\n\nClaude: ZIP"
        turns = [("2026-09-01", "user", "畑の写真から病気を見分けるアプリを作りたいです")]
        h = kiroku.handout(skill, turns)
        self.assertLess(h.index("## スキル"), h.index("1. **長所**"))
        self.assertLess(h.index("1. **長所**"), h.index("## 資料"))
        self.assertLess(h.index("## 資料"), h.index("畑の写真"))
        self.assertNotIn("Claude: ZIP", h)

    def test_summary(self):
        s = kiroku.summary([("2026-08-20", "user", "あ"), ("2026-09-01", "user", "いい"), ("", "user", "う"), ("", "ai", "え")])
        self.assertEqual((s["messages"], s["first"], s["last"], s["months"]), (3, "2026-08-20", "2026-09-01",
                                                                             {"2026-08": 1, "2026-09": 1}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
