# SPDX-License-Identifier: AGPL-3.0-or-later
"""The aiai app, in Flet. site/server.py serves it as the web page at /app/;
the same code is meant to become the iPhone and Android app with flet build.

It shows the skills (each folder's SKILL.md, copied into assets/skills/ by
site/make_assets.py), the thinking behind aiai (assets/kangaekata.md), the
news (assets/news/*.adoc) and the second opinion (soudan_view.py, which
talks to soudan/server.py). A skill can be copied whole, to paste into the
person's own AI.
"""
import os
import re

import flet as ft
from kiroku_view import LOCAL, KirokuView
from news_view import NewsView
from server_view import ServerView
from soudan_view import SoudanView

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
# Where a skill's ZIP can be fetched (site/server.py serves /skills/<name>.zip)
SITE = os.environ.get("AIAI_SITE", "http://127.0.0.1:8020").rstrip("/")

# The order and grouping of the skills on the list; others come last
GROUPS = [("知る", ["rireki"]),
          ("考える", ["tenshoku", "gakusei"]),
          ("作る", ["genba", "website", "moushikomi", "keikaku"])]
ICONS = {"rireki": ft.Icons.HISTORY, "tenshoku": ft.Icons.WORK_OUTLINE, "gakusei": ft.Icons.SCHOOL, "genba": ft.Icons.PHOTO_CAMERA,
         "website": ft.Icons.LANGUAGE, "moushikomi": ft.Icons.EVENT_AVAILABLE, "keikaku": ft.Icons.GRASS}
STEPS = [("1", "スキルを選ぶ"), ("2", "あなたの AI に貼る"), ("3", "対話しながら作る")]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def split_skill(text):
    """(name, description, body) of a SKILL.md: its front matter, then the rest."""
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        return "", "", text
    head = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
    return head.get("name", "").strip(), head.get("description", "").strip(), m.group(2).strip()


def load_skills(folder):
    """{name: (title, description, whole text)} from folder/*.md."""
    out = {}
    if not os.path.isdir(folder):
        return out
    for f in sorted(os.listdir(folder)):
        if f.endswith(".md"):
            text = read(os.path.join(folder, f))
            name, desc, body = split_skill(text)
            title = next((ln[2:].strip() for ln in body.splitlines() if ln.startswith("# ")), name)
            out[name or f[:-3]] = (title, desc, text)
    return out


def load_news(folder):
    """[(date, title, body)] from folder/*.adoc, newest first."""
    items = []
    if not os.path.isdir(folder):
        return items
    for f in os.listdir(folder):
        if not f.endswith(".adoc"):
            continue
        title, date, body = "", f[:10], []
        for line in read(os.path.join(folder, f)).splitlines():
            if line.startswith("= ") and not title:
                title = line[2:].strip()
            elif line.startswith(":日付:"):
                date = line.split(":", 2)[2].strip()
            elif not line.startswith(":"):
                body.append(line)
        items.append((date, title, "\n".join(body).strip()))
    return sorted(items, reverse=True)


