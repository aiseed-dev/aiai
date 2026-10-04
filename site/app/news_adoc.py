# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reads and writes a day's news adoc (news/YYYY-MM-DD.adoc) as the app edits
it: the title and date, then one entry per "==" section with its 分野 and
国・地域, its paragraphs, and its sources (the 出典 lines). Writing gives the
same shape back, so a file the person edited by hand and one the app saved
look alike. Only the standard library is used.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NEWS_DIR = os.path.join(ROOT, "news")
TASTES = os.path.join(NEWS_DIR, "好み.adoc")


def parse(text):
    """{"title", "date", "entries": [{"heading", "area", "region", "body", "sources"}]}.

    body is the paragraphs joined by blank lines; sources is one 出典 per line
    (the trailing " +" that continues a line in adoc is dropped)."""
    doc = {"title": "", "date": "", "entries": []}
    entry, paras, para = None, [], []

    def close_para():
        if para:
            paras.append(" ".join(x.strip() for x in para) if all(x.isascii() for x in para) else "".join(x.strip() for x in para))
            para.clear()

    def close_entry():
        close_para()
        if entry is not None:
            entry["sources"] = [p[:-2].strip() if p.endswith(" +") else p for p in paras if p.startswith("出典")]
            entry["body"] = "\n\n".join(p for p in paras if not p.startswith("出典"))
            doc["entries"].append(entry)
        paras.clear()

    for line in text.splitlines():
        if line.startswith("== "):
            close_entry()
            entry = {"heading": line[3:].strip(), "area": "", "region": "", "body": "", "sources": []}
        elif line.startswith("= ") and entry is None:
            doc["title"] = line[2:].strip()
        elif m := re.match(r":([^:]+): ?(.*)", line):
            k, v = m[1], m[2].strip()
            if entry is None:
                if k == "日付":
                    doc["date"] = v
            elif k == "分野":
                entry["area"] = v
            elif k == "国・地域":
                entry["region"] = v
        elif not line.strip():
            close_para()
        else:
            # sources are one per line; a line ending in " +" is complete on its own
            if line.startswith("出典") or (para and para[-1].endswith(" +")):
                close_para()
            para.append(line.rstrip())
            if line.rstrip().endswith(" +"):
                close_para()
    close_entry()
    return doc


def render(doc):
    """The adoc text of a parsed (and edited) day."""
    out = [f"= {doc['title'].strip()}", f":日付: {doc['date'].strip()}", ""]
    for e in doc["entries"]:
        out += [f"== {e['heading'].strip()}", f":分野: {e['area'].strip()}", f":国・地域: {e['region'].strip()}", ""]
        body = e["body"].strip()
        if body:
            out += [body, ""]
        sources = [s.strip() for s in e["sources"] if s.strip()]
        for i, s in enumerate(sources):
            out.append(s + (" +" if i < len(sources) - 1 else ""))
        if sources:
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def days(folder=NEWS_DIR):
    """The dates that have a file, newest first."""
    if not os.path.isdir(folder):
        return []
    return sorted((f[:-5] for f in os.listdir(folder) if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.adoc", f)), reverse=True)


def path_of(date, folder=NEWS_DIR):
    return os.path.join(folder, f"{date}.adoc")


def load(date, folder=NEWS_DIR):
    with open(path_of(date, folder), encoding="utf-8") as f:
        return parse(f.read())


def save(date, doc, folder=NEWS_DIR):
    with open(path_of(date, folder), "w", encoding="utf-8") as f:
        f.write(render(doc))


def areas(tastes_path=TASTES):
    """The areas named in 好み.adoc (its === headings)."""
    if not os.path.exists(tastes_path):
        return []
    with open(tastes_path, encoding="utf-8") as f:
        return [m[1].strip() for m in re.finditer(r"^=== (.+)$", f.read(), re.M)]


def urls(text):
    return re.findall(r"https?://[^\s<>()、。」』）]+[^\s<>()、。」』）.,:;]", text)
