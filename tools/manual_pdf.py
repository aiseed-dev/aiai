# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prints the user manual (tameshi/docs/manual.adoc) to tameshi/docs/manual.pdf.

    python tools/manual_pdf.py [--out tameshi/docs/manual.pdf]

The manual is read as site/make_site.py reads it for the page 使い方 (the same
AsciiDoc subset), made into one HTML page for A4 (margins of 18 mm, a table of
contents at the top, tables and figures not cut across pages), and printed by
the Google Chrome on this machine, headless, without the header and the
footer of a browser. When Chrome is not found, this says so and stops. Run it
after changing the manual, and commit the PDF. Only the standard library is used.
"""
import argparse
import html
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "site"))
import make_site  # noqa: E402

DOCS = os.path.join(ROOT, "tameshi", "docs")
CHROMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome")

CSS = """
@page { size: A4; margin: 18mm; }
* { box-sizing: border-box; }
body { font-family: "Noto Sans JP", "Ume Gothic", "梅ゴシック", sans-serif; font-size: 10.5pt; line-height: 1.7;
       color: #1c2420; background: #ffffff; margin: 0; }
h1 { font-size: 20pt; margin: 0 0 4mm; }
h2 { font-size: 14pt; margin: 9mm 0 3mm; padding-bottom: 1mm; border-bottom: 1px solid #bdb7aa; break-after: avoid; }
h3 { font-size: 11.5pt; margin: 6mm 0 2mm; break-after: avoid; }
p, li { overflow-wrap: anywhere; }
p { margin: 0 0 3mm; }
ul, ol { margin: 0 0 3mm; padding-left: 1.4em; }
li { margin: 1mm 0; }
a { color: #0f766e; text-decoration: none; }
code { font-family: "Noto Sans Mono CJK JP", "Ume Gothic", monospace; font-size: 0.92em; background: #f1ede3; padding: 0 1mm; }
pre { background: #f1ede3; padding: 3mm; white-space: pre-wrap; break-inside: avoid; }
blockquote { margin: 0 0 3mm; padding: 2mm 4mm; border-left: 3px solid #0f766e; background: #f1ede3; break-inside: avoid; }
blockquote p { margin: 0; }
table { border-collapse: collapse; width: 100%; font-size: 9.5pt; margin: 0 0 4mm; }
th, td { border: 1px solid #bdb7aa; padding: 1.5mm 2.5mm; text-align: left; vertical-align: top; }
th { background: #f1ede3; }
tr, figure { break-inside: avoid; }
figure { margin: 3mm auto; max-width: 90mm; }
figure img { width: 100%; height: auto; display: block; }
.toc { margin: 0 0 6mm; padding: 3mm 4mm 3mm 8mm; background: #f1ede3; }
.date { color: #5d6763; margin: 0 0 6mm; }
"""


def chrome():
    for name in CHROMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def manual_html(text):
    """One HTML page of the manual: the title, a table of contents, then the sections."""
    title, sections = make_site.read_adoc(text, "file://" + DOCS + "/images/")
    toc = '<ol class="toc">' + "".join(f'<li><a href="#{x["id"]}">{make_site.adoc_inline(x["title"])}</a></li>'
                                       for x in sections[1:] if x["level"] == 2) + "</ol>"
    body = "\n".join(f'<h{x["level"]} id="{x["id"]}">{make_site.adoc_inline(x["title"])}</h{x["level"]}>\n{x["html"]}'
                     for x in sections[1:])
    return (f'<!DOCTYPE html>\n<html lang="ja"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"<style>{CSS}</style></head><body>\n<h1>{html.escape(title)}</h1>\n{sections[0]['html']}\n{toc}\n{body}\n</body></html>\n")


def main():
    ap = argparse.ArgumentParser(description="利用者マニュアルを PDF にします(Google Chrome のヘッドレスで印刷します)")
    ap.add_argument("--out", default=os.path.join(DOCS, "manual.pdf"))
    a = ap.parse_args()
    browser = chrome()
    if not browser:
        sys.exit("Google Chrome が見つかりません。Chrome を入れてから、もう一度動かしてください")
    with open(os.path.join(DOCS, "manual.adoc"), encoding="utf-8") as f:
        page = manual_html(f.read())
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "manual.html")
        with open(src, "w", encoding="utf-8") as f:
            f.write(page)
        run = subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
                              f"--print-to-pdf={os.path.abspath(a.out)}", "file://" + src],
                             capture_output=True, text=True, timeout=120)
    if run.returncode != 0 or not os.path.exists(a.out):
        sys.exit("PDF にできませんでした: " + run.stderr.strip()[-400:])
    print(f"{a.out} に書きました({os.path.getsize(a.out)} バイト)")


if __name__ == "__main__":
    main()
