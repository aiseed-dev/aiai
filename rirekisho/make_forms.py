"""Makes the resume forms from the Ministry of Health, Labour and Welfare's
own xlsx of its resume example (履歴書様式例, 2021-04-16):

    python make_forms.py kouroushourirekishoA4.xlsx [out folder]

It writes 履歴書-厚労省.form.adoc with its look 履歴書-厚労省.tmpl.adoc, and
履歴書-JIS.form.adoc with 履歴書-JIS.tmpl.adoc, into the out folder (this
folder when left out). The Ministry's layout is kept; what changes:

- the fonts become BIZ UD (MS Mincho → BIZ UD明朝, MS PMincho → BIZ UDP明朝,
  MS PGothic → BIZ UDPゴシック, the title's HG font → BIZ UD明朝)
- the row heights are scaled so that rows 1 to 52 fit an A4 page at 100%,
  in steps of 0.75pt (a Windows pixel), so Excel prints one page a side
- the cells that take data hold marks such as {氏名}; the photo box is the
  field 写真

The JIS form is the same frame with what JIS Z 8303's example had and the
Ministry's dropped put back, as the Ministry shows it for comparison
(新たな履歴書の様式例の作成について, page 3).

Needs officework (pip install officework).
"""
import os
import sys

from officework import sheet


def biz(name):
    """The BIZ UD face for an MS or HG face."""
    if "Ｐ明朝" in name or "P明朝" in name:
        return "BIZ UDP明朝"
    if "明朝" in name or name.startswith("HG"):
        return "BIZ UD明朝"
    if "Ｐゴシック" in name or "Pゴシック" in name:
        return "BIZ UDPゴシック"
    return "BIZ UDゴシック"


def col(a1):
    return "".join(c for c in a1 if c.isalpha())


def row(a1):
    return int("".join(c for c in a1 if c.isdigit()))


def ministry(src):
    """The Ministry's form with BIZ UD fonts, rows fitted to A4 and marks."""
    b = sheet.Book.open(src)
    while len(b.sheet_names) > 1:
        b.remove(b[b.sheet_names[-1]])
    b.properties.title = "履歴書"
    s = b[0]
    s.title = "履歴書"

    # Fonts: BIZ UD in place of the MS and HG fonts, everywhere they are named
    b.replace_fonts({name: biz(name) for name in b.fonts_used()})
    for a1 in list(_cells_without_font(s)):
        s._s.set_fmt(a1, font="BIZ UDP明朝")
    for i, sp in enumerate(s._s.shapes):
        s._s.set_shape(i, font=biz(sp["font"] or "ＭＳ Ｐ明朝"),
                       field="写真" if "写真をはる位置" in (sp["text"] or "") else None)
    b.set_default_font("BIZ UDP明朝", 11.0)

    # Row heights: rows 1..52 fit the printable height of A4 at 100%
    dflt = s._s.default_row_height or 13.5
    h = [s._s.row_height(r) or dflt for r in range(1, 53)]
    _, _, top, bottom = s._s.margins_mm or (15.0, 10.0, 19.0, 10.0)
    usable = (297.0 - top - bottom) * 72.0 / 25.4
    total = sum(h)
    # a little room below the last row, so a printer's own margin does not
    # push it to a second page
    k = min(usable * 0.97 / total, 1.0)
    for r, v in enumerate(h, start=1):
        s._s.set_row_height(r, round(v * k / 0.75) * 0.75)
    s._s.print_scale = 100
    print(f"rows: {total:.1f}pt -> {sum(round(v * k / 0.75) * 0.75 for v in h):.1f}pt"
          f" (x{k:.3f}), printable {usable:.1f}pt", file=sys.stderr)

    # Marks
    marks = {
        "E3": "{日付.年}年　{日付.月}月　{日付.日}日現在",
        "C5": "{ふりがな}",
        "B7": "{氏名}",
        "B10": "　{生年月日.年}年　{生年月日.月}月　{生年月日.日}日生　（満{年齢}歳）",
        "I10": "{性別}",
        "C12": "{現住所ふりがな}",
        "C13": "{郵便番号}",
        "B15": "{現住所}",
        "J13": "{電話}",
        "C17": "{連絡先ふりがな}",
        "C19": "{連絡先郵便番号}",
        "B20": "{連絡先}",
        "J19": "{連絡先電話}",
        "M33": "{志望の動機など}",
    }
    # 学歴・職歴: 15 rows on the left page, 7 more on the right
    left = [26, 28, 30, 32, 34, 35, 37, 39, 40, 42, 44, 46, 47, 48, 49]
    right = [4, 6, 8, 9, 10, 12, 14]
    for i, r in enumerate(left + right, start=1):
        y, m, t = ("B", "C", "D") if i <= len(left) else ("M", "N", "O")
        marks[f"{y}{r}"] = f"{{学歴・職歴.{i}.年}}"
        marks[f"{m}{r}"] = f"{{学歴・職歴.{i}.月}}"
        marks[f"{t}{r}"] = f"{{学歴・職歴.{i}.内容}}"
    for i, r in enumerate([18, 21, 22, 25, 27, 29], start=1):
        marks[f"M{r}"] = f"{{免許・資格.{i}.年}}"
        marks[f"N{r}"] = f"{{免許・資格.{i}.月}}"
        marks[f"O{r}"] = f"{{免許・資格.{i}.内容}}"
    for i, r in enumerate([46, 47, 48, 49], start=1):
        marks[f"M{r}"] = f"{{本人希望.{i}}}"
    for a1, text in marks.items():
        s[a1] = text  # the cell keeps its format
    # A long answer wraps inside the box and starts at its top
    s._s.set_fmt("M33", wrap=True, vertical="top")
    return b


