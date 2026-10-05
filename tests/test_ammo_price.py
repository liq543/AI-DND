"""SRD ammunition is priced per bundle (Arrows: 20 for 1 GP), while inventories count single pieces.
Also: coins kept in a container (a vault) move in and out with `coins ... --from`."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class AmmoPriceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-ammo-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Ammo Test")
        self.ok("char", "create", "--name", "Kira Vale", "--player", "T", "--class", "Fighter", "--species", "Human",
                "--background", "Soldier", "--method", "standard", "--scores", "str=15,dex=14,con=13,int=8,wis=12,cha=10",
                "--bonus", "str+2,con+1", "--skills", "perception,survival", "--languages", "Elvish,Dwarvish", "--equipment", "B", "--bg-equipment", "B",
                "--species-skill", "insight", "--species-feat", "Alert", "--fighting-style", "Defense",
                "--masteries", "longsword,javelin,greatsword")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def test_bundle_prices(self):
        out = self.ok("item", "add", "kira-vale", "Bolts", "--qty", "20", "--purchase")
        self.assertIn("purchased for 1 GP", out)
        out = self.ok("item", "sell", "kira-vale", "bolts-1", "--qty", "14")
        self.assertIn("for 3 SP 5 CP", out)   # 14 bolts at half of 5 cp each

    def test_vault_coins(self):
        self.ok("map", "gen", "wilderness", "--biome", "plains", "--w", "20", "--h", "14", "--id", "hall", "--seed", "2", "--show")
        self.ok("place", "kira-vale", "5,5", "--map", "hall")
        self.ok("map", "container", "hall", "6,6", "--name", "Iron strongbox", "--id", "vault")
        self.ok("coins", "kira-vale", "+20gp", "--source", "loot: test purse")
        out = self.ok("coins", "vault", "15gp", "--from", "kira-vale")
        self.assertIn("Iron strongbox: 15 GP", out)
        out = self.ok("coins", "kira-vale", "5gp", "--from", "vault")
        self.assertIn("Iron strongbox: 10 GP", out)
        code, out = _cli.run(self.env, "coins", "kira-vale", "50gp", "--from", "vault")
        self.assertNotEqual(code, 0)
        out = self.ok("coins", "vault", "+70gp", "--source", "tribute: a vassal's quarter")
        self.assertIn("Iron strongbox: 80 GP", out)
        out = self.ok("coins", "vault", "-30gp", "--source", "spent: wages")
        self.assertIn("Iron strongbox: 50 GP", out)
        from engine import render, core
        camp = next(p for p in (self.tmp / "campaigns").iterdir() if p.is_dir() and not p.name.startswith("_"))
        st = core.replay(core.Store(camp).load())
        self.assertIn("50 crowns", render.render_map(st["maps"]["hall"], "player", live=True))


if __name__ == "__main__":
    unittest.main()
