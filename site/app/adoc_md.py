# SPDX-License-Identifier: AGPL-3.0-or-later
"""AsciiDoc to Markdown for the documents the app shows: the user manual (site/make_assets.py copies it
into the app) and the results of the 作る tab (tameshi_view.py). Only the standard library is used."""
import re


def join_lines(lines):
    """Joins wrapped lines: a space only between two ASCII words, as Japanese has none."""
    out = ""
    for line in (x.strip() for x in lines):
        if out and line and out[-1].isascii() and out[-1] not in " (" and line[0].isascii():
            out += " "
        out += line
    return out


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
