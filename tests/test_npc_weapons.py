"""NPCs can fight with a real weapon from their inventory (e.g. a captain handed a +1 sword), not only stat-block actions."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from engine import mechanics as M


class NpcWeaponTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-npcweap-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "NPC Weapon Test")
        self.ok("map", "gen", "wilderness", "--biome", "plains", "--w", "20", "--h", "14", "--id", "field", "--seed", "2", "--show")
        self.ok("npc", "add", "bandit", "--at", "5,5", "--map", "field", "--name", "Captain Rhosk", "--side", "ally")
        self.ok("item", "add", "captain-rhosk", "Longsword +1", "--source", "gift: test", "--identified")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def test_equipped_magic_sword_becomes_an_attack(self):
        rhosk = _cli.game(self.env).get("captain-rhosk")
        self.assertIsNone(M.held_weapon_action(rhosk, "longsword +1"))   # carried, not in hand
        sword = next(i["id"] for i in rhosk["inventory"] if "longsword" in i["name"].lower())
        self.ok("item", "equip", "captain-rhosk", sword)
        act = M.monster_action(_cli.game(self.env).get("captain-rhosk"), "longsword +1")
        self.assertEqual(act["bonus"], 3)                  # Str +0, Proficiency +2, +1 sword
        self.assertEqual(act["damage"][0]["dice"], "1d8+1")


if __name__ == "__main__":
    unittest.main()
