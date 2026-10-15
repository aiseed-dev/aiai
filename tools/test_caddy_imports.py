# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tries tools/caddy_imports.py without Caddy (a fake caddy command) and without touching /etc:

    python3 tools/test_caddy_imports.py
"""
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import caddy_imports as ci  # noqa: E402

OTHER = "api.example.com {\n    reverse_proxy 127.0.0.1:8000\n}\n"


class CaddyImportsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.tmp.name, "Caddyfile")
        self.caddy = os.path.join(self.tmp.name, "caddy")
        self.fake_caddy(0)

    def tearDown(self):
        self.tmp.cleanup()

    def fake_caddy(self, code):
        with open(self.caddy, "w") as f:
            f.write(f"#!/bin/sh\necho checked\nexit {code}\n")
        os.chmod(self.caddy, stat.S_IRWXU)

    def write(self, text):
        with open(self.file, "w", encoding="utf-8") as f:
            f.write(text)

    def read(self):
        with open(self.file, encoding="utf-8") as f:
            return f.read()

    def run_it(self):
        """Runs the program; `systemctl reload` is only recorded."""
        real, reloads = ci.subprocess.run, []

        def fake(cmd, **kw):
            if cmd[:2] == ["systemctl", "reload"]:
                reloads.append(cmd)
                return real(["true"], **kw)
            return real(cmd, **kw)
        with mock.patch.object(ci.subprocess, "run", side_effect=fake):
            code = ci.main(["--caddyfile", self.file, "--caddy", self.caddy])
        return code, reloads

    def test_the_lines_are_put_back_after_the_other_site_and_caddy_is_reloaded(self):
        self.write(OTHER)
        code, reloads = self.run_it()
        self.assertEqual(code, 0)
        self.assertEqual(self.read(), OTHER + "import /etc/caddy/aiai.caddy\nimport /etc/caddy/shinsa.caddy\n")
        self.assertEqual(len(reloads), 1)

    def test_nothing_is_done_when_the_lines_are_there(self):
        self.write(OTHER + "import /etc/caddy/aiai.caddy\n  import /etc/caddy/shinsa.caddy\n")
        before = self.read()
        code, reloads = self.run_it()
        self.assertEqual((code, reloads, self.read()), (0, [], before))

    def test_only_the_missing_line_is_added(self):
        self.write(OTHER + "import /etc/caddy/aiai.caddy")  # no newline at the end
        self.run_it()
        self.assertEqual(self.read(), OTHER + "import /etc/caddy/aiai.caddy\nimport /etc/caddy/shinsa.caddy\n")

    def test_a_file_caddy_refuses_is_not_written(self):
        self.write(OTHER)
        self.fake_caddy(1)
        code, reloads = self.run_it()
        self.assertEqual((code, reloads, self.read()), (1, [], OTHER))
        self.assertEqual(sorted(os.listdir(self.tmp.name)), ["Caddyfile", "caddy"])  # no file left behind


if __name__ == "__main__":
    unittest.main(verbosity=2)
