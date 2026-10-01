# SPDX-License-Identifier: AGPL-3.0-or-later
"""A made-up model for trying the second opinion without any company's API.
It never reads the draft; it answers in the shape 観点/共通.md asks for, and
says it is a fake. Never use it on a real server."""


class FakeModel:
    def __init__(self, name):
        self.name = name

    def answer(self, system, messages):
        kind = system.split("\n# ", 1)[1].splitlines()[0] if "\n# " in system else ""
        text = (f"(試しのモデル「{self.name}」の答えです。下書きは読んでいません)\n\n"
                f"1. よい所: 「{kind}」について、自分の言葉で書けています\n"
                "2. 見直すとよい所: 根拠になる経験を、1 つ書き足せますか\n"
                "3. 確かめが要る事実: 数字や制度は、公開の資料で確かめてください\n"
                "4. 次にする行動: 書き足した下書きで、もう一度相談してください")
        return text, len(str(messages)), len(text)
