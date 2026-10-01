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
from soudan_view import SoudanView

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# The order and grouping of the skills on the list; others come last
GROUPS = [("考える", ["tenshoku", "gakusei"]),
          ("作る", ["genba", "website", "moushikomi", "keikaku"])]


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
    page.title = "aiai"
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
        return ft.ListTile(title=ft.Text(title, weight=ft.FontWeight.BOLD), subtitle=ft.Text(desc),
                           trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT), on_click=lambda e: show_skill(name))

    def show_list():
        controls = [heading("スキル"),
                    note("スキルを開き、「写す」で写して、ふだん使っている AI に貼ってください。"
                         "AI が、あなたに聞きながら一緒に進めます。")]
        shown = set()
        for group, names in GROUPS:
            names = [n for n in names if n in skills]
            if names:
                controls.append(ft.Text(group, size=16, weight=ft.FontWeight.BOLD))
                controls += [skill_tile(n) for n in names]
                shown.update(names)
        rest = [n for n in skills if n not in shown]
        if rest:
            controls.append(ft.Text("ほか", size=16, weight=ft.FontWeight.BOLD))
            controls += [skill_tile(n) for n in rest]
        show(controls)

    def show_skill(name):
        title, desc, text = skills[name]

        async def copy(e):
            await clipboard.set(text)
            page.show_dialog(ft.SnackBar(ft.Text("写しました。あなたの AI に貼ってください")))

        _, _, md = split_skill(text)
        show([ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, tooltip="一覧に戻る", on_click=lambda e: show_list()),
                      ft.FilledButton("写す", icon=ft.Icons.CONTENT_COPY, on_click=copy)],
                     alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
              note(desc), ft.Divider(), markdown(md)])

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

    tabs = [show_list, show_kangaekata, show_news, show_soudan]

    async def change(e):
        result = tabs[e.control.selected_index]()
        if result is not None:
            await result

    async def open_soudan():
        page.navigation_bar.selected_index = 3
        await show_soudan()

    async def route_change(e):
        # Coming back from sign-in: the code is in the address
        if await soudan.take_code(e.route):
            await open_soudan()

    page.navigation_bar = ft.NavigationBar(
        destinations=[ft.NavigationBarDestination(icon=ft.Icons.MENU_BOOK, label="スキル"),
                      ft.NavigationBarDestination(icon=ft.Icons.LIGHTBULB_OUTLINE, label="考え方"),
                      ft.NavigationBarDestination(icon=ft.Icons.NOTIFICATIONS_NONE, label="お知らせ"),
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
