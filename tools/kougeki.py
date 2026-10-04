# SPDX-License-Identifier: AGPL-3.0-or-later
"""Counts the attacks a server has seen, on the server itself: SSH log-in
attempts (from the sshd journal), probing HTTP requests (from Caddy's
access log and its journal), and the ports open to the world. Prints an
adoc report, or JSON with --json, or with --out writes the day's record
(YYYY-MM-DD.adoc and .json) into a folder, which a daily timer does so the
record grows day by day. Needs to read the journal and the log, so it is
run as root. Only the standard library is used.

    sudo python3 tools/kougeki.py [--hours 24] [--json]
    sudo python3 tools/kougeki.py --out /home/dev/aiai-server [--ai gemini]   # the daily record, run just after midnight

With --ai gemini, Gemini reads the day's counts next to the earlier days'
and writes a short note (anything unusual, anything to act on) into the
record; it reads and writes nothing else. On Google Cloud it is called
with the machine's service account (no key on the server); elsewhere with
GOOGLE_API_KEY. The aiai app's サーバー tab reads the folder (over SSH, or
on the server itself) and shows the days side by side.
"""
import argparse
import collections
import datetime
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
import zoneinfo

ACCESS_LOGS = ["/var/log/caddy/aiai-access.log"]
# Paths that only probes ask for on a site that has none of them
PROBE = re.compile(r"\.(env|git|aws|ssh|php|asp|aspx|jsp|cgi|bak|sql|yml|yaml)(\?|$)|/(wp-|xmlrpc|phpmyadmin|admin|console|actuator|"
                   r"cgi-bin|config|\.well-known/(?!acme)|server-status|telescope|_catalog|login\.action|owa/|ecp/|vendor/|"
                   r"\.vscode|CLAUDE\.md|AGENTS\.md|copilot-instructions|boaform|HNAP1|manager/html|solr/|jenkins|druid|geoserver)", re.I)
SCANNER = re.compile(r"zgrab|masscan|nmap|nikto|sqlmap|nuclei|python-requests|go-http-client|curl/|libwww|censys|shodan|"
                     r"internet-measurement|expanse|palo alto|l9explore|odin|netcraft", re.I)


