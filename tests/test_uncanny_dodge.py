"""Rogue Uncanny Dodge: after an attacker's hit, the Reaction halves that attack's damage (round down)."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class UncannyDodgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-ud-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Dodge Test", "--set", "start_level=5")
        self.ok("char", "create", "--name", "Kira Vale", "--class", "Rogue", "--species", "Human", "--background", "Criminal",
                "--method", "standard", "--scores", "str=8,dex=15,con=14,int=10,wis=12,cha=13", "--bonus", "dex+1,con+2",
                "--skills", "athletics,perception,deception,acrobatics", "--species-skill", "insight",
                "--species-feat", "Skilled", "--skilled", "persuasion,history,Disguise Kit",
                "--languages", "Elvish,Halfling", "--expertise", "stealth,sleight of hand", "--masteries", "shortsword,dagger")
        show = self.ok("char", "show", "kira-vale")
        for _ in range(5):
            if "Rogue 5" in show:
                break
            lvl = int(show.split("**Rogue ")[1].split("**")[0])
            self.ok("char", "levelup", "kira-vale", *(["--subclass", "Thief"] if lvl == 2 else ["--feat", "Ability Score Improvement", "--asi", "dex+2"] if lvl == 3 else []), "--hp", "avg")
            show = self.ok("char", "show", "kira-vale")
        self.ok("map", "gen", "wilderness", "--biome", "plains", "--w", "20", "--h", "14", "--id", "field", "--seed", "2", "--show")
        self.ok("place", "kira-vale", "5,5", "--map", "field")
        self.ok("npc", "add", "bandit", "--at", "6,5", "--map", "field", "--name", "Snag")
        self.ok("combat", "start")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def hp(self):
        return _cli.game(self.env).get("kira-vale")["hp"]

    def test_halves_the_hit(self):
        import engine.mechanics as M
        before = self.hp()
        g = _cli.game(self.env)
        M.apply_damage(g, g.get("kira-vale"), [[9, "slashing"]], source="scimitar", attacker=g.get("snag"))
        g.commit()
        self.assertEqual(self.hp(), before - 9)
        self.assertIn("halved to 4", self.ok("feature", "kira-vale", "uncanny dodge"))
        self.assertEqual(self.hp(), before - 4)
        code, out = _cli.run(self.env, "feature", "kira-vale", "uncanny dodge")
        self.assertNotEqual(code, 0)   # no second dodge of the same hit (and the Reaction is spent)

    def test_needs_a_hit(self):
        code, out = _cli.run(self.env, "feature", "kira-vale", "uncanny dodge")
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
