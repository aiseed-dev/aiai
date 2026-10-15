# SPDX-License-Identifier: AGPL-3.0-or-later
"""The 作る tab of the aiai app: the steps of "度々聞いていることを、アプリにする"
(rireki/SKILL.md) that Google Cloud's Gemini does for a person who signs in. It talks to
tameshi/server.py at /tameshi, with the fields, buttons and notices of tameshi/docs/design.adoc, 5.
One stage is open at a time, the one named at the end of the address (/app/tameshi/<place>, the second
step when none); the buttons that carry a result on open the next one:

    2 今あるアプリを探す  3 どう良くするかを考える  5 今あるアプリの課題を集める
    6 設計書とマニュアルを作る  8 テストの手順を作る

The longer jobs take minutes; their lists are read again every 5 seconds while one is
running. The stages can always be filled in and pressed; a button that asks Gemini for something sends a
person who is not signed in to the sign-in screen first (design 5.1). Signing in and registering are screens
of their own, /app/tameshi/signin and /app/tameshi/touroku (design 5.7); a person who has done either returns
to the stage that was open, with what was written still in it, and presses the button again.
The sign-in with Google or Apple comes back to /app/tameshi/<place> with a one-time code in the
address, which is traded for a session number. The session number is kept in the browser's or the app's
own storage (SharedPreferences, key aiai.tameshi.token, as in soudan_view.py), so a reload or reopening stays
signed in until the server refuses it (401) or the person signs out; either removes it (design 5.6).
On the phone only the test account signs in. Settings:

    AIAI_TAMESHI_URL  the server as people reach it (default AIAI_SITE + /tameshi); sign-in links use it
                      (AIAI_TAMESHI=1 is another thing: it tells site/server.py to mount the server)
    AIAI_TAMESHI_API  the same server as this app reaches it, when that differs
    AIAI_RETURN       the app's address, where sign-in comes back to (default AIAI_SITE + /app/)
"""
import asyncio
import fnmatch
import os
import re
import urllib.parse

import flet as ft
import httpx
from adoc_md import adoc_to_md
from glyphs import preload

SITE = os.environ.get("AIAI_SITE", "http://127.0.0.1:8020").rstrip("/")
PUBLIC = (os.environ.get("AIAI_TAMESHI_URL") or SITE + "/tameshi").rstrip("/")
API = os.environ.get("AIAI_TAMESHI_API", PUBLIC).rstrip("/")
RETURN = (os.environ.get("AIAI_RETURN") or SITE + "/app/").rstrip("/") + "/"
SIGN_IN = {"google": "Google でサインイン", "apple": "Apple でサインイン"}

# The places of the flow that can be opened with /app/tameshi/<place>, by the name of the field
PLACES = {"chousa": "2 今あるアプリを探す", "kaizen": "3 どう良くするかを考える", "kadai": "5 今あるアプリの課題を集める",
          "sekkei": "6 設計書とマニュアルを作る", "tesuto": "8 テストの手順を作る"}
# The screens that are not a stage: signing in and registering, with their own routes /tameshi/<screen>
SCREENS = {"signin": "サインイン", "touroku": "新しく登録する"}
JOBS = {"chousa": "今あるアプリを探す", "kadai": "今あるアプリの課題を集める", "sekkei": "設計書とマニュアル", "tesuto": "テストの手順"}
# The server's count of the day that a stage uses
QUOTA = {"chousa": "chousa", "kaizen": "chat", "kadai": "kadai", "sekkei": "sekkei", "tesuto": "tesuto"}
STATUS = {"waiting": "待っています", "running": "進めています", "done": "できました", "error": "止まりました"}
# What a form needs before it is sent, in the words of the server's refusal (design 5.3)
ENOUGH = {"chousa": "何度も頼んでいることを書いてください",
          "kadai": "読ませる結果を選んでください",
          "sekkei": "SKILL.md と参考の資料を選んでください",
          "tesuto": "読ませる設計書とマニュアルを選ぶか、資料を選んでください"}
# The documents of each job (design 5.8): (pattern of the path, title, shown open). The open ones come first, the rest
# are closed tiles in this order; a file that matches none is a closed tile titled by its path.
DOCUMENTS = {
    "chousa": [("chousa/*.adoc", "調べた結果", True)],
    "kadai": [("references/*-analysis.adoc", "課題の資料", True)],
    "sekkei": [("docs/manual.adoc", "利用者マニュアル", True), ("docs/design.adoc", "設計書", False),
               ("docs/kakunin.adoc", "照らし合わせの記録", False)],
    "tesuto": [("docs/test.adoc", "テストの手順", True), ("docs/test-kakunin.adoc", "確かめの記録", False)],
}
TOKEN_KEY = "aiai.tameshi.token"  # where the session number is kept
PICTURE_WIDTH = 720  # a picture is as wide as the box, up to this
NONE = "-"  # the choice of 読ませない in a dropdown, which keeps no empty key


