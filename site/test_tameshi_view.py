# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tries the addresses and the routes of site/app/tameshi_view.py, which needs Flet (skipped without it):

    python site/test_tameshi_view.py
"""
import importlib
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))

try:
    import flet  # noqa: F401
except ImportError:
    flet = None


def load(env):
    """site/app/tameshi_view.py read again with exactly this environment."""
    with mock.patch.dict(os.environ, env, clear=True):
        sys.modules.pop("tameshi_view", None)
        return importlib.import_module("tameshi_view")


@unittest.skipUnless(flet, "Flet is not installed")
class TameshiViewTest(unittest.TestCase):
    def test_the_addresses_come_from_the_site(self):
        v = load({"AIAI_SITE": "https://aiai.example"})
        self.assertEqual((v.PUBLIC, v.API, v.RETURN), ("https://aiai.example/tameshi", "https://aiai.example/tameshi", "https://aiai.example/app/"))

    def test_the_mount_switch_is_not_an_address(self):
        # the server has AIAI_TAMESHI=1 to mount tameshi/server.py; that is no address of it
        v = load({"AIAI_SITE": "https://aiai.example", "AIAI_TAMESHI": "1"})
        self.assertEqual((v.PUBLIC, v.API), ("https://aiai.example/tameshi", "https://aiai.example/tameshi"))

    def test_the_addresses_can_be_set(self):
        v = load({"AIAI_SITE": "https://aiai.example", "AIAI_TAMESHI_URL": "https://t.example/x/", "AIAI_TAMESHI_API": "http://127.0.0.1:8020/tameshi",
                  "AIAI_RETURN": "https://aiai.example/app"})
        self.assertEqual((v.PUBLIC, v.API, v.RETURN), ("https://t.example/x", "http://127.0.0.1:8020/tameshi", "https://aiai.example/app/"))

    def test_the_strip_has_the_eight_steps_and_the_stages_are_the_places(self):
        v = load({})
        self.assertEqual([label.split()[0] for label, _ in v.STRIP], list("12345678"))
        self.assertEqual([key for _, key in v.STRIP if key], ["chousa", "kaizen", "kadai", "sekkei", "tesuto"])  # the steps Gemini does
        self.assertEqual(set(v.PLACES), {key for _, key in v.STRIP if key})
        self.assertEqual([key for _, key in v.OTHERS], ["chat", "news"])
        self.assertEqual(set(v.NAMES), set(v.PLACES) | {"chat", "news"})
        self.assertEqual(set(v.QUOTA), set(v.NAMES))
        self.assertEqual(v.OWN_STEP, "この段は、自分と、ふだん使っている AI でします")

    def test_signing_in_and_registering_are_screens_that_are_no_stage(self):
        v = load({})
        self.assertEqual(set(v.SCREENS), {"signin", "touroku"})
        self.assertFalse(set(v.SCREENS) & set(v.PLACES))
        self.assertFalse(set(v.SCREENS) & set(v.NAMES))

    def test_the_place_at_the_end_of_the_address(self):
        v = load({})
        self.assertEqual(v.place_of("/tameshi/chousa?code=abc"), (True, "chousa", "abc"))
        self.assertEqual(v.place_of("/tameshi"), (True, "", ""))
        self.assertEqual(v.place_of("/tameshi/nani"), (True, "", ""))
        self.assertEqual(v.place_of("/tameshi/signin"), (True, "signin", ""))
        self.assertEqual(v.place_of("/tameshi/touroku"), (True, "touroku", ""))
        self.assertEqual(v.place_of("/?code=abc"), (False, "", ""))
        self.assertEqual(v.place_of(None), (False, "", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
