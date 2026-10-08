"""A Stone of Good Luck adds +1 to every ability check: skills, plain ability checks and tool checks alike."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path


class LuckstoneChecksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-luck-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Luck Test")
        self.ok("char", "create", "--name", "Kira Vale", "--class", "Fighter", "--species", "Human", "--background", "Soldier",
                "--method", "standard", "--scores", "str=15,dex=13,con=14,int=8,wis=12,cha=10", "--bonus", "str+2,con+1",
                "--skills", "perception,survival", "--equipment", "A", "--bg-equipment", "A",
                "--species-skill", "insight", "--species-feat", "Alert", "--fighting-style", "Defense",
                "--masteries", "longsword,greatsword,javelin", "--languages", "Elvish,Dwarvish")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def mod(self, *check):
        out = self.ok("check", "kira-vale", *check)
        m = re.search(r"\d+\)\s*([+-]\s*\d+)?\s*=", out)
        self.assertIsNotNone(m, out)
        return int((m.group(1) or "0").replace(" ", ""))

    def test_luckstone_adds_to_plain_ability_checks(self):
        before = self.mod("strength")
        self.ok("item", "add", "kira-vale", "Stone of Good Luck (Luckstone)", "--source", "loot: test", "--identified",
                "--override", "test fixture")
        sid = next(i["id"] for i in _cli.game(self.env).get("kira-vale")["inventory"] if "luck" in i["name"].lower())
        self.ok("item", "equip", "kira-vale", sid)
        self.ok("item", "attune", "kira-vale", sid)
        self.assertEqual(self.mod("strength"), before + 1)


if __name__ == "__main__":
    unittest.main()
