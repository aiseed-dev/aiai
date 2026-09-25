"""The screen for requests, in Flet. server.py serves it as the web page at
/app/; the same code is meant to become the iPhone and Android app with
flet build (not tried yet).

It reads the item list from the server (GET /api/form) and builds the form
from it, so a new kind of request needs no change here. Settings:

    MOUSHIKOMI_SERVER   the server's address (default http://127.0.0.1:8000)
    MOUSHIKOMI_RETURN   where sign-in comes back to: the web page's address,
                        or the app's own link (default <server>/app/)
"""
import datetime
import os
import urllib.parse

import flet as ft
import httpx

SERVER = os.environ.get("MOUSHIKOMI_SERVER", "http://127.0.0.1:8000").rstrip("/")
RETURN = os.environ.get("MOUSHIKOMI_RETURN", SERVER + "/app/")
TOKEN_KEY = "moushikomi.token"
WEEKDAYS = "月火水木金土日"


def allowed_dates(rules, today):
    """The dates that may be chosen, from the item list's rules."""
    first = int(rules.get("何日先から", "0") or 0)
    last = int(rules.get("何日先まで", "30") or 30)
    closed = [w for w in rules.get("休みの曜日", "").split("・") if w]
    out = []
    for n in range(first, last + 1):
        d = today + datetime.timedelta(days=n)
        if WEEKDAYS[d.weekday()] not in closed:
            out.append(d)
    return out


def date_label(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d.month}月{d.day}日({WEEKDAYS[d.weekday()]})"


def rows_text(tables):
    """「食パン 2、あんパン 3」 from the table rows of a request."""
    parts = []
    for rows in tables.values():
        for r in rows:
            parts.append(" ".join(v for v in r.values() if v))
    return "、".join(parts)


class Api:
    def __init__(self, token=None):
        self.token = token
        self.http = httpx.AsyncClient(base_url=SERVER, timeout=15)

    def headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def call(self, method, path, **kw):
        r = await self.http.request(method, path, headers=self.headers(), **kw)
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = r.text
            raise ApiError(r.status_code, detail if isinstance(detail, list) else [str(detail)])
        return r.json()


class ApiError(Exception):
    def __init__(self, status, messages):
        super().__init__("\n".join(messages))
        self.status, self.messages = status, messages


