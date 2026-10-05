"""The agenda: scheduled events the engine announces when their time comes, with optional automatic payments."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class AgendaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-agenda-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Agenda Test")
        self.ok("map", "gen", "wilderness", "--biome", "plains", "--w", "20", "--h", "14", "--id", "hall", "--seed", "2", "--show")
        self.ok("map", "container", "hall", "6,6", "--name", "Iron strongbox", "--id", "vault")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def vault(self):
        from engine import core
        camp = next(p for p in (self.tmp / "campaigns").iterdir() if p.is_dir() and not p.name.startswith("_"))
        return core.replay(core.Store(camp).load())["maps"]["hall"]["containers"][0].get("coins_cp", 0)

    def test_announced_and_auto_paid_when_due(self):
        self.ok("agenda", "add", "--in", "2d", "--text", "The steward pays in the cart's takings", "--pay", "650gp",
                "--to", "vault", "--auto")
        self.ok("agenda", "add", "--at", "Day 1 20:00", "--text", "A gem buyer arrives with scales")
        self.assertIn("gem buyer", self.ok("agenda", "list"))
        out = self.ok("time", "1d")
        self.assertIn("Due", out)
        self.assertIn("gem buyer", out)
        self.assertEqual(self.vault(), 0)
        out = self.ok("time", "1d")
        self.assertIn("Paid 650 GP", out)
        self.assertEqual(self.vault(), 65000)

    def test_dice_payment_and_done(self):
        self.ok("agenda", "add", "--in", "1h", "--text", "Sales come back", "--pay", "600+2d40", "--to", "vault", "--auto")
        self.ok("time", "2h")
        self.assertGreaterEqual(self.vault(), 60200)
        self.ok("agenda", "add", "--in", "1h", "--text", "Wages due", "--pay=-10gp", "--to", "vault")
        self.ok("time", "2h")   # announced, not auto-paid
        self.ok("agenda", "done", "a2", "--note", "paid by hand")
        self.assertNotIn("Wages due", self.ok("agenda", "list"))


if __name__ == "__main__":
    unittest.main()
