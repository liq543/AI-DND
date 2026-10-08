"""Champion 7, Additional Fighting Style (rules/classes/fighter.md): level-up asks for a second Fighting Style feat."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class ChampionStyleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-champ-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Champion Test")
        self.ok("char", "create", "--name", "Kira Vale", "--class", "Fighter", "--species", "Human", "--background", "Soldier",
                "--method", "standard", "--scores", "str=15,dex=13,con=14,int=8,wis=12,cha=10", "--bonus", "str+2,con+1",
                "--skills", "perception,survival", "--equipment", "A", "--bg-equipment", "A",
                "--species-skill", "insight", "--species-feat", "Alert", "--fighting-style", "Great Weapon Fighting",
                "--masteries", "longsword,greatsword,javelin", "--languages", "Elvish,Dwarvish")
        self.ok("xp", "award", "--amount", "23000", "--reason", "test", "--override", "test fixture")
        steps = {3: ["--subclass", "Champion"], 4: ["--feat", "Ability Score Improvement", "--asi", "str+1,con+1"],
                 6: ["--feat", "Ability Score Improvement", "--asi", "dex+2"]}
        for lv in range(2, 7):
            self.ok("char", "levelup", "kira-vale", "--hp", "avg", *steps.get(lv, []))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def feats(self):
        return [f["name"] for f in _cli.game(self.env).get("kira-vale")["feats"]]

    def test_level_seven_asks_for_and_grants_a_second_style(self):
        code, out = _cli.run(self.env, "char", "levelup", "kira-vale", "--hp", "avg")
        self.assertNotEqual(code, 0)
        self.assertIn("Additional Fighting Style", out)
        code, out = _cli.run(self.env, "char", "levelup", "kira-vale", "--hp", "avg", "--fighting-style", "Great Weapon Fighting")
        self.assertNotEqual(code, 0)
        self.ok("char", "levelup", "kira-vale", "--hp", "avg", "--fighting-style", "Defense")
        self.assertIn("Defense", self.feats())
        self.assertIn("Great Weapon Fighting", self.feats())


if __name__ == "__main__":
    unittest.main()
