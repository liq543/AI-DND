"""A stat block's AC includes its armour; `npc unarmored` gives the SRD unarmoured AC (10 + Dex), `armored` restores it."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class UnarmoredTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-unarm-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Armour Test")
        self.ok("npc", "add", "noble", "--name", "Oswin Hale", "--side", "neutral")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def ac(self):
        from engine import core
        camp = next(p for p in (self.tmp / "campaigns").iterdir() if p.is_dir() and not p.name.startswith("_"))
        return core.replay(core.Store(camp).load())["entities"]["oswin-hale"]["ac"]

    def test_unarmored_and_back(self):
        armoured = self.ac()
        self.assertEqual(armoured, 15)                      # SRD noble: breastplate
        self.assertIn("AC 11", self.ok("npc", "unarmored", "oswin-hale"))   # Dex 12 -> 10 + 1
        self.assertEqual(self.ac(), 11)
        self.ok("npc", "armored", "oswin-hale")
        self.assertEqual(self.ac(), armoured)

    def test_leave_announces_a_visible_creature(self):
        self.assertIn("leaves the scene", self.ok("npc", "leave", "oswin-hale"))
        self.assertIn("is back", self.ok("npc", "return", "oswin-hale"))


if __name__ == "__main__":
    unittest.main()
