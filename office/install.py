# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turns officework into the resume and application-form edition.

    python office/install.py            # put the settings and buttons in place
    python office/install.py --remove   # take them away (back to the full ribbon)

It copies ribbon.toml and ribbon/aiai_*.py into ~/.config/officework/ and
writes where this repository is into aiai.txt, so the buttons find the
forms and tools. An existing ribbon.toml that differs is kept unless
--force is given. Restart officework afterwards.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONF = os.path.expanduser("~/.config/officework")


def ours():
    return sorted(f for f in os.listdir(os.path.join(HERE, "ribbon")) if f.startswith("aiai_") and f.endswith(".py"))


def install(force):
    os.makedirs(os.path.join(CONF, "ribbon"), exist_ok=True)
    src, dst = os.path.join(HERE, "ribbon.toml"), os.path.join(CONF, "ribbon.toml")
    if os.path.exists(dst) and not force and open(dst, encoding="utf-8").read() != open(src, encoding="utf-8").read():
        sys.exit(f"{dst} が既にあります。置き換えるときは --force を付けてください")
    shutil.copyfile(src, dst)
    for f in ours():
        shutil.copyfile(os.path.join(HERE, "ribbon", f), os.path.join(CONF, "ribbon", f))
    with open(os.path.join(CONF, "aiai.txt"), "w", encoding="utf-8") as f:
        f.write(ROOT + "\n")
    print(f"{CONF} に置きました。officework を起動し直してください")


def remove():
    gone = [os.path.join(CONF, "aiai.txt")] + [os.path.join(CONF, "ribbon", f) for f in ours()]
    toml = os.path.join(CONF, "ribbon.toml")
    kept = ""
    if os.path.exists(toml):
        # A ribbon.toml changed by hand is left for the person to look at
        if open(toml, encoding="utf-8").read() == open(os.path.join(HERE, "ribbon.toml"), encoding="utf-8").read():
            gone.append(toml)
        else:
            kept = f"{toml} は書き換えてあったので残しました。"
    for p in gone:
        if os.path.exists(p):
            os.remove(p)
    print(f"取り除きました。{kept}officework を起動し直すと、元のリボンに戻ります")


if __name__ == "__main__":
    if "--remove" in sys.argv:
        remove()
    else:
        install("--force" in sys.argv)
