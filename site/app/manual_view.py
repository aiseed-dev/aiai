# SPDX-License-Identifier: AGPL-3.0-or-later
"""The 使い方 tab of the aiai app: the whole user manual (tameshi/docs/manual.adoc), which
site/make_assets.py copies into assets/manual/ as Markdown with its figures. The web page 使い方
(/tsukaikata.html) is the short form of the same manual; the PDF is made by tools/manual_pdf.py.
"""
import os
import re

import flet as ft


def manual_controls(folder, markdown, heading, site):
    """[control] of the manual: its Markdown, with each figure as an image from assets/manual/."""
    path = os.path.join(folder, "manual.md")
    if not os.path.exists(path):
        return [heading("使い方"), ft.Text("利用者マニュアルが見つかりません")]
    with open(path, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"\A# .*\n+", "", text)  # the title is the heading below
    controls = [heading("使い方")]
    for chunk in re.split(r"(?m)^(!\[[^\]]*\]\([^)]+\))\n", text):
        m = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", chunk.strip())
        if m:
            controls.append(ft.Container(ft.Image(src=f"manual/{m[2]}", semantics_label=m[1], width=360), alignment=ft.Alignment.CENTER))
        elif chunk.strip():
            controls.append(markdown(chunk))
    controls.append(ft.OutlinedButton("利用者マニュアルの PDF", icon=ft.Icons.PICTURE_AS_PDF,
                                      action=ft.OpenUrl(f"{site}/tsukaikata/manual.pdf", target=ft.UrlTarget.BLANK)))
    return controls