async def main(page: ft.Page):
    page.title = "aiai — AI 時代の学び方"
    page.padding = 0
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.TEAL)
    skills = load_skills(os.path.join(ASSETS, "skills"))
    news = load_news(os.path.join(ASSETS, "news"))
    clipboard = ft.Clipboard()
    prefs = ft.SharedPreferences()
    body = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
    frame = ft.Container(body, padding=16, expand=True)

    def heading(text):
        return ft.Text(text, size=22, weight=ft.FontWeight.BOLD)

    def note(text):
        return ft.Text(text, size=13, color=ft.Colors.ON_SURFACE_VARIANT)

    def markdown(text):
        return ft.Markdown(text, selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_FLAVORED,
                           auto_follow_links=True, auto_follow_links_target=ft.UrlTarget.BLANK)

    def show(controls):
        body.controls = controls
        page.update()

    def skill_tile(name):
        title, desc, _ = skills[name]
        icon = ft.Container(ft.Icon(ICONS.get(name, ft.Icons.MENU_BOOK), color=ft.Colors.ON_PRIMARY_CONTAINER),
                            width=44, height=44, border_radius=14, bgcolor=ft.Colors.PRIMARY_CONTAINER,
                            alignment=ft.Alignment.CENTER)
        tile = ft.ListTile(leading=icon, title=ft.Text(title, weight=ft.FontWeight.BOLD),
                           subtitle=ft.Text(desc, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                           trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT), on_click=lambda e: show_skill(name))
        return ft.Card(tile, elevation=0, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW)

    def hero():
        """The band at the top of the first screen: what aiai is, and the three steps."""
        steps = ft.Row([ft.Container(ft.Row([
            ft.Container(ft.Text(n, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY, size=12), width=22,
                         height=22, border_radius=11, bgcolor=ft.Colors.WHITE, alignment=ft.Alignment.CENTER),
            ft.Text(t, color=ft.Colors.WHITE, size=13)], spacing=6, tight=True),
            padding=ft.Padding.symmetric(vertical=6, horizontal=10), border_radius=999, bgcolor=ft.Colors.with_opacity(0.18, ft.Colors.WHITE))
            for n, t in STEPS], wrap=True, spacing=8, run_spacing=8)
        return ft.Container(ft.Column([
            ft.Text("aiai", size=30, weight=ft.FontWeight.W_800, color=ft.Colors.WHITE),
            ft.Text("AI 時代の学び方", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD, size=16),
            ft.Text("主役は、あなたの AI。スキルを写して、ふだん使っている AI に貼ると、AI があなたに聞きながら一緒に作ります。",
                    color=ft.Colors.with_opacity(0.92, ft.Colors.WHITE), size=13),
            steps], spacing=10),
            padding=20, border_radius=22,
            gradient=ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                                       colors=["#0b5c56", "#0f766e"]))

    def group_header(text):
        return ft.Container(ft.Text(text, size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY),
                            padding=ft.Padding.only(top=10, left=4))

    def show_list():
        controls = [hero()]
        shown = set()
        for group, names in GROUPS:
            names = [n for n in names if n in skills]
            if names:
                controls.append(group_header(group))
                controls += [skill_tile(n) for n in names]
                shown.update(names)
        rest = [n for n in skills if n not in shown]
        if rest:
            controls.append(group_header("ほか"))
            controls += [skill_tile(n) for n in rest]
        controls.append(note("見本の人、店、数字は、すべて架空です。"))
        show(controls)

    def show_skill(name):
        title, desc, text = skills[name]

        async def copy(e):
            await clipboard.set(text)
            page.show_dialog(ft.SnackBar(ft.Text("写しました。あなたの AI に貼ってください")))

        _, _, md = split_skill(text)
        zip_url = f"{SITE}/skills/{name}.zip"
        show([ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, tooltip="一覧に戻る", on_click=lambda e: show_list()),
                      ft.Row([ft.OutlinedButton("ZIP", icon=ft.Icons.DOWNLOAD, tooltip="スキルとして上げる ZIP",
                                                action=ft.OpenUrl(zip_url, target=ft.UrlTarget.BLANK)),
                              ft.FilledButton("写す", icon=ft.Icons.CONTENT_COPY, on_click=copy)], spacing=8)],
                     alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
              note(desc),
              note("ChatGPT、Claude、Gemini では、スキルとして上げて使えます(Claude は ZIP、Gemini は SKILL.md か ZIP)。"
                   "スキルが使えないときは、「写す」でチャットに貼ります。"),
              ft.Divider(), markdown(md)])

    def show_kangaekata():
        show([heading("考え方"), markdown(read(os.path.join(ASSETS, "kangaekata.md")))])

    def show_news():
        controls = [heading("お知らせ")]
        for date, title, text in news:
            controls.append(ft.Card(ft.Container(ft.Column([
                note(date), ft.Text(title, size=16, weight=ft.FontWeight.BOLD), ft.Text(text)], spacing=6),
                padding=16)))
        if not news:
            controls.append(note("まだありません。"))
        show(controls)

    soudan = SoudanView(page, prefs, show)
    await soudan.start()

    async def show_soudan():
        show([ft.ProgressRing()])
        await soudan.render()

    kiroku = KirokuView(page, prefs, show)

    async def show_kiroku():
        show([ft.ProgressRing()])
        await kiroku.render()

    news_edit = NewsView(page, show)

    async def show_news_edit():
        show([ft.ProgressRing()])
        await news_edit.render()

    server = ServerView(page, show)

    async def show_server():
        await server.render()

    # The records tab reads this PC and the news tab writes to it, so they are there only
    # when the app runs on the person's own PC; elsewhere the news is read-only
    tabs = [show_list] + ([show_kiroku, show_server] if LOCAL else []) + [show_kangaekata, show_news_edit if LOCAL else show_news, show_soudan]

    async def change(e):
        result = tabs[e.control.selected_index]()
        if result is not None:
            await result

    async def open_soudan():
        page.navigation_bar.selected_index = tabs.index(show_soudan)
        await show_soudan()

    async def route_change(e):
        # Coming back from sign-in: the code is in the address
        if await soudan.take_code(e.route):
            await open_soudan()

    page.navigation_bar = ft.NavigationBar(
        destinations=[ft.NavigationBarDestination(icon=ft.Icons.MENU_BOOK, label="スキル")]
        + ([ft.NavigationBarDestination(icon=ft.Icons.HISTORY, label="記録"),
            ft.NavigationBarDestination(icon=ft.Icons.SHIELD_OUTLINED, label="サーバー")] if LOCAL else [])
        + [ft.NavigationBarDestination(icon=ft.Icons.LIGHTBULB_OUTLINE, label="考え方"),
                      ft.NavigationBarDestination(icon=ft.Icons.NEWSPAPER if LOCAL else ft.Icons.NOTIFICATIONS_NONE,
                                                  label="ニュース" if LOCAL else "お知らせ"),
                      ft.NavigationBarDestination(icon=ft.Icons.FORUM_OUTLINED, label="相談")],
        on_change=change)
    page.on_route_change = route_change
    page.add(ft.SafeArea(frame, expand=True))
    if await soudan.take_code(page.route):
        await open_soudan()
    else:
        show_list()


if __name__ == "__main__":
    ft.run(main)
