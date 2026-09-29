"""Opportunity attacks in player-roll (viewer) mode: the attack is requested first and rolled later, when the
target has already moved away. The opportunity-attack window must stay open until the Roll resolves.

Run:  python -m unittest discover -s tests -v
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class OpportunityAttackViewerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-oa-"))
        cls.env = {**os.environ, "DND_CAMPAIGNS": str(cls.tmp / "campaigns"), "DND_ENGINE_HOME": str(cls.tmp / "home"),
                   "PYTHONIOENCODING": "utf-8"}
        cls.ok("campaign", "new", "OA Test")
        cls.ok("char", "create", "--name", "Kira Vale", "--class", "Fighter", "--species", "Human", "--background", "Soldier",
               "--method", "standard", "--scores", "str=15,dex=13,con=14,int=8,wis=12,cha=10", "--bonus", "str+2,con+1",
               "--skills", "perception,survival", "--languages", "Elvish,Dwarvish", "--species-skill", "insight",
               "--species-feat", "Alert", "--fighting-style", "Defense", "--masteries", "longsword,javelin,greatsword")
        cls.ok("map", "gen", "arena", "--preset", "crypt", "--seed", "3", "--id", "arena", "--show")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def ok(cls, *args):
        p = subprocess.run([sys.executable, "-m", "engine", *args], cwd=ROOT, env=cls.env, capture_output=True,
                           text=True, encoding="utf-8")
        out = p.stdout + p.stderr
        assert p.returncode == 0, f"{args} failed:\n{out}"
        return out

    def state(self):
        from importlib import reload
        os.environ.update({k: v for k, v in self.env.items() if k.startswith("DND_")})
        import engine.store as st
        reload(st)
        import engine.core as core
        reload(core)
        return core.Game(st.active_dir())

    def test_requested_opportunity_attack_resolves_after_target_left(self):
        self.ok("place", "kira", "5,5", "--map", "arena")
        self.ok("npc", "add", "goblin-warrior", "--name", "Snag", "--at", "6,5", "--map", "arena")
        self.ok("item", "equip", "kira", "greatsword-1")
        self.ok("combat", "start")
        try:
            # Snag ends up out of reach, and Kira has the opportunity-attack window a move warning would open
            self.ok("move", "snag", "--path", "7,5 8,5 9,5 10,5", "--force", "test: stepped away")
            self.ok("combat", "oa-window", "kira,snag", "--reason", "test: Snag left Kira's reach")
            self.ok("set", "player_rolls=viewer")
            out = self.ok("attack", "kira", "snag", "greatsword", "--reaction")
            self.assertIn("request", out)
            rid = next(iter(self.state().state["requests"]))
            out = self.ok("request", "roll", rid)   # used to fail: "out of Greatsword's 5 ft reach"
            self.assertIn("attacks Snag", out)
            g = self.state()
            from engine import mechanics as M
            self.assertIsNone(M.economy(g, "kira").get("oa_window"))   # the window closes once the attack resolves
        finally:
            self.ok("set", "player_rolls=auto")
            self.ok("combat", "end")


if __name__ == "__main__":
    unittest.main()
