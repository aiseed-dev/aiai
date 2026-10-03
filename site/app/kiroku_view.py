# SPDX-License-Identifier: AGPL-3.0-or-later
"""The records tab of the aiai app: reads the person's AI records on this PC
(the tools' records, or an export file they pick), shows what was read, and
with one button has the AI agent on the second-opinion server write a
report. Only what the person wrote is read, and identifying details are
hidden on this PC before anything is sent.

It is shown only when the app runs on the person's own PC (AIAI_LOCAL=1),
because on a shared server "this PC" would be the server. AIAI_RECORDS_HOME
points the search for the tools' records elsewhere than the home folder.
"""
import io
import os
import tempfile

import flet as ft

import kiroku
from soudan_view import TOKEN_KEY, Api, ApiError

LOCAL = os.environ.get("AIAI_LOCAL") == "1"


class KirokuView:
    def __init__(self, page, prefs, show):
        self.page, self.prefs, self.show = page, prefs, show
        self.picker = ft.FilePicker()
        self.messages, self.sources = [], []
        self.models, self.model = [], None
        self.result = ft.Column(spacing=8)

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
            ft.Text("記録から報告書を作る", size=22, weight=ft.FontWeight.BOLD),
            self.note("この PC にある、あなたの AI の記録を読みます。読むのは、あなたが AI に書いた発言だけです。"
                      "メールアドレスや電話番号などに見える物は、この PC の上で伏せてから送ります。"),
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
                     ft.Text(f"あなたの発言 {s['messages']} 件({s['first'] or '日付なし'} から {s['last'] or '日付なし'} まで)"),
                     self.note(f"最近の月: {months}" if months else "日付は読めませんでした")]
            if self.messages:
                box = ft.Dropdown(label="報告書を書くモデル", width=280, value=self.model,
                                  options=[ft.DropdownOption(key=m, text=m) for m in self.models])
                box.on_select = lambda e: setattr(self, "model", e.control.value)
                read += [box, ft.FilledButton("報告書を作る", icon=ft.Icons.AUTO_AWESOME, on_click=self.make),
                         self.note("AI エージェントが、「自分を知る」「次を考える」の順に項目を作り、1 つの報告書に"
                                   "まとめます。相談のタブでサインインし、招待の番号で使い始めた人だけが使えます。")]
        return read + [self.result]

    def load(self, label, messages):
        self.sources.append(f"{label}: {len(messages)} 件" if messages else f"{label}: 読めませんでした")
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

    async def make(self, e):
        api = Api(await self.prefs.get(TOKEN_KEY))
        self.result.controls = [ft.Row([ft.ProgressRing(width=20, height=20),
                                        ft.Text("AI エージェントが報告書を作っています")])]
        self.page.update()
        try:
            out = await api.call("POST", "/api/reports", json={
                "model": self.model or "", "material": kiroku.material(self.messages),
                "sources": "、".join(self.sources)})
        except ApiError as err:
            self.result.controls = [ft.Text(m, color=ft.Colors.ERROR) for m in err.messages]
            if err.status in (401, 403):
                self.result.controls.append(self.note("相談のタブで、サインインと同意を済ませてください。"))
            self.page.update()
            return
        clipboard = ft.Clipboard()

        async def copy(ev):
            await clipboard.set(out["report"])
            self.page.show_dialog(ft.SnackBar(ft.Text("報告書を写しました")))

        self.result.controls = [ft.Divider(), ft.Row([ft.Text("報告書", size=18, weight=ft.FontWeight.BOLD),
                                                       ft.OutlinedButton("写す", icon=ft.Icons.CONTENT_COPY, on_click=copy)],
                                                      alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                                self.note("相談のタブの「あなたの記録」にも残ります。"),
                                ft.Markdown(out["report"], selectable=True)]
        self.page.update()
