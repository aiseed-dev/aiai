"""What the aiai ribbon buttons do (office/ribbon/*.py call these).

A button works on the book open in officework, which must be a data file
(.sheet.adoc). The form comes from the data's head: `= 履歴書` with
`:様式: 厚労省` means 履歴書-厚労省.form.adoc. It is looked for in the
data's folder first, then in the folders of this repository.
"""
import glob
import os
import warnings

from officework import calc as xw, sheet

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_path():
    """The data file open in officework; refuses anything else."""
    p = xw.Book.attach().fullname
    if not p or not p.endswith(".sheet.adoc"):
        raise SystemExit("データのファイル(.sheet.adoc)を開いてから押してください")
    if xw.ui_state().get("dirty"):
        raise SystemExit("データを保存してから押してください")
    return p


def head(path):
    """(title, form kind) from the data's head, which ends at the first blank line."""
    title = kind = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                break
            if line.startswith("= "):
                title = line[2:].strip()
            elif line.startswith(":様式:"):
                kind = line[len(":様式:"):].strip() or None
    return title, kind


def form_of(data):
    title, kind = head(data)
    if not title:
        raise SystemExit("データの 1 行目に「= 書類の名前」がありません")
    name = f"{title}-{kind}.form.adoc" if kind else f"{title}.form.adoc"
    places = [os.path.dirname(data)] + sorted(glob.glob(os.path.join(ROOT, "*", "")))
    for d in places:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    raise SystemExit(f"様式 {name} が見つかりません(データと同じフォルダーと aiai の中を探しました)")


def fill(data):
    form = form_of(data)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        filled = sheet.Book.fill(sheet.Book.open(form), sheet.Book.open(data))
    return form, filled


def findings(filled):
    missing = "、".join(filled.missing) or "なし"
    bessi = "、".join(t for t, _, _ in filled.bessi) or "なし"
    return f"データに無い名前: {missing}。別紙に続く表: {bessi}"


def umeru():
    """Fill the form and write a PDF next to the data, for reading and printing.

    The data (.sheet.adoc) is what is kept and handed in; the PDF is only
    its printed look, so no .xlsx or .docx is made."""
    import pathlib
    import webbrowser

    data = data_path()
    form, filled = fill(data)
    out = os.path.join(os.path.dirname(data), os.path.basename(form).replace(".form.adoc", ".pdf"))
    filled.save(out)
    webbrowser.open(pathlib.Path(out).as_uri())
    print(f"{os.path.basename(out)} を作りました。{findings(filled)}")


def tashikameru():
    """Tell the names the data lacks and the tables carried to a 別紙, writing nothing."""
    data = data_path()
    _, filled = fill(data)
    print(findings(filled))


def houkoku_shitagaki():
    """Write the value-free report draft next to the data."""
    import houkoku

    data = data_path()
    text = houkoku.draft(form_of(data), data)
    out = os.path.join(os.path.dirname(data), "報告の下書き.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(f"{out} に書きました。データの値は入っていません")
