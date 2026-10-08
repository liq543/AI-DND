"""House rule `xp_rate`: every XP award is multiplied by the table's chosen rate, publicly."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class XpRateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-xprate-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Rate Test")
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

    def xp(self):
        return _cli.game(self.env).get("kira-vale")["xp"]

    def test_doubles_awards_and_says_so(self):
        self.ok("xp", "award", "--amount", "50", "--reason", "plain")
        self.assertEqual(self.xp(), 50)
        self.ok("set", "xp_rate=2")
        out = self.ok("xp", "award", "--amount", "50", "--reason", "doubled")
        self.assertEqual(self.xp(), 150)
        self.assertIn("house XP rate", out)

    def test_rejects_unknown_rates(self):
        code, _ = _cli.run(self.env, "set", "xp_rate=10")
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
