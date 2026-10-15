# SPDX-License-Identifier: AGPL-3.0-or-later
"""The 作る tab of the aiai app: the steps of "度々聞いていることを、アプリにする"
(rireki/SKILL.md) that Google Cloud's Gemini does for a person who signs in. It talks to
tameshi/server.py at /tameshi, with the fields, buttons and notices of tameshi/docs/design.adoc, 5.
One stage is open at a time, under a strip of the eight steps like the top page's flow:

    2 今あるアプリを探す  3 どう良くするかを考える  5 今あるアプリの課題を集める
    6 設計書とマニュアルを作る  8 テストの手順を作る  then a dialogue with a guide, and the news

The longer jobs take minutes; their lists are read again every 5 seconds while one is
running. The sign-in comes back to /app/tameshi/<place> with a one-time code in the
address, which is traded for a session number kept only while the app is open (as in
soudan_view.py). On the phone only the test account signs in. Settings:

    AIAI_TAMESHI_URL  the server as people reach it (default AIAI_SITE + /tameshi); sign-in links use it
                      (AIAI_TAMESHI=1 is another thing: it tells site/server.py to mount the server)
    AIAI_TAMESHI_API  the same server as this app reaches it, when that differs
    AIAI_RETURN       the app's address, where sign-in comes back to (default AIAI_SITE + /app/)
"""
import asyncio
import os
import re
import urllib.parse

import flet as ft
import httpx
from glyphs import preload

SITE = os.environ.get("AIAI_SITE", "http://127.0.0.1:8020").rstrip("/")
PUBLIC = (os.environ.get("AIAI_TAMESHI_URL") or SITE + "/tameshi").rstrip("/")
API = os.environ.get("AIAI_TAMESHI_API", PUBLIC).rstrip("/")
RETURN = (os.environ.get("AIAI_RETURN") or SITE + "/app/").rstrip("/") + "/"
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
MIHON_URL = "https://github.com/aiseed-dev/aiai/tree/main/hackathon/mihon"
SIGN_IN = {"google": "Google でサインイン", "apple": "Apple でサインイン"}

# The places of the flow that can be opened with /app/tameshi/<place>, by the name of the field
PLACES = {"chousa": "2 今あるアプリを探す", "kaizen": "3 どう良くするかを考える", "kadai": "5 今あるアプリの課題を集める",
          "sekkei": "6 設計書とマニュアルを作る", "tesuto": "8 テストの手順を作る"}
JOBS = {"chousa": "今あるアプリを探す", "kadai": "今あるアプリの課題を集める", "sekkei": "設計書とマニュアル", "tesuto": "テストの手順"}
# The strip of steps over the stage, like the flow of the top page: (label, place, whether Gemini does it)
STRIP = [("1 見つける", None), ("2 探す", "chousa"), ("3 考える", "kaizen"), ("4 決める", None), ("5 課題", "kadai"),
         ("6 設計書", "sekkei"), ("7 実装", None), ("8 テスト", "tesuto")]
OTHERS = [("対話", "chat"), ("ニュース", "news")]  # outside the flow, at the right end of the strip
NAMES = dict(PLACES, chat="手引きを読ませた Gemini と対話する", news="今日のニュースを作らせる")  # what the person is going to, by place
QUOTA = {"chousa": "chousa", "kaizen": "chat", "kadai": "kadai", "sekkei": "sekkei", "tesuto": "tesuto", "chat": "chat", "news": "news"}
OWN_STEP = "この段は、自分と、ふだん使っている AI でします"
STATUS = {"waiting": "待っています", "running": "進めています", "done": "できました", "error": "止まりました"}
# What a form needs before it is sent, in the words of the server's refusal (design 5.3)
ENOUGH = {"chousa": "何度も頼んでいることを書くか、資料を選んでください",
          "kadai": "読ませる結果を選ぶか、資料を選んでください",
          "sekkei": "SKILL.md と参考の資料を選ぶか、見本で試してください",
          "tesuto": "読ませる設計書とマニュアルを選ぶか、資料を選んでください"}
NONE = "-"  # the choice of 読ませない in a dropdown, which keeps no empty key


