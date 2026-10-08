"""combat reset-turn <id>: replay an earlier creature's turn this round after the DM played it wrong."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class ResetTurnRewindTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-rewind-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Rewind Test")
        self.ok("map", "gen", "wilderness", "--biome", "plains", "--w", "20", "--h", "14", "--id", "field", "--seed", "2", "--show")
        for i, n in enumerate(("Anna", "Bert", "Cleo")):
            self.ok("npc", "add", "bandit", "--at", f"{3 + i * 3},5", "--map", "field", "--name", n)
        self.ok("combat", "start")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def test_rewinds_to_an_earlier_creature(self):
        g = _cli.game(self.env)
        first = g.state["combat"]["order"][0]["id"]
        self.ok("action", first, "dodge")
        self.ok("combat", "next")
        second = _cli.game(self.env).state["combat"]["order"][1]["id"]
        self.ok("action", second, "dodge")
        self.ok("combat", "reset-turn", first, "--reason", "its turn was played wrong")
        g = _cli.game(self.env)
        self.assertEqual(g.state["combat"]["order"][g.state["combat"]["turn"]]["id"], first)
        self.assertFalse(g.state["combat"]["economy"].get(first))
        self.assertFalse(g.state["combat"]["economy"].get(second))

    def test_cannot_rewind_to_a_creature_still_to_act(self):
        g = _cli.game(self.env)
        last = g.state["combat"]["order"][-1]["id"]
        code, out = _cli.run(self.env, "combat", "reset-turn", last, "--reason", "nothing to replay here")
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
