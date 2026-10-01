# SPDX-License-Identifier: AGPL-3.0-or-later
"""Copies each folder's SKILL.md into app/assets/skills/, so the app (web or
iPhone and Android) carries the skills with it. Run it before serving or
building the app. Only the standard library is used.

    python site/make_assets.py
"""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "app", "assets", "skills")


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    n = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "site")
        if "SKILL.md" in filenames:
            name = os.path.basename(dirpath)
            shutil.copyfile(os.path.join(dirpath, "SKILL.md"), os.path.join(OUT, name + ".md"))
            n += 1
    print(f"{OUT} に {n} のスキルを写しました")


if __name__ == "__main__":
    main()
