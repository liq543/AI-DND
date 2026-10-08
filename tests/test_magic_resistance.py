"""Magic Resistance (Advantage on saves against spells and magical effects) and Greater Magic Resistance (automatic
success on those saves; spell attack rolls automatically miss), as in rules/monsters (e.g. archmage, rakshasa)."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class MagicResistanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-mr-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Magic Resistance Test")
        self.ok("map", "gen", "wilderness", "--biome", "plains", "--w", "20", "--h", "14", "--id", "field", "--seed", "2", "--show")
        self.ok("npc", "add", "rakshasa", "--at", "9,5", "--map", "field", "--name", "Tiger Lord", "--side", "enemy")
        self.ok("npc", "add", "archmage", "--at", "12,5", "--map", "field", "--name", "Old Mage", "--side", "enemy")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def test_greater_magic_resistance_auto_succeeds_on_spell_saves(self):
        out = self.ok("save", "tiger-lord", "wis", "--dc", "30", "--spell", "--source", "a spell")
        self.assertIn("automatically succeeds", out)
        self.assertIn("Greater Magic Resistance", out)

    def test_greater_magic_resistance_does_not_cover_mundane_saves(self):
        out = self.ok("save", "tiger-lord", "con", "--dc", "10", "--source", "a fall")
        self.assertNotIn("automatically succeeds", out)

    def test_plain_magic_resistance_gives_advantage(self):
        out = self.ok("save", "old-mage", "wis", "--dc", "10", "--spell", "--source", "a spell")
        self.assertIn("Magic Resistance", out)
        self.assertNotIn("automatically succeeds", out)


if __name__ == "__main__":
    unittest.main()
