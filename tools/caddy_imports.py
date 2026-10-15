# SPDX-License-Identifier: AGPL-3.0-or-later
"""Keeps aiai's import lines in a Caddyfile that another project rewrites.

On the aiai VM, Caddy is shared with another site, whose deploy script writes its own
/etc/caddy/Caddyfile and drops the lines that bring in aiai's sites. This puts the lines
back when they are missing, checks the whole file with `caddy validate`, and reloads Caddy.
It changes nothing else in the file, and does nothing when the lines are there.

    sudo python3 tools/caddy_imports.py [--caddyfile /etc/caddy/Caddyfile] \\
        [--line "import /etc/caddy/aiai.caddy" --line "import /etc/caddy/shinsa.caddy"] [--dry-run]

systemd runs it when the file changes (aiai-caddy-imports.path) and every 5 minutes
(aiai-caddy-imports.timer), so a rewrite the watch misses is caught too. What it did is in
`journalctl -u aiai-caddy-imports`. Only the standard library is used.
"""
import argparse
import os
import subprocess
import sys
import tempfile

LINES = ["import /etc/caddy/aiai.caddy", "import /etc/caddy/shinsa.caddy"]


def missing(text, lines):
    """The lines that are not in the file as lines of their own."""
    have = {line.strip() for line in text.splitlines()}
    return [line for line in lines if line not in have]


def with_lines(text, lines):
    """The file with the lines added at the end, one per line."""
    return text + ("" if text.endswith("\n") or not text else "\n") + "".join(line + "\n" for line in lines)


def valid(path, caddy="caddy"):
    r = subprocess.run([caddy, "validate", "--config", path, "--adapter", "caddyfile"], capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or r.stdout).strip().splitlines()[-1:] or [""]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Caddyfile に aiai の import の行が無ければ足し、確かめて、読み込み直します")
    ap.add_argument("--caddyfile", default="/etc/caddy/Caddyfile")
    ap.add_argument("--line", action="append", help="あるべき行(何度でも)。既定は aiai と審査用の 2 行")
    ap.add_argument("--caddy", default="caddy", help="caddy の命令")
    ap.add_argument("--dry-run", action="store_true", help="足す行を出すだけで、書かない")
    a = ap.parse_args(argv)
    lines = a.line or LINES
    with open(a.caddyfile, encoding="utf-8") as f:
        text = f.read()
    gone = missing(text, lines)
    if not gone:
        return 0
    print("無くなっていた行: " + "、".join(gone))
    if a.dry_run:
        return 0
    new = with_lines(text, gone)
    # check the new file before it replaces the old one, so a broken file never reaches Caddy
    folder = os.path.dirname(os.path.abspath(a.caddyfile))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".Caddyfile.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new)
        ok, why = valid(tmp, a.caddy)
        if not ok:
            print("足すと設定が正しくなくなるので、書きませんでした: " + why[0], file=sys.stderr)
            return 1
        os.chmod(tmp, os.stat(a.caddyfile).st_mode & 0o777)
        os.replace(tmp, a.caddyfile)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    r = subprocess.run(["systemctl", "reload", "caddy"], capture_output=True, text=True)
    if r.returncode != 0:
        print("Caddy を読み込み直せませんでした: " + r.stderr.strip(), file=sys.stderr)
        return 1
    print("行を足して、Caddy を読み込み直しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
