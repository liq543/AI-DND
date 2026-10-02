"""Sagas: a campaign can be the next chapter of an earlier one, and characters and companions carry over with their
sheets exactly as the earlier chapter's signed log has them."""
import _cli  # noqa: E402  (in-process CLI runner)
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class SagaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-saga-"))
        cls.env = {**os.environ, "DND_CAMPAIGNS": str(cls.tmp / "campaigns"), "DND_ENGINE_HOME": str(cls.tmp / "home"),
                   "PYTHONIOENCODING": "utf-8"}
        cls.ok("campaign", "new", "First Chapter", "--set", "start_level=3")
        cls.ok("char", "create", "--name", "Kira Vale", "--class", "Fighter", "--species", "Human", "--background", "Soldier",
               "--method", "standard", "--scores", "str=15,dex=13,con=14,int=8,wis=12,cha=10", "--bonus", "str+2,con+1",
               "--skills", "perception,survival", "--languages", "Elvish,Dwarvish", "--species-skill", "insight",
               "--species-feat", "Alert", "--fighting-style", "Defense", "--masteries", "longsword,javelin,greatsword")
        cls.ok("item", "add", "kira", "Silver locket", "--custom", "Her mother's locket, a lock of red hair inside.",
               "--source", "loot: the bandit captain")
        cls.ok("coins", "kira", "+40gp", "--source", "loot: the bandit captain's purse")
        cls.ok("char", "bio", "kira", "appearance", "Tall and red-braided, with a scar through one eyebrow.")
        cls.ok("map", "gen", "arena", "--preset", "crypt", "--seed", "3", "--id", "camp", "--show")
        cls.ok("place", "kira", "3,3", "--map", "camp")
        cls.ok("npc", "describe", "kira", "--text", "Disguised as a travelling nun, hood up.")
        cls.ok("char", "create", "--name", "Oren Vell", "--class", "Wizard", "--species", "Elf", "--background", "Sage",
               "--method", "pointbuy", "--scores", "str=8,dex=14,con=14,int=15,wis=12,cha=8", "--bonus", "int+2,con+1",
               "--skills", "investigation,medicine", "--languages", "Elvish,Draconic", "--species-skill", "perception",
               "--mi-cantrips", "light,mage hand", "--mi-spell", "shield")
        cls.ok("spells", "set", "oren-vell", "--cantrips", "fire bolt,ray of frost,minor illusion",
               "--prepared", "magic missile,sleep,burning hands,mage armor",
               "--spellbook", "magic missile,shield,sleep,burning hands,detect magic,mage armor")
        cls.ok("place", "oren-vell", "5,5", "--map", "camp")
        cls.ok("cast", "oren-vell", "shield", "--free", "Magic Initiate")      # the once-a-day free cast, spent
        cls.ok("cast", "oren-vell", "mage armor", "--targets", "oren-vell")    # and a level 1 slot
        cls.ok("npc", "add", "commoner", "--name", "Wren Ashdown", "--at", "2,2")
        cls.ok("npc", "describe", "wren-ashdown", "--text", "A freckled stable-girl with a crooked grin")
        cls.ok("npc", "add", "bandit", "--name", "Captain Rhosk", "--at", "4,4")
        cls.ok("damage", "kira", "5", "slashing", "--source", "a lucky cut")
        cls.ok("damage", "captain-rhosk", "50", "slashing", "--source", "Kira's longsword")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def run_cli(cls, *args):
        return _cli.run(cls.env, *args)

    @classmethod
    def ok(cls, *args):
        code, out = cls.run_cli(*args)
        assert code == 0, f"{args} failed:\n{out}"
        return out

    def rule(self, *args, contains=None):
        code, out = self.run_cli(*args)
        self.assertEqual(code, 2, f"expected a rule refusal for {args}, got:\n{out}")
        if contains:
            self.assertIn(contains, out)
        return out

    def state(self, slug):
        from engine import core
        return core.replay(core.Store(self.tmp / "campaigns" / slug).load())

    def test_next_chapter_carries_the_crew_over(self):
        before = self.state("first-chapter")["entities"]["kira"]
        self.ok("campaign", "new", "Second Chapter", "--from", "first-chapter", "--set", "start_level=6")
        st = self.state("second-chapter")
        self.assertEqual(st["campaign"]["chapter"], 2)
        self.assertEqual(st["campaign"]["previous"], "first-chapter")
        self.assertEqual(st["campaign"]["saga"], "First Chapter")
        self.assertTrue((self.tmp / "campaigns" / "second-chapter" / "chronicle.md").exists())
        self.assertIn("campaigns/first-chapter/", (self.tmp / "campaigns" / "second-chapter" / "chronicle.md").read_text(encoding="utf-8"))

        out = self.ok("char", "import", "kira")
        self.assertIn("carries over from First Chapter", out)
        kira = self.state("second-chapter")["entities"]["kira"]
        # the sheet is the same sheet: items, coins, classes, features
        self.assertEqual([i["name"] for i in kira["inventory"]], [i["name"] for i in before["inventory"]])
        self.assertEqual(kira["coins"], before["coins"])
        self.assertEqual(kira["classes"], before["classes"])
        self.assertEqual(kira["chronicle"]["from"], "first-chapter")
        # fresh from the road: rested, and off the old map
        self.assertEqual(kira["hp"], kira["hp_max"])
        self.assertNotIn("token", kira)
        # the last scene's disguise stays behind; her lasting description comes along
        self.assertNotIn("appearance", kira)
        self.assertEqual(kira["bio"]["appearance"], "Tall and red-braided, with a scar through one eyebrow.")
        self.assertIn("stayed behind", out)
        # the chapter starts at level 6: XP comes up to the floor and the level-ups follow the normal rules
        self.assertEqual(kira["xp"], 14000)
        self.ok("char", "levelup", "kira", "--subclass", "Champion")
        # a companion carries over too, with the look the players know
        out = self.ok("char", "import", "wren-ashdown")
        self.assertIn("still fits", out)
        wren = self.state("second-chapter")["entities"]["wren-ashdown"]
        self.assertEqual(wren["appearance"], "A freckled stable-girl with a crooked grin")
        # the time between chapters is a Long Rest: slots and once-a-day free casts come back
        before_oren = self.state("first-chapter")["entities"]["oren"]
        self.assertTrue(any(x.get("free_used") for x in before_oren["granted_spells"]))
        self.assertTrue(before_oren["slots_used"])
        self.ok("char", "import", "oren")
        oren = self.state("second-chapter")["entities"]["oren"]
        self.assertFalse(any(x.get("free_used") for x in oren["granted_spells"]))
        self.assertEqual(oren["slots_used"], {})
        # no doubles, and the dead stay dead
        self.rule("char", "import", "kira", contains="already in this campaign")
        self.rule("char", "import", "captain-rhosk", contains="the dead don't carry over")

    def test_lore_bard_magical_discoveries(self):
        # rules/classes/bard.md, College of Lore 6: two spells from the Cleric, Druid or Wizard lists, always prepared
        from engine import chargen
        class A: pass
        a = A(); a.discoveries = "fireball,revivify"; a.bonus_skills = None
        cls = __import__("engine.srd", fromlist=["srd"]).find("classes", "Bard")
        e = {"skills": [], "expertise": [], "choices": {}, "subclasses": {"Bard": "College of Lore"}, "granted_spells": []}
        patch = {}
        chargen.apply_level_choices(e, cls, "Bard", 6, ["Subclass feature"], patch, a)
        self.assertEqual(patch["choices"]["discoveries"], ["fireball", "revivify"])
        self.assertTrue(all(x["source"].startswith("Magical Discoveries") for x in patch["granted_spells"]))
        a.discoveries = "vicious mockery,fireball"
        from engine.core import RuleError
        with self.assertRaises(RuleError):
            chargen.apply_level_choices(e, cls, "Bard", 6, ["Subclass feature"], {}, a)   # a Bard spell isn't a discovery
        a.discoveries = "fireball,wall of fire"
        with self.assertRaises(RuleError):
            chargen.apply_level_choices(e, cls, "Bard", 6, ["Subclass feature"], {}, a)   # level 4: no slot for it yet

    def test_a_tampered_chapter_cannot_be_continued(self):
        self.ok("campaign", "new", "Clean Chapter")
        log = self.tmp / "campaigns" / "clean-chapter" / "engine" / "events.jsonl"
        lines = log.read_text(encoding="utf-8").splitlines()
        ev = json.loads(lines[0])
        ev["data"]["title"] = "Forged"
        lines[0] = json.dumps(ev)
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        code, out = self.run_cli("campaign", "new", "Forged Sequel", "--from", "clean-chapter")
        self.assertNotEqual(code, 0)
        self.assertIn("TAMPERING", out)
        self.assertFalse((self.tmp / "campaigns" / "forged-sequel").exists())


if __name__ == "__main__":
    unittest.main()
