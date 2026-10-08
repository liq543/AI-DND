"""Robe of Eyes (rules/magic-items/robe-of-eyes.md): while worn and attuned, Darkvision and Truesight 120 ft and
Advantage on sight-based Wisdom (Perception) checks."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from engine import mechanics as M
from engine.core import item_sense


class RobeOfEyesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-robe-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Robe Test")
        self.ok("char", "create", "--name", "Kira Vale", "--class", "Fighter", "--species", "Human", "--background", "Soldier",
                "--method", "standard", "--scores", "str=15,dex=13,con=14,int=8,wis=12,cha=10", "--bonus", "str+2,con+1",
                "--skills", "perception,survival", "--equipment", "A", "--bg-equipment", "A",
                "--species-skill", "insight", "--species-feat", "Alert", "--fighting-style", "Defense",
                "--masteries", "longsword,greatsword,javelin", "--languages", "Elvish,Dwarvish")
        self.ok("item", "add", "kira-vale", "Robe of Eyes", "--source", "loot: test", "--identified", "--override", "test fixture")
        self.robe = next(i["id"] for i in self.kira()["inventory"] if "robe" in i["name"].lower())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def kira(self):
        return _cli.game(self.env).get("kira-vale")

    def test_senses_and_perception_only_when_attuned(self):
        self.assertEqual(item_sense(self.kira(), "truesight"), 0)
        self.assertNotIn("Robe of Eyes", self.ok("check", "kira-vale", "perception", "--dc", "10"))
        self.ok("item", "equip", "kira-vale", self.robe)
        self.ok("item", "attune", "kira-vale", self.robe)
        kira = self.kira()
        self.assertEqual(item_sense(kira, "truesight"), 120)
        self.assertEqual(M.vision_ft(None, kira, {"lighting": "dark"}), 120)
        self.assertIn("Robe of Eyes", self.ok("check", "kira-vale", "perception", "--dc", "10"))

    def test_attune_through_a_short_rest(self):
        before = _cli.game(self.env).state["time"]
        out = self.ok("rest", "short", "--attune", f"kira-vale:{self.robe}")
        self.assertIn("through the Short Rest", out)
        self.assertEqual(_cli.game(self.env).state["time"] - before, 60)
        self.assertEqual(item_sense(self.kira(), "darkvision"), 120)


if __name__ == "__main__":
    unittest.main()
