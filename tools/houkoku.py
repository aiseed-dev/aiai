"""Makes a draft report of filling a form, without any of the data's values.

    python tools/houkoku.py 様式.form.adoc データ.sheet.adoc

It fills the form, and prints what can be told without telling who you
are: the form, the officework version, the fields (name and kind only),
the names the data lacks, the tables carried to a 別紙 and the number of
pages. Paste it into a report (GitHub の Issue「様式・スキルの不具合」).
"""
import importlib.metadata
import os
import platform
import sys
import warnings

from officework import doc, sheet


def main():
    if len(sys.argv) < 3:
        sys.exit("使い方: python tools/houkoku.py 様式 データ.sheet.adoc")
    form_path, data_path = sys.argv[1], sys.argv[2]
    data = sheet.Book.open(data_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if form_path.lower().endswith(".docx"):
            filled = doc.Doc.fill_form(doc.Doc.open(form_path), data)
        else:
            filled = sheet.Book.fill(sheet.Book.open(form_path), data)
    try:
        dl = filled.draw_list()
        fields = [(f["name"], f["kind"]) for p in dl["pages"] for f in p["fields"]]
        pages = len(dl["pages"])
    except Exception as e:  # the report still goes out without the layout
        fields, pages = [], f"組めませんでした: {e}"
    # One entry per field, a table's rows told as one (学歴・職歴: 22 行 × 年・月・内容)
    seen, tables = [], {}
    for name, kind in fields:
        parts = name.split(".")
        if len(parts) == 3 and parts[1].isdigit():
            rows, cols = tables.setdefault(parts[0], (set(), []))
            rows.add(int(parts[1]))
            if parts[2] not in cols:
                cols.append(parts[2])
            if (parts[0], "表") not in seen:
                seen.append((parts[0], "表"))
        elif (name, kind) not in seen:
            seen.append((name, kind))
    seen = [(n, f"{len(tables[n][0])} 行 × {'・'.join(tables[n][1])}" if k == "表" else k) for n, k in seen]
    print("## 様式を埋めた結果(値は含みません)")
    print()
    print(f"- 様式: {os.path.basename(form_path)}")
    print(f"- officework: {importlib.metadata.version('officework')}")
    print(f"- Python: {platform.python_version()} / {platform.system()} {platform.machine()}")
    print(f"- ページ: {pages}")
    print(f"- データに無い名前: {'、'.join(filled.missing) or 'なし'}")
    print(f"- 別紙に回った表: {'、'.join(f'{t}({a}〜{b} 行目)' for t, a, b in filled.bessi) or 'なし'}")
    print(f"- 欄({len(seen)}): " + "、".join(f"{n}({k})" for n, k in seen))


if __name__ == "__main__":
    main()
