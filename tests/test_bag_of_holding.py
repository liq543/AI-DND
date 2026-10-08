"""Bag of Holding: carried items go inside it (500 lb), a bag can't go into another bag, and items come back out."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class BagOfHoldingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-bag-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Bag Test", "--set", "start_level=5")
        self.ok("char", "create", "--name", "Kira Vale", "--class", "Rogue", "--species", "Human", "--background", "Criminal",
                "--method", "standard", "--scores", "str=8,dex=15,con=14,int=10,wis=12,cha=13", "--bonus", "dex+1,con+2",
                "--skills", "athletics,perception,deception,acrobatics", "--species-skill", "insight",
                "--species-feat", "Skilled", "--skilled", "persuasion,history,Disguise Kit",
                "--languages", "Elvish,Halfling", "--expertise", "stealth,sleight of hand", "--masteries", "shortsword,dagger")
        self.ok("item", "add", "kira-vale", "Bag of Holding", "--source", "loot: test")
        self.ok("item", "add", "kira-vale", "Plate Armor", "--source", "loot: test")
        self.ok("item", "add", "kira-vale", "Spear", "--qty", "10", "--source", "loot: test")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def inv(self):
        return _cli.game(self.env).get("kira-vale")["inventory"]

    def ids(self, name):
        return [i for i in self.inv() if i["name"] == name]

    def test_items_go_in_and_come_out(self):
        bag = self.ids("Bag of Holding")[0]["id"]
        plate = self.ids("Plate Armor")[0]["id"]
        self.ok("item", "stash", "kira-vale", plate, "--to", bag)
        self.assertEqual(self.ids("Plate Armor")[0].get("in"), bag)
        self.assertIn("(in Bag of Holding)", self.ok("char", "show", "kira-vale"))
        self.ok("item", "unbag", "kira-vale", plate)
        self.assertFalse(self.ids("Plate Armor")[0].get("in"))

    def test_part_of_a_stack(self):
        bag = self.ids("Bag of Holding")[0]["id"]
        spear = self.ids("Spear")[0]["id"]
        self.assertIn("about 12 of 500 lb", self.ok("item", "stash", "kira-vale", spear, "--to", bag, "--qty", "4"))
        spears = self.ids("Spear")
        self.assertEqual(sorted((s.get("qty"), bool(s.get("in"))) for s in spears), [(4, True), (6, False)])

    def test_no_bag_in_a_bag(self):
        self.ok("item", "add", "kira-vale", "Bag of Holding", "--source", "loot: second bag")
        bags = self.ids("Bag of Holding")
        code, out = _cli.run(self.env, "item", "stash", "kira-vale", bags[1]["id"], "--to", bags[0]["id"])
        self.assertNotEqual(code, 0)
        self.assertIn("Astral", out)


if __name__ == "__main__":
    unittest.main()
