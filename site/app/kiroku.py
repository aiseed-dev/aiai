# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reads a person's AI records on their own PC, mechanically: the records
that AI tools keep (Claude Code, Codex, Gemini CLI), the export ZIPs that
ChatGPT, Claude and Gemini send, and the CSV of Copilot activity that a
personal Microsoft account can export (its columns are not published, so
a column is taken only when its name says it is what the person typed). Only what the person wrote is kept.
Only the standard library is used, so the app carries it everywhere.

Formats are not fixed per company: any JSON is walked, and a dict that
says it is from the user (role / author.role / sender / type = user or
human) with text in it (content, text, parts) becomes one message. What
cannot be read this way is reported as not read.
"""
import csv
import datetime
import glob
import io
import json
import os
import re
import unicodedata
import zipfile

USER_ROLES = {"user", "human"}
TIME_KEYS = ("timestamp", "created_at", "create_time", "createTime", "time", "date")

# What gets hidden before anything leaves the PC
MASKS = [
    (re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+"), "[メールアドレス]"),
    (re.compile(r"(?<![\d-])\d{3}-\d{4}(?![\d-])|〒\s*\d{7}(?!\d)"), "[郵便番号]"),
    (re.compile(r"(?<![\d-])0\d{1,4}-?\d{1,4}-?\d{3,4}(?![\d-])"), "[電話番号]"),
    (re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)"), "[12 桁の数字]"),
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})"),
     "[鍵]"),
]


def mask(text):
    t = unicodedata.normalize("NFKC", text)
    for pattern, label in MASKS:
        t = pattern.sub(label, t)
    return t


# ---- finding the records ----------------------------------------------------


def tool_records(home=None):
    """{source: [paths]} of the records AI tools keep on this PC."""
    home = home or os.path.expanduser("~")
    found = {
        "Claude Code": glob.glob(os.path.join(home, ".claude", "projects", "*", "*.jsonl")),
        "Codex": glob.glob(os.path.join(home, ".codex", "history.jsonl"))
        + glob.glob(os.path.join(home, ".codex", "sessions", "**", "*.jsonl"), recursive=True),
        "Gemini CLI": glob.glob(os.path.join(home, ".gemini", "tmp", "*", "chats", "*")),
    }
    return {k: sorted(v) for k, v in found.items() if v}


# ---- reading ------------------------------------------------------------------


def _text_of(value):
    """The plain text in a content-like value: a string, a list of parts, or a dict."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        out = []
        for part in value:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict) and part.get("type") in (None, "text", "input_text"):
                out.append(_text_of(part.get("text", part.get("content", ""))))
        return "\n".join(x for x in out if x)
    if isinstance(value, dict):
        for k in ("parts", "text", "content"):
            if k in value:
                return _text_of(value[k])
    return ""


def _role_of(d):
    for v in (d.get("role"), d.get("sender"), d.get("type")):
        if isinstance(v, str):
            return v.lower()
    author = d.get("author")
    if isinstance(author, dict) and isinstance(author.get("role"), str):
        return author["role"].lower()
    return ""


def _time_of(d):
    for k in TIME_KEYS:
        v = d.get(k)
        if isinstance(v, (int, float)) and v > 1e9:
            return datetime.datetime.fromtimestamp(v, datetime.timezone.utc).date().isoformat()
        if isinstance(v, str) and re.match(r"\d{4}-\d{2}-\d{2}", v):
            return v[:10]
    return ""


def _walk(obj, out, when=""):
    """Collects (date, text) of user messages anywhere in a JSON value."""
    if isinstance(obj, dict):
        when = _time_of(obj) or when
        if obj.get("isMeta") or obj.get("isSidechain"):
            return
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else None
        target = msg if msg is not None and _role_of(msg) else obj
        if _role_of(target) in USER_ROLES:
            text = _text_of(target.get("content", target.get("text", target.get("parts", ""))))
            if text.strip():
                out.append((when or _time_of(target), text.strip()))
            return
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _walk(v, out, when)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, out, when)


def read_json_text(text):
    """User messages in a JSON or JSON Lines text."""
    out = []
    try:
        _walk(json.loads(text), out)
        return out
    except ValueError:
        pass
    for line in text.splitlines():
        line = line.strip()
        if line:
            try:
                _walk(json.loads(line), out)
            except ValueError:
                continue
    return out


PROMPT_COLUMN = re.compile(r"prompt|question|request|user|query|input|質問|入力|依頼", re.I)
DATE_COLUMN = re.compile(r"date|time|日時|日付", re.I)


def read_csv_text(text):
    """User messages in a CSV whose header names the prompt column; nothing otherwise."""
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    if not rows:
        return []
    head = rows[0]
    prompt = next((i for i, h in enumerate(head) if PROMPT_COLUMN.search(h) and not re.search(r"response|answer|回答", h, re.I)), None)
    if prompt is None:
        return []
    date = next((i for i, h in enumerate(head) if DATE_COLUMN.search(h)), None)
    out = []
    for r in rows[1:]:
        if prompt < len(r) and r[prompt].strip():
            d = r[date][:10] if date is not None and date < len(r) and re.match(r"\d{4}-\d{2}-\d{2}", r[date]) else ""
            out.append((d, r[prompt].strip()))
    return out


def read_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if path.lower().endswith(".csv"):
        return read_csv_text(text)
    return read_json_text(text)


def read_zip(path):
    """User messages in the JSON files inside an export ZIP."""
    out = []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.lower().endswith((".json", ".jsonl")):
                out += read_json_text(z.read(name).decode("utf-8", errors="replace"))
            elif name.lower().endswith(".csv"):
                out += read_csv_text(z.read(name).decode("utf-8", errors="replace"))
    return out


# ---- what the app shows and sends ------------------------------------------------


def summary(messages):
    """Counts and the span of dates, for the screen."""
    dates = sorted(d for d, _ in messages if d)
    months = {}
    for d in dates:
        months[d[:7]] = months.get(d[:7], 0) + 1
    return {"messages": len(messages), "chars": sum(len(t) for _, t in messages),
            "first": dates[0] if dates else "", "last": dates[-1] if dates else "", "months": months}


def material(messages, limit=60000, per_message=600):
    """Masked user messages, spread over the whole span, at most `limit` characters.

    Short and repeated messages are dropped; long ones are cut. When there
    is more than fits, messages are taken at even steps from oldest to newest.
    """
    seen, items = set(), []
    for d, t in sorted(messages, key=lambda m: m[0]):
        t = " ".join(t.split())
        if len(t) < 15 or t in seen:
            continue
        seen.add(t)
        items.append(f"[{d or '日付なし'}] {mask(t[:per_message])}")
    total = sum(len(x) + 1 for x in items)
    if total > limit and items:
        step = total / limit
        items = [items[int(i * step)] for i in range(int(len(items) / step))]
    return "\n".join(items)
