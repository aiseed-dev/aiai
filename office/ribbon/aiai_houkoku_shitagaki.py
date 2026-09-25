# SPDX-License-Identifier: AGPL-3.0-or-later
リボン = {"ラベル": "報告の下書き", "タブ": "報告"}
# An aiai button. install.py wrote where aiai is into aiai.txt.
import os
import sys

with open(os.path.expanduser("~/.config/officework/aiai.txt"), encoding="utf-8") as f:
    sys.path.insert(0, os.path.join(f.read().strip(), "tools"))
import office_kit

office_kit.houkoku_shitagaki()
