"""Quicksave / quickload: a quickload restores the game exactly (log, state, notes), and the log still verifies."""
import _cli  # noqa: E402  (in-process CLI runner)
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class QuicksaveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-qs-"))
        cls.env = {**os.environ, "DND_CAMPAIGNS": str(cls.tmp / "campaigns"), "DND_ENGINE_HOME": str(cls.tmp / "home"),
                   "PYTHONIOENCODING": "utf-8"}
        cls.ok("campaign", "new", "Save Test")
        cls.ok("npc", "add", "goblin-warrior", "--name", "Snag", "--side", "enemy")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def ok(cls, *args):
        code, out = _cli.run(cls.env, *args)
        assert code == 0, f"{args} failed:\n{out}"
        return out

    def camp(self):
        return next(p for p in (self.tmp / "campaigns").iterdir() if p.is_dir() and not p.name.startswith("_"))

    def state(self):
        from engine import core
        return core.replay(core.Store(self.camp()).load())

    def test_quickload_restores_everything_exactly(self):
        camp = self.camp()
        (camp / "npcs.md").write_text("before\n", encoding="utf-8")
        self.ok("quicksave", "before-fight", "--label", "just before the fight")
        before_log = (camp / "engine" / "events.jsonl").read_text(encoding="utf-8")
        before_state = json.dumps(self.state(), sort_keys=True)
        # the future: rolls, damage, a new note
        self.ok("roll", "1d20", "--purpose", "a roll that should vanish")
        self.ok("damage", "snag", "5", "piercing", "--source", "a stab")
        (camp / "npcs.md").write_text("after\n", encoding="utf-8")
        (camp / "log").mkdir(exist_ok=True)
        (camp / "log" / "future.md").write_text("never happened\n", encoding="utf-8")
        self.assertNotEqual(json.dumps(self.state(), sort_keys=True), before_state)
        out = self.ok("quickload", "before-fight")
        self.assertIn("Quickloaded", out)
        self.assertEqual((camp / "engine" / "events.jsonl").read_text(encoding="utf-8"), before_log)
        self.assertEqual(json.dumps(self.state(), sort_keys=True), before_state)
        self.assertEqual((camp / "npcs.md").read_text(encoding="utf-8"), "before\n")
        self.assertFalse((camp / "log" / "future.md").exists())
        self.ok("verify")                      # the truncated log is still a valid signed chain
        self.ok("roll", "1d20", "--purpose", "play goes on after a quickload")
        self.ok("quickload")                   # loading the same (latest) slot again works too
        self.assertEqual(json.dumps(self.state(), sort_keys=True), before_state)
        backups = list((camp / "engine" / "backups").glob("*.jsonl"))
        self.assertEqual([p.name for p in backups], ["latest.jsonl"])   # no backup holds the discarded future

    def test_save_at_an_earlier_event_and_list(self):
        from engine import core
        n = len(core.Store(self.camp()).load())
        self.ok("roll", "1d6", "--purpose", "later")
        self.ok("quicksave", "earlier", "--at-seq", str(n))
        self.assertIn("earlier", self.ok("quicksave", "list"))
        self.ok("quickload", "earlier")
        self.assertEqual(len(core.Store(self.camp()).load()), n)
        code, out = _cli.run(self.env, "quickload", "nope")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
