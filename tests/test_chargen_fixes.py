"""Regression tests for character-creation bugs found in beta play (SRD typos, missed feature choices).

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


class ChargenFixesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-cg-"))
        cls.env = {**os.environ, "DND_CAMPAIGNS": str(cls.tmp / "campaigns"), "DND_ENGINE_HOME": str(cls.tmp / "home"),
                   "PYTHONIOENCODING": "utf-8"}
        cls.ok("campaign", "new", "Level Three", "--set", "start_level=3")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def run_cli(cls, *args):
        p = subprocess.run([sys.executable, "-m", "engine", *args], cwd=ROOT, env=cls.env, capture_output=True,
                           text=True, encoding="utf-8")
        return p.returncode, p.stdout + p.stderr

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

    def test_rogue_leather_armor_and_athletics(self):
        self.ok("char", "create", "--name", "Nim Quick", "--class", "Rogue", "--species", "Human", "--background", "Criminal",
                "--method", "standard", "--scores", "str=8,dex=15,con=14,int=10,wis=12,cha=13", "--bonus", "dex+1,con+2",
                "--skills", "athletics,perception,deception,acrobatics", "--species-skill", "insight",
                "--species-feat", "Skilled", "--skilled", "persuasion,history,Disguise Kit",
                "--languages", "Elvish,Halfling", "--expertise", "stealth,sleight of hand", "--masteries", "shortsword,dagger")
        sheet = self.ok("char", "show", "nim")
        self.assertIn("Leather Armor (equipped)", sheet)
        self.assertIn("AC** 14", sheet)
        self.assertIn("Persuasion +3*", sheet)
        self.assertIn("History +2*", sheet)
        self.assertIn("Disguise Kit", sheet)
        out = self.ok("char", "levelup", "nim")
        self.assertIn("level 2", out)
        self.ok("char", "levelup", "nim", "--subclass", "Thief")
        self.assertIn("**XP:** 900", self.ok("char", "show", "nim"))
        self.ok("item", "unequip", "nim", "shortsword-1")
        self.ok("item", "unequip", "nim", "dagger-1")
        self.ok("item", "equip", "nim", "shortbow-1")
        sheet = self.ok("char", "show", "nim")
        bow = next(l for l in sheet.splitlines() if l.startswith("| Shortbow"))
        self.assertNotIn("mastery", bow)  # Nim picked Shortsword and Dagger masteries, not Shortbow

    def test_wizard_quarterstaff_and_scholar(self):
        self.ok("char", "create", "--name", "Oona Page", "--class", "Wizard", "--species", "Dwarf", "--background", "Sage",
                "--method", "standard", "--scores", "str=8,dex=13,con=14,int=15,wis=12,cha=10", "--bonus", "int+1,con+2",
                "--skills", "investigation,insight", "--languages", "Dwarvish,Draconic",
                "--mi-cantrips", "light,prestidigitation", "--mi-spell", "shield")
        self.ok("item", "equip", "oona", "quarterstaff-1")
        self.rule("char", "levelup", "oona", contains="Scholar")
        self.ok("char", "levelup", "oona", "--scholar", "arcana")
        self.assertIn("Arcana +7**", self.ok("char", "show", "oona"))

    def test_bard_instrument_and_lore_proficiencies(self):
        base = ["char", "create", "--name", "Lia Song", "--class", "Bard", "--species", "Human", "--background", "Acolyte",
                "--method", "standard", "--scores", "str=8,dex=14,con=13,int=10,wis=12,cha=15", "--bonus", "cha+2,wis+1",
                "--skills", "deception,persuasion,performance", "--species-skill", "stealth", "--species-feat", "Alert",
                "--mi-cantrips", "guidance,thaumaturgy", "--mi-spell", "bless", "--languages", "Elvish,Dwarvish"]
        self.rule(*base, contains="--instrument")
        self.ok(*base, "--instrument", "viol")
        sheet = self.ok("char", "show", "lia")
        self.assertIn("Viol", sheet)
        self.assertIn("Entertainer's Pack", sheet)
        self.ok("char", "levelup", "lia", "--expertise", "deception,persuasion")
        self.rule("char", "levelup", "lia", "--subclass", "College of Lore", contains="Bonus Proficiencies")
        self.ok("char", "levelup", "lia", "--subclass", "College of Lore", "--bonus-skills", "perception,history,arcana")
        self.assertIn("Perception +3*", self.ok("char", "show", "lia"))

    def test_spell_save_conditions_parsed(self):
        sys.path.insert(0, str(ROOT))
        from engine import srd
        self.assertEqual(srd.find("spells", "sleep")["effect"].get("condition"), "incapacitated")
        self.assertEqual(srd.find("spells", "hold person")["effect"].get("condition"), "paralyzed")
        self.assertTrue(srd.find("spells", "hold person")["effect"].get("repeat"))
        self.assertFalse(srd.find("spells", "sleep")["effect"].get("repeat"))

    def test_creature_info_reads_ac_through_cover(self):
        sys.path.insert(0, str(ROOT))
        from engine import views

        class G:
            state = {"feed": [{"kind": "roll", "text": "⚔ Kit Corvell attacks Blade B with Shortbow: 1d20(1) +5 = 6 vs AC 19 (half cover +2) → MISS (natural 1)"},
                              {"kind": "roll", "text": "⚔ Blade B attacks Tobias Fenwick with Slash: 1d20(3) +4 = 7 vs AC 11 → MISS"}]}
        info = views.creature_info(G(), {"id": "blade-b", "name": "Blade B", "side": "enemy", "hp": 14, "hp_max": 14, "conditions": []})
        self.assertEqual(info["ac_known"], 17)
        self.assertEqual(info["misses_against"], 1)
        self.assertEqual(info["attacks_seen"], ["Slash"])

    def test_dropped_items_lie_on_the_map(self):
        self.ok("char", "create", "--name", "Dex Floor", "--class", "Fighter", "--species", "Dwarf", "--background", "Soldier",
                "--method", "standard", "--scores", "str=15,dex=13,con=14,int=8,wis=12,cha=10", "--bonus", "str+2,con+1",
                "--skills", "perception,survival", "--languages", "Elvish,Dwarvish", "--fighting-style", "Defense",
                "--masteries", "longsword,javelin,greatsword")
        self.ok("map", "gen", "arena", "--preset", "crypt", "--seed", "5", "--id", "floor", "--show")
        self.ok("place", "dex", "3,3", "--map", "floor")
        out = self.ok("item", "drop", "dex", "javelin-1", "--qty", "2")
        self.assertIn("lies on the floor at (3,3)", out)
        svg_path = self.ok("map", "render", "floor").strip().splitlines()[-1]
        self.assertIn("flooritem", Path(svg_path).read_text(encoding="utf-8"))
        self.ok("place", "dex", "8,8", "--map", "floor")
        self.rule("item", "pickup", "dex", "floor-1", contains="next to")
        self.ok("place", "dex", "3,3", "--map", "floor")
        self.assertIn("picks up 2× Javelin", self.ok("item", "pickup", "dex", "floor-1"))
        self.rule("item", "floor-record", "dex", "Javelin", "--to", "3,3", contains="no unrecorded drop")

    def test_fliers_use_fly_speed(self):
        sys.path.insert(0, str(ROOT))
        from engine.mechanics import move_speed
        self.assertEqual(move_speed({"kind": "monster", "speed": {"walk": 5, "fly": 50}, "conditions": []}), 50)
        self.assertEqual(move_speed({"kind": "monster", "speed": {"walk": 5, "fly": 50},
                                     "conditions": [{"name": "grappled"}]}), 0)

    def test_catch_up_for_old_characters_and_resourceful(self):
        self.ok("char", "create", "--name", "Tam Old", "--class", "Fighter", "--species", "Human", "--background", "Soldier",
                "--method", "standard", "--scores", "str=15,dex=13,con=14,int=8,wis=12,cha=10", "--bonus", "str+2,con+1",
                "--skills", "perception,survival", "--languages", "Elvish,Dwarvish", "--species-skill", "insight",
                "--species-feat", "Alert", "--fighting-style", "Defense", "--masteries", "longsword,javelin,greatsword")
        self.rule("char", "catch-up", "tam", contains="no missed choices")
        out = self.ok("rest", "long")
        self.assertIn("Resourceful", out)
        self.ok("char", "levelup", "tam")
        self.ok("char", "levelup", "tam", "--subclass", "Champion")
        self.assertIn("Advantage (Remarkable Athlete)", self.ok("check", "tam", "athletics", "--dc", "10"))


if __name__ == "__main__":
    unittest.main()
