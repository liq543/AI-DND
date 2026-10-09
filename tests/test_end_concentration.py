"""SRD: a caster can end Concentration at any time, no action required (`action <who> end-concentration`)."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class EndConcentrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-conc-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Concentration Test")
        self.ok("char", "create", "--name", "Wren Ashdown", "--class", "Wizard", "--species", "Dwarf", "--background", "Sage",
                "--method", "standard", "--scores", "str=8,dex=13,con=14,int=15,wis=12,cha=10", "--bonus", "con+2,int+1",
                "--skills", "investigation,insight", "--languages", "Dwarvish,Draconic",
                "--mi-cantrips", "light,prestidigitation", "--mi-spell", "shield")
        self.ok("spells", "set", "wren", "--cantrips", "fire bolt,ray of frost,minor illusion",
                "--prepared", "magic missile,sleep,burning hands,mage armor",
                "--spellbook", "magic missile,shield,sleep,burning hands,detect magic,mage armor")
        self.ok("map", "gen", "wilderness", "--biome", "plains", "--w", "20", "--h", "14", "--id", "field", "--seed", "2", "--show")
        self.ok("place", "wren", "5,7", "--map", "field")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def test_end_concentration_any_time(self):
        code, out = _cli.run(self.env, "action", "wren", "end-concentration")
        self.assertEqual(code, 2, out)                      # nothing to end
        self.assertIn("isn't concentrating", out)
        self.ok("cast", "wren", "detect magic", "--ritual")
        self.assertTrue(_cli.game(self.env).get("wren").get("concentration"))
        out = self.ok("action", "wren", "end-concentration")
        self.assertIn("loses Concentration", out)
        self.assertFalse(_cli.game(self.env).get("wren").get("concentration"))

    def test_refund_stat_block_daily_spell(self):
        # a voided innate cast (a stat block's "N/Day Each" spell) can be given back publicly
        self.ok("npc", "add", "mage", "--at", "9,7", "--map", "field", "--name", "Captain Rhosk", "--side", "enemy")
        rid = next(e["id"] for e in _cli.game(self.env).state["entities"].values() if e["name"] == "Captain Rhosk")
        self.ok("cast", rid, "invisibility", "--targets", rid)
        self.assertEqual(_cli.game(self.env).get(rid).get("per_day_used", {}).get("invisibility-day"), 1)
        out = self.ok("spells", "refund", rid, "--spell", "invisibility", "--source", "the cast was voided")
        self.assertIn("daily cast", out)
        self.assertEqual(_cli.game(self.env).get(rid).get("per_day_used", {}).get("invisibility-day"), 0)


if __name__ == "__main__":
    unittest.main()
