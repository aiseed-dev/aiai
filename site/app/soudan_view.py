# SPDX-License-Identifier: AGPL-3.0-or-later
"""The second-opinion tab of the aiai app, for recruited people: sign in,
enter the invitation code and agree, consult one or two models, rate their answers, note what happened, and read or delete
one's record. It talks to soudan/server.py over HTTP. Settings:

    AIAI_SOUDAN        the second-opinion server as people reach it
                       (default http://127.0.0.1:8020/soudan); sign-in links use it
    AIAI_SOUDAN_API    the same server as this app reaches it, when that differs
                       (on the web, the app runs on the server: 127.0.0.1)
    AIAI_RETURN        where sign-in comes back to: the app's web address or
                       the app's own link (default http://127.0.0.1:8020/app/)
"""
import os
import urllib.parse

import flet as ft
import httpx

PUBLIC = os.environ.get("AIAI_SOUDAN", "http://127.0.0.1:8020/soudan").rstrip("/")
API = os.environ.get("AIAI_SOUDAN_API", PUBLIC).rstrip("/")
RETURN = os.environ.get("AIAI_RETURN", "http://127.0.0.1:8020/app/")
TOKEN_KEY = "aiai.soudan.token"
NAMES = {"apple": "Apple でサインイン", "google": "Google でサインイン"}


class ApiError(Exception):
    def __init__(self, status, messages):
        super().__init__("\n".join(messages))
        self.status, self.messages = status, messages


class Api:
    def __init__(self, token=None):
        self.token = token
        self.http = httpx.AsyncClient(base_url=API, timeout=180)

    async def call(self, method, path, **kw):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            r = await self.http.request(method, path, headers=headers, **kw)
        except httpx.HTTPError:
            raise ApiError(0, ["セカンドオピニオンのサーバーにつながりませんでした"])
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = r.text
            raise ApiError(r.status_code, detail if isinstance(detail, list) else [str(detail)])
        return r.json()