def _cells_without_font(s):
    """The cells that hold something but name no font."""
    for r in s.iter_rows():
        for c in r:
            if c.value is not None and not s._s.fmt(c.coordinate).get("font"):
                yield c.coordinate


def jis(b):
    """The JIS layout from the Ministry's: 性別 circled from ※男・女, the
    right of 志望の動機 given to 通勤時間, 扶養家族数, 配偶者 and 配偶者の扶養義務,
    the photo box's sizes, and JIS's 記入上の注意 under the first page."""
    s = b[0]
    base = s._s.fmt("M33")
    edge = base.get("border_top") or "thin"
    # The Ministry's note says 性別 may be left out; JIS has its own note
    s["B51"] = None
    for i, sp in enumerate(s._s.shapes):
        if sp["field"] == "写真":
            text = (sp["text"] or "").replace("縦　　", "縦　36～40mm").replace("横　　", "横　24～30mm")
            s._s.set_shape(i, text=text)

    def boxed(a, z, text, pt, horizontal, vertical, wrap, lined):
        """One box: merged, its text in the top left cell, a line all round."""
        if a != z:
            s.merge_cells(f"{a}:{z}")
        c0, c1 = sheet.column_index_from_string(col(a)), sheet.column_index_from_string(col(z))
        for r in range(row(a), row(z) + 1):
            for c in range(c0, c1 + 1):
                a1 = f"{sheet.get_column_letter(c)}{r}"
                edges = {
                    "border_top": edge if lined and r == row(a) else None,
                    "border_bottom": edge if lined and r == row(z) else None,
                    "border_left": edge if lined and c == c0 else None,
                    "border_right": edge if lined and c == c1 else None,
                }
                s[a1] = text if a1 == a else None
                s._s.set_fmt(a1, font=base.get("font"), size=pt, horizontal=horizontal,
                             vertical=vertical, wrap=wrap and a1 == a, fill=None, **edges)

    boxed("H10", "J11", "※{性別:男・女}", 12, "center", "center", False, True)
    # Two lines as JIS sets them: １ and ２, then ３ under １
    boxed("B52", "J52",
          "記入上の注意　１．鉛筆以外の黒又は青の筆記具で記入。　　"
          "２．数字はアラビア数字で、文字はくずさず正確に書く。\n"
          "　　　　　　　３．※印のところは、該当するものを○で囲む。",
          8, "left", "center", False, False)
    boxed("M32", "O32", "　志望の動機、特技、好きな学科、アピールポイントなど", 10, "left", "center", False, True)
    boxed("M33", "O42", "{志望の動機など}", 14, "left", "top", True, True)
    boxed("P32", "Q32", "　通勤時間", 10, "left", "center", False, True)
    boxed("P33", "Q34", "約　{通勤時間.時間}　時間　{通勤時間.分}　分", 12, "center", "center", False, True)
    boxed("P35", "Q36", "　扶養家族数（配偶者を除く）", 9, "left", "center", False, True)
    boxed("P37", "Q38", "{扶養家族数}　人", 12, "right", "center", False, True)
    boxed("P39", "P39", "配偶者", 9, "center", "center", False, True)
    boxed("Q39", "Q39", "配偶者の扶養義務", 9, "center", "center", False, True)
    boxed("P40", "P42", "※{配偶者:有・無}", 10, "center", "center", False, True)
    boxed("Q40", "Q42", "※{配偶者の扶養義務:有・無}", 11, "center", "center", False, True)
    # The note takes two lines
    s._s.set_row_height(52, 24.0)
    return b


def save(b, name, source, out):
    """The two files of a form: the cells, merges and marks, and its look."""
    b.save(os.path.join(out, f"{name}.form.adoc"),
           attributes=[("template", name), ("出典", source)])
    b.save_look(os.path.join(out, f"{name}.tmpl.adoc"))
    print(f"{name}: fields {len(b.fields())}", file=sys.stderr)


def main():
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(__file__))
    os.makedirs(out, exist_ok=True)
    b = ministry(src)
    save(b, "履歴書-厚労省", "厚生労働省「履歴書様式例」(2021-04-16)", out)
    save(jis(b), "履歴書-JIS",
         "厚生労働省「履歴書様式例」(2021-04-16)に、JIS Z 8303 の様式例の欄を足しました", out)


if __name__ == "__main__":
    main()
