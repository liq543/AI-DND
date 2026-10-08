"""SRD Flame Tongue: a Bonus Action command word sets it ablaze (+2d6 Fire on a hit) while held and attuned;
stowing it puts the flames out."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class FlameTongueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-ft-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Flame Test")
        self.ok("char", "create", "--name", "Kira Vale", "--class", "Fighter", "--species", "Human", "--background", "Soldier",
                "--method", "standard", "--scores", "str=15,dex=13,con=14,int=8,wis=12,cha=10", "--bonus", "str+2,con+1",
                "--skills", "perception,survival", "--equipment", "A", "--bg-equipment", "A",
                "--species-skill", "insight", "--species-feat", "Alert", "--fighting-style", "Defense",
                "--masteries", "longsword,greatsword,javelin", "--languages", "Elvish,Dwarvish")
        self.ok("item", "add", "kira-vale", "Flame Tongue (Longsword)", "--source", "loot: test", "--identified",
                "--override", "test fixture")
        self.ok("map", "gen", "wilderness", "--biome", "plains", "--w", "20", "--h", "14", "--id", "field", "--seed", "2", "--show")
        self.ok("place", "kira-vale", "5,5", "--map", "field")
        self.ok("npc", "add", "ogre", "--at", "6,5", "--map", "field", "--name", "Big Ogre", "--side", "enemy")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def blade(self):
        g = _cli.game(self.env)
        return next(i for i in g.get("kira-vale")["inventory"] if "flame tongue" in i["name"].lower())

    def test_needs_holding_and_attunement(self):
        bid = self.blade()["id"]
        self.ok("item", "unequip", "kira-vale", bid) if self.blade().get("equipped") else None
        code, _ = _cli.run(self.env, "item", "light", "kira-vale", bid)
        self.assertNotEqual(code, 0)
        self.ok("item", "equip", "kira-vale", bid)
        if not self.blade().get("attuned"):
            code, out = _cli.run(self.env, "item", "light", "kira-vale", bid)
            self.assertNotEqual(code, 0)
            self.assertIn("attunement", out)

    def test_ablaze_adds_fire_and_unequip_puts_it_out(self):
        bid = self.blade()["id"]
        if not self.blade().get("equipped"):
            self.ok("item", "equip", "kira-vale", bid)
        if not self.blade().get("attuned"):
            self.ok("item", "attune", "kira-vale", bid)
        self.assertIn("bursts into flame", self.ok("item", "light", "kira-vale", bid))
        self.assertTrue(self.blade().get("lit"))
        self.ok("combat", "start")
        for _ in range(30):
            while "Kira Vale" not in self.ok("combat", "status").split("➤")[1].split("\n")[0]:
                self.ok("combat", "next")
            out = self.ok("attack", "kira-vale", "big-ogre", bid)
            self.ok("combat", "next")
            if "HIT" in out:
                self.assertIn("flames", out)
                self.assertIn("fire", out)
                break
        else:
            self.fail("no hit in 30 swings")
        self.ok("item", "unequip", "kira-vale", bid)
        self.assertFalse(self.blade().get("lit"))


if __name__ == "__main__":
    unittest.main()
