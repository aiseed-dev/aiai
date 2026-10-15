# SPDX-License-Identifier: AGPL-3.0-or-later
"""Copies what the app (web, or iPhone and Android) carries with it into app/assets/:
each folder's SKILL.md into skills/, and the
user manual (tameshi/docs/manual.adoc) as manual/manual.md, in Markdown, with its figures in
manual/images/. Run it before serving or building the app. Only the standard library is used.

    python site/make_assets.py
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(HERE, "app", "assets")
OUT = os.path.join(ASSETS, "skills")
DOCS = os.path.join(ROOT, "tameshi", "docs")

sys.path.insert(0, os.path.join(HERE, "app"))
from adoc_md import adoc_to_md, join_lines  # noqa: E402


def first_paragraph(readme):
    """The first paragraph of a README.md, joined into one line: what a person reads first about a guide.
    A README that opens with a list, a table or code gives ''."""
    lines, i = readme.splitlines(), 0
    while i < len(lines) and (not lines[i].strip() or lines[i].startswith("#")):
        i += 1
    para = []
    while i < len(lines) and lines[i].strip():
        if lines[i].startswith(("|", "```", "- ", "* ", "1. ", "#")):
            return "" if not para else join_lines(para)
        para.append(lines[i])
        i += 1
    return join_lines(para)


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
            readme = os.path.join(dirpath, "README.md")
            if os.path.exists(readme):  # the first paragraph of its README, for the list of guides (plain text)
                with open(readme, encoding="utf-8") as f:
                    lead = first_paragraph(f.read()).replace("`", "")
                if lead:
                    with open(os.path.join(OUT, name + ".lead.txt"), "w", encoding="utf-8") as g:
                        g.write(lead + "\n")
            n += 1
    manual = os.path.join(ASSETS, "manual")
    if os.path.isdir(manual):
        shutil.rmtree(manual)
    shutil.copytree(os.path.join(DOCS, "images"), os.path.join(manual, "images"))
    with open(os.path.join(DOCS, "manual.adoc"), encoding="utf-8") as f, open(os.path.join(manual, "manual.md"), "w", encoding="utf-8") as g:
        g.write(adoc_to_md(f.read()))
    print(f"{OUT} に {n} のスキルを写しました。利用者マニュアル(manual/)も写しました")


if __name__ == "__main__":
    main()