async def main(page: ft.Page):
    page.title = "申し込み"
    page.scroll = ft.ScrollMode.AUTO
    page.padding = 16
    prefs = ft.SharedPreferences()
    api = Api(await prefs.get(TOKEN_KEY))

    async def take_code(route):
        """Coming back from sign-in: trade the one-time code for a session token."""
        code = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(route or "").query)).get("code")
        if not code:
            return False
        try:
            api.token = (await api.call("POST", "/api/session", json={"code": code}))["token"]
            await prefs.set(TOKEN_KEY, api.token)
        except ApiError:
            pass
        page.navigate("/")  # take the used code out of the address
        return True

    await take_code(page.route)
    form = await api.call("GET", "/api/form")
    page.title = form["title"]

    async def show():
        page.controls.clear()
        page.controls.append(ft.Text(form["title"], size=24, weight=ft.FontWeight.BOLD))
        me = None
        if api.token:
            try:
                me = await api.call("GET", "/api/me")
            except ApiError:
                api.token = None
                await prefs.remove(TOKEN_KEY)
        if me is None:
            signed_out()
        else:
            await signed_in(me)
        page.update()

    def signed_out():
        page.controls.append(ft.Text("申し込むには、Apple か Google でサインインしてください。"
                                     "名前はうかがいません。"))
        names = {"apple": "Apple でサインイン", "google": "Google でサインイン"}
        for p in form["providers"]:
            url = f"{SERVER}/login/{p}?" + urllib.parse.urlencode({"next": RETURN})
            page.controls.append(ft.FilledButton(names.get(p, p), width=280,
                                                 action=ft.OpenUrl(url, target=ft.UrlTarget.SELF)))

    async def signed_in(me):
        values, tables, errors = {}, {}, ft.Column()
        picked = {}  # what each dropdown shows; kept from on_select, the sure way it comes back

        def choice_box(**kw):
            dd = ft.Dropdown(**kw)
            picked[id(dd)] = kw.get("value")
            dd.on_select = lambda e: picked.__setitem__(id(e.control), e.control.value)
            return dd

        def value_of(c):
            return (picked.get(id(c)) if isinstance(c, ft.Dropdown) else c.value) or ""

        fields = ft.Column(spacing=12)
        today = datetime.date.today()
        for it in form["items"]:
            name, kind = it["名前"], it["書き方"]
            label = name + ("" if it["必須"] == "必須" else "(なくてもかまいません)")
            if name == form["rules"].get("期限") or kind == "日付":
                opts = [ft.DropdownOption(key=d.isoformat(), text=date_label(d.isoformat()))
                        for d in allowed_dates(form["rules"], today)]
                c = choice_box(label=label, options=opts, width=280)
            elif kind.startswith("選ぶ:"):
                c = choice_box(label=label, width=280,
                                options=[ft.DropdownOption(key=x, text=x) for x in kind[3:].split("・")])
            else:
                c = ft.TextField(label=label, width=280, max_length=200)
            values[name] = c
            fields.controls.append(c)
            if it.get("説明"):
                fields.controls.append(ft.Text(it["説明"], size=12, color=ft.Colors.ON_SURFACE_VARIANT))
        most = int(form["rules"].get("一つの品物の数まで", "10") or 10)
        for tname, d in form["tables"].items():
            cols = d["列"]
            choice = next((c for c in cols if c["書き方"].startswith("選ぶ:")), None)
            count = next((c for c in cols if c["書き方"] == "数"), None)
            fields.controls.append(ft.Text(tname, weight=ft.FontWeight.BOLD))
            if choice and count and len(cols) == 2:
                # One line per choice with how many, e.g. each bread and its count
                rows = []
                for x in choice["書き方"][3:].split("・"):
                    dd = choice_box(value="0", width=110, options=[
                        ft.DropdownOption(key=str(n), text=str(n)) for n in range(0, most + 1)])
                    rows.append((x, dd))
                    fields.controls.append(ft.Row([ft.Text(x, width=160), dd]))
                tables[tname] = ("counts", choice["列"], count["列"], rows)
            else:
                box = [ft.TextField(label=c["列"], width=160) for c in cols]
                fields.controls.append(ft.Row(box, wrap=True))
                tables[tname] = ("one", cols, box)

        async def send(e):
            body = {"values": {k: value_of(c) for k, c in values.items()}, "tables": {}}
            for tname, spec in tables.items():
                if spec[0] == "counts":
                    _, cname, nname, rows = spec
                    body["tables"][tname] = [{cname: x, nname: value_of(dd)} for x, dd in rows
                                             if value_of(dd) not in ("", "0")]
                else:
                    _, cols, box = spec
                    row = {c["列"]: value_of(b) for c, b in zip(cols, box)}
                    body["tables"][tname] = [row] if any(row.values()) else []
            try:
                await api.call("POST", "/api/requests", json=body)
            except ApiError as err:
                errors.controls = [ft.Text(m, color=ft.Colors.ERROR) for m in err.messages]
                page.update()
                return
            page.show_dialog(ft.SnackBar(ft.Text("申し込みました")))
            await show()

        def canceller(rid):
            async def cancel(e):
                await api.call("DELETE", f"/api/requests/{rid}")
                page.show_dialog(ft.SnackBar(ft.Text("取り消しました")))
                await show()
            return cancel

        async def sign_out(e):
            try:
                await api.call("POST", "/api/logout")
            except ApiError:
                pass
            api.token = None
            await prefs.remove(TOKEN_KEY)
            await show()

        page.controls.append(ft.Text(f"{me['email'] or '(メールアドレスなし)'} でサインインしています",
                                     size=12, color=ft.Colors.ON_SURFACE_VARIANT))
        page.controls.append(fields)
        page.controls.append(errors)
        page.controls.append(ft.FilledButton("申し込む", on_click=send))

        mine = await api.call("GET", "/api/requests")
        page.controls.append(ft.Divider())
        page.controls.append(ft.Text("自分の申し込み", size=18, weight=ft.FontWeight.BOLD))
        if not mine:
            page.controls.append(ft.Text("まだありません。"))
        due = form["rules"].get("期限", "")
        for r in mine:
            vals = r["values"]
            head = date_label(r["due"])
            others = "、".join(f"{k} {v}" for k, v in vals.items() if k != due and v)
            page.controls.append(ft.Card(ft.Container(padding=12, content=ft.Column([
                ft.Text(head, weight=ft.FontWeight.BOLD),
                ft.Text(rows_text(r["tables"])),
                ft.Text(others, size=12),
                ft.TextButton("取り消す", on_click=canceller(r["id"])),
            ]))))
        if me.get("shop"):
            everyone = await api.call("GET", "/api/shop/requests")
            page.controls.append(ft.Divider())
            page.controls.append(ft.Text("店の一覧(すべての申し込み)", size=18, weight=ft.FontWeight.BOLD))
            for r in everyone:
                vals = r["values"]
                page.controls.append(ft.Text(
                    f"{date_label(r['due'])} {' '.join(v for k, v in vals.items() if k != due)}: "
                    f"{rows_text(r['tables'])}"))
        page.controls.append(ft.Divider())
        page.controls.append(ft.TextButton("サインアウト", on_click=sign_out))

    async def route_change(e):
        # A web page that comes back from sign-in keeps its session; only the route changes
        if await take_code(e.route):
            await show()

    page.on_route_change = route_change
    await show()


if __name__ == "__main__":
    ft.run(main)
