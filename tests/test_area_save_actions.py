"""Save-based monster actions with an area (rules/monsters, e.g. a rakshasa's Baleful Command): several targets in one
use, every condition in "the X and Y conditions", and "until the start of the <monster>'s next turn" ending on the
monster's turn, not the target's."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class AreaSaveActionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-area-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Area Save Test")
        self.ok("map", "gen", "wilderness", "--biome", "plains", "--w", "20", "--h", "14", "--id", "field", "--seed", "2", "--show")
        self.ok("npc", "add", "rakshasa", "--at", "9,5", "--map", "field", "--name", "Tiger Lord", "--side", "enemy")
        self.ok("npc", "add", "commoner", "--at", "10,5", "--map", "field", "--name", "Oswin Hale", "--side", "ally")
        self.ok("npc", "add", "commoner", "--at", "9,7", "--map", "field", "--name", "Captain Rhosk", "--side", "ally")
        self.ok("combat", "start")
        while "Tiger Lord" not in self.ok("combat", "status").split("➤")[1].split("\n")[0]:
            self.ok("combat", "next")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def conds(self, eid):
        return {c["name"]: c for c in _cli.game(self.env).get(eid).get("conditions", [])}

    def test_two_targets_both_conditions_and_duration(self):
        out = self.ok("attack", "tiger-lord", "oswin-hale,captain-rhosk", "baleful command")
        self.assertEqual(out.count("WIS save DC 18"), 2)
        failed = [e for e in ("oswin-hale", "captain-rhosk")
                  if _cli.game(self.env).get(e)["hp"] <= 0 or "frightened" in self.conds(e)]
        for e in failed:
            if _cli.game(self.env).get(e)["hp"] > 0:
                c = self.conds(e)
                self.assertIn("incapacitated", c)
                self.assertEqual(c["frightened"].get("until"), "start of tiger-lord's next turn")
        # back round to the rakshasa: whatever it imposed ends
        self.ok("combat", "next")
        while "Tiger Lord" not in self.ok("combat", "status").split("➤")[1].split("\n")[0]:
            self.ok("combat", "next")
        for e in ("oswin-hale", "captain-rhosk"):
            if _cli.game(self.env).get(e)["hp"] > 0:
                self.assertNotIn("frightened", self.conds(e))
                self.assertNotIn("incapacitated", self.conds(e))


if __name__ == "__main__":
    unittest.main()
