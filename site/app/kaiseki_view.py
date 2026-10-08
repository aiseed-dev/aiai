# SPDX-License-Identifier: AGPL-3.0-or-later
"""The 解析 tab of the aiai app, when it runs on the person's own PC: the
day-by-day summaries of how the site is read (tools/kaiseki_matome.py writes
them on the server into ~/aiai-server/kaiseki), brought over SSH into the
same folder here; and a button that has the person's AI CLI fix the site
from them (kaiseki/naosu.py), on a branch of its own, whose diff the person
reads and then merges or drops. Publishing stays with the person.
"""
import asyncio
import io
import json
import os
import re
import subprocess
import sys
import tarfile

import flet as ft

from server_view import REMOTE_DIR, SERVER

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
LOCAL_DIR = os.path.join(os.path.expanduser("~"), "aiai-server", "kaiseki")
NAOSU = os.path.join(ROOT, "kaiseki", "naosu.py")
AIS = ["claude", "gemini", "codex"]


def days(folder=LOCAL_DIR):
    """{date: summary} of the JSON files in the folder, newest first."""
    out = {}
    if os.path.isdir(folder):
        for f in sorted(os.listdir(folder), reverse=True):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", f):
                try:
                    with open(os.path.join(folder, f), encoding="utf-8") as fh:
                        out[f[:-5]] = json.load(fh)
                except (OSError, ValueError):
                    pass
    return out


def git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    return r.stdout.strip()


def branches():
    """The branches the AI made, kaiseki/YYYY-MM-DD, newest first."""
    return sorted((b.strip(" *") for b in git("branch", "--list", "kaiseki/*").splitlines()), reverse=True)


