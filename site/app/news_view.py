# SPDX-License-Identifier: AGPL-3.0-or-later
"""The news tab of the aiai app, when it runs on the person's own PC: have an
AI's CLI write today's draft (news/tsukuru.py), then go through it item by
item, keeping, dropping and rewording, and save it back as adoc. The
person's tastes (news/好み.adoc) are edited in the same tab. Committing and
publishing stay with the person.
"""
import asyncio
import datetime
import os
import sys
import zoneinfo

import flet as ft

import news_adoc

TSUKURU = os.path.join(news_adoc.NEWS_DIR, "tsukuru.py")
AIS = ["claude", "gemini", "codex"]
TZ = zoneinfo.ZoneInfo("Asia/Tokyo")


class NewsView:
    def __init__(self, page, show):
        self.page, self.show = page, show
        self.date = None
        self.doc = None
        self.ai = AIS[0]
        self.fields = []        # per entry: dict of the controls holding its text
        self.title_field = None
        self.tastes_field = None
        self.status = ft.Column(spacing=6)
        self.making = False

    def note(self, text):
        return ft.Text(text, size=13, color=ft.Colors.ON_SURFACE_VARIANT)

    async def render(self):
        if self.date is None:
            had = news_adoc.days()
            self.date = had[0] if had else None
        if self.date and self.doc is None:
            self.doc = news_adoc.load(self.date)
        self.show(self.controls())

    # ---- the screen ----------------------------------------------------------

    def controls(self):
        top = [ft.Text("ニュースを作って、直す", size=22, weight=ft.FontWeight.BOLD),
               self.note("自分の AI の CLI に今日の下書きを書かせ、記事ごとに残す、消す、直すをして、adoc に保存します。"
                         "コミットと公開は、あなたがします。")]
        ai_box = ft.Dropdown(label="書かせる AI", width=160, value=self.ai,
                             options=[ft.DropdownOption(key=a, text=a) for a in AIS])
        ai_box.on_select = lambda e: setattr(self, "ai", e.control.value)
        days = news_adoc.days()
        day_box = ft.Dropdown(label="日", width=170, value=self.date,
                              options=[ft.DropdownOption(key=d, text=d) for d in days])
        day_box.on_select = self.pick_day
        make = ft.FilledButton("今日の下書きを作る", icon=ft.Icons.AUTO_AWESOME, on_click=self.make, disabled=self.making)
        top += [ft.Row([ai_box, make, day_box], wrap=True, spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.status]
        body = self.editor() if self.doc else [self.note("まだニュースのファイルがありません。「今日の下書きを作る」から始めます。")]
        return top + body + self.tastes()

    def editor(self):
        self.fields = []
        self.title_field = ft.TextField(label="題", value=self.doc["title"], dense=True, expand=True)
        out = [ft.Divider(), ft.Row([ft.Text(self.date, size=18, weight=ft.FontWeight.BOLD),
                                     ft.FilledButton("保存", icon=ft.Icons.SAVE, on_click=self.save),
                                     ft.OutlinedButton("元に戻す", icon=ft.Icons.UNDO, on_click=self.reload)],
                                    spacing=10, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
               ft.Row([self.title_field])]
        areas = news_adoc.areas()
        for i, e in enumerate(self.doc["entries"]):
            opts = areas + ([e["area"]] if e["area"] and e["area"] not in areas else [])
            f = {"heading": ft.TextField(label="見出し", value=e["heading"], multiline=True, min_lines=1, max_lines=3, dense=True),
                 "area": ft.Dropdown(label="分野", width=180, value=e["area"] or None,
                                     options=[ft.DropdownOption(key=a, text=a) for a in opts]),
                 "region": ft.TextField(label="国・地域", value=e["region"], width=160, dense=True),
                 "body": ft.TextField(label="本文", value=e["body"], multiline=True, min_lines=3, max_lines=14),
                 "sources": ft.TextField(label="出典(1 行に 1 つ)", value="\n".join(e["sources"]), multiline=True,
                                         min_lines=1, max_lines=6, text_size=12)}
            f["area"].on_select = (lambda ff: (lambda ev: ff.__setitem__("area_value", ev.control.value)))(f)
            f["area_value"] = e["area"]
            links = [ft.TextButton(u[:60] + ("…" if len(u) > 60 else ""), icon=ft.Icons.OPEN_IN_NEW, on_click=self.opener(u))
                     for u in news_adoc.urls("\n".join(e["sources"]))]
            card = ft.Card(ft.Container(ft.Column([
                ft.Row([ft.Text(f"{i + 1}", weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Container(expand=True),
                        ft.OutlinedButton("消す", icon=ft.Icons.DELETE_OUTLINE,
                                          on_click=(lambda k: (lambda ev: self.drop(k)))(i))]),
                f["heading"], ft.Row([f["area"], f["region"]], wrap=True, spacing=10), f["body"], f["sources"],
                ft.Row(links, wrap=True, spacing=4) if links else ft.Container()],
                spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH), padding=16))
            self.fields.append(f)
            out.append(card)
        if not self.doc["entries"]:
            out.append(self.note("記事が 1 つもありません。保存すると、題と日付だけのファイルになります。"))
        out.append(ft.Row([ft.FilledButton("保存", icon=ft.Icons.SAVE, on_click=self.save)]))
        return out

    def tastes(self):
        text = ""
        if os.path.exists(news_adoc.TASTES):
            with open(news_adoc.TASTES, encoding="utf-8") as f:
                text = f.read()
        self.tastes_field = ft.TextField(value=text, multiline=True, min_lines=6, max_lines=24, text_size=13, expand=True)
        return [ft.Divider(), ft.Text("好み", size=18, weight=ft.FontWeight.BOLD),
                self.note("分野と分野ごとの見る目、地域、言葉、件数、扱わない物。AI はこれを読んで探します(news/好み.adoc)。"),
                ft.Row([self.tastes_field]),
                ft.Row([ft.OutlinedButton("好みを保存", icon=ft.Icons.SAVE, on_click=self.save_tastes)])]

    # ---- what the buttons do ---------------------------------------------------

    def opener(self, url):
        async def go(ev):
            await self.page.launch_url(url)
        return go

    def gather(self):
        """The edited day, from the fields."""
        entries = []
        for f in self.fields:
            entries.append({"heading": f["heading"].value or "", "area": f.get("area_value") or f["area"].value or "",
                            "region": f["region"].value or "", "body": f["body"].value or "",
                            "sources": [s for s in (f["sources"].value or "").splitlines() if s.strip()]})
        return {"title": self.title_field.value or "", "date": self.doc["date"] or self.date, "entries": entries}

    async def pick_day(self, e):
        self.date, self.doc = e.control.value, None
        await self.render()

    async def reload(self, e):
        self.doc = None
        self.status.controls = []
        await self.render()

    def drop(self, k):
        self.doc = self.gather()
        del self.doc["entries"][k]
        self.show(self.controls())

    async def save(self, e):
        self.doc = self.gather()
        news_adoc.save(self.date, self.doc)
        rel = os.path.relpath(news_adoc.path_of(self.date), news_adoc.ROOT)
        self.status.controls = [ft.Text(f"{rel} に保存しました({len(self.doc['entries'])} 件)。コミットは git でしてください。")]
        self.show(self.controls())

    async def save_tastes(self, e):
        with open(news_adoc.TASTES, "w", encoding="utf-8") as f:
            f.write((self.tastes_field.value or "").rstrip() + "\n")
        self.page.show_dialog(ft.SnackBar(ft.Text("好みを保存しました")))

    async def make(self, e):
        """Runs news/tsukuru.py with the chosen CLI, off the event loop, and shows its last
        lines. What is being edited on the screen is kept, unless today's file is new."""
        today = datetime.datetime.now(TZ).date().isoformat()
        if self.doc:
            self.doc = self.gather()
        if os.path.exists(news_adoc.path_of(today)):
            self.status.controls = [ft.Text(f"{today} の分はもうあります。直すなら、下の欄で直して保存します。")]
            self.show(self.controls())
            return
        self.making = True
        ring = ft.ProgressRing(width=18, height=18)
        self.status.controls = [ft.Row([ring, ft.Text(f"{self.ai} が今日の下書きを書いています(数分かかります)")])]
        self.show(self.controls())
        try:
            proc = await asyncio.create_subprocess_exec(sys.executable, TSUKURU, "--ai", self.ai, cwd=news_adoc.ROOT,
                                                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            out, _ = await proc.communicate()
            lines = out.decode("utf-8", errors="replace").strip().splitlines()
        except OSError as err:
            lines = [str(err)]
        self.making = False
        self.status.controls = [ft.Text("\n".join(lines[-8:]) or f"{self.ai} から答えがありませんでした", size=13, selectable=True)]
        if os.path.exists(news_adoc.path_of(today)):
            self.date, self.doc = today, None
        await self.render()
