# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lets the browser fetch the Japanese glyphs a screen needs before the screen is drawn.

The web app does not carry a Japanese font; Flutter fetches the glyphs in pieces when
text that needs them is first laid out, and text laid out while a piece is still coming
loses characters (「サインインすると、」 drew as 「サイ イ」). So a screen whose characters
have not been drawn yet is shown first as a nearly invisible line of them for a moment,
then built. Only the standard library is used (besides Flet).
"""
import asyncio

import flet as ft


def non_ascii(text):
    """The distinct characters of text beyond ASCII, as one string."""
    return "".join(sorted({c for c in text if ord(c) > 127}))


async def preload(show, text, seconds=1.5):
    """Shows a progress ring and, almost invisible, the characters of text; waits so the glyphs come."""
    show([ft.ProgressRing(), ft.Text(non_ascii(text), size=1, opacity=0.01)])
    await asyncio.sleep(seconds)
