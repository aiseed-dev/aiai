# SPDX-License-Identifier: AGPL-3.0-or-later
"""Copies what the app (web, or iPhone and Android) carries with it into app/assets/:
each folder's SKILL.md into skills/, the news tastes (news/好み.adoc) as tastes.adoc, and the
user manual (tameshi/docs/manual.adoc) as manual/manual.md, in Markdown, with its figures in
manual/images/. Run it before serving or building the app. Only the standard library is used.

    python site/make_assets.py
"""
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(HERE, "app", "assets")
OUT = os.path.join(ASSETS, "skills")
DOCS = os.path.join(ROOT, "tameshi", "docs")


def join_lines(lines):
    """Joins wrapped lines: a space only between two ASCII words, as Japanese has none."""
    out = ""
    for line in (x.strip() for x in lines):
        if out and line and out[-1].isascii() and out[-1] not in " (" and line[0].isascii():
            out += " "
        out += line
    return out


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


def inline(text):
    """Markdown of one line of AsciiDoc: URL[label] becomes a link, *bold* becomes **bold**."""
    # a <name> in a sentence is a name, not a tag; code is left as it is
    text = "".join(x if x.startswith("`") else x.replace("<", "\\<") for x in re.split(r"(`[^`]*`)", text))
    text = re.sub(r"(https?://[^\s\[\]<>]+)\[([^\]]*)\]", lambda m: f"[{m[2]}]({m[1]})", text)
    return re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", r"**\1**", text)


def adoc_to_md(text):
    """Markdown of the user manual's AsciiDoc: headings, paragraphs, lists, tables, quotes, code, images."""
    lines, out, para, items = text.splitlines(), [], [], []

    def close():
        if para:
            out.append(inline(join_lines(para)))
            para.clear()
        if items:
            out.append("\n".join(items))
            items.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if re.match(r"^:[^:\s][^:]*:", line) or re.fullmatch(r"\[.*\]", line.strip()) or line.strip() == "+":
            continue
        if not line.strip():
            close()
        elif m := re.match(r"^(={1,3}) (.*)$", line):
            close()
            out.append("#" * len(m[1]) + " " + m[2].strip())
        elif line.startswith("|==="):
            close()
            rows = []
            while i < len(lines) and not lines[i].startswith("|==="):
                if lines[i].strip():
                    rows.append([inline(c.strip()) for c in lines[i].strip().lstrip("|").split(" | ")])
                i += 1
            i += 1
            out.append("\n".join(["| " + " | ".join(rows[0]) + " |", "|" + "---|" * len(rows[0])]
                                 + ["| " + " | ".join(r) + " |" for r in rows[1:]]))
        elif line.startswith("____"):
            close()
            quote = []
            while i < len(lines) and not lines[i].startswith("____"):
                if lines[i].strip():
                    quote.append(lines[i])
                i += 1
            i += 1
            out.append("> " + inline(join_lines(quote)))
        elif line.startswith("----"):
            close()
            code = []
            while i < len(lines) and not lines[i].startswith("----"):
                code.append(lines[i])
                i += 1
            i += 1
            out.append("```\n" + "\n".join(code) + "\n```")
        elif m := re.fullmatch(r"image::([^\[]+)\[(.*)\]", line.strip()):
            close()
            out.append(f"![{m[2]}]({m[1]})")
        elif m := re.match(r"^(\*+|\.+) (.*)$", line):
            if para:
                close()
            pad = "  " * (len(m[1]) - 1)
            items.append(pad + ("1. " if m[1][0] == "." else "- ") + inline(m[2]))
        elif items and line.startswith(" "):  # a wrapped line of the last item
            items[-1] = items[-1] + ("" if not items[-1][-1].isascii() or not line.strip()[0].isascii() else " ") + inline(line.strip())
        else:
            if items:
                close()
            para.append(line)
    close()
    return "\n\n".join(out) + "\n"


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
    shutil.copyfile(os.path.join(ROOT, "news", "好み.adoc"), os.path.join(ASSETS, "tastes.adoc"))
    manual = os.path.join(ASSETS, "manual")
    if os.path.isdir(manual):
        shutil.rmtree(manual)
    shutil.copytree(os.path.join(DOCS, "images"), os.path.join(manual, "images"))
    with open(os.path.join(DOCS, "manual.adoc"), encoding="utf-8") as f, open(os.path.join(manual, "manual.md"), "w", encoding="utf-8") as g:
        g.write(adoc_to_md(f.read()))
    print(f"{OUT} に {n} のスキルを写しました。好みと、利用者マニュアル(manual/)も写しました")


if __name__ == "__main__":
    main()