class ApiError(Exception):
    def __init__(self, status, messages):
        super().__init__("、".join(messages))
        self.status, self.messages = status, messages


def first_sentences(text, n=2):
    """The first n sentences of a text (up to the 。), which is what a stage says of what Gemini does."""
    return "".join(re.findall(r"[^。]*。", text)[:n])


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def place_of(route):
    """(is this a route of the tab, the place named at its end, the one-time code) of an address."""
    parts = urllib.parse.urlsplit(route or "")
    segments = [s for s in parts.path.split("/") if s]
    if not segments or segments[0] != "tameshi":
        return False, "", ""
    place = segments[1] if len(segments) > 1 and segments[1] in PLACES else ""
    return True, place, dict(urllib.parse.parse_qsl(parts.query)).get("code", "")


class TameshiView:
    """The 作る tab. show(controls) puts controls on the tab's screen; body is the column that
    scrolls, so that a place can be brought to the top."""

    def __init__(self, page, show, body):
        self.page, self.show, self.body = page, show, body
        self.http = httpx.AsyncClient(base_url=API, timeout=300)
        self.token = ""
        self.info = None
        self.me = None
        self.aim = ""          # the place the person is going to, until the stage is opened
        self.active = "chousa"  # the stage that is open: one at a time
        self.built = False
        self.picker = ft.FilePicker()
        self.clipboard = ft.Clipboard()
        self.talk = []         # the dialogue with a guide
        self.kaizen_talk = []  # the dialogue of step 3
        self.picked = {k: [] for k in JOBS}  # the materials picked for each job: [(name, bytes)]
        self.cards = {}        # job id -> (status, card), so a finished job is built once
        self.polling = False
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
            raise ApiError(r.status_code, detail if isinstance(detail, list) else [str(detail or f"うまくいきませんでした({r.status_code})")])
        return r

    async def json(self, method, path, **kw):
        return (await self.call(method, path, **kw)).json()

    # ---- coming back from sign-in, and being sent to a place ---------------------------

    async def take_route(self, route):
        """For a route of the tab: trades the code in it for a session number and strips the code;
        returns whether the route was one of the tab."""
        mine, place, code = place_of(route)
        if not mine:
            return False
        if place:
            self.aim = place
        if code:
            try:
                self.token = (await self.json("POST", "/api/session", json={"code": code}))["token"]
            except ApiError:
                pass
            self.page.navigate("/tameshi" + (f"/{place}" if place else ""))  # takes the used code out of the address
        return True

    async def render(self):
        """The tab: built once, then shown again as it was. Goes to the place the person was sent to."""
        async with self.lock:
            if not self.built:
                with open(__file__, encoding="utf-8") as f:
                    await preload(self.show, f.read())  # this tab's own words, so none of them loses a character
                await self.build()
            await self.refresh()
            self.show([self.root])
            await self.arrive()
        if self.token:
            asyncio.create_task(self.list_jobs())

    async def refresh(self):
        """What the server says of this person: the sign-in when not signed in, else the person's line."""
        self.me = None
        if self.token:
            try:
                self.me = await self.json("GET", "/api/me")
            except ApiError:
                pass
        me = self.me
        self.sign_in_box.visible = me is None
        self.use_box.visible = me is not None
        if me:
            self.who.value = "テストアカウント" if me["provider"] == "test" else (me["email"] or me["provider"])
        elif self.info.get("error"):
            self.say(self.sign_in_note, "いまは使えません: " + self.info["error"], True)
        self.enter(self.active)
        self.test_box.visible = bool(self.info and self.info["test_login"])
        self.page.update()

    def update_left(self):
        """The count left of the stage that is open: the person's line has no other."""
        if self.me:
            self.left.value = f"今日あと: {self.me['left'][QUOTA[self.active]]} 回"

    def enter(self, place):
        """Makes the stage of this place the open one: its box is shown, its tag in the strip is filled, and what
        depends on it (the line of the sign-in, the count left, whether its inputs can be pressed) follows."""
        self.active = place
        for key, box in self.sections.items():
            box.visible = key == place
        for key, (chip, label) in self.chips.items():
            filled = key == place
            chip.bgcolor = ft.Colors.PRIMARY if filled else (ft.Colors.PRIMARY_CONTAINER if key in PLACES else ft.Colors.SURFACE_CONTAINER)
            label.color = ft.Colors.ON_PRIMARY if filled else (ft.Colors.ON_PRIMARY_CONTAINER if key in PLACES else ft.Colors.ON_SURFACE_VARIANT)
            label.weight = ft.FontWeight.BOLD if filled else ft.FontWeight.W_500
        self.stage_note.value = ""
        signed, may = self.me is not None, bool(self.me and self.me["kaihatsu"])
        self.stage.disabled = not signed or (place in JOBS and not may)
        if signed and place in JOBS and not may:
            self.stage_note.value = "この機能は、使える人を決めています"
            self.stage_note.color = ft.Colors.ERROR
        elif not self.info.get("error"):
            self.sign_in_note.value = f"サインインすると、「{NAMES[place]}」に進みます"
            self.sign_in_note.color = None
        for p, b in self.provider_buttons.items():
            b.action = ft.OpenUrl(f"{PUBLIC}/login/{p}?" + urllib.parse.urlencode({"next": RETURN + "tameshi/" + place}), target=ft.UrlTarget.SELF)
            b.visible = bool(self.page.web and self.info and p in self.info["providers"])
        self.update_left()

    async def open(self, place):
        """What pressing a tag of the strip does, and what arriving at /app/tameshi/<place> does: the stage opens."""
        self.enter(place)
        self.page.update()

    async def arrive(self):
        """Opens the stage the person was sent to (the second step when none), and the first field of it, once signed in."""
        place, self.aim = self.aim or self.active, ""
        await self.open(place)
        if self.me and not self.stage.disabled:
            first = self.first_field.get(place)
            if first is not None:
                try:
                    await first.focus()
                except Exception:  # a screen that cannot focus is no reason to stop
                    pass

    async def goto(self, place):
        """The stage of this place opens, and its first field can be typed in: what the buttons that carry a result on do."""
        await self.open(place)
        try:
            await self.body.scroll_to(offset=0, duration=0)
            first = self.first_field.get(place)
            if first is not None:
                await first.focus()
        except Exception:  # a screen that cannot scroll or focus is no reason to stop
            pass

    # ---- small parts ------------------------------------------------------------------

    def note(self, text="", small=True):
        return ft.Text(text, size=13 if small else 14, color=ft.Colors.ON_SURFACE_VARIANT, selectable=True)

    def say(self, control, text, bad=False):
        control.value = text
        control.color = ft.Colors.ERROR if bad else ft.Colors.ON_SURFACE_VARIANT
        self.page.update()

    def labelled(self, label, control):
        return ft.Column([ft.Text(label, size=14, weight=ft.FontWeight.W_600), control], spacing=4)

    def field(self, hint="", lines=1, max_lines=None, max_length=None, **more):
        if lines > 1:
            more |= {"multiline": True, "min_lines": lines, "max_lines": max_lines or max(lines, 6)}
        return ft.TextField(hint_text=hint, max_length=max_length, **more)

    def link(self, label, url):
        return ft.TextButton(label, action=ft.OpenUrl(url, target=ft.UrlTarget.BLANK))

    def section(self, key, title, controls):
        """One box of the tab; its key lets the tab scroll to it."""
        return ft.Container(ft.Column([ft.Text(title, size=19, weight=ft.FontWeight.BOLD), *controls], spacing=10),
                            key=key, padding=16, border_radius=14, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW)

    async def pick_materials(self, kind, shown):
        files = await self.picker.pick_files(allow_multiple=True, with_data=True, file_type=ft.FilePickerFileType.CUSTOM,
                                             allowed_extensions=["md", "adoc", "txt", "zip"])
        if files:
            self.picked[kind] = [(f.name, f.bytes or b"") for f in files]
            shown.value = "選んだ資料: " + "、".join(n for n, _ in self.picked[kind])
            self.page.update()

    def materials(self, kind):
        """The row that picks the materials of a job: the button and the names picked."""
        shown = self.note("")
        button = ft.OutlinedButton("資料を選ぶ", icon=ft.Icons.UPLOAD_FILE,
                                   on_click=lambda e: asyncio.create_task(self.pick_materials(kind, shown)))
        return self.labelled("資料(なくてもかまいません)", ft.Column([button, shown], spacing=4)) if kind != "sekkei" else \
            self.labelled("資料", ft.Column([button, shown], spacing=4))

    def chooser(self, label):
        """A dropdown of finished jobs, which starts with 読ませない; the jobs are put in by list_jobs."""
        box = ft.Dropdown(value=NONE, options=[ft.DropdownOption(key=NONE, text="読ませない")], width=420)
        return self.labelled(label, box), box

    # ---- building the tab -------------------------------------------------------------

    async def build(self):
        if self.info is None:
            try:
                self.info = await self.json("GET", "/api/info")
            except ApiError as e:
                self.info = {"guides": [], "providers": [], "test_login": False, "error": str(e)}
        self.first_field = {}
        self.job_boxes = {}   # kind -> the column that lists the jobs of that kind
        self.job_notes = {}
        self.chooses = {}     # kind -> the dropdown that reads a finished job of another kind
        self.fields = {}
        # sign-in
        self.sign_in_note = self.note("")
        self.provider_buttons = {p: ft.FilledButton(t, width=280, visible=False) for p, t in SIGN_IN.items()}
        self.test_id = ft.TextField(hint_text="ID", width=280)
        self.test_password = ft.TextField(hint_text="パスワード", password=True, can_reveal_password=True, width=280,
                                          on_submit=self.test_login)
        self.test_box = ft.Column([self.note("審査用のテストアカウント"), self.test_id, self.test_password,
                                   ft.OutlinedButton("入る", on_click=self.test_login)], spacing=8, visible=False)
        self.sign_in_box = self.section("sign-in", "サインイン", [
            ft.Column(list(self.provider_buttons.values()), spacing=8), self.test_box, self.sign_in_note])
        # who and how many are left
        self.who, self.left = self.note(""), self.note("")
        self.use_box = ft.Container(ft.Row([self.who, ft.Text("・"), self.left, ft.Text("・"),
                                            ft.TextButton("サインアウト", on_click=self.sign_out)], wrap=True, spacing=6), visible=False)
        # the stages, of which one is open; the strip of the steps over them, like the top page's flow
        self.sections = {"chousa": self.build_chousa(), "kaizen": self.build_kaizen(), "kadai": self.build_kadai(),
                         "sekkei": self.build_sekkei(), "tesuto": self.build_tesuto(), "chat": self.build_dialogue(), "news": self.build_news()}
        self.first_field["chat"], self.first_field["news"] = self.say_box, self.tastes
        for key, box in self.sections.items():
            box.visible = key == self.active
        self.stage = ft.Column(list(self.sections.values()), spacing=0)
        self.stage_note = self.note("")  # what a tag of a step that is not Gemini's says, and what a person who may not ask is told
        self.root = ft.Column([
            ft.Text("作る", size=22, weight=ft.FontWeight.BOLD),
            self.note("アプリを作る流れの 2、3、5、6、8 の段を、Google Cloud の Gemini に頼めます。書いたことは記録しません。", small=False),
            self.build_strip(), self.stage_note, self.sign_in_box, self.use_box, self.stage], spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.built = True

    def build_strip(self):
        """The eight steps as small tags in one row, as the flow of the top page has them: the steps Gemini does can be
        pressed (they are coloured), the others are light and say so when pressed. At the right end, the two that are
        outside the flow. Where the width is short, the tags go on a second row."""
        self.chips = {}

        def tag(label, key):
            text = ft.Text(label, size=13)
            chip = ft.Container(text, padding=ft.Padding.symmetric(vertical=6, horizontal=12), border_radius=999,
                                on_click=(lambda e: asyncio.create_task(self.open(key))) if key else self.own_step(label))
            if key:
                self.chips[key] = (chip, text)
            else:
                chip.bgcolor, text.color = ft.Colors.SURFACE_CONTAINER_LOW, ft.Colors.ON_SURFACE_VARIANT
            return chip

        steps = ft.Row([tag(label, key) for label, key in STRIP], wrap=True, spacing=6, run_spacing=6)
        others = ft.Row([tag(label, key) for label, key in OTHERS], wrap=True, spacing=6, run_spacing=6)
        return ft.Row([steps, others], wrap=True, alignment=ft.MainAxisAlignment.SPACE_BETWEEN, spacing=12, run_spacing=6)

    def own_step(self, label):
        """What pressing a tag of a step that the person does with their own AI does: says so, small."""
        def pressed(e):
            self.stage_note.value, self.stage_note.color = f"{label}: {OWN_STEP}", ft.Colors.ON_SURFACE_VARIANT
            self.page.update()
        return pressed

    def job_section(self, kind, key, title, description, controls, buttons, trial=None):
        """A box with the fields of a job, its buttons, and the list of the jobs asked for."""
        self.job_notes[kind] = self.note("")
        self.job_boxes[kind] = ft.Column(spacing=10)
        parts = [self.note(first_sentences(description)), *controls, ft.Row(buttons, wrap=True, spacing=8)]
        if trial:
            parts.append(ft.Row([self.note(trial[0]), ft.TextButton(trial[1], on_click=lambda e: asyncio.create_task(self.submit(kind, True))),
                                 self.link("見本を見る", MIHON_URL)], wrap=True, spacing=4))
        parts.append(self.note("数分かかります。作った物は 7 日で消します"))
        return self.section(key, title, [*parts, self.job_notes[kind], self.job_boxes[kind]])

    def go_button(self, kind, label):
        return ft.FilledButton(label, on_click=lambda e: asyncio.create_task(self.submit(kind)))

    def build_chousa(self):
        self.fields["chousa"] = {"note": self.field("例: 毎週、売上の表を渡して、品目ごとの集計と先週との比べを頼んでいる", 3, max_length=2000)}
        self.first_field["chousa"] = self.fields["chousa"]["note"]
        return self.job_section(
            "chousa", "chousa", PLACES["chousa"],
            "AI に何度も頼んでいることを書くと、Gemini が、似たアプリを Google 検索で 3 つまで選び、公式サイト、ストアの説明、"
            "利用規約、料金のページを読んで、機能、料金、問題点を、出典を付けてまとめます。SKILL.md や参考の資料(.md、.adoc、.txt か、"
            "それを入れた ZIP)も足せます。数分かかります。作った物は 7 日で消します。",
            [self.labelled("何度も頼んでいること", self.fields["chousa"]["note"]), self.materials("chousa")],
            [self.go_button("chousa", "探す")], ("架空の見本(パン屋の取り置きのアプリ)でも試せます。", "見本で探す"))

    def build_kaizen(self):
        pick, self.kaizen_job = self.chooser("読ませる結果")
        self.chooses["kaizen"] = self.kaizen_job
        self.kaizen_app = self.field("例: 集計のアプリ", max_length=200)
        self.kaizen_fuman = self.field("例: 毎週、売上の表を渡して集計させている。前の週の表が残らないので、先週との比べを毎回自分で作っている", 3, max_length=2000)
        self.kaizen_hoshii = self.field("例: 先週の表を残し、比べた表も一緒に出してほしい", 2, max_length=1000)
        self.first_field["kaizen"] = self.kaizen_fuman
        self.kaizen_note = self.note("")
        self.kaizen_log = ft.Column(spacing=8)
        self.kaizen_say = self.field("", 2, max_length=4000)
        self.kaizen_start = ft.Column([
            pick, self.labelled("使ったアプリ", self.kaizen_app), self.labelled("困った場面と、困ったこと", self.kaizen_fuman),
            self.labelled("どうなればよいか(分かれば)", self.kaizen_hoshii),
            ft.FilledButton("考える", on_click=self.kaizen_begin)], spacing=10)
        self.kaizen_talkbox = ft.Column([
            self.kaizen_log, self.kaizen_say,
            ft.Row([ft.FilledButton("送る", on_click=self.kaizen_next), ft.TextButton("初めから", on_click=self.kaizen_again)], spacing=8)],
            spacing=10, visible=False)
        return self.section("kaizen", PLACES["kaizen"], [
            self.note("今あるアプリを使ってみて、不満な所を具体的に書きます。どのアプリの、どの場面で、何が困るのかが分からないと、Gemini も一緒に考えられません。"),
            self.kaizen_start, self.kaizen_talkbox, self.kaizen_note])

    def build_kadai(self):
        pick, research = self.chooser("読ませる結果")
        self.chooses["kadai"] = research
        self.fields["kadai"] = {"name": self.field("例: toriooki", max_length=40),
                                "note": self.field("例: 前の週の表が残らないので、先週との比べを毎回自分で作っている", 3, max_length=2000)}
        self.first_field["kadai"] = self.fields["kadai"]["name"]
        return self.job_section(
            "kadai", "kadai", PLACES["kadai"],
            "「今あるアプリを探す」の結果か、渡した資料に出てくるアプリについて、使う人にとっての問題点と、運営の作りの問題点を、Gemini が Google 検索で"
            "公式サイトや利用規約などを読んで、出典を付けてまとめます。アプリの名前が出てこなければ、似たことをしているアプリを探してから調べます。"
            "できる物は、手引きの手順 5 の資料(references/<名前>-analysis.adoc)です。数分かかります。作った物は 7 日で消します。",
            [pick, self.labelled("作るアプリの名前(英数字とハイフン。資料のファイルの名前に使います)", self.fields["kadai"]["name"]),
             self.labelled("3 で分かった不満(あれば)", self.fields["kadai"]["note"]), self.materials("kadai")],
            [self.go_button("kadai", "集める")], ("架空の見本(パン屋の取り置きのアプリ)でも試せます。", "見本で集める"))

    def build_sekkei(self):
        pick, kadai = self.chooser("読ませる課題の資料")
        self.chooses["sekkei"] = kadai
        self.fields["sekkei"] = {"note": self.field("足したいこと(なくてもかまいません)", 2, max_length=2000)}
        self.first_field["sekkei"] = None
        return self.job_section(
            "sekkei", "sekkei", PLACES["sekkei"],
            "作るアプリの SKILL.md と参考の資料(.md、.adoc、.txt か、それを入れた ZIP)を渡します。SKILL.md は、手引き「度々聞いていることを、アプリにする」の"
            "「アプリの SKILL.md の形」に沿って、自分の AI と書きます。上の「今あるアプリの課題を集める」の資料も読ませられます。Gemini 4 Argon が設計書と"
            "利用者マニュアルを書き、画面の絵を Nano Banana が描き、最後に 2 つを照らし合わせます。数分かかります。作った物は 7 日で消します。",
            [pick, self.materials("sekkei"), self.fields["sekkei"]["note"]],
            [self.go_button("sekkei", "設計書とマニュアルを作る")],
            ("資料が手元に無ければ、架空の見本(パン屋の取り置きのアプリ)で試せます。", "見本で設計書とマニュアルを作る"))

    def build_tesuto(self):
        pick, sekkei = self.chooser("読ませる設計書とマニュアル")
        self.chooses["tesuto"] = sekkei
        self.fields["tesuto"] = {"note": self.field("例: スマートフォンのブラウザーで使う。店の画面はまだ作っていない", 3, max_length=2000)}
        self.first_field["tesuto"] = self.fields["tesuto"]["note"]
        section = self.job_section(
            "tesuto", "tesuto", PLACES["tesuto"],
            "作ったアプリを確かめる手順を、設計書と利用者マニュアルから作ります。マニュアルの操作ごとに、することと、そうなるはずの結果を並べ、"
            "5 の段の問題点ごとに、起きないことの確かめ方を書きます。手順のとおりに自分で使って確かめ、AI には、同じ項目で試験を書かせます。"
            "数分かかります。作った物は 7 日で消します。",
            [pick, self.labelled("作ったアプリについて(あれば)", self.fields["tesuto"]["note"]), self.materials("tesuto")],
            [self.go_button("tesuto", "テストの手順を作る")])
        # a small sentence after the button: the sample of step 6 can be read, so there is no sample button here
        section.content.controls.insert(-2, self.note("「6 設計書とマニュアルを作る」の見本の結果からも作れます。"))
        return section

    def build_dialogue(self):
        guides = self.info["guides"]
        self.guide = ft.Dropdown(value="rireki" if any(g["name"] == "rireki" for g in guides) else (guides[0]["name"] if guides else None),
                                 options=[ft.DropdownOption(key=g["name"], text=g["title"]) for g in guides], width=420,
                                 on_select=self.guide_changed)
        self.log = ft.Column(spacing=8)
        self.say_box = self.field("例: 始めたいです", 2, max_length=4000)
        self.chat_note = self.note("")
        return self.section("chat", "手引きを読ませた Gemini と対話する", [
            self.labelled("手引き", self.guide), self.log, self.say_box,
            ft.FilledButton("送る", on_click=self.chat_send), self.chat_note])

    def build_news(self):
        try:
            tastes = read(os.path.join(ASSETS, "tastes.adoc"))
        except OSError:
            tastes = ""
        self.tastes = ft.TextField(value=tastes, multiline=True, min_lines=8, max_lines=14, max_length=4000)
        self.news_note = self.note("")
        self.news_out = ft.Column(visible=False, spacing=8)
        return self.section("news", "今日のニュースを作らせる", [
            self.note("分野、地域、件数、扱わない物を書きます。下は aiai のニュースの好みです。書き替えて使えます。"),
            self.tastes, ft.FilledButton("作る", on_click=self.news_make), self.news_note, self.news_out])

    # ---- signing in and out -----------------------------------------------------------

    async def test_login(self, e):
        try:
            self.token = (await self.json("POST", "/api/test-login", json={"id": self.test_id.value or "", "password": self.test_password.value or ""}))["token"]
        except ApiError as err:
            self.say(self.sign_in_note, "、".join(err.messages), True)
            return
        self.test_password.value = ""
        await self.render()

    async def sign_out(self, e):
        try:
            await self.call("POST", "/api/logout", json={})
        except ApiError:
            pass
        self.token, self.me = "", None
        await self.refresh()

    # ---- the dialogue and the news ----------------------------------------------------

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

    async def guide_changed(self, e):
        self.talk = []
        self.log.controls = []
        self.page.update()

    async def chat_send(self, e):
        text = (self.say_box.value or "").strip()
        if not text:
            return
        self.talk.append({"role": "user", "text": text})
        self.log.controls.append(self.bubble("user", text))
        self.say_box.value = ""
        self.say(self.chat_note, "Gemini が答えています")
        try:
            d = await self.json("POST", "/api/chat", json={"guide": self.guide.value, "messages": self.talk})
        except ApiError as err:
            self.talk.pop()
            self.log.controls.pop()
            self.say(self.chat_note, "、".join(err.messages), True)
            return
        self.talk.append({"role": "model", "text": d["text"]})
        self.log.controls.append(self.bubble("model", d["text"]))
        self.count_left(d)
        self.say(self.chat_note, "")

    async def news_make(self, e):
        self.say(self.news_note, "Gemini が Google 検索で探して、書いています(1 分ほどかかります)")
        self.news_out.visible = False
        try:
            d = await self.json("POST", "/api/news", json={"tastes": self.tastes.value or ""})
        except ApiError as err:
            self.say(self.news_note, "、".join(err.messages), True)
            return

        async def copy(e):
            await self.clipboard.set(d["adoc"])
            self.say(self.news_note, "コピーしました")

        self.news_out.controls = [ft.Text(d["adoc"], selectable=True, size=13), ft.OutlinedButton("コピー", icon=ft.Icons.CONTENT_COPY, on_click=copy)]
        self.news_out.visible = True
        self.count_left(d)
        self.say(self.news_note, "")

    # ---- step 3: how to make the apps there are better ----------------------------------

    async def kaizen_begin(self, e):
        fuman = (self.kaizen_fuman.value or "").strip()
        if not fuman:
            self.say(self.kaizen_note, "困った場面と、困ったことを書いてください", True)
            return
        app, hoshii = (self.kaizen_app.value or "").strip(), (self.kaizen_hoshii.value or "").strip()
        text = f"使ったアプリ: {app or '(書いていません)'}\n困った場面と、困ったこと: {fuman}" + (f"\nどうなればよいか: {hoshii}" if hoshii else "")
        await self.kaizen_ask(text)

    async def kaizen_next(self, e):
        text = (self.kaizen_say.value or "").strip()
        if text:
            self.kaizen_say.value = ""
            await self.kaizen_ask(text)

    async def kaizen_ask(self, text):
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
            return
        self.kaizen_talk.append({"role": "model", "text": d["text"]})
        self.kaizen_log.controls.append(self.bubble("model", d["text"]))
        self.count_left(d)
        self.say(self.kaizen_note, "")

    def kaizen_reset(self):
        self.kaizen_talk = []
        self.kaizen_log.controls = []
        self.kaizen_start.visible, self.kaizen_talkbox.visible = True, False
        self.kaizen_note.value = ""

    async def kaizen_again(self, e):
        self.kaizen_reset()
        self.page.update()

    # ---- the longer jobs ---------------------------------------------------------------

    async def submit(self, kind, mihon=False):
        """Asks for a job: checks what it needs, as the server would, then sends it."""
        note = self.job_notes[kind]
        f = self.fields.get(kind, {})
        text = (f["note"].value or "").strip() if "note" in f else ""
        choose = self.chooses.get(kind)
        chosen = "" if choose is None or choose.value == NONE else choose.value
        given = bool(self.picked[kind]) or mihon or chosen or (kind == "chousa" and text)
        if kind == "tesuto" and mihon:
            return
        if not given:
            self.say(note, ENOUGH[kind], True)
            return
        data = {"kind": kind, "note": text}
        if mihon:
            data["mihon"] = "1"
        if kind == "kadai":
            data |= {"research": chosen, "name": (f["name"].value or "").strip()}
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
                ft.DropdownOption(key=j["id"], text=f"{JOBS[kind]} ・ {j['created']}") for j in jobs if j["kind"] == kind and j["status"] == "done"]
            box.value = had if any(o.key == had for o in box.options) else NONE

    async def card(self, j, d):
        """What one job shows: its line, its steps, a notice if it stopped, and, when done, its buttons and files."""
        parts = [ft.Text(f"{JOBS[j['kind']]} ・ {j['created']} ・ {STATUS[j['status']]}", weight=ft.FontWeight.W_600)]
        parts += [ft.Text(s["name"] + (f"({s['seconds']} 秒)" if "seconds" in s else ""), size=13) for s in d["steps"]]
        if d["error"]:
            parts.append(ft.Text(d["error"], size=13, color=ft.Colors.ERROR))
        if j["status"] == "done":
            parts.append(ft.Row(self.card_buttons(j["id"], j["kind"]), wrap=True, spacing=8))
            for path in d["files"]:
                parts.append(await self.file_view(j["id"], path))
        return ft.Container(ft.Column(parts, spacing=6), padding=12, border_radius=10, bgcolor=ft.Colors.SURFACE)

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

    async def file_view(self, jid, path):
        """A picture, or a file that shows its text when opened."""
        if path.endswith(".png"):
            try:
                png = (await self.call("GET", f"/api/jobs/{jid}/file", params={"path": path})).content
            except ApiError:
                return ft.Text(path, size=13)
            return ft.Image(src=png, width=240, semantics_label=path)
        text = ft.Text("", selectable=True, size=13)
        loaded = {"yes": False}

        async def opened(e):
            if e.control.expanded and not loaded["yes"]:
                loaded["yes"] = True
                try:
                    text.value = (await self.call("GET", f"/api/jobs/{jid}/file", params={"path": path})).text
                except ApiError as err:
                    text.value = "、".join(err.messages)
                self.page.update()

        return ft.ExpansionTile(title=ft.Text(path, size=14), controls=[ft.Container(text, padding=12)], on_change=opened)