class SoudanView:
    """Fills the given column with the second-opinion screen."""

    def __init__(self, page, prefs, show):
        self.page, self.prefs, self.show = page, prefs, show
        self.api = Api()
        self.info = None

    async def start(self):
        self.api.token = await self.prefs.get(TOKEN_KEY)

    async def take_code(self, route):
        """Coming back from sign-in: trade the one-time code for a session token."""
        code = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(route or "").query)).get("code")
        if not code:
            return False
        try:
            self.api.token = (await self.api.call("POST", "/api/session", json={"code": code}))["token"]
            await self.prefs.set(TOKEN_KEY, self.api.token)
        except ApiError:
            pass
        self.page.navigate("/")  # take the used code out of the address
        return True

    def note(self, text):
        return ft.Text(text, size=13, color=ft.Colors.ON_SURFACE_VARIANT)

    def errors_of(self, err):
        return [ft.Text(m, color=ft.Colors.ERROR) for m in err.messages]

    async def render(self):
        head = [ft.Text("セカンドオピニオン", size=22, weight=ft.FontWeight.BOLD),
                self.note("あなたの AI と作った下書きを、ほかの会社の AI のモデルに見てもらいます。"
                          "1 つの AI だけに頼らないための、もう 1 つの目です。"
                          "いまは研究として、募集に応じた人だけが使えます。")]
        try:
            if self.info is None:
                self.info = await self.api.call("GET", "/api/info")
            me = None
            if self.api.token:
                try:
                    me = await self.api.call("GET", "/api/me")
                except ApiError:
                    self.api.token = None
                    await self.prefs.remove(TOKEN_KEY)
            if me is None:
                self.show(head + self.signed_out())
            elif not me["agreed"]:
                self.show(head + self.consent(me["invited"]))
            else:
                self.show(head + await self.member(me))
        except ApiError as err:
            self.show(head + self.errors_of(err))

    def signed_out(self):
        out = [self.note("使うには、Apple か Google でサインインしてください。名前はうかがいません。")]
        for p in self.info["providers"]:
            url = f"{PUBLIC}/login/{p}?" + urllib.parse.urlencode({"next": RETURN})
            out.append(ft.FilledButton(NAMES.get(p, p), width=280,
                                       action=ft.OpenUrl(url, target=ft.UrlTarget.SELF)))
        return out

    def consent(self, invited):
        code = ft.TextField(label="招待の番号(例: ABCD-EFGH)", width=280, visible=not invited)
        errors = ft.Column()

        async def agree(e):
            try:
                await self.api.call("POST", "/api/agree",
                                    json={"version": self.info["consent_version"], "code": code.value or ""})
            except ApiError as err:
                if err.status == 409:
                    self.info = None
                errors.controls = self.errors_of(err)
                self.page.update()
                return
            await self.render()

        out = [ft.Markdown(self.info["consent"], selectable=True)]
        if not invited:
            out.append(self.note("募集に応じた人に、招待の番号をお渡ししています。番号は、1 つにつき 1 人だけが使えます。"))
        return out + [code, errors, ft.FilledButton("同意して使い始める", on_click=agree),
                      ft.TextButton("サインアウト", on_click=self.sign_out)]

    async def member(self, me):
        kinds = self.info["kinds"]
        picked = {"kind": None}
        kind_box = ft.Dropdown(label="相談の種類", width=280,
                               options=[ft.DropdownOption(key=k["name"], text=k["title"]) for k in kinds])
        kind_box.on_select = lambda e: picked.__setitem__("kind", e.control.value)
        model_boxes = [ft.Checkbox(label=m, value=False) for m in self.info["models"]]
        draft = ft.TextField(label="下書き(識別情報を除いて貼ってください)", multiline=True,
                             min_lines=6, max_lines=20)
        errors = ft.Column()
        answers = ft.Column(spacing=12)
        sending = ft.ProgressRing(visible=False, width=20, height=20)

        async def send(e):
            chosen = [b.label for b in model_boxes if b.value]
            errors.controls, answers.controls = [], []
            sending.visible = True
            self.page.update()
            try:
                out = await self.api.call("POST", "/api/consults", json={
                    "kind": picked["kind"] or "", "draft": draft.value or "", "models": chosen})
            except ApiError as err:
                errors.controls = self.errors_of(err)
                sending.visible = False
                self.page.update()
                return
            sending.visible = False
            for a in out:
                if "error" in a:
                    answers.controls.append(ft.Text(f"{a['model']}: {a['error']}", color=ft.Colors.ERROR))
                else:
                    answers.controls.append(self.answer_card(a["model"], a["answer"], a["id"], None))
            self.page.update()

        event = ft.TextField(label="出来事(応募した、面接を受けた、開業届を出した など)", max_length=1000)
        event_errors = ft.Column()

        async def add_event(e):
            try:
                await self.api.call("POST", "/api/events", json={"text": event.value or ""})
            except ApiError as err:
                event_errors.controls = self.errors_of(err)
                self.page.update()
                return
            self.page.show_dialog(ft.SnackBar(ft.Text("書き足しました")))
            await self.render()

        record = await self.api.call("GET", "/api/record")
        history = []
        for r in reversed(record):
            if r["type"] == "event":
                history.append(ft.ListTile(leading=ft.Icon(ft.Icons.FLAG_OUTLINED), title=ft.Text(r["text"]),
                                           subtitle=ft.Text(r["created"][:10])))
            else:
                history.append(self.answer_card(r["model"], r["answer"], r["id"], r["rating"],
                                                f"{r['created'][:10]} {self.kind_title(r['kind'])}", r["draft"]))

        return [self.note(f"{me['email'] or '(メールアドレスなし)'} でサインインしています。"
                          f"相談は 1 日 {self.info['per_day']} 回までです。"),
                ft.Text("相談する", size=16, weight=ft.FontWeight.BOLD),
                kind_box, ft.Text("見てもらうモデル(1 つか 2 つ)"), ft.Row(model_boxes, wrap=True), draft,
                errors, ft.Row([ft.FilledButton("見てもらう", on_click=send), sending]), answers,
                ft.Divider(),
                ft.Text("出来事を書き足す", size=16, weight=ft.FontWeight.BOLD),
                event, event_errors, ft.OutlinedButton("書き足す", on_click=add_event),
                ft.Divider(),
                ft.Text("あなたの記録", size=16, weight=ft.FontWeight.BOLD),
                *(history or [self.note("まだありません。")]),
                ft.Divider(),
                ft.Row([ft.TextButton("記録をすべて消す", on_click=self.confirm_forget),
                        ft.TextButton("サインアウト", on_click=self.sign_out)], wrap=True)]

    def kind_title(self, name):
        return next((k["title"] for k in self.info["kinds"] if k["name"] == name), name)

    def answer_card(self, model, answer, cid, rating, head=None, draft=None):
        async def rate(e):
            try:
                await self.api.call("POST", f"/api/consults/{cid}/rating", json={"rating": int(e.control.value)})
                self.page.show_dialog(ft.SnackBar(ft.Text("評価を付けました")))
            except ApiError as err:
                self.page.show_dialog(ft.SnackBar(ft.Text("\n".join(err.messages))))

        stars = ft.Dropdown(label="評価", width=120, value=str(rating) if rating else None,
                            options=[ft.DropdownOption(key=str(n), text=str(n)) for n in range(1, 6)])
        stars.on_select = rate
        parts = [ft.Text(model, weight=ft.FontWeight.BOLD)]
        if head:
            parts.insert(0, self.note(head))
        if draft:
            parts.append(ft.ExpansionTile(title=ft.Text("下書き", size=13), controls=[ft.Text(draft, selectable=True)]))
        parts += [ft.Markdown(answer, selectable=True), ft.Row([self.note("役に立った度合い(1 から 5)"), stars], wrap=True)]
        return ft.Card(ft.Container(ft.Column(parts, spacing=8), padding=16))

    async def confirm_forget(self, e):
        async def forget(e):
            self.page.pop_dialog()
            try:
                await self.api.call("DELETE", "/api/record")
            except ApiError:
                pass
            self.api.token = None
            await self.prefs.remove(TOKEN_KEY)
            self.page.show_dialog(ft.SnackBar(ft.Text("記録をすべて消しました")))
            await self.render()

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("記録をすべて消しますか"),
            content=ft.Text("相談、評価、出来事、同意の記録を消します。元に戻せません。"),
            actions=[ft.TextButton("やめる", on_click=lambda e: self.page.pop_dialog()),
                     ft.FilledButton("消す", on_click=forget)]))

    async def sign_out(self, e):
        try:
            await self.api.call("POST", "/api/logout")
        except ApiError:
            pass
        self.api.token = None
        await self.prefs.remove(TOKEN_KEY)
        await self.render()
