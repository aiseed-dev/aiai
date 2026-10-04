# SPDX-License-Identifier: AGPL-3.0-or-later
"""The server tab of the aiai app, when it runs on the person's own PC: the
day-by-day record of what the person's server has seen (SSH log-in
attempts, probing HTTP requests, the ports open to the world), which a
daily timer on the server writes with tools/kougeki.py into a folder of
YYYY-MM-DD.json and .adoc. The tab brings the folder over SSH into the
same folder on this PC (so the record is the person's), lists the days
side by side, and opens one day's details. AIAI_SERVER names the server
as ssh takes it (dev@example.jp); empty means this machine is the server.
"""
import asyncio
import io
import json
import os
import re
import tarfile

import flet as ft

SERVER = os.environ.get("AIAI_SERVER", "")
REMOTE_DIR = os.environ.get("AIAI_SERVER_DIR", "aiai-server")      # under the server's home
LOCAL_DIR = os.path.join(os.path.expanduser("~"), "aiai-server")


def days(folder=LOCAL_DIR):
    """{date: record} of the JSON files in the folder, newest first."""
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


class ServerView:
    def __init__(self, page, show):
        self.page, self.show = page, show
        self.records = {}
        self.picked = None
        self.status = ft.Column(spacing=6)
        self.fetching = False

    def note(self, text):
        return ft.Text(text, size=13, color=ft.Colors.ON_SURFACE_VARIANT)

    async def render(self):
        self.records = days()
        if self.picked not in self.records:
            self.picked = next(iter(self.records), None)
        self.show(self.controls())

    # ---- the screen ----------------------------------------------------------

    def controls(self):
        where = f"{SERVER} の ~/{REMOTE_DIR}" if SERVER else f"この機械の {LOCAL_DIR}"
        out = [ft.Text("サーバーの攻撃の記録", size=22, weight=ft.FontWeight.BOLD),
               self.note("サーバーが毎日 0 時 5 分に、その日の SSH のログインの試み、穴を探す HTTP の要求、外に開いている口を数え、"
                         f"AI(Gemini)に読ませて所見を付けて記録します(tools/kougeki.py)。記録は {where} にあります。"),
               ft.Row([ft.FilledButton("サーバーから取り込む" if SERVER else "読み直す", icon=ft.Icons.DOWNLOAD,
                                       on_click=self.fetch, disabled=self.fetching)], spacing=10),
               self.status]
        if not self.records:
            return out + [self.note("まだ記録がありません。サーバーで最初の日が過ぎると、1 つ目の記録ができます。")]
        return out + [ft.Divider(), ft.Text("日ごと", size=16, weight=ft.FontWeight.BOLD), self.table(), ft.Divider()] + self.details()

    def table(self):
        rows = []
        for d, r in self.records.items():
            s, h = r["ssh"], r["http"]
            top = s["top_ips"][0] if s["top_ips"] else ("", 0)
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.TextButton(d, on_click=self.picker(d))),
                ft.DataCell(ft.Text(f"{s['attempts']:,}")),
                ft.DataCell(ft.Text(f"{top[0]} ({top[1]})" if top[0] else "")),
                ft.DataCell(ft.Text(f"{h['requests']:,}")),
                ft.DataCell(ft.Text(f"{h['probes']:,}")),
                ft.DataCell(ft.Text(str(len(r["ports"]))))],
                selected=(d == self.picked)))
        return ft.Row([ft.DataTable(columns=[ft.DataColumn(ft.Text("日")), ft.DataColumn(ft.Text("SSH の試み"), numeric=True),
                                             ft.DataColumn(ft.Text("多い相手")), ft.DataColumn(ft.Text("HTTP の要求"), numeric=True),
                                             ft.DataColumn(ft.Text("穴を探す要求"), numeric=True), ft.DataColumn(ft.Text("開いている口"), numeric=True)],
                                    rows=rows)], scroll=ft.ScrollMode.AUTO)

    def picker(self, d):
        def go(ev):
            self.picked = d
            self.show(self.controls())
        return go

    def card(self, title, lines):
        return ft.Card(ft.Container(ft.Column([ft.Text(title, size=16, weight=ft.FontWeight.BOLD)]
                                              + [x if isinstance(x, ft.Control) else ft.Text(x) for x in lines], spacing=6),
                                    padding=16))

    def details(self):
        r = self.records[self.picked]
        s, h = r["ssh"], r["http"]
        pw = s["settings"].get("passwordauthentication")
        ssh_lines = [f"失敗したログインの試み: {s['attempts']:,} 回。鍵で入れた回数: {s['accepted']} 回。"]
        if pw == "no":
            ssh_lines.append(ft.Text("パスワードでの認証は切ってあり、鍵だけなので、この試みでは入れません。", color=ft.Colors.PRIMARY))
        elif pw == "yes":
            ssh_lines.append(ft.Text("パスワードでの認証が有効です。鍵だけにすることを勧めます。", color=ft.Colors.ERROR))
        if s["top_ips"]:
            ssh_lines.append(self.note("多い相手: " + "、".join(f"{ip}({n})" for ip, n in s["top_ips"])))
        if s["top_users"]:
            ssh_lines.append(self.note("試された名前: " + "、".join(f"{u}({n})" for u, n in s["top_users"])))
        http_lines = [f"要求: {h['requests']:,} 件。穴を探す要求: {h['probes']:,} 件。"
                      + ("" if h["source"] == "access log" else "(アクセスログが無いので、失敗した要求だけを数えています)")]
        for label, key in (("ホストごと", "by_host"), ("探された所", "probe_paths"), ("探してきた相手", "probe_ips"), ("走査の道具の名乗り", "scanners")):
            if h[key]:
                http_lines.append(self.note(f"{label}: " + "、".join(f"{k or '(無し)'}({n})" for k, n in h[key])))
        clipboard = ft.Clipboard()

        async def copy(ev):
            await clipboard.set(r["adoc"])
            self.page.show_dialog(ft.SnackBar(ft.Text("写しました")))

        out = [ft.Text(f"{r['day']} の記録({r['host']}、{r['when'][11:16]} に数えた直近 {r['hours']} 時間)", size=16, weight=ft.FontWeight.BOLD),
               ft.Row([ft.OutlinedButton("adoc を写す", icon=ft.Icons.CONTENT_COPY, on_click=copy)])]
        if r.get("ai"):
            text = r["ai"]["text"] or f"読めませんでした: {r['ai'].get('error', '')}"
            out.append(self.card(f"AI の所見({r['ai']['model']})", [ft.Text(text, selectable=True),
                                                                   self.note("AI は数えた物を読んで書くだけで、サーバーには何も変えません。読んで決めるのは、あなたです。")]))
        return out + [self.card("SSH", ssh_lines), self.card("HTTP", http_lines),
                      self.card("外に開いている口", [self.note("、".join(f"{local} ({proc})" for local, proc in r["ports"]) or "ありません")])]

    # ---- bringing the record over ----------------------------------------------

    async def fetch(self, e):
        """tar of the server's folder over SSH, unpacked into the folder here."""
        if not SERVER:
            await self.render()
            return
        self.fetching = True
        self.status.controls = [ft.Row([ft.ProgressRing(width=18, height=18), ft.Text("取り込んでいます")])]
        self.show(self.controls())
        err = b""
        try:
            proc = await asyncio.create_subprocess_exec("ssh", "-o", "BatchMode=yes", SERVER, "tar", "cf", "-", "-C", REMOTE_DIR, ".",
                                                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, err = await proc.communicate()
            if proc.returncode != 0:
                raise OSError(err.decode("utf-8", errors="replace").strip()[-400:])
            os.makedirs(LOCAL_DIR, exist_ok=True)
            n = 0
            with tarfile.open(fileobj=io.BytesIO(out)) as tar:
                for m in tar.getmembers():
                    if m.isfile() and re.fullmatch(r"\./\d{4}-\d{2}-\d{2}\.(json|adoc)", m.name):
                        tar.extract(m, LOCAL_DIR, filter="data")
                        n += 1
            self.status.controls = [self.note(f"{LOCAL_DIR} に {n} のファイルを取り込みました")]
        except (OSError, tarfile.TarError) as ex:
            self.status.controls = [ft.Text("取り込めませんでした。SSH で入れるか、サーバーに記録のフォルダーがあるかを見てください。", color=ft.Colors.ERROR),
                                    self.note(str(ex)[-400:])]
        self.fetching = False
        await self.render()
