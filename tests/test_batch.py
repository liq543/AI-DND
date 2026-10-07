"""Speed without loosening the rules: `engine batch`, the verified-prefix record, and the live table catching up.

A batch runs many DM commands in one process (one load, one save, one table update). Every step goes through the
same handlers and rules as on its own; a refused step stops the batch there, and nothing is chained past it.
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import _cli  # noqa: E402  (in-process CLI runner)


class BatchAndSpeedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="dnd-batch-"))
        cls.env = {**os.environ, "DND_CAMPAIGNS": str(cls.tmp / "campaigns"), "DND_ENGINE_HOME": str(cls.tmp / "home"),
                   "PYTHONIOENCODING": "utf-8"}
        cls.ok("campaign", "new", "Batch Realm")
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
        code, out = _cli.run(cls.env, *args)
        assert code == 0, f"{args} failed:\n{out}"
        return out

    def batch(self, text, *flags):
        path = self.tmp / "steps.txt"
        path.write_text(text, encoding="utf-8")
        return _cli.run(self.env, "batch", str(path), *flags)

    def count(self):
        return len(_cli.game(self.env).events)

    # ------------------------------------------------------------------ batch
    def test_batch_runs_every_step_and_saves_once(self):
        before = self.count()
        code, out = self.batch('# comments and blank lines are skipped\n\n'
                               'say "Rain on the slates."\n'
                               'py -m engine say --as "Kira Vale" "Wet again."\n'
                               'time 5m \\\n  --reason "waiting out the shower"\n')
        self.assertEqual(code, 0, out)
        self.assertIn("3 of 3 step(s) done", out)
        g = _cli.game(self.env)
        texts = [e["data"].get("text") for e in g.events[before:] if e["type"] == "feed"]
        self.assertEqual(texts[:2], ["Rain on the slates.", "“Wet again.”"])
        self.assertTrue(all(e["seq"] == i for i, e in enumerate(g.events, 1)))   # one signed, unbroken chain
        self.ok("verify")

    def test_a_refused_step_stops_the_batch_and_keeps_the_steps_before(self):
        before = self.count()
        code, out = self.batch('say "Before the refusal."\n'
                               'coins kira -999999gp --source "spent: more than anyone has"\n'
                               'say "Never said."\n')
        self.assertEqual(code, 2, out)
        self.assertIn("Stopped at step 2", out)
        self.assertIn("not run 3", out)
        texts = [e["data"].get("text") for e in _cli.game(self.env).events[before:] if e["type"] == "feed"]
        self.assertIn("Before the refusal.", texts)
        self.assertNotIn("Never said.", texts)

    def test_atomic_keeps_nothing_when_a_step_is_refused(self):
        before = self.count()
        code, out = self.batch('say "Atomic one."\ncoins kira -999999gp --source "spent: too much"\n', "--atomic")
        self.assertEqual(code, 2, out)
        self.assertEqual(self.count(), before)

    def test_dry_run_saves_nothing_and_never_previews_dice(self):
        before = self.count()
        code, out = self.batch('say "Only checking."\n', "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("nothing was saved", out)
        code, out = self.batch('roll 1d20 --purpose "a peek"\n', "--dry-run")
        self.assertEqual(code, 2, out)
        self.assertIn("dice", out)
        self.assertEqual(self.count(), before)

    def test_a_bad_line_runs_nothing(self):
        before = self.count()
        code, out = self.batch('say "Fine."\nnot-a-command at all\n')
        self.assertEqual(code, 2, out)
        self.assertIn("line 2", out)
        self.assertEqual(self.count(), before)
        code, out = self.batch('say "Fine."\nquickload somewhere\n')
        self.assertEqual(code, 2, out)
        self.assertIn("can't run inside a batch", out)
        self.assertEqual(self.count(), before)

    def test_a_refused_step_leaves_no_trace_in_the_state(self):
        g = _cli.game(self.env)
        gp = g.get("kira")["coins"].get("gp", 0)
        code, out = self.batch('coins kira +5gp --source "found: a test purse"\n'
                               'coins kira -999999gp --source "spent: too much"\n')
        self.assertEqual(code, 2, out)
        self.assertEqual(_cli.game(self.env).get("kira")["coins"].get("gp", 0), gp + 5)

    # ------------------------------------------------------------------ verified prefix and catching up
    def test_tampering_inside_the_verified_prefix_is_still_caught(self):
        self.ok("say", "A line to verify past.")
        g = _cli.game(self.env)
        path = Path(g.dir) / "engine" / "events.jsonl"
        record = Path(g.dir) / "engine" / ".verified.json"
        self.assertTrue(record.exists())
        original = path.read_text(encoding="utf-8")
        try:
            path.write_text(original.replace("A line to verify past.", "A line to verify pest.", 1), encoding="utf-8")
            code, out = _cli.run(self.env, "status")
            self.assertEqual(code, 3, out)
            self.assertIn("TAMPERING", out)
        finally:
            path.write_text(original, encoding="utf-8")
        self.ok("verify")

    def test_a_forged_verified_record_is_ignored(self):
        g = _cli.game(self.env)
        record = Path(g.dir) / "engine" / ".verified.json"
        rec = json.loads(record.read_text(encoding="utf-8"))
        try:
            record.write_text(json.dumps({**rec, "count": rec["count"] + 5}), encoding="utf-8")   # mac no longer matches
            self.assertEqual(len(_cli.game(self.env).events), rec["count"])
        finally:
            record.write_text(json.dumps(rec), encoding="utf-8")

    # ------------------------------------------------------------------ one-line shortcuts
    def test_scene_sets_lighting_and_weather_with_the_banner(self):
        self.ok("scene", "The crypt at night", "--desc", "cold", "--map", "arena", "--lighting", "dark", "--ambient", "fog")
        g = _cli.game(self.env)
        self.assertEqual(g.state["maps"]["arena"].get("lighting"), "dark")
        self.assertEqual(g.state["view"]["anim"]["ambient"], "fog")
        self.assertEqual(g.state["view"]["map"], "arena")

    def test_npc_add_describes_and_aligns_in_one_line(self):
        out = self.ok("npc", "add", "commoner", "--at", "2,2", "--map", "arena", "--side", "neutral", "--name", "Oswin Hale",
                      "--desc", "A bald innkeeper in a leather apron.", "--align", "lawful neutral")
        self.assertIn("Lawful Neutral", out)
        e = _cli.game(self.env).get("oswin-hale")
        self.assertEqual(e["appearance"], "A bald innkeeper in a leather apron.")
        self.assertEqual(e["alignment"], "Lawful Neutral")
        code, out = _cli.run(self.env, "npc", "add", "commoner", "--name", "Wrong", "--align", "sort of nice")
        self.assertEqual(code, 2, out)

    def test_the_table_catches_up_on_new_events_only(self):
        g = _cli.game(self.env)
        n = len(g.events)
        self.ok("say", "Something new for the table.")
        fresh = g.caught_up()
        self.assertIsNotNone(fresh)
        self.assertEqual(len(fresh.events), n + 1)
        self.assertEqual(len(g.events), n)            # the old copy is left alone for readers on other threads
        self.assertEqual(fresh.state["seq"], _cli.game(self.env).state["seq"])


if __name__ == "__main__":
    unittest.main()