class ApiError(Exception):
    def __init__(self, status, messages):
        super().__init__("、".join(messages))
        self.status, self.messages = status, messages


def place_of(route):
    """(is this a route of the tab, the place named at its end, the one-time code) of an address.
    The place is a stage of PLACES or one of the SCREENS, or empty."""
    parts = urllib.parse.urlsplit(route or "")
    segments = [s for s in parts.path.split("/") if s]
    if not segments or segments[0] != "tameshi":
        return False, "", ""
    place = segments[1] if len(segments) > 1 and (segments[1] in PLACES or segments[1] in SCREENS) else ""
    return True, place, dict(urllib.parse.parse_qsl(parts.query)).get("code", "")


def when(created):
    """The time of a job as people read it: 2026-10-15T16:43+09:00 becomes 10 月 15 日 16:43 (no year, as the
    server already gives its own time zone). Anything else is returned as it is."""
    m = re.match(r"\d{4}-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})", created or "")
    if not m:
        return created or ""
    return f"{int(m[1])} 月 {int(m[2])} 日 {m[3]}:{m[4]}"


class TameshiView:
    """The 作る tab. show(controls) puts controls on the tab's screen; body is the column that
    scrolls, so that a place can be brought to the top."""

    def __init__(self, page, prefs, show, body):
        self.page, self.prefs, self.show, self.body = page, prefs, show, body
        self.http = httpx.AsyncClient(base_url=API, timeout=300)
        self.token = ""
        self.info = None
        self.me = None
        self.aim = ""          # the place the person is going to, until the stage is opened
        self.active = "chousa"  # the stage that is open: one at a time; it stays while a screen is shown, to return to
        self.screen = ""       # "signin" or "touroku" while that screen is shown, else empty (the stage view)
        self.built = False
        self.picker = ft.FilePicker()
        self.kaizen_talk = []  # the dialogue of step 3
        self.picked = {k: [] for k in JOBS}  # the materials picked for each job: [(name, bytes)]
        self.cards = {}        # job id -> (status, card), so a finished job is built once
        self.polling = False
        self.to_top = False    # the next arrival scrolls to the top (see goto)
        self.lock = asyncio.Lock()  # a sign-in coming back shows the tab twice at once

    # ---- the server ----------------------------------------------------------------

    async def call(self, method, path, **kw):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            r = await self.http.request(method, path, headers=headers, **kw)
        except httpx.HTTPError:
            raise ApiError(0, ["サーバーにつながりませんでした"])
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = None
            if r.status_code == 401 and self.token:
                self.token, self.me = "", None
                await self.forget_token()  # the server refused it: it is of no use any more
            raise ApiError(r.status_code, detail if isinstance(detail, list) else [str(detail or f"うまくいきませんでした({r.status_code})")])
        return r

    async def load_token(self):
        """The kept session number, when there is none in memory (a reload or reopening starts with none)."""
        if not self.token:
            try:
                self.token = await self.prefs.get(TOKEN_KEY) or ""
            except Exception:  # storage that cannot be read is no reason to stop: the person signs in again
                self.token = ""

    async def keep_token(self, token):
        self.token = token
        try:
            await self.prefs.set(TOKEN_KEY, token)
        except Exception:  # not kept, but the person is signed in for now
            pass

    async def forget_token(self):
        try:
            await self.prefs.remove(TOKEN_KEY)
        except Exception:
            pass

    async def json(self, method, path, **kw):
        return (await self.call(method, path, **kw)).json()

    # ---- coming back from sign-in, and being sent to a place ---------------------------

    async def take_route(self, route):
        """For a route of the tab: trades the code in it for a session number and strips the code;
        returns whether the route was one of the tab."""
        mine, place, code = place_of(route)
        if not mine:
            return False
        self.screen = place if place in SCREENS else ""
        if place and not self.screen:
            self.aim = place
        if code:
            try:
                await self.keep_token((await self.json("POST", "/api/session", json={"code": code}))["token"])
            except ApiError:
                pass
            self.page.navigate("/tameshi" + (f"/{place}" if place else ""))  # takes the used code out of the address
        return True

    def current_root(self):
        """The screen that is current: the signing in, the registering, or the stage view."""
        return {"signin": self.signin_root, "touroku": self.touroku_root}.get(self.screen, self.root)

    def clear_screens(self):
        """The password fields are emptied whenever a screen is left or shown again, and the notices with them."""
        for field in (self.signin_password, self.touroku_password, self.touroku_again):
            field.value = ""
        self.signin_error.value = self.touroku_error.value = ""

    async def render(self):
        """The tab: built once, then shown again as it was. Goes to the place the person was sent to."""
        back = ""
        async with self.lock:
            if not self.built:
                with open(__file__, encoding="utf-8") as f:
                    await preload(self.show, f.read())  # this tab's own words, so none of them loses a character
                await self.build()
            self.clear_screens()
            await self.load_token()
            await self.refresh()
            if self.screen and self.me:  # someone signed in has no use for the two screens: back to the stage
                self.screen, back = "", "/tameshi/" + self.active
            elif not self.screen and self.me is None and not self.info.get("error"):
                # Not signed in: the stage does not open, the sign-in screen does (design 5.1). The place the person
                # came for stays the open one, so that signing in opens it. The route change shows the screen,
                # so render does not come here again.
                self.active, self.aim = self.aim or self.active, ""
                self.enter(self.active)
                self.screen, back = "signin", "/tameshi/signin"
            self.show([self.current_root()])
            if not self.screen:
                await self.arrive()
        if back:
            await self.page.push_route(back)  # outside the lock: the route change renders again
        elif self.token and not self.screen:
            asyncio.create_task(self.list_jobs())

    async def refresh(self):
        """What the server says of this person: the person's line when signed in, nothing when not."""
        self.me = None
        if self.token:
            try:
                self.me = await self.json("GET", "/api/me")
            except ApiError:
                pass
        me = self.me
        self.use_box.visible = me is not None
        if me:
            self.who.value = "テストアカウント" if me["provider"] == "test" else (me["email"] or me.get("id") or me["provider"])
        self.enter(self.active)
        self.page.update()

    def update_left(self):
        """The count left of the stage that is open: the person's line has no other."""
        if self.me:
            self.left.value = f"今日あと: {self.me['left'][QUOTA[self.active]]} 回"

    def enter(self, place):
        """Makes the stage of this place the open one: its box is shown, and what depends on it (the count left) follows."""
        self.active = place
        for key, box in self.sections.items():
            box.visible = key == place
        if self.info.get("error"):  # the server could not be asked: the stage is open, but nothing it does will work
            self.stage_note.value, self.stage_note.color = "いまは使えません: " + self.info["error"], ft.Colors.ERROR
        else:
            self.stage_note.value, self.stage_note.color = "", ft.Colors.ON_SURFACE_VARIANT
        self.stage_note.visible = bool(self.stage_note.value)  # empty, it would leave a gap under the title
        for p, b in self.provider_buttons.items():
            b.action = ft.OpenUrl(f"{PUBLIC}/login/{p}?" + urllib.parse.urlencode({"next": RETURN + "tameshi/" + place}), target=ft.UrlTarget.SELF)
            b.visible = bool(self.page.web and self.info and p in self.info["providers"])
        self.update_left()

    async def open(self, place):
        """What arriving at /app/tameshi/<place> and the buttons that carry a result on do: the stage opens, and the
        notices left under its buttons by an earlier visit are cleared (a refresh of the job lists does not come here)."""
        self.enter(place)
        if place in self.job_notes:
            self.job_notes[place].value = ""
        if place == "kaizen":
            self.kaizen_note.value = ""
        self.page.update()

    async def arrive(self):
        """Opens the stage the person was sent to (the second step when none), and the first field of it, once signed in."""
        place, self.aim = self.aim or self.active, ""
        await self.open(place)
        if self.to_top:  # sent here by a button that carries a result on: the stage is read from its top
            self.to_top = False
            try:
                await self.body.scroll_to(offset=0, duration=0)
            except Exception:  # a screen that cannot scroll is no reason to stop
                pass
        if self.me:
            first = self.first_field.get(place)
            if first is not None:
                try:
                    await first.focus()
                except Exception:  # a screen that cannot focus is no reason to stop
                    pass

    async def goto(self, place):
        """The stage of this place opens, and its first field can be typed in: what the buttons that carry a result on do.
        The address follows (/tameshi/<place>), so a reload returns to this stage. The route change renders the tab and
        arrive opens the stage, once; what the buttons set in the choosers before is kept. When the address already
        names this place no route change comes, so the stage is opened here."""
        self.to_top = True
        if place_of(self.page.route)[1] == place:
            self.aim = place
            await self.arrive()
        else:
            await self.page.push_route("/tameshi/" + place)

    # ---- small parts ------------------------------------------------------------------

    def note(self, text="", small=True):
        return ft.Text(text, size=13 if small else 14, color=ft.Colors.ON_SURFACE_VARIANT, selectable=True)

    def say(self, control, text, bad=False):
        control.value = text
        control.color = ft.Colors.ERROR if bad else ft.Colors.ON_SURFACE_VARIANT
        self.page.update()

    def labelled(self, label, control):
        return ft.Column([ft.Text(label, size=14, weight=ft.FontWeight.W_600), control], spacing=4,
                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    def field(self, hint="", lines=1, max_lines=None, max_length=None, **more):
        if lines > 1:
            more |= {"multiline": True, "min_lines": lines, "max_lines": max_lines or max(lines, 6)}
        return ft.TextField(hint_text=hint, max_length=max_length, **more)

    def link(self, label, url):
        return ft.TextButton(label, action=ft.OpenUrl(url, target=ft.UrlTarget.BLANK))

    def section(self, key, title, controls):
        """One box of the tab; its key lets the tab scroll to it."""
        return ft.Container(ft.Column([ft.Text(title, size=19, weight=ft.FontWeight.BOLD), *controls], spacing=10,
                                     horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                            key=key, padding=16, border_radius=14, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW)

    async def pick_materials(self, kind, shown):
        files = await self.picker.pick_files(allow_multiple=True, with_data=True, file_type=ft.FilePickerFileType.CUSTOM,
                                             allowed_extensions=["md", "adoc", "txt", "zip"])
        if files:
            self.picked[kind] = [(f.name, f.bytes or b"") for f in files]
            shown.value = "選んだ資料: " + "、".join(n for n, _ in self.picked[kind])
            self.page.update()

    def materials(self, kind):
        """The row that picks the materials of a job: the button, and the names picked under it."""
        shown = self.note("")
        button = ft.OutlinedButton("資料を選ぶ", icon=ft.Icons.UPLOAD_FILE,
                                   on_click=lambda e: asyncio.create_task(self.pick_materials(kind, shown)))
        return ft.Column([button, shown], spacing=4)

    def chooser(self, place, label):
        """A dropdown of finished jobs, which starts with 読ませない; the jobs are put in by list_jobs, and the
        row is shown only when there is a job to choose."""
        box = ft.Dropdown(value=NONE, options=[ft.DropdownOption(key=NONE, text="読ませない")], width=420)
        row = self.labelled(label, ft.Row([box]))  # in a Row, so that the dropdown keeps its width of 420
        row.visible = False
        self.chooses[place], self.choose_rows[place] = box, row
        return row, box

    # ---- building the tab -------------------------------------------------------------

    async def build(self):
        if self.info is None:
            try:
                self.info = await self.json("GET", "/api/info")
            except ApiError as e:
                self.info = {"providers": [], "test_login": False, "error": str(e)}
        self.first_field = {}
        self.job_boxes = {}   # kind -> the column that lists the jobs of that kind
        self.job_notes = {}
        self.chooses = {}     # place -> the dropdown that reads a finished job of another kind
        self.choose_rows = {}  # place -> the row of that dropdown, which is shown only when there is a job to read
        self.fields = {}
        self.build_screens()
        # who and how many are left
        self.who, self.left = self.note(""), self.note("")
        self.use_box = ft.Row([self.who, ft.Text("・"), self.left, ft.Text("・"),
                               ft.TextButton("サインアウト", on_click=self.sign_out)], wrap=True, spacing=6, visible=False)
        # the stages, of which one is open
        self.sections = {"chousa": self.build_chousa(), "kaizen": self.build_kaizen(), "kadai": self.build_kadai(),
                         "sekkei": self.build_sekkei(), "tesuto": self.build_tesuto()}
        for key, box in self.sections.items():
            box.visible = key == self.active
        self.stage = ft.Column(list(self.sections.values()), spacing=0)
        self.stage_note = self.note("")  # says that the server is not there
        self.root = ft.Column([
            ft.Text("作る", size=22, weight=ft.FontWeight.BOLD),
            self.stage_note, self.use_box, self.stage], spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.built = True

    def build_screens(self):
        """The two screens of design 5.7, each a box of about 420 px in the middle."""
        self.provider_buttons = {p: ft.FilledButton(t, visible=False) for p, t in SIGN_IN.items()}
        self.signin_error = ft.Text("", size=13, color=ft.Colors.ERROR, selectable=True)
        self.signin_id = ft.TextField(label="ID")
        self.signin_password = ft.TextField(label="パスワード", password=True, can_reveal_password=True,
                                            on_submit=lambda e: asyncio.create_task(self.log_in(e)))
        self.signin_root = self.screen_box("サインイン", [
            ft.Column(list(self.provider_buttons.values()), spacing=8),
            self.signin_id, self.signin_password,
            ft.FilledButton("サインイン", on_click=self.log_in),
            self.signin_error,
            ft.Row([ft.Text("登録していない人は", size=14), ft.TextButton("新しく登録する", on_click=self.to("touroku"))],
                   wrap=True, spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)])
        self.touroku_error = ft.Text("", size=13, color=ft.Colors.ERROR, selectable=True)
        self.touroku_id = ft.TextField(label="ID", helper="小文字の英数字と - _ で、3〜32 字")
        self.touroku_password = ft.TextField(label="パスワード", helper="8 字以上", password=True, can_reveal_password=True)
        self.touroku_again = ft.TextField(label="パスワード(もう一度)", password=True, can_reveal_password=True,
                                          on_submit=lambda e: asyncio.create_task(self.register(e)))
        self.touroku_root = self.screen_box("新しく登録する", [
            self.note("ID とパスワードを決めます。メールアドレスは要りません。登録したあと、持ち主が承認すると、Gemini に頼めるようになります。", small=False),
            self.touroku_id, self.touroku_password, self.touroku_again,
            ft.Row([self.note("登録すると、プライバシーポリシーに同意したことになります"), self.link("プライバシーポリシー", SITE + "/privacy.html")],
                   wrap=True, spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.FilledButton("登録する", on_click=self.register),
            self.touroku_error,
            ft.Row([ft.Text("登録してある人は", size=14), ft.TextButton("サインイン", on_click=self.to("signin"))],
                   wrap=True, spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)])

    def screen_box(self, title, controls):
        """A screen: one box of 420 px in the middle, with the title over the controls."""
        box = ft.Container(ft.Column([ft.Text(title, size=19, weight=ft.FontWeight.BOLD), *controls], spacing=12,
                                     horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                           width=420, padding=24, border_radius=14, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW)
        return ft.Row([box], alignment=ft.MainAxisAlignment.CENTER)

    def job_section(self, kind, title, sentence, controls, buttons):
        """A box with its one sentence, the inputs of a job, its button row,
        and the list of the jobs asked for."""
        self.job_notes[kind] = self.note("")
        self.job_boxes[kind] = ft.Column(spacing=10)
        return self.section(kind, title, [self.note(sentence, small=False), *controls, ft.Row(buttons, wrap=True, spacing=8),
                                          self.job_notes[kind], self.job_boxes[kind]])

    def go_button(self, kind, label):
        return ft.FilledButton(label, on_click=lambda e: asyncio.create_task(self.submit(kind)))

    def build_chousa(self):
        self.fields["chousa"] = {"note": self.field("", 8, 20, max_length=2000)}
        self.first_field["chousa"] = self.fields["chousa"]["note"]
        return self.job_section(
            "chousa", PLACES["chousa"], "何度も頼んでいることを書くと、Gemini が似たアプリを探し、出典を付けてまとめます。",
            [self.labelled("何度も頼んでいること", self.fields["chousa"]["note"])], [self.go_button("chousa", "探す")])

    def build_kaizen(self):
        pick, self.kaizen_job = self.chooser("kaizen", "読ませる結果")
        self.kaizen_fuman = self.field("", 8, 20, max_length=2000)
        self.first_field["kaizen"] = self.kaizen_fuman
        self.kaizen_note = self.note("")
        self.kaizen_log = ft.Column(spacing=8)
        self.kaizen_say = self.field("", 4, 12, max_length=4000)
        self.kaizen_start = ft.Column([
            pick, self.labelled("困っていること", self.kaizen_fuman), ft.Row([ft.FilledButton("考える", on_click=self.kaizen_begin)])],
            spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.kaizen_talkbox = ft.Column([
            self.kaizen_log, self.kaizen_say,
            ft.Row([ft.FilledButton("送る", on_click=self.kaizen_next), ft.TextButton("初めから", on_click=self.kaizen_again)], spacing=8)],
            spacing=10, visible=False, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        return self.section("kaizen", PLACES["kaizen"], [
            self.note("今あるアプリで困っていることを書くと、Gemini と一緒に、どう良くするかを考えます。", small=False),
            self.kaizen_start, self.kaizen_talkbox, self.kaizen_note])

    def build_kadai(self):
        pick, _ = self.chooser("kadai", "読ませる結果")
        self.first_field["kadai"] = None
        return self.job_section(
            "kadai", PLACES["kadai"], "探した結果を選ぶと、Gemini がそのアプリの問題点を集め、出典を付けてまとめます。",
            [pick], [self.go_button("kadai", "集める")])

    def build_sekkei(self):
        pick, _ = self.chooser("sekkei", "読ませる課題の資料")
        self.first_field["sekkei"] = None
        return self.job_section(
            "sekkei", PLACES["sekkei"], "SKILL.md と資料を選ぶと、Gemini が設計書と、画面の絵を入れたマニュアルを作ります。",
            [pick, self.materials("sekkei")], [self.go_button("sekkei", "作る")])

    def build_tesuto(self):
        pick, _ = self.chooser("tesuto", "読ませる設計書とマニュアル")
        self.first_field["tesuto"] = None
        return self.job_section(
            "tesuto", PLACES["tesuto"], "設計書とマニュアルを選ぶと、Gemini がテストの手順を作ります。",
            [pick, self.materials("tesuto")], [self.go_button("tesuto", "作る")])

    # ---- signing in and out -----------------------------------------------------------

    async def go(self, route):
        """Goes to a screen (signin, touroku) or a stage: the route changes, and the app shows what it names."""
        await self.page.push_route("/tameshi/" + route)

    async def signed_in_or_go(self):
        """True when the person is signed in. If not, goes to the sign-in screen and returns False, so that the
        button that asked for Gemini does nothing else; after signing in the person presses it again."""
        if self.me is not None:
            return True
        await self.go("signin")
        return False

    def to(self, route):
        """A button that goes to a screen or a stage."""
        return lambda e: asyncio.create_task(self.go(route))

    async def enter_with(self, path, error, body):
        """Signs in, or registers, with what the screen has written; then the person is back on the stage that was open."""
        try:
            await self.keep_token((await self.json("POST", path, json=body))["token"])
        except ApiError as err:
            self.say(error, "、".join(err.messages), True)
            return
        self.clear_screens()
        await self.go(self.active)  # render shows the stage again, with the person's line

    async def log_in(self, e):
        await self.enter_with("/api/login", self.signin_error,
                              {"id": self.signin_id.value or "", "password": self.signin_password.value or ""})

    async def register(self, e):
        if (self.touroku_password.value or "") != (self.touroku_again.value or ""):
            self.say(self.touroku_error, "2 つのパスワードが同じではありません", True)
            return
        await self.enter_with("/api/register", self.touroku_error,
                              {"id": self.touroku_id.value or "", "password": self.touroku_password.value or ""})

    async def sign_out(self, e):
        try:
            await self.call("POST", "/api/logout", json={})
        except ApiError:
            pass
        self.token, self.me, self.screen, self.aim = "", None, "", ""
        await self.forget_token()
        await self.render()  # a signed-out person lands on the sign-in screen

    # ---- the answers of Gemini ---------------------------------------------------------

    def bubble(self, role, text):
        you = role == "user"
        return ft.Container(ft.Text(text, selectable=True), padding=ft.Padding.symmetric(vertical=8, horizontal=12), border_radius=12,
                            bgcolor=ft.Colors.PRIMARY_CONTAINER if you else ft.Colors.SURFACE_CONTAINER_HIGHEST,
                            margin=ft.Margin.only(left=40 if you else 0, right=0 if you else 40))

    def count_left(self, d):
        """An answer says how many are left of what it used, which is what the open stage counts."""
        if d.get("left") is not None and self.me:
            self.me["left"][QUOTA[self.active]] = d["left"]
            self.update_left()

    # ---- step 3: how to make the apps there are better ----------------------------------

    async def kaizen_begin(self, e):
        if not await self.signed_in_or_go():
            return
        fuman = (self.kaizen_fuman.value or "").strip()
        if not fuman:
            self.say(self.kaizen_note, "困った場面と、困ったことを書いてください", True)
            return
        await self.kaizen_ask(f"使ったアプリ: (書いていません)\n困った場面と、困ったこと: {fuman}")

    async def kaizen_next(self, e):
        if not await self.signed_in_or_go():
            return
        text = (self.kaizen_say.value or "").strip()
        if text:
            self.kaizen_say.value = ""
            if not await self.kaizen_ask(text):
                self.kaizen_say.value = text  # what was written stays
                self.page.update()

    async def kaizen_ask(self, text):
        """Asks Gemini in the dialogue of step 3; returns whether it answered."""
        self.kaizen_talk.append({"role": "user", "text": text})
        self.kaizen_log.controls.append(self.bubble("user", text))
        self.kaizen_start.visible, self.kaizen_talkbox.visible = False, True
        self.say(self.kaizen_note, "Gemini が考えています")
        job = self.kaizen_job.value
        try:
            d = await self.json("POST", "/api/kaizen", json={"job": "" if job == NONE else job, "messages": self.kaizen_talk})
        except ApiError as err:
            self.kaizen_talk.pop()
            self.kaizen_log.controls.pop()
            if not self.kaizen_talk:
                self.kaizen_start.visible, self.kaizen_talkbox.visible = True, False
            self.say(self.kaizen_note, "、".join(err.messages), True)
            return False
        self.kaizen_talk.append({"role": "model", "text": d["text"]})
        self.kaizen_log.controls.append(self.bubble("model", d["text"]))
        self.count_left(d)
        self.say(self.kaizen_note, "")
        return True

    def kaizen_reset(self):
        self.kaizen_talk = []
        self.kaizen_log.controls = []
        self.kaizen_start.visible, self.kaizen_talkbox.visible = True, False
        self.kaizen_note.value = ""

    async def kaizen_again(self, e):
        self.kaizen_reset()
        self.page.update()

    # ---- the longer jobs ---------------------------------------------------------------

    async def submit(self, kind):
        """Asks for a job: checks the sign-in and what it needs, as the server would, then sends it."""
        if not await self.signed_in_or_go():
            return
        note = self.job_notes[kind]
        f = self.fields.get(kind, {})
        text = (f["note"].value or "").strip() if "note" in f else ""
        choose = self.chooses.get(kind)
        chosen = "" if choose is None or choose.value == NONE else choose.value
        # the design job is made from the SKILL.md and the materials; the problems chosen only add to them
        given = bool(self.picked[kind]) if kind == "sekkei" else bool(self.picked[kind]) or chosen or text
        if not given:
            self.say(note, ENOUGH[kind], True)
            return
        data = {"kind": kind, "note": text}
        if kind == "kadai":
            data["research"] = chosen
        if kind == "sekkei":
            data["kadai"] = chosen
        if kind == "tesuto":
            data["sekkei"] = chosen
        files = [("files", (name, content, "application/octet-stream")) for name, content in self.picked[kind]]
        self.say(note, "送っています")
        try:
            await self.call("POST", "/api/jobs", data={k: v for k, v in data.items() if v}, files=files or None)
        except ApiError as err:
            self.say(note, "、".join(err.messages), True)
            return
        self.say(note, "始めました。下で進み具合を見られます")
        try:  # a job used one of the day's
            self.me = await self.json("GET", "/api/me")
            self.update_left()
        except ApiError:
            pass
        await self.list_jobs()

    async def list_jobs(self):
        """Reads the person's jobs and puts each in its box; reads again every 5 seconds while one is going."""
        if not self.token or self.polling:
            return
        self.polling = True
        try:
            while True:
                try:
                    jobs = (await self.json("GET", "/api/jobs"))["jobs"]
                except ApiError:
                    return
                busy = False
                lists = {k: [] for k in JOBS}
                for j in jobs:
                    busy = busy or j["status"] in ("waiting", "running")
                    held = self.cards.get(j["id"])
                    if held is None or held[0] != j["status"] or j["status"] in ("waiting", "running"):
                        try:
                            detail = await self.json("GET", f"/api/jobs/{j['id']}")
                            self.cards[j["id"]] = (j["status"], await self.card(j, detail))
                        except ApiError:
                            continue
                    if j["kind"] in lists:
                        lists[j["kind"]].append(self.cards[j["id"]][1])
                for gone in set(self.cards) - {j["id"] for j in jobs}:  # jobs the server deleted
                    del self.cards[gone]
                for kind, controls in lists.items():
                    self.job_boxes[kind].controls = controls
                self.fill_choices(jobs)
                self.page.update()
                if not busy or not self.me:
                    return
                await asyncio.sleep(5)
        except Exception:  # the page was closed
            return
        finally:
            self.polling = False

    def fill_choices(self, jobs):
        """The dropdowns that read a finished job: kaizen and kadai read a search, sekkei the problems, tesuto the design."""
        reads = {"kaizen": "chousa", "kadai": "chousa", "sekkei": "kadai", "tesuto": "sekkei"}
        for place, kind in reads.items():
            box = self.chooses[place]
            had = box.value
            box.options = [ft.DropdownOption(key=NONE, text="読ませない")] + [
                ft.DropdownOption(key=j["id"], text=f"{JOBS[kind]} ・ {when(j['created'])}") for j in jobs if j["kind"] == kind and j["status"] == "done"]
            box.value = had if any(o.key == had for o in box.options) else NONE
            self.choose_rows[place].visible = len(box.options) > 1  # shown only when there is a finished job to read

    async def card(self, j, d):
        """What one job shows: its line; while it goes, its steps; if it stopped, the notice; when done, its documents
        (the main one open), then the buttons (design 5.8)."""
        parts = [ft.Text(f"{JOBS[j['kind']]} ・ {when(j['created'])} ・ {STATUS[j['status']]}", weight=ft.FontWeight.W_600)]
        if j["status"] in ("waiting", "running"):
            parts += [ft.Text(s["name"] + (f"({s['seconds']} 秒)" if "seconds" in s else ""), size=13) for s in d["steps"]]
        if d["error"]:
            parts.append(ft.Text(d["error"], size=13, color=ft.Colors.ERROR))
        if j["status"] == "done":
            parts += await self.documents(j["id"], j["kind"], d["files"])
            parts.append(ft.Row(self.card_buttons(j["id"], j["kind"]), wrap=True, spacing=8))
        return ft.Container(ft.Column(parts, spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                            padding=12, border_radius=10, bgcolor=ft.Colors.SURFACE)

    def card_buttons(self, jid, kind):
        async def zip_it(e):
            try:
                data = (await self.call("GET", f"/api/jobs/{jid}/zip")).content
            except ApiError as err:
                self.say(self.job_notes[kind], "、".join(err.messages), True)
                return
            await self.picker.save_file(file_name=f"aiai-{kind}-{jid[:6]}.zip", src_bytes=data)

        def to(place, choose, label):
            async def go(e):
                if place == "kaizen":
                    self.kaizen_reset()
                choose.value = jid
                self.page.update()
                await self.goto(place)
            return ft.FilledButton(label, on_click=go)

        buttons = [ft.OutlinedButton("まとめてダウンロード(ZIP)", icon=ft.Icons.DOWNLOAD, on_click=zip_it)]
        if kind == "chousa":
            buttons += [to("kaizen", self.kaizen_job, "この結果で、どう良くするかを考える"), to("kadai", self.chooses["kadai"], "この結果で、課題を集める")]
        if kind == "kadai":
            buttons.append(to("sekkei", self.chooses["sekkei"], "この資料で、設計書とマニュアルを作る"))
        if kind == "sekkei":
            buttons.append(to("tesuto", self.chooses["tesuto"], "この結果で、テストの手順を作る"))
        return buttons

    def arrange(self, kind, files):
        """The files of a done job in the order they are shown: [(path, title, shown open)], the open documents first, then the
        closed ones named in DOCUMENTS, then the rest titled by their paths. Pictures are not here (see pictures)."""
        texts = [f for f in files if not f.endswith(".png")]
        named = []
        for pattern, title, opened in DOCUMENTS.get(kind, []):
            named += [(f, title, opened) for f in texts if fnmatch.fnmatchcase(f, pattern)]
        known = {f for f, _, _ in named}
        named += [(f, f, False) for f in texts if f not in known]
        return sorted(named, key=lambda x: not x[2])  # stable: the open ones first

    async def fetch(self, jid, path):
        """(text of a file of a job, the notice of the server when it could not be read)."""
        try:
            return (await self.call("GET", f"/api/jobs/{jid}/file", params={"path": path})).text, ""
        except ApiError as err:
            return "", "、".join(err.messages)

    def reading(self, path, text):
        """A document as it is read: an .adoc as Markdown (the same conversion as the user manual, without the pictures,
        which are shown by pictures()), links in a new tab, the text selectable; any other file as plain text."""
        if path.endswith((".adoc", ".md")):
            md = adoc_to_md(text) if path.endswith(".adoc") else text
            md = re.sub(r"^!\[[^\]]*\]\((?!https?:)[^)]*\)[ \t]*\n?", "", md, flags=re.M)  # a picture of the job, shown below
            return ft.Markdown(md, selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_FLAVORED,
                               auto_follow_links=True, auto_follow_links_target=ft.UrlTarget.BLANK)
        return ft.Text(text, size=13, selectable=True)

    async def pictures(self, jid, files):
        """The screen pictures of a job, one by one, as wide as the box (up to PICTURE_WIDTH)."""
        out = []
        for path in (f for f in files if f.endswith(".png")):
            try:
                png = (await self.call("GET", f"/api/jobs/{jid}/file", params={"path": path})).content
            except ApiError:
                out.append(ft.Text(path, size=13))
                continue
            out.append(ft.Image(src=png, width=PICTURE_WIDTH, fit=ft.BoxFit.CONTAIN, semantics_label=path))
        return out

    async def documents(self, jid, kind, files):
        """The documents of a done job: the main one open (the pictures under it) with no title of its own, as the
        document begins with its heading; the others as tiles titled by DOCUMENTS, read when they are opened."""
        out, pictures = [], await self.pictures(jid, files)
        for path, title, opened in self.arrange(kind, files):
            if opened:
                text, bad = await self.fetch(jid, path)
                out.append(ft.Text(bad, size=13, color=ft.Colors.ERROR) if bad else self.reading(path, text))
                if pictures:  # the pictures belong to the manual, the open document of the design job
                    out += pictures
                    pictures = []
            else:
                out.append(self.tile(jid, path, title))
        return out + pictures

    def tile(self, jid, path, title):
        """A closed document; its text is read when it is opened, once."""
        holder = ft.Container(padding=12)
        loaded = {"yes": False}

        async def opened(e):
            if e.control.expanded and not loaded["yes"]:
                loaded["yes"] = True
                text, bad = await self.fetch(jid, path)
                holder.content = ft.Text(bad, size=13, color=ft.Colors.ERROR) if bad else self.reading(path, text)
                self.page.update()

        return ft.ExpansionTile(title=ft.Text(title, size=14), controls=[holder], on_change=opened)