def sh(cmd):
    try:
        return subprocess.run(cmd, text=True, capture_output=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def ssh_report(hours):
    """Log-in attempts that failed, from sshd's journal."""
    out = sh(["journalctl", "-u", "ssh", "-u", "sshd", "--since", f"-{hours}h", "-o", "cat", "--no-pager"])
    ips, users, attempts = collections.Counter(), collections.Counter(), 0
    for line in out.splitlines():
        if re.search(r"Invalid user|Failed password|authenticating user|\[preauth\]|Unable to negotiate", line):
            attempts += 1
            m = re.search(r"from ([0-9a-f.:]+)", line)
            if m:
                ips[m[1]] += 1
            m = re.search(r"(?:Invalid user|for invalid user|for) (\S+) from", line)
            if m and m[1] not in ("invalid",):
                users[m[1]] += 1
    accepted = len(re.findall(r"Accepted (?:publickey|password)", out))
    settings = {}
    for line in sh(["sshd", "-T"]).splitlines():
        k, _, v = line.partition(" ")
        if k in ("passwordauthentication", "permitrootlogin", "kbdinteractiveauthentication", "port"):
            settings[k] = v
    return {"attempts": attempts, "top_ips": ips.most_common(5), "top_users": users.most_common(5),
            "accepted": accepted, "settings": settings}


def read_access(path, since):
    """Caddy's JSON access lines newer than `since` (a timestamp)."""
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("ts", 0) >= since:
                rows.append(r)
    return rows


def http_report(hours):
    """Requests seen by Caddy: the access log where there is one, the journal's errors otherwise."""
    since = datetime.datetime.now(datetime.timezone.utc).timestamp() - hours * 3600
    rows = []
    for p in ACCESS_LOGS:
        rows += read_access(p, since)
    source = "access log"
    if not rows:  # only the errors Caddy puts in the journal
        source = "journal"
        for line in sh(["journalctl", "-u", "caddy", "--since", f"-{hours}h", "-o", "cat", "--no-pager"]).splitlines():
            if '"request"' in line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    total, probes, by_host, probe_ips, probe_paths, scanners, statuses = 0, 0, collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
    for r in rows:
        req = r.get("request", {})
        uri, host, ip = req.get("uri", ""), req.get("host", ""), req.get("remote_ip") or req.get("client_ip", "")
        ua = " ".join(req.get("headers", {}).get("User-Agent", []))
        total += 1
        by_host[host] += 1
        statuses[str(r.get("status", ""))[:1] + "xx"] += 1
        if PROBE.search(uri):
            probes += 1
            probe_ips[ip] += 1
            probe_paths[uri[:80]] += 1
        if SCANNER.search(ua):
            scanners[ua[:60]] += 1
    return {"source": source, "requests": total, "probes": probes, "by_host": by_host.most_common(6),
            "probe_ips": probe_ips.most_common(5), "probe_paths": probe_paths.most_common(8),
            "scanners": scanners.most_common(5), "statuses": sorted(statuses.items())}


def ports_report():
    """What listens to the outside (not only on this machine)."""
    out = sh(["ss", "-ltnpH"])
    open_ports = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        local = parts[3]
        if local.startswith(("127.", "[::1]")):
            continue
        m = re.search(r'users:\(\("([^"]+)"', line)
        open_ports.append((local, m[1] if m else ""))
    return sorted(set(open_ports))


def report(hours):
    now = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Tokyo"))
    # Run just after midnight, the record is the day that just ended
    return {"when": now.isoformat(timespec="minutes"), "day": (now - datetime.timedelta(hours=1)).date().isoformat(),
            "hours": hours, "host": sh(["hostname"]).strip(), "ssh": ssh_report(hours), "http": http_report(hours),
            "ports": ports_report()}


# ---- the AI's note -----------------------------------------------------------------


def metadata(path):
    """A value from Google Cloud's metadata server (only on a Compute Engine machine)."""
    req = urllib.request.Request("http://metadata.google.internal/computeMetadata/v1/" + path, headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.read().decode("utf-8")


def ask_gemini(prompt, model):
    """Gemini's answer to one prompt: Vertex AI with the machine's service account, or
    the Gemini API with GOOGLE_API_KEY."""
    key = os.environ.get("GOOGLE_API_KEY")
    if key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        headers = {}
    else:
        project = metadata("project/project-id")
        token = json.loads(metadata("instance/service-accounts/default/token"))["access_token"]
        url = f"https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/publishers/google/models/{model}:generateContent"
        headers = {"Authorization": f"Bearer {token}"}
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096}}  # the model's thinking counts too
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=120) as resp:
        answer = json.load(resp)
    parts = answer.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()


def earlier_days(folder, today):
    """One line per earlier day's record in the folder, newest first, at most 14."""
    lines = []
    if folder and os.path.isdir(folder):
        for f in sorted(os.listdir(folder), reverse=True):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", f) and f[:-5] != today and len(lines) < 14:
                try:
                    with open(os.path.join(folder, f), encoding="utf-8") as fh:
                        r = json.load(fh)
                    top = r["ssh"]["top_ips"][0] if r["ssh"]["top_ips"] else ["", 0]
                    lines.append(f"- {f[:-5]}: SSH の試み {r['ssh']['attempts']} 回(多い相手 {top[0]} {top[1]} 回)、鍵で入れた {r['ssh']['accepted']} 回、"
                                 f"HTTP {r['http']['requests']} 件のうち穴を探す物 {r['http']['probes']} 件、開いている口 {len(r['ports'])}")
                except (OSError, ValueError, KeyError):
                    pass
    return lines


