"""SRD Knocking Out a Creature: 1 HP and Unconscious; it starts a Short Rest, at the end of which the condition ends,
or sooner if it regains any HP."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class KnockoutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-ko-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Knockout Test")
        self.ok("npc", "add", "commoner", "--name", "Oswin Hale", "--side", "enemy")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def knock_out(self):
        import engine.mechanics as M
        g = _cli.game(self.env)
        M.apply_damage(g, g.get("oswin-hale"), [[50, "bludgeoning"]], source="fist", melee_within_5=True, knockout=True)
        g.commit()

    def oswin(self):
        g = _cli.game(self.env)
        e = g.get("oswin-hale")
        return e["hp"], {c["name"] for c in e.get("conditions", [])}, e.get("dead")

    def test_knockout_leaves_one_hp_and_unconscious(self):
        self.knock_out()
        hp, conds, dead = self.oswin()
        self.assertEqual(hp, 1)
        self.assertIn("unconscious", conds)
        self.assertFalse(dead)

    def test_wakes_after_a_short_rest(self):
        self.knock_out()
        self.ok("time", "30m")
        self.assertIn("unconscious", self.oswin()[1])
        out = self.ok("time", "30m")
        self.assertIn("comes round", out)
        self.assertNotIn("unconscious", self.oswin()[1])

    def test_regaining_hp_ends_it_early(self):
        self.knock_out()
        self.ok("heal", "oswin-hale", "1", "--source", "first aid")
        hp, conds, _ = self.oswin()
        self.assertEqual(hp, 2)
        self.assertNotIn("unconscious", conds)


if __name__ == "__main__":
    unittest.main()
