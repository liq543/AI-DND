"""Loot the engine remembers: notable foes leave loot owed after a fight, sealed caches hide their contents until opened,
and a DM-run companion gets a reminder of its whole kit at the start of its turn."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from engine import views


class LootTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-loot-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Loot Test")
        self.ok("char", "create", "--name", "Kira Vale", "--class", "Fighter", "--species", "Human", "--background", "Soldier",
                "--method", "standard", "--scores", "str=15,dex=13,con=14,int=8,wis=12,cha=10", "--bonus", "str+2,con+1",
                "--skills", "perception,survival", "--equipment", "A", "--bg-equipment", "A",
                "--species-skill", "insight", "--species-feat", "Alert", "--fighting-style", "Defense",
                "--masteries", "longsword,greatsword,javelin", "--languages", "Elvish,Dwarvish")
        self.ok("map", "gen", "wilderness", "--biome", "plains", "--w", "20", "--h", "14", "--id", "field", "--seed", "2", "--show")
        self.ok("place", "kira-vale", "5,5", "--map", "field")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def fail(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertNotEqual(code, 0, f"{args} should have been refused:\n{out}")
        return out

    def test_notable_foe_leaves_loot_owed_until_decided(self):
        self.ok("npc", "add", "bandit-captain", "--at", "6,5", "--map", "field", "--name", "Captain Rhosk", "--side", "enemy")
        self.ok("npc", "add", "bandit", "--at", "7,7", "--map", "field", "--side", "enemy")
        self.ok("combat", "start")
        self.ok("damage", "captain-rhosk", "200", "slashing", "--source", "test")
        gob = next(i for i, e in _cli.game(self.env).entities.items() if e.get("srd") and "bandit" in i and "captain" not in i)
        self.ok("damage", gob, "200", "slashing", "--source", "test")
        out = self.ok("combat", "end")
        self.assertIn("loot owed for Captain Rhosk", out)
        self.assertNotIn("Bandit", out.split("loot owed for")[1].split(".")[0])
        self.assertIn("Loot owed", self.ok("status"))
        self.assertIn("loot still undecided", self.ok("time", "10m", "--reason", "catching breath"))
        self.ok("loot", "body", "captain-rhosk", "--items", "Longsword +1; 2x Potion of Healing", "--coins", "30gp")
        self.assertNotIn("Loot owed", self.ok("status"))
        g = _cli.game(self.env)
        m = g.state["maps"]["field"]
        box = next(c for c in m["containers"] if c.get("sealed"))
        public = views.player_view(g)
        self.assertTrue(views.in_sealed(m, next(f for f in m["floor"] if f.get("in") == box["id"])))
        names = [f["name"] for f in public["maps"]["field"]["floor"]]
        self.assertNotIn("Longsword +1", names)
        self.assertNotIn("coins_cp", next(c for c in public["maps"]["field"]["containers"] if c["id"] == box["id"]))
        self.fail("item", "pickup", "kira-vale", next(f["id"] for f in m["floor"] if f.get("in") == box["id"]))
        out = self.ok("loot", "open", "kira-vale", box["id"])
        self.assertIn("Potion of Healing", out)
        self.assertIn("30", out)
        floor_id = next(f["id"] for f in _cli.game(self.env).state["maps"]["field"]["floor"] if f.get("in") == box["id"])
        out = self.ok("item", "pickup", "kira-vale", floor_id)
        self.assertNotIn("+1", out)  # an unidentified magic item keeps its real name hidden when picked up
        self.assertNotIn("the the", out.lower())

    def test_loot_none_needs_a_reason(self):
        self.ok("npc", "add", "bandit-captain", "--at", "6,5", "--map", "field", "--name", "Captain Rhosk", "--side", "enemy")
        self.ok("combat", "start")
        self.ok("damage", "captain-rhosk", "200", "slashing", "--source", "test")
        self.ok("combat", "end")
        self.fail("loot", "none", "captain-rhosk")
        self.ok("loot", "none", "captain-rhosk", "--reason", "fell in the river with everything")
        self.assertNotIn("Loot owed", self.ok("status"))

    def test_tier_cap_applies_to_caches(self):
        self.fail("loot", "cache", "field", "3,3", "--name", "Old chest", "--items", "Holy Avenger (Longsword)")
        self.ok("loot", "cache", "field", "3,3", "--name", "Old chest", "--items", "Longsword +1", "--lock", "15")

    def test_locked_cache_needs_the_lock_beaten(self):
        self.ok("loot", "cache", "field", "5,6", "--name", "Iron strongbox", "--items", "Ledger=a merchant's ledger",
                "--coins", "140gp", "--lock", "15", "--id", "strongbox")
        self.fail("coins", "kira-vale", "10gp", "--from", "strongbox", "--source", "take")
        self.assertIn("locked (DC 15)", self.fail("loot", "open", "kira-vale", "strongbox"))
        out = self.ok("loot", "open", "kira-vale", "strongbox", "--unlocked", "forced it: Athletics 17 vs DC 15")
        self.assertIn("Ledger", out)
        self.ok("coins", "kira-vale", "140gp", "--from", "strongbox", "--source", "take")

    def test_same_box_id_on_two_maps_uses_the_characters_map(self):
        self.ok("map", "gen", "wilderness", "--biome", "plains", "--w", "20", "--h", "14", "--id", "meadow", "--seed", "3")
        self.ok("loot", "cache", "meadow", "4,4", "--name", "Far chest", "--id", "chest", "--coins", "5gp")
        self.ok("loot", "cache", "field", "5,6", "--name", "Near chest", "--id", "chest", "--coins", "9gp")
        self.ok("loot", "open", "kira-vale", "chest")
        self.ok("coins", "kira-vale", "9gp", "--from", "chest", "--source", "take")
        out = self.ok("loot", "cache", "meadow", "6,6", "--name", "Another")
        self.assertNotIn("box-1", self.ok("loot", "cache", "field", "7,7", "--name", "Yet another"))
        self.assertIn("box-1", out)

    def test_container_names_take_the_right_article(self):
        from engine.mechanics import the
        self.assertEqual(the("Iron chest"), "the Iron chest")
        self.assertEqual(the("The miller's chest"), "the miller's chest")
        self.assertEqual(the("Kira's pack"), "Kira's pack")
        self.assertEqual(the("Captain Rhosk's saddlebags"), "Captain Rhosk's saddlebags")

    def test_companion_turn_lists_its_kit(self):
        self.ok("item", "add", "kira-vale", "Potion of Healing", "--source", "loot: test")
        g = _cli.game(self.env)
        kira = g.get("kira-vale")
        kira["player"] = "DM"
        from engine import loot
        loot.companion_kit(g, kira)
        text = "\n".join(g.out)
        self.assertIn("whole kit", text)
        self.assertIn("Potion of Healing", text)
        self.assertIn("Second Wind", text)


if __name__ == "__main__":
    unittest.main()