def ai_note(r, folder, model):
    before = earlier_days(folder, r["day"])
    prompt = ("あなたは、個人が持つ小さなサーバーの、1 日分の攻撃の記録を読む係です。サーバーには何もできず、読んで短く書くだけです。\n"
              "次の今日の記録と、前の日の数を見て、日本語の「です・ます」の説明文で、8 行以内で書いてください。\n"
              "1. 前の日と比べて、いつもと違うこと(増えた、減った、新しい種類の物、新しく開いた口)。無ければ「いつもどおりです」と書きます\n"
              "2. 人が手を打った方がよいこと。無ければ「手を打つことはありません」と書きます\n"
              "推測で書かず、記録にある数だけを使います。パスワードでの認証が切ってあれば、SSH の試みは入れないので、回数が多くても手を打つ物ではありません。\n\n"
              f"<今日の記録>\n{r['adoc']}\n</今日の記録>\n\n<前の日>\n" + ("\n".join(before) or "(まだありません)") + "\n</前の日>\n")
    try:
        text = ask_gemini(prompt, model)
        return {"model": model, "text": text or "(答えがありませんでした)"}
    except (OSError, ValueError, KeyError, urllib.error.URLError) as e:
        detail = getattr(e, "read", lambda: b"")()
        return {"model": model, "text": "", "error": (detail.decode("utf-8", errors="replace") if detail else str(e))[:300]}


def adoc(r):
    s, h = r["ssh"], r["http"]
    lines = [f"= サーバーの攻撃の記録 {r['day']}", f":日付: {r['day']}", f":日時: {r['when']}", f":範囲: 直近 {r['hours']} 時間",
             f":ホスト: {r['host']}", "",
             "== SSH", "",
             f"失敗したログインの試み: {s['attempts']} 回。鍵で入れた回数: {s['accepted']} 回。"]
    if s["settings"]:
        pw = s["settings"].get("passwordauthentication")
        lines.append("パスワードでの認証は " + ("切ってあります(鍵だけ)。" if pw == "no" else "有効です。鍵だけにすることを勧めます。")
                     + f" root でのログイン: {s['settings'].get('permitrootlogin', '?')}。")
    if s["top_ips"]:
        lines += ["", "多い相手:"] + [f"- {ip}: {n} 回" for ip, n in s["top_ips"]]
    if s["top_users"]:
        lines += ["", "試された名前:"] + [f"- {u}: {n} 回" for u, n in s["top_users"]]
    lines += ["", "== HTTP", "",
              f"要求: {h['requests']} 件({'アクセスログ' if h['source'] == 'access log' else '失敗した要求の記録だけ'})。"
              f"穴を探す要求: {h['probes']} 件。"]
    if h["by_host"]:
        lines += ["", "ホストごと:"] + [f"- {host or '(無し)'}: {n} 件" for host, n in h["by_host"]]
    if h["probe_paths"]:
        lines += ["", "探された所:"] + [f"- {p}: {n} 件" for p, n in h["probe_paths"]]
    if h["probe_ips"]:
        lines += ["", "探してきた相手:"] + [f"- {ip}: {n} 件" for ip, n in h["probe_ips"]]
    if h["scanners"]:
        lines += ["", "走査の道具の名乗り:"] + [f"- {ua}: {n} 件" for ua, n in h["scanners"]]
    lines += ["", "== 外に開いている口", ""] + [f"- {local} ({proc})" for local, proc in r["ports"]]
    if r.get("ai"):
        lines += ["", f"== AI の所見({r['ai']['model']})", "", r["ai"]["text"] or f"(読めませんでした: {r['ai'].get('error', '')})"]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="このサーバーが受けた攻撃を数えます")
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", help="この日の記録(adoc と json)を書くフォルダー。日付は、数えた範囲の終わりの 1 時間前の日")
    ap.add_argument("--ai", choices=["gemini"], help="数えた物を AI に読ませて、所見を記録に足す")
    ap.add_argument("--model", default="gemini-3.5-flash")
    a = ap.parse_args()
    r = report(a.hours)
    r["adoc"] = adoc(r)
    if a.ai:
        r["ai"] = ai_note(r, a.out, a.model)
        r["adoc"] = adoc(r)
    if a.out:
        day = r["day"]
        os.makedirs(a.out, exist_ok=True)
        with open(os.path.join(a.out, f"{day}.json"), "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False)
        with open(os.path.join(a.out, f"{day}.adoc"), "w", encoding="utf-8") as f:
            f.write(r["adoc"])
        print(os.path.join(a.out, f"{day}.adoc"))
    elif a.json:
        print(json.dumps(r, ensure_ascii=False))
    else:
        print(r["adoc"], end="")


if __name__ == "__main__":
    main()
