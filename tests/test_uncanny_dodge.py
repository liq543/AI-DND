"""Rogue Uncanny Dodge: after an attacker's hit, the Reaction halves that attack's damage (round down).
Also: Vicious Mockery's failed save gives Disadvantage on the target's next attack roll, used up by that roll."""
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

    def test_answers_a_hand_rolled_attack(self):
        # a spell attack the engine leaves to the DM (rolled by hand) is recorded with `damage --attacker`
        before = self.hp()
        self.ok("damage", "kira-vale", "8", "force", "--source", "Spiritual Weapon", "--attacker", "snag")
        self.assertIn("halved to 4", self.ok("feature", "kira-vale", "uncanny dodge"))
        self.assertEqual(self.hp(), before - 4)

    def test_readied_spell_released_off_turn(self):
        # a spell readied with the Ready action is released with the Reaction when the trigger comes
        import engine.mechanics as M
        from engine.core import RuleError
        self.ok("npc", "add", "cultist-fanatic", "--at", "8,8", "--map", "field", "--name", "Brother Vell")
        self.ok("combat", "add", "brother-vell")
        while _cli.game(self.env).state["combat"]["order"][_cli.game(self.env).state["combat"]["turn"]]["id"] == "brother-vell":
            self.ok("combat", "next")
        g = _cli.game(self.env)
        with self.assertRaises(RuleError):                             # nothing readied: off-turn casting is refused
            M.cast(g, "brother-vell", "light", targets=(), readied=True)
        M.set_economy(g, "brother-vell", action_used=True, action_used_for="ready")
        M.cast(g, "brother-vell", "light", targets=(), readied=True)    # released as the Reaction
        self.assertTrue(M.economy(g, "brother-vell").get("reaction_used"))

    def test_needs_a_hit(self):
        code, out = _cli.run(self.env, "feature", "kira-vale", "uncanny dodge")
        self.assertNotEqual(code, 0)

    def test_mockery_disadvantage_spent_on_next_attack(self):
        import engine.mechanics as M
        g = _cli.game(self.env)
        M.add_condition(g, g.get("snag"), "mocked", source="Vicious Mockery", until="end of its next turn", quiet=True)
        g.commit()
        g = _cli.game(self.env)
        adv, dis = M.attack_modes(g, g.get("snag"), g.get("kira-vale"), False, 5)
        self.assertIn("Vicious Mockery", dis)
        while _cli.game(self.env).state["combat"]["order"][_cli.game(self.env).state["combat"]["turn"]]["id"] != "snag":
            self.ok("combat", "next")
        out = self.ok("attack", "snag", "kira-vale", "scimitar")
        self.assertIn("Disadvantage", out)
        g = _cli.game(self.env)
        self.assertNotIn("mocked", M.condition_names(g.get("snag")))


if __name__ == "__main__":
    unittest.main()
