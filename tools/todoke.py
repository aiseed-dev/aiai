"""Hands in forms as adoc: one data file for the person, one per office.

    python tools/todoke.py tsukuru 事業.sheet.adoc 開業届.koumoku.adoc
    python tools/todoke.py uketsuke 開業届.koumoku.adoc 受け取ったフォルダー

tsukuru (make) copies the person's own data into one form's data file,
item by item as the form's item list (.koumoku.adoc) says. Items the form
asks to be written for its own purpose (元 = 書き分け) are left empty, and
a request for an AI is written next to it with the purpose and the
business data only (no name, address or number).

uketsuke (receive) checks every .sheet.adoc in a folder against the item
list and writes 受付一覧.adoc: what to fix per file, and the values as one
table keyed by the form's item codes.

Only the standard library is used: an adoc table is lines of text, so the
side that receives needs no office software.
"""
import datetime
import glob
import os
import re
import sys

# ---- reading and writing adoc data files -----------------------------------


def read(path):
    """{"title", "attrs", "tables": [(name, header, rows)]} of an adoc data file."""
    doc = {"title": None, "attrs": {}, "tables": []}
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    i = 0
    while i < len(lines) and lines[i].strip():  # the head ends at the first blank line
        line = lines[i].strip()
        if line.startswith("= "):
            doc["title"] = line[2:].strip()
        elif m := re.match(r"^:([^:]+):\s*(.*)$", line):
            doc["attrs"][m.group(1)] = m.group(2)
        i += 1
    name, table, rows = None, False, []
    for line in lines[i:]:
        s = line.rstrip()
        if s == "|===":
            if table:
                header = None
                if rows and rows[0] == "HEADER":
                    rows.pop(0)
                    header = rows.pop(0)
                doc["tables"].append((name, header, [r for r in rows if r != "HEADER"]))
                name, rows = None, []
            table = not table
        elif table:
            if s.startswith("|"):
                rows.append([c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", s)[1:]])
            elif not s.strip():
                if len(rows) == 1:  # a blank line after the first row marks it as the header
                    rows.insert(0, "HEADER")
            elif rows:
                last = rows[-1]
                last[-1] = re.sub(r"\s*\+$", "", last[-1]) + "\n" + s.strip()
        elif s.startswith(".") and len(s) > 1 and not s.startswith(".."):
            name = s[1:].strip()
    for _, _, rows in doc["tables"]:
        for r in rows:
            r[:] = [re.sub(r"\s*\+$", "", c) for c in r]
    return doc


def pairs(doc):
    """All two-column tables without a header, as one {name: value}."""
    out = {}
    for _, header, rows in doc["tables"]:
        if header is None:
            for r in rows:
                if len(r) >= 2:
                    out[r[0]] = r[1]
    return out


def cell(v):
    v = v.replace("|", "\\|")
    return " +\n".join(v.split("\n"))


def items(koumoku):
    """The item list: [{"コード", "名前", "必須", "書き方", "元", "説明"}]."""
    for _, header, rows in koumoku["tables"]:
        if header and "名前" in header and "書き方" in header:
            return [dict(zip(header, r)) for r in rows]
    raise SystemExit("項目の表(名前・書き方の列がある表)がありません")


# ---- checking one value -----------------------------------------------------


def my_number_ok(v):
    """12 digits whose last is the check digit (施行令第8条)."""
    if not re.fullmatch(r"\d{12}", v):
        return False
    p = [int(c) for c in reversed(v[:11])]
    s = sum(pn * (n + 1 if n <= 6 else n - 5) for n, pn in enumerate(p, 1))
    r = s % 11
    return int(v[11]) == (0 if r <= 1 else 11 - r)


def check(kind, v):
    """None when the value fits the item's 書き方, else how to write it."""
    if kind == "日付":
        try:
            datetime.date.fromisoformat(v)
            return None if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else "2026-07-01 の形で書きます"
        except ValueError:
            return "2026-07-01 の形で書きます"
    if kind == "年":
        return None if re.fullmatch(r"\d{4}", v) else "2026 の形で書きます"
    if kind == "郵便番号":
        return None if re.fullmatch(r"\d{3}-\d{4}", v) else "100-0001 の形で書きます"
    if kind == "電話":
        return None if re.fullmatch(r"\d{2,5}-\d{1,4}-\d{3,4}", v) else "03-0000-0000 の形で書きます"
    if kind == "数":
        return None if re.fullmatch(r"\d+", v) else "数字で書きます"
    if kind == "個人番号":
        return None if my_number_ok(v) else "12 桁の個人番号を書きます(最後の 1 桁が合いません)"
    if kind.startswith("選ぶ:"):
        choices = kind[3:].split("・")
        return None if v in choices else f"{'・'.join(choices)} のどれかを書きます"
    if kind.startswith("複数:"):
        choices = kind[3:].split("・")
        bad = [x for x in v.split("、") if x not in choices]
        return None if not bad else f"{'・'.join(choices)} から選び、「、」で区切ります"
    return None


def problems(its, data):
    out = []
    names = {it["名前"] for it in its}
    for it in its:
        v = data.get(it["名前"])
        if v is None:
            out.append(f"{it['名前']}: この行がありません")
        elif not v:
            if it["必須"] == "必須":
                out.append(f"{it['名前']}: 書いてありません")
        elif why := check(it["書き方"], v):
            out.append(f"{it['名前']}: {why}")
    out += [f"{n}: この書類の項目にありません" for n in data if n not in names]
    return out


# ---- tsukuru: the person's data -> one form's data -----------------------------


def value_from(src, base):
    """The value for an item whose 元 is `src`: a name, or name.年 for a date's year."""
    if src in base:
        return base[src]
    if src.endswith(".年") and base.get(src[:-2], "")[:4].isdigit():
        return base[src[:-2]][:4]
    return None


def tsukuru(data_path, koumoku_path):
    base_doc, kd = read(data_path), read(koumoku_path)
    base, its = pairs(base_doc), items(kd)
    form = kd["title"] or os.path.basename(koumoku_path).split(".")[0]
    rows, asks, by_hand = [], [], []
    for it in its:
        src = it.get("元", "")
        if src == "書き分け":
            rows.append((it["名前"], ""))
            asks.append(it)
        elif src in ("", "-"):
            rows.append((it["名前"], ""))
            by_hand.append(it["名前"])
        else:
            v = value_from(src, base)
            if v is None:
                raise SystemExit(f"{it['名前']} の元「{src}」が {os.path.basename(data_path)} にありません")
            rows.append((it["名前"], v))
    head = [f"= {form}"] + [f":{k}: {v}" for k, v in kd["attrs"].items() if k in ("様式", "様式ID")]
    head.append(f":元のデータ: {os.path.basename(data_path)}")
    body = ["", f".{form}", '[cols="1,3"]', "|==="] + [f"|{n} |{cell(v)}" for n, v in rows] + ["|==="]
    out = os.path.join(os.path.dirname(data_path), f"{form}.sheet.adoc")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(head + body) + "\n")
    print(f"{out} を作りました")
    if by_hand:
        print(f"この書類のために書く項目: {'、'.join(by_hand)}")
    if asks or by_hand:
        # The request starts from the person: the AI asks what only the person
        # can answer and writes from the person's own words. Only the business
        # table goes to the AI, not the name, address or number.
        jigyou = [(n, v) for t, h, rs in base_doc["tables"] if t == "事業" for n, v, *_ in rs]
        ask_person = [it for it in its if it.get("元") in ("", "-") and it["書き方"] != "個人番号"]
        req = os.path.join(os.path.dirname(data_path), f"{form}.依頼.md")
        with open(req, "w", encoding="utf-8") as f:
            f.write(f"# {form}を書く手伝いの依頼\n\n")
            f.write("あなたは、この人が自分で考えて書類を書くのを手伝います。専門の言葉を使わずに話してください。\n")
            f.write("答えを先に出さないでください。何のための項目か、選ぶと何が変わるかを、下の説明と役所の書き方に")
            f.write("書いてある範囲で伝え、本人が考えて決められるようにします。\n")
            f.write("事業の内容に無いことは足さないでください。分からないことは、推測せずに本人に聞いてください。\n\n")
            if url := re.search(r"https?://[^)\s]+", kd["attrs"].get("出典", "")):
                f.write(f"役所の様式と書き方: {url.group(0)}\n\n")
            f.write("## 本人が書いた事業のこと\n\n" + "\n".join(f"- {n}: {v}" for n, v in jigyou) + "\n")
            if ask_person:
                f.write("\n## 本人に聞いて決めてもらうこと\n\n")
                f.write("1 つずつ聞いてください。決めるのは本人です。\n\n")
                for it in ask_person:
                    note = f"({it['説明']})" if it.get("説明") else ""
                    f.write(f"- {it['名前']}: {it['書き方']}{note}\n")
            for it in asks:
                f.write(f"\n## 本人の言葉から書く文: {it['名前']}\n\n{it['説明']}\n")
                f.write("\n下書きを見せ、本人が自分の言葉で直せるようにしてください。\n")
        print(f"AI への依頼を {req} に書きました")


# ---- uketsuke: check what came in ------------------------------------------------


def uketsuke(koumoku_path, folder):
    kd = read(koumoku_path)
    its = items(kd)
    form = kd["title"] or os.path.basename(koumoku_path).split(".")[0]
    files = sorted(p for p in glob.glob(os.path.join(folder, "*.sheet.adoc")))
    results, values = [], []
    for p in files:
        d = read(p)
        if d["title"] != form:
            continue
        data = pairs(d)
        results.append((os.path.basename(p), problems(its, data)))
        values.append((os.path.basename(p), data))
    # The individual number is checked but never copied into the list
    cols = [it for it in its if it["書き方"] != "個人番号"]
    lines = [f"= 受付一覧({form})", f":作成日: {datetime.date.today().isoformat()}", "",
             ".受け付けた書類", '[cols="2,1,4"]', "|===", "|ファイル |結果 |直す所", ""]
    for name, probs in results:
        lines.append(f"|{name} |{'直す所があります' if probs else '受け付けられます'} |{cell(chr(10).join(probs))}")
    lines += ["|===", "", ".項目の値(個人番号は写しません)", "|==="]
    key = lambda it: it["コード"] if it.get("コード") not in (None, "", "-") else it["名前"]
    lines.append("|ファイル " + " ".join(f"|{key(it)}" for it in cols))
    lines.append("")
    for name, data in values:
        lines.append(f"|{name} " + " ".join(f"|{cell(data.get(it['名前'], ''))}" for it in cols))
    lines.append("|===")
    out = os.path.join(folder, f"受付一覧-{form}.adoc")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    ok = sum(1 for _, p in results if not p)
    print(f"{out} に書きました。{len(results)} 件のうち、受け付けられるのは {ok} 件です")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "tsukuru":
        tsukuru(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 4 and sys.argv[1] == "uketsuke":
        uketsuke(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
