# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adds up a farm business plan written in adoc, year by year.

    python keikaku.py 経営計画.sheet.adoc

The plan holds four tables (see 経営計画.sheet.adoc):

    知識          what the person knows per area, where they learned it,
                  what is missing, and which figures it touches
    作付け        one row per crop and year: area, yield, price, costs, hours
    固定費        yearly costs that do not follow the area (rent, machines)
    その他の収入  money that is not farm income (a grant, for one)

Every row needs a 根拠 (where the figure comes from). Rows without one are
listed, because a plan is only as good as the figures it rests on.

It prints the totals per year and writes 経営計画の結果.adoc next to the
plan: the totals, and the crop table and figures in the shape the
青年等就農計画 data asks for (現状 = the first year, 目標 = the last).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
from todoke import read, tables_of  # noqa: E402


def num(v):
    v = v.replace(",", "").strip()
    return float(v) if v else 0.0


def rows_of(tables, name):
    if name not in tables:
        return []
    h, rs = tables[name]
    return [dict(zip(h, r + [""] * (len(h) - len(r)))) for r in rs]


def fmt(x):
    return f"{round(x):,}"


def main(path):
    doc = read(path)
    t = tables_of(doc)
    crops, fixed, other = rows_of(t, "作付け"), rows_of(t, "固定費"), rows_of(t, "その他の収入")
    # What the person still has to learn, and which figures of the plan it touches
    gaps = [(r["分野"], r["まだ足りないこと"], r.get("計画のどこに効くか", ""))
            for r in rows_of(t, "知識") if r.get("まだ足りないこと", "").strip()]
    unknown = [r["分野"] for r in rows_of(t, "知識") if not r.get("知っていること", "").strip()]
    living = num(doc["attrs"].get("生活費(千円)", "0"))
    no_basis = [f"{n}: {r.get('作目') or r.get('費目') or r.get('名前')}({r.get('年', '')})"
                for n, rs in (("作付け", crops), ("固定費", fixed), ("その他の収入", other))
                for r in rs if not r.get("根拠", "").strip()]
    years = sorted({int(r["年"]) for r in crops + fixed + other if r.get("年", "").isdigit()})
    out = []
    for y in years:
        cs = [r for r in crops if r["年"] == str(y)]
        sales = sum(num(r["面積(a)"]) / 10 * num(r["10aあたり収量(kg)"]) * num(r["単価(円/kg)"]) for r in cs) / 1000
        var = sum(num(r["面積(a)"]) / 10 * num(r["10aあたり経費(円)"]) for r in cs) / 1000
        hours = sum(num(r["面積(a)"]) / 10 * num(r["10aあたり労働時間(時間)"]) for r in cs)
        fix = sum(num(r["年額(千円)"]) for r in fixed if r["年"] in (str(y), "毎年"))
        oth = sum(num(r["金額(千円)"]) for r in other if r["年"] == str(y))
        income = sales - var - fix
        out.append((y, sales, var + fix, income, hours, oth, income + oth - living))
    lines = [f"= 経営計画の結果({doc['title'] or ''})", "", ".年ごとの計算", "|===",
             "|年 |売上(千円) |経費(千円) |農業所得(千円) |労働時間(時間) |その他の収入(千円) |生活費を引いた残り(千円)", ""]
    for y, s, c, i, h, o, rest in out:
        lines.append(f"|{y}年目 |{fmt(s)} |{fmt(c)} |{fmt(i)} |{fmt(h)} |{fmt(o)} |{fmt(rest)}")
    lines.append("|===")
    if out:
        first, last = out[0], out[-1]
        lines += ["", "青年等就農計画に写す値です。現状は 1 年目、目標は最後の年です。", "",
                  ".青年等就農計画の値", '[cols="1,3"]', "|===",
                  f"|年間農業所得の現状(千円) |{round(first[3])}", f"|年間農業所得の目標(千円) |{round(last[3])}",
                  f"|年間労働時間の現状(時間) |{round(first[4])}", f"|年間労働時間の目標(時間) |{round(last[4])}", "|==="]
        names = list(dict.fromkeys(r["作目"] for r in crops))

        def cell(name, y, what):
            r = next((r for r in crops if r["作目"] == name and r["年"] == str(y)), None)
            if not r:
                return "0a" if what == "a" else "0kg"
            a = num(r["面積(a)"])
            return f"{a:g}a" if what == "a" else f"{round(a / 10 * num(r['10aあたり収量(kg)']))}kg"

        lines += ["", "事業.sheet.adoc の作目の表に写す形です。", "", ".作目", "|===",
                  "|作目・部門名 |現状の作付面積・飼養頭数 |現状の生産量 |目標の作付面積・飼養頭数 |目標の生産量", ""]
        for n in names:
            lines.append(f"|{n} |{cell(n, first[0], 'a')} |{cell(n, first[0], 'kg')} |{cell(n, last[0], 'a')} |{cell(n, last[0], 'kg')}")
        lines.append("|===")
    if no_basis:
        lines += ["", "根拠の書いていない行: " + "、".join(no_basis)]
    if gaps:
        lines += ["", "まだ足りない知識と、それが効く所です。", "", ".まだ足りない知識", "|===",
                  "|分野 |まだ足りないこと |計画のどこに効くか", ""]
        lines += [f"|{a} |{b} |{c}" for a, b, c in gaps] + ["|==="]
    res = os.path.join(os.path.dirname(os.path.abspath(path)), "経営計画の結果.adoc")
    with open(res, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    for y, s, c, i, h, o, rest in out:
        print(f"{y}年目: 売上 {fmt(s)} 千円、経費 {fmt(c)} 千円、農業所得 {fmt(i)} 千円、労働時間 {fmt(h)} 時間、生活費を引いた残り {fmt(rest)} 千円")
    if no_basis:
        print("根拠の書いていない行: " + "、".join(no_basis))
    if gaps:
        print(f"まだ足りない知識: {len(gaps)} 分野({'、'.join(g[0] for g in gaps)})")
    if unknown:
        print(f"知っていることが書いていない分野: {'、'.join(unknown)}")
    print(f"{res} に書きました")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
