"""Standing forces: units with numbers, kit (SRD armor sets their AC), coin shares (attitude) and mustering."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class ForcesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-forces-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Forces Test")
        self.ok("char", "create", "--name", "Kira Vale", "--class", "Fighter", "--species", "Human", "--background", "Soldier",
                "--method", "standard", "--scores", "str=15,dex=13,con=14,int=8,wis=12,cha=10", "--bonus", "str+2,con+1",
                "--skills", "perception,survival", "--equipment", "A", "--bg-equipment", "A",
                "--species-skill", "insight", "--species-feat", "Alert", "--fighting-style", "Defense",
                "--masteries", "longsword,greatsword,javelin", "--languages", "Elvish,Dwarvish")
        self.ok("map", "gen", "wilderness", "--biome", "plains", "--w", "20", "--h", "14", "--id", "field", "--seed", "2", "--show")
        self.ok("place", "kira-vale", "5,5", "--map", "field")
        self.ok("forces", "add", "militia", "--name", "Oakhollow militia", "--stat", "commoner", "--count", "4",
                "--captain", "Oswin Hale", "--pay", "2sp/day")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def unit(self):
        return _cli.game(self.env).state["forces"]["militia"]

    def test_issued_armor_sets_ac_and_uses_up_the_kit(self):
        self.ok("loot", "cache", "field", "5,6", "--name", "Armoury", "--id", "armoury", "--items", "5x Chain Shirt; 4x Shield")
        self.ok("loot", "open", "kira-vale", "armoury")
        out = self.ok("forces", "equip", "militia", "--from", "armoury", "--armor", "Chain Shirt", "--shield")
        self.assertIn("AC 10 → 15", out)     # commoner: Chain Shirt 13 + Dex 0, + Shield 2
        _, short = _cli.run(self.env, "forces", "equip", "militia", "--from", "armoury", "--shield")
        self.assertIn("not 4", short)        # the shields are all issued
        made = self.ok("forces", "muster", "militia", "--count", "2", "--at", "8,8", "--map", "field")
        self.assertIn("AC 15", made)
        self.ok("npc", "add", "guard", "--at", "9,9", "--map", "field", "--name", "Turncoat", "--side", "enemy")
        self.ok("forces", "enlist", "militia", "--ids", "turncoat")
        self.assertEqual(_cli.game(self.env).get("turncoat")["ac"], 15)

    def test_a_crown_a_man_moves_their_attitude(self):
        self.ok("coins", "kira-vale", "+10gp", "--source", "loot: test")
        out = self.ok("forces", "share", "militia", "--coins", "2gp", "--from", "kira-vale", "--reason", "a token")
        self.assertIn("stays Indifferent", out)
        out = self.ok("forces", "share", "militia", "--coins", "4gp", "--from", "kira-vale", "--reason", "spoils")
        self.assertIn("Indifferent → Friendly", out)
        self.assertEqual(self.unit()["attitude"], "friendly")
        self.assertIn("Forces", self.ok("status"))


if __name__ == "__main__":
    unittest.main()