class KaisekiView:
    def __init__(self, page, show):
        self.page, self.show = page, show
        self.records, self.picked = {}, None
        self.ai = AIS[0]
        self.status = ft.Column(spacing=6)
        self.busy = False
        self.diff_of = None

    def note(self, text):
        return ft.Text(text, size=13, color=ft.Colors.ON_SURFACE_VARIANT)

    async def render(self):
        self.records = days()
        if self.picked not in self.records:
            self.picked = next(iter(self.records), None)
        self.show(self.controls())

    # ---- the screen ----------------------------------------------------------

    def controls(self):
        where = f"{SERVER} の ~/{REMOTE_DIR}/kaiseki" if SERVER else f"この機械の {LOCAL_DIR}"
        ai_box = ft.Dropdown(label="直させる AI", width=160, value=self.ai, options=[ft.DropdownOption(key=a, text=a) for a in AIS])
        ai_box.on_select = lambda e: setattr(self, "ai", e.control.value)
        out = [ft.Text("読まれ方の記録で、サイトを直す", size=22, weight=ft.FontWeight.BOLD),
               self.note("サイトは、読む人がどこで読み、何を探しているかを記録します。サーバーが毎日 0 時 10 分にまとめ、"
                         f"Claude Haiku 5.5 が所見を付けます(tools/kaiseki_matome.py)。まとめは {where} にあります。"
                         "「記録から直させる」で、あなたの AI がページを直し、足りないページを書き、別の枝にコミットします。"),
               ft.Row([ft.OutlinedButton("サーバーから取り込む" if SERVER else "読み直す", icon=ft.Icons.DOWNLOAD,
                                         on_click=self.fetch, disabled=self.busy),
                       ai_box,
                       ft.FilledButton("記録から直させる", icon=ft.Icons.AUTO_FIX_HIGH, on_click=self.fix,
                                       disabled=self.busy or not self.records)],
                      wrap=True, spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
               self.status]
        out += self.fixes()
        if not self.records:
            return out + [self.note("まだまとめがありません。サーバーで最初の日が過ぎると、1 つ目のまとめができます。")]
        return out + [ft.Divider(), ft.Text("日ごと", size=16, weight=ft.FontWeight.BOLD), self.table(), ft.Divider()] + self.details()

    def table(self):
        rows = []
        for d, r in self.records.items():
            searched = sum(n for _, n in r["searches"])
            missing = sum(n for _, n in r["nohit"]) + sum(n for _, n in r["notfound"])
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.TextButton(d, on_click=self.picker(d))),
                ft.DataCell(ft.Text(f"{r['views']:,}")),
                ft.DataCell(ft.Text(f"{round(r['phone_share'] * 100)}%" if r["phone_share"] is not None else "")),
                ft.DataCell(ft.Text(f"{searched:,}")),
                ft.DataCell(ft.Text(f"{missing:,}"))], selected=(d == self.picked)))
        return ft.Row([ft.DataTable(columns=[ft.DataColumn(ft.Text("日")), ft.DataColumn(ft.Text("表示"), numeric=True),
                                             ft.DataColumn(ft.Text("スマートフォン"), numeric=True),
                                             ft.DataColumn(ft.Text("探した言葉"), numeric=True),
                                             ft.DataColumn(ft.Text("見つからなかった"), numeric=True)], rows=rows)],
                      scroll=ft.ScrollMode.AUTO)

    def picker(self, d):
        def go(ev):
            self.picked = d
            self.show(self.controls())
        return go

    def card(self, title, lines):
        return ft.Card(ft.Container(ft.Column([ft.Text(title, size=16, weight=ft.FontWeight.BOLD)]
                                              + [x if isinstance(x, ft.Control) else ft.Text(x, selectable=True) for x in lines],
                                              spacing=6), padding=16))

    def details(self):
        r = self.records[self.picked]
        out = [ft.Text(f"{r['day']} の読まれ方({r['site']})", size=16, weight=ft.FontWeight.BOLD)]
        if r.get("ai"):
            out.append(self.card(f"AI の所見({r['ai']['model']})", [r["ai"]["text"] or f"読めませんでした: {r['ai'].get('error', '')}"]))
        pages = []
        for p in r["pages"]:
            how = [f"{p['views']} 回"]
            if p["seconds"] is not None:
                how.append(f"中ほど {p['seconds']} 秒")
            if p["scroll"] is not None:
                how.append(f"下へ {p['scroll']}%、終わりまで {round(p['to_end'] * 100)}%")
            pages.append(f"{p['path']}: {'、'.join(how)}")
        out.append(self.card("ページ", pages or ["ありません"]))
        if r["sections"]:
            out.append(self.card("読んだ見出し(たどり着いた割合)", [
                f"{path}: " + "、".join(f"{v}({round(s * 100)}%)" if s is not None else v for v, _, s in items)
                for path, items in r["sections"].items()]))
        for key, head in (("searches", "探した言葉"), ("nohit", "探して見つからなかった言葉"), ("notfound", "見つからなかったページ")):
            if r[key]:
                out.append(self.card(head, ["、".join(f"{v}({n})" for v, n in r[key])]))
        for key, head in (("opens", "開いた全文"), ("uses", "写した、ダウンロードした手引き"), ("links", "次に開いたページ")):
            if r[key]:
                out.append(self.card(head, [f"{p} → {v}({n})" for p, v, n in r[key]]))
        return out

    def fixes(self):
        """The branches the AI made: what changed, and buttons to read, merge or drop."""
        out = []
        for b in branches():
            stat = git("diff", "--stat", f"HEAD...{b}")
            log = git("log", "-1", "--format=%B", b)
            row = ft.Row([ft.OutlinedButton("差分を読む", icon=ft.Icons.DIFFERENCE, on_click=self.differ(b)),
                          ft.FilledButton("取り込む", icon=ft.Icons.CALL_MERGE, on_click=self.runner("--merge", b), disabled=self.busy),
                          ft.OutlinedButton("捨てる", icon=ft.Icons.DELETE_OUTLINE, on_click=self.runner("--drop", b), disabled=self.busy)],
                         wrap=True, spacing=8)
            lines = [log, ft.Text(stat, font_family="monospace", size=12, selectable=True), row]
            if self.diff_of == b:
                diff = git("diff", f"HEAD...{b}")
                lines.append(ft.Text(diff[:30000] + ("\n…(長いので途中まで)" if len(diff) > 30000 else ""),
                                     font_family="monospace", size=12, selectable=True))
            out.append(self.card(f"AI が直した枝: {b}", lines))
        return out

    # ---- what the buttons do ---------------------------------------------------

    def differ(self, b):
        def go(ev):
            self.diff_of = None if self.diff_of == b else b
            self.show(self.controls())
        return go

    def runner(self, flag, b):
        async def go(ev):
            await self.naosu(flag, b)
        return go

    async def naosu(self, *args):
        self.busy = True
        what = "AI が記録を読んで直しています(数分かかります)" if args[0] == "--ai" else "動かしています"
        self.status.controls = [ft.Row([ft.ProgressRing(width=18, height=18), ft.Text(what)])]
        self.show(self.controls())
        try:
            proc = await asyncio.create_subprocess_exec(sys.executable, NAOSU, *args, cwd=ROOT,
                                                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            out, _ = await proc.communicate()
            lines = out.decode("utf-8", errors="replace").strip().splitlines()
        except OSError as err:
            lines = [str(err)]
        self.busy = False
        self.diff_of = None
        self.status.controls = [ft.Text("\n".join(lines[-12:]) or "答えがありませんでした", size=13, selectable=True)]
        await self.render()

    async def fix(self, e):
        await self.naosu("--ai", self.ai)

    async def fetch(self, e):
        """tar of the server's folder over SSH, unpacked into the folder here."""
        if not SERVER:
            await self.render()
            return
        self.busy = True
        self.status.controls = [ft.Row([ft.ProgressRing(width=18, height=18), ft.Text("取り込んでいます")])]
        self.show(self.controls())
        try:
            proc = await asyncio.create_subprocess_exec("ssh", "-o", "BatchMode=yes", SERVER, "tar", "cf", "-", "'--exclude=*.db*'",
                                                        "-C", f"{REMOTE_DIR}/kaiseki", ".",
                                                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, err = await proc.communicate()
            if proc.returncode != 0:
                raise OSError(err.decode("utf-8", errors="replace").strip()[-400:])
            os.makedirs(LOCAL_DIR, exist_ok=True)
            n = 0
            with tarfile.open(fileobj=io.BytesIO(out)) as tar:
                for m in tar.getmembers():
                    # the summaries only; the raw record (kaiseki.db) stays on the server
                    if m.isfile() and re.fullmatch(r"\./\d{4}-\d{2}-\d{2}\.(json|adoc)", m.name):
                        tar.extract(m, LOCAL_DIR, filter="data")
                        n += 1
            self.status.controls = [self.note(f"{LOCAL_DIR} に {n} のファイルを取り込みました")]
        except (OSError, tarfile.TarError) as ex:
            self.status.controls = [ft.Text("取り込めませんでした。SSH で入れるか、サーバーにまとめのフォルダーがあるかを見てください。",
                                            color=ft.Colors.ERROR), self.note(str(ex)[-400:])]
        self.busy = False
        await self.render()
