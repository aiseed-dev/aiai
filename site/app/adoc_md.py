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


# a URL ends at the first character outside this set: Japanese text follows a URL without a space
BARE_URL = r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'*+,;=%]+"
URL_LINK = re.compile(r"(https?://[^\s\[\]<>]+)\[([^\]]*)\]|" + BARE_URL)


def link(m):
    """URL[label] becomes [label](URL); a bare URL becomes [URL](URL) so that the viewer does not autolink
    the Japanese text after it. A trailing . or , is not part of the URL."""
    if m[1]:
        return f"[{m[2]}]({m[1]})"
    url = m[0].rstrip(".,")
    return f"[{url}]({url})" + m[0][len(url):]


def inline(text):
    """Markdown of one line of AsciiDoc: URL[label] becomes a link, a bare URL becomes an explicit link,
    *bold* becomes **bold**."""
    # a <name> in a sentence is a name, not a tag; code is left as it is (links too)
    text = "".join(x if x.startswith("`") else URL_LINK.sub(link, x.replace("<", "\\<"))
                   for x in re.split(r"(`[^`]*`)", text))
    return re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", r"**\1**", text)


def table_columns(attr):
    """Number of columns named by the cols attribute of a block attribute line, or 0 if there is none."""
    m = re.search(r'cols\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^,\]\s]+))', attr or "")
    if not m:
        return 0
    total = 0
    for item in (m[1] or m[2] or m[3]).split(","):
        if item.strip():
            n = re.match(r"\s*(\d+)\*", item)  # "3*" is three columns; "3*2" too
            total += int(n[1]) if n else 1
    return total


# a cell specifier written right before "|": span (2+), alignment or style (a, h, l, ...)
SPECIFIER = re.compile(r"(?:^|(?<=\s))(?:\d+(?:\.\d+)?\+)?[ahlmdes]?$")


def table_to_md(body, attr):
    """Markdown of the lines between |=== and |===. The cells are all the |-separated pieces in order (a line holds
    one or many cells; a line without a leading | continues the previous cell). The columns come from the cols
    attribute, else from the cell count of the first non-blank line. Spans are not honoured."""
    cells, first_count = [], 0
    for line in body:
        if not line.strip():
            continue
        parts = re.split(r"(?<!\\)\|", line)
        head = parts[0].strip()
        if len(parts) == 1:  # no cell starts here: the line continues the previous cell
            if cells:
                cells[-1].append(line)
            continue
        if head and not SPECIFIER.fullmatch(head) and cells:  # text before the first | continues the previous cell
            cells[-1].append(head)
        started = 0
        for k in range(1, len(parts)):
            text = parts[k]
            if k < len(parts) - 1:  # a specifier at the end of this piece belongs to the next cell
                spec = SPECIFIER.search(text)
                if spec and spec[0]:
                    text = text[:spec.start()]
            cells.append([text])
            started += 1
        first_count = first_count or started
    ncols = table_columns(attr) or first_count or 1
    rows = []
    for k in range(0, len(cells), ncols):
        row = [inline(join_lines(c)) for c in cells[k:k + ncols]]
        rows.append(row + [""] * (ncols - len(row)))
    if not rows:
        return ""
    return "\n".join(["| " + " | ".join(rows[0]) + " |", "|" + "---|" * ncols]
                     + ["| " + " | ".join(r) + " |" for r in rows[1:]])


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

    attr = None  # the last block attribute line, used by a |=== that follows
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if re.fullmatch(r"\[.*\]", line.strip()):
            attr = line.strip()
            continue
        if re.match(r"^:[^:\s][^:]*:", line) or line.strip() == "+":
            continue
        if line.strip():
            table_attr, attr = attr, None
        if not line.strip():
            close()
        elif m := re.match(r"^(={1,3}) (.*)$", line):
            close()
            out.append("#" * len(m[1]) + " " + m[2].strip())
        elif line.startswith("|==="):
            close()
            body = []
            while i < len(lines) and not lines[i].startswith("|==="):
                body.append(lines[i])
                i += 1
            i += 1
            if md := table_to_md(body, table_attr):
                out.append(md)
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
