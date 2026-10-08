"""Charged wands (rules/magic-items): cast the wand's spell for charges, no slot spent; charges come back at dawn."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class WandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-wand-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Wand Test")
        self.ok("char", "create", "--name", "Kira Vale", "--class", "Fighter", "--species", "Human", "--background", "Soldier",
                "--method", "standard", "--scores", "str=15,dex=13,con=14,int=8,wis=12,cha=10", "--bonus", "str+2,con+1",
                "--skills", "perception,survival", "--equipment", "A", "--bg-equipment", "A",
                "--species-skill", "insight", "--species-feat", "Alert", "--fighting-style", "Defense",
                "--masteries", "longsword,greatsword,javelin", "--languages", "Elvish,Dwarvish")
        self.ok("item", "add", "kira-vale", "Wand of Magic Missiles", "--source", "loot: test", "--identified",
                "--override", "test fixture")
        self.ok("map", "gen", "wilderness", "--biome", "plains", "--w", "20", "--h", "14", "--id", "field", "--seed", "2", "--show")
        self.ok("place", "kira-vale", "5,5", "--map", "field")
        self.ok("npc", "add", "ogre", "--at", "9,5", "--map", "field", "--name", "Big Ogre", "--side", "enemy")
        self.ok("combat", "start")
        self.wand = next(i["id"] for i in self.inv() if "wand" in i["name"].lower())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def inv(self):
        return _cli.game(self.env).get("kira-vale")["inventory"]

    def charges(self):
        return next(i for i in self.inv() if i["id"] == self.wand).get("charges")

    def kiras_turn(self):
        while "Kira Vale" not in self.ok("combat", "status").split("➤")[1].split("\n")[0]:
            self.ok("combat", "next")

    def test_charges_spent_by_level_and_capped(self):
        self.kiras_turn()
        out = self.ok("cast", "kira-vale", "magic missile", "--item", self.wand, "--level", "3",
                      "--targets", "big-ogre,big-ogre,big-ogre,big-ogre,big-ogre")
        self.assertIn("3 charge(s) spent, 4 left", out)
        self.assertEqual(self.charges(), 4)
        self.ok("combat", "next")
        self.kiras_turn()
        code, out = _cli.run(self.env, "cast", "kira-vale", "magic missile", "--item", self.wand, "--level", "4",
                             "--targets", "big-ogre")
        self.assertNotEqual(code, 0)

    def test_dawn_restores_charges(self):
        self.kiras_turn()
        self.ok("cast", "kira-vale", "magic missile", "--item", self.wand, "--level", "3",
                "--targets", "big-ogre,big-ogre,big-ogre,big-ogre,big-ogre")
        self.ok("combat", "end")
        self.ok("time", "24h", "--reason", "a day passes")
        self.ok("combat", "start")
        self.kiras_turn()
        out = self.ok("cast", "kira-vale", "magic missile", "--item", self.wand, "--targets", "big-ogre,big-ogre,big-ogre")
        self.assertIn("regains charges at dawn", out)
        self.assertGreaterEqual(self.charges(), 5)


if __name__ == "__main__":
    unittest.main()
