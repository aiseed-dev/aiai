# SPDX-License-Identifier: AGPL-3.0-or-later
"""The records tab of the aiai app: reads the person's AI records on this PC
(the tools' records, or an export file they pick), shows what was read, and
with one button makes the handout: one file with the rireki skill and the
dialogue, for the person's own AI to make the items from. People who signed
in to the second-opinion server can instead have its AI agent write the
report. The dialogue is read, so how the person answered the AI shows;
identifying details are hidden on this PC before anything leaves it.

It is shown only when the app runs on the person's own PC (AIAI_LOCAL=1),
because on a shared server "this PC" would be the server. AIAI_RECORDS_HOME
points the search for the tools' records elsewhere than the home folder.
"""
import asyncio
import io
import os
import tempfile

import flet as ft

import kiroku
from soudan_view import TOKEN_KEY, Api, ApiError

LOCAL = os.environ.get("AIAI_LOCAL") == "1"
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
HANDOUT_NAME = "aiai-rireki.md"  # written in the person's home folder


class KirokuView:
    def __init__(self, page, prefs, show):
        self.page, self.prefs, self.show = page, prefs, show
        self.picker = ft.FilePicker()
        self.messages, self.sources = [], []
        self.models, self.model = [], None
        self.result = ft.Column(spacing=8)
        self.handout_path = ""

    def note(self, text):
        return ft.Text(text, size=13, color=ft.Colors.ON_SURFACE_VARIANT)

    async def render(self):
        api = Api(await self.prefs.get(TOKEN_KEY))
        try:
            self.models = (await api.call("GET", "/api/info"))["models"]
        except ApiError:
            self.models = []
        self.model = self.model or (self.models[0] if self.models else None)
        self.show(self.controls())

    def controls(self):
        read = [
            ft.Text("記録を、あなたの AI に渡す材料にする", size=22, weight=ft.FontWeight.BOLD),
            self.note("この PC にある、あなたと AI の対話の記録を読み、1 つのファイルにまとめます。そのファイルを、"
                      "使っている AI に渡すと、「自分を知る」「次を考える」の 12 の項目を作ってくれます。"
                      "AI の答えを受けて、あなたがどう返したかに、長所や考え方が出ます。メールアドレスや電話番号などに"
                      "見える物は、この PC の上で伏せます。ほかの記録を足すのも自由です。"),
            ft.Row([ft.FilledButton("PC の AI の道具の記録を読む", icon=ft.Icons.COMPUTER, on_click=self.read_tools),
                    ft.OutlinedButton("書き出したファイルを選ぶ", icon=ft.Icons.UPLOAD_FILE, on_click=self.pick)],
                   wrap=True, spacing=8),
            self.note("道具の記録: Claude Code(デスクトップアプリの Claude Code と Cowork を含む)、Codex、Gemini CLI。"
                      "書き出し: ChatGPT と Claude の ZIP、Copilot の CSV など。読めないファイルは、読めないと出します。"),
        ]
        if self.sources:
            s = kiroku.summary(self.messages)
            months = "、".join(f"{m} {n} 件" for m, n in sorted(s["months"].items())[-6:])
            read += [ft.Divider(), ft.Text("読んだ記録", size=16, weight=ft.FontWeight.BOLD),
                     *[ft.Text(f"・{x}") for x in self.sources],
                     ft.Text(f"あなたの発言 {s['messages']} 件、AI の答え {s['replies']} 件"
                             f"({s['first'] or '日付なし'} から {s['last'] or '日付なし'} まで)"),
                     self.note(f"最近の月: {months}" if months else "日付は読めませんでした")]
            if any(who == "user" for _, who, _ in self.messages):
                read += [ft.FilledButton("材料のファイルを作る", icon=ft.Icons.DESCRIPTION, on_click=self.make_handout),
                         self.note("できたファイルを、使っている AI のチャットに上げて(または貼って)、「このとおりに項目を作って」"
                                   "と頼みます。項目は、あなたの AI が 1 つずつ作り、あなたが直します。")]
                if self.models:
                    box = ft.Dropdown(label="報告書を書くモデル", width=280, value=self.model,
                                      options=[ft.DropdownOption(key=m, text=m) for m in self.models])
                    box.on_select = lambda e: setattr(self, "model", e.control.value)
                    read += [ft.Divider(), ft.Text("相談のサーバーで報告書を作る", size=16, weight=ft.FontWeight.BOLD),
                             self.note("相談のタブでサインインし、招待の番号で使い始めた人は、相談のサーバーの AI エージェントにも"
                                       "頼めます。12 の項目を 1 つずつ書き、要約を付けて 1 つの報告書にします。"),
                             box, ft.OutlinedButton("報告書を作る", icon=ft.Icons.AUTO_AWESOME, on_click=self.make)]
        return read + [self.result]

    def load(self, label, messages):
        mine = sum(1 for _, who, _ in messages if who == "user")
        self.sources.append(f"{label}: あなたの発言 {mine} 件" if mine else f"{label}: 読めませんでした")
        self.messages += messages

    async def read_tools(self, e):
        self.messages, self.sources, self.result.controls = [], [], []
        found = kiroku.tool_records(os.environ.get("AIAI_RECORDS_HOME"))
        if not found:
            self.sources.append("この PC に、AI の道具の記録は見つかりませんでした")
        for source, paths in found.items():
            msgs = []
            for p in paths:
                msgs += kiroku.read_file(p)
            self.load(f"{source}({len(paths)} ファイル)", msgs)
        await self.render()

    async def pick(self, e):
        files = await self.picker.pick_files(allow_multiple=True, with_data=True,
                                             file_type=ft.FilePickerFileType.CUSTOM,
                                             allowed_extensions=["zip", "json", "jsonl", "csv"])
        if not files:
            return
        self.messages, self.sources, self.result.controls = [], [], []
        for f in files:
            try:
                if f.name.lower().endswith(".zip"):
                    msgs = kiroku.read_zip(f.path or io.BytesIO(f.bytes))
                elif f.path:
                    msgs = kiroku.read_file(f.path)
                else:
                    with tempfile.NamedTemporaryFile(suffix=os.path.splitext(f.name)[1]) as t:
                        t.write(f.bytes or b"")
                        t.flush()
                        msgs = kiroku.read_file(t.name)
            except Exception:
                msgs = []
            self.load(f.name, msgs)
        await self.render()

    def copy_button(self, text, said):
        clipboard = ft.Clipboard()

        async def copy(ev):
            await clipboard.set(text)
            self.page.show_dialog(ft.SnackBar(ft.Text(said)))
        return ft.OutlinedButton("写す", icon=ft.Icons.CONTENT_COPY, on_click=copy)

    async def make_handout(self, e):
        """Writes the handout next to the person's home folder, since the app runs on
        their PC, and shows where it is; 写す copies it for pasting instead."""
        with open(os.path.join(ASSETS, "skills", "rireki.md"), encoding="utf-8") as f:
            skill = f.read()
        text = kiroku.handout(skill, self.messages)
        self.handout_path = os.path.join(os.path.expanduser("~"), HANDOUT_NAME)
        with open(self.handout_path, "w", encoding="utf-8") as f:
            f.write(text)
        self.result.controls = [
            ft.Divider(),
            ft.Row([ft.Text("材料のファイルができました", size=18, weight=ft.FontWeight.BOLD),
                    self.copy_button(text, "材料を写しました")], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Text(self.handout_path, selectable=True),
            self.note(f"{len(text):,} 字。使っている AI のチャットに、このファイルを上げるか、「写す」で貼ります。"
                      "ファイルは、このまま、ほかの人には渡さないでください。")]
        self.page.update()

    async def make(self, e):
        api = Api(await self.prefs.get(TOKEN_KEY))
        progress = ft.Text("AI エージェントが報告書を作っています")
        self.result.controls = [ft.Row([ft.ProgressRing(width=20, height=20), progress])]
        self.page.update()
        try:
            r = await api.call("POST", "/api/reports", json={
                "model": self.model or "", "material": kiroku.material(self.messages),
                "sources": "、".join(self.sources)})
            while r["status"] == "running":
                progress.value = f"AI エージェントが報告書を作っています({r['done']}/{r['steps']})"
                self.page.update()
                await asyncio.sleep(3)
                r = await api.call("GET", f"/api/reports/{r['id']}")
        except ApiError as err:
            self.result.controls = [ft.Text(m, color=ft.Colors.ERROR) for m in err.messages]
            if err.status in (401, 403):
                self.result.controls.append(self.note("相談のタブで、サインインと同意を済ませてください。"))
            self.page.update()
            return
        self.result.controls = [ft.Divider(), ft.Row([ft.Text("報告書", size=18, weight=ft.FontWeight.BOLD),
                                                       self.copy_button(r["report"], "報告書を写しました")],
                                                      alignment=ft.MainAxisAlignment.SPACE_BETWEEN)]
        if r["status"] == "failed":
            self.result.controls.append(ft.Text(f"{r['done']}/{r['steps'] - 1} の項目までで止まりました: {r['error']}",
                                                color=ft.Colors.ERROR))
        self.result.controls += [self.note("相談のタブの「あなたの記録」にも残ります。"),
                                 ft.Markdown(r["report"], selectable=True)]
        self.page.update()
