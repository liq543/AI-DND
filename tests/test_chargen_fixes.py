"""Regression tests for character-creation bugs found in beta play (SRD typos, missed feature choices).

Run:  python -m unittest discover -s tests -v
"""
import _cli  # noqa: E402  (in-process CLI runner)
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
        self.ok("char", "create", "--name", "Mira Page", "--class", "Wizard", "--species", "Dwarf", "--background", "Sage",
                "--method", "standard", "--scores", "str=8,dex=13,con=14,int=15,wis=12,cha=10", "--bonus", "int+1,con+2",
                "--skills", "investigation,insight", "--languages", "Dwarvish,Draconic",
                "--mi-cantrips", "light,prestidigitation", "--mi-spell", "shield")
        self.ok("item", "equip", "mira", "quarterstaff-1")
        self.rule("char", "levelup", "mira", contains="Scholar")
        self.ok("char", "levelup", "mira", "--scholar", "arcana")
        self.assertIn("Arcana +7**", self.ok("char", "show", "mira"))
        # Ritual Adept: a ritual in the spellbook can be cast without being prepared
        self.ok("spells", "set", "mira", "--cantrips", "fire bolt,light,mage hand", "--prepared", "magic missile",
                "--spellbook", "detect magic,magic missile,shield,sleep,mage armor,alarm")
        self.assertIn("as a ritual", self.ok("cast", "mira", "detect magic", "--ritual"))
        self.rule("cast", "mira", "sleep", "--ritual", contains="prepared")

    def test_bard_instrument_and_lore_proficiencies(self):
        base = ["char", "create", "--name", "Lia Song", "--class", "Bard", "--species", "Human", "--background", "Acolyte",
                "--method", "standard", "--scores", "str=8,dex=14,con=13,int=10,wis=12,cha=15", "--bonus", "cha+2,wis+1",
                "--skills", "deception,persuasion,performance", "--species-skill", "stealth", "--species-feat", "Alert",
                "--mi-cantrips", "guidance,thaumaturgy", "--mi-spell", "bless", "--languages", "Elvish,Dwarvish"]
        self.rule(*base, contains="--instrument")
        self.ok(*base, "--instrument", "viol")
        # tool checks: the tool's ability + PB when proficient; needs the tool in hand
        self.rule("check", "lia", "thieves' tools", "--dc", "15", contains="needs Thieves' Tools")
        self.assertIn("DEX (Calligrapher's Supplies, proficient)", self.ok("check", "lia", "calligrapher's supplies", "--dc", "15"))
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
        # Sleep repeats its save once at the end of the target's next turn; a second failure means Unconscious
        self.assertEqual(srd.find("spells", "sleep")["effect"].get("escalate"), "unconscious")

    def test_creature_info_reads_ac_through_cover(self):
        sys.path.insert(0, str(ROOT))
        from engine import views

        class G:
            state = {"feed": [{"kind": "roll", "text": "⚔ Nim Quick attacks Blade B with Shortbow: 1d20(1) +5 = 6 vs AC 19 (half cover +2) → MISS (natural 1)"},
                              {"kind": "roll", "text": "⚔ Blade B attacks Oswin Hale with Slash: 1d20(3) +4 = 7 vs AC 11 → MISS"}]}
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

    def test_switching_maps_snapshots_the_old_one(self):
        self.ok("map", "gen", "arena", "--preset", "crypt", "--seed", "8", "--id", "roomone", "--show")
        out = self.ok("map", "gen", "arena", "--preset", "ruins", "--seed", "9", "--id", "roomtwo", "--show")
        self.assertIn("Saved the exact state", out)
        snaps = list((self.tmp / "campaigns").rglob("views/maps/roomone-*.md"))
        self.assertTrue(snaps, "no snapshot written for the map we left")
        self.assertIn("roomone", snaps[0].read_text(encoding="utf-8"))

    def test_bespoke_grid_and_theme(self):
        grid = self.tmp / "barge.txt"
        grid.write_text("~~~~~~\n~####~\n~#ka#~\n~#ld#~\n~~~~~~\n", encoding="utf-8")
        self.ok("map", "gen", "arena", "--preset", "crypt", "--seed", "4", "--id", "barge")
        self.assertIn("6×5", self.ok("map", "import-grid", "barge", "--out", str(grid)))
        self.ok("map", "set", "barge", "--kv", "theme=ship")
        self.rule("map", "set", "barge", "--kv", "theme=disco", contains="theme")
        svg = Path(self.ok("map", "render", "barge").strip().splitlines()[-1]).read_text(encoding="utf-8")
        self.assertIn("url(#carpet)", svg)
        self.assertIn("url(#felt)", svg)
        bad = self.tmp / "bad.txt"
        bad.write_text("##Z#\n", encoding="utf-8")
        self.rule("map", "import-grid", "barge", "--out", str(bad), contains="Unknown terrain")

    def test_interior_styles_and_new_furnishings(self):
        grid = self.tmp / "baths.txt"
        grid.write_text("#########\n#qqwwwqq#\n#pewww.j#\n#zziyccl#\n####dd###\n", encoding="utf-8")
        self.ok("map", "gen", "interior", "--building", "shop", "--seed", "3", "--id", "baths")
        self.ok("map", "import-grid", "baths", "--out", str(grid))
        self.ok("map", "set", "baths", "--kv", "theme=bathhouse")
        self.ok("map", "set", "baths", "--kv", "walls=brick")
        self.ok("map", "set", "baths", "--kv", "accent=#aa3355")
        self.rule("map", "set", "baths", "--kv", "walls=wallpaper", contains="walls")
        self.rule("map", "set", "baths", "--kv", "accent=pink", contains="accent")
        svg = Path(self.ok("map", "render", "baths").strip().splitlines()[-1]).read_text(encoding="utf-8")
        self.assertIn('id="wallface"', svg)      # brick wall faces
        self.assertIn("url(#fine)", svg)         # the bathhouse's mosaic floor
        self.assertIn("url(#tiles)", svg)        # the tiled 'z' squares
        self.assertIn("#fbf6ee", svg)            # stone coping round the built pool
        self.assertIn("#aa3355", svg)            # the map's own accent colour

    def test_generated_interiors_vary_and_connect(self):
        from engine import maps
        for kind in ("tavern", "temple", "bathhouse", "manor", "shop", "warehouse", "library", "tower"):
            shapes = set()
            for seed in range(12):
                m = maps.gen_interior(seed, kind=kind)
                shapes.add(tuple(m["grid"]))
                walk = dict(m, grid=["".join("." if c == "D" else c for c in r) for r in m["grid"]])
                dist, _ = maps.pathfind(walk, tuple(m["start"]))
                for r in m["rooms"]:
                    cells = [(x, y) for y in range(r["y"], r["y"] + r["h"]) for x in range(r["x"], r["x"] + r["w"])]
                    self.assertTrue(any(c in dist for c in cells), f"{kind} seed {seed}: {r['label']} can't be reached")
            self.assertEqual(len(shapes), 12, f"{kind} interiors repeat")
        self.assertEqual(maps.gen_interior(1, kind="bathhouse")["theme"], "bathhouse")
        self.assertEqual(maps.gen_interior(1, kind="tavern")["theme"], "timber")

    def test_journal_collects_handouts(self):
        self.ok("show", "text", "The butler did it.", "--title", "A Note")
        self.rule("journal", "add", "no title here", contains="--title")
        self.assertIn("Added to the journal", self.ok("journal", "add", "Remember the mill.", "--title", "Reminder"))
        events = next((self.tmp / "campaigns").rglob("events.jsonl")).read_text(encoding="utf-8")
        self.assertIn('"journal.add"', events)
        self.assertIn("The butler did it.", events)

    def test_map_links(self):
        self.ok("map", "gen", "arena", "--preset", "crypt", "--seed", "11", "--id", "upstairs")
        self.ok("map", "gen", "arena", "--preset", "crypt", "--seed", "12", "--id", "cellar")
        self.ok("map", "link", "upstairs", "cellar")
        self.rule("map", "link", "upstairs", "nowhere", contains="both must exist")
        events = next((self.tmp / "campaigns").rglob("events.jsonl")).read_text(encoding="utf-8")
        self.assertIn('"links":["cellar"]', events)
        self.assertIn('"links":["upstairs"]', events)

    def test_contest_lie_vs_insight(self):
        self.ok("char", "create", "--name", "Ivo Ear", "--class", "Fighter", "--species", "Dwarf", "--background", "Soldier",
                "--method", "standard", "--scores", "str=15,dex=13,con=14,int=8,wis=12,cha=10", "--bonus", "str+2,con+1",
                "--skills", "insight,survival", "--languages", "Elvish,Dwarvish", "--fighting-style", "Defense",
                "--masteries", "longsword,javelin,greatsword")
        self.ok("npc", "add", "spy", "--name", "Liar", "--side", "neutral")
        out = self.ok("contest", "liar", "deception", "--vs", "ivo", "--vs-skill", "insight", "--passive")
        self.assertIn("passive Insight 13", out)
        self.assertIn("wins", out)
        hidden = self.ok("contest", "liar", "deception", "--vs", "ivo", "--vs-skill", "insight", "--passive", "--hidden")
        self.assertIn("[secret]", hidden)

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


    def test_item_note_alias_keeps_mechanics(self):
        self.ok("char", "create", "--name", "Cane Carrier", "--class", "Rogue", "--species", "Human", "--background", "Criminal",
                "--method", "standard", "--scores", "str=8,dex=15,con=14,int=10,wis=12,cha=13", "--bonus", "dex+1,con+2",
                "--skills", "athletics,perception,deception,acrobatics", "--species-skill", "insight",
                "--species-feat", "Skilled", "--skilled", "persuasion,history,Disguise Kit",
                "--languages", "Elvish,Halfling", "--expertise", "stealth,sleight of hand", "--masteries", "shortsword,dagger")
        self.ok("item", "add", "cane", "Rapier", "--source", "loot: a cane")
        self.rule("item", "note", "cane", "rapier", contains="--text")
        out = self.ok("item", "note", "cane", "rapier", "--alias", "Silverwood Walking Stick", "--text", "A blade hidden in a walking stick.")
        self.assertIn("Silverwood Walking Stick", out)
        sheet = self.ok("char", "show", "cane")
        self.assertIn("Silverwood Walking Stick (Rapier)", sheet)
        self.assertIn("A blade hidden in a walking stick.", sheet)
        self.ok("item", "equip", "cane", "rapier")      # still a Rapier to the engine
        self.assertIn("Walking Stick (Rapier) (equipped)", self.ok("char", "show", "cane"))
        from engine import assets
        svg = assets.item_card({"name": "Rapier", "kind": "weapon", "alias": "Silverwood Walking Stick",
                                "note": "A blade hidden in a walking stick.", "source": "loot"})
        self.assertIn("Silverwood Walking Stick", svg)
        self.assertIn("Rapier", svg)


    def test_monster_short_rest_hit_dice(self):
        self.ok("npc", "add", "bandit", "--name", "Tired Bandit", "--side", "neutral")
        self.ok("damage", "tired-bandit", "5", "slashing", "--source", "test")
        out = self.ok("rest", "short", "--who", "tired-bandit", "--hd", "tired-bandit:2")
        self.assertGreaterEqual(out.count("Hit Point Die"), 2)   # a roll for each die spent
        self.rule("rest", "short", "--who", "tired-bandit", "--hd", "tired-bandit:9", contains="Hit Point Dice left")

    def test_dim_light_does_not_cap_sight_and_walls_block(self):
        # a 110-ft dim hall beside a sealed room: the far end of the hall is seen, the sealed room is not
        import json
        grid = self.tmp / "hall.txt"
        rows = ["#" * 24, "#" + "." * 22 + "#", "#" * 24, "#" + "." * 5 + "#" * 18, "#" * 24]
        grid.write_text("\n".join(rows) + "\n", encoding="utf-8")
        self.ok("map", "gen", "dungeon", "--name", "Dim Hall", "--id", "dimhall", "--w", "30", "--h", "20")
        self.ok("map", "import-grid", "dimhall", "--out", str(grid))
        self.ok("map", "set", "dimhall", "--kv", "lighting=dim")
        self.ok("char", "create", "--name", "Seer Human", "--class", "Rogue", "--species", "Human", "--background", "Criminal",
                "--method", "standard", "--scores", "str=8,dex=15,con=14,int=10,wis=12,cha=13", "--bonus", "dex+1,con+2",
                "--skills", "athletics,perception,deception,acrobatics", "--species-skill", "insight",
                "--species-feat", "Skilled", "--skilled", "persuasion,history,Disguise Kit",
                "--languages", "Elvish,Halfling", "--expertise", "stealth,sleight of hand", "--masteries", "shortsword,dagger")
        self.ok("place", "seer", "--map", "dimhall", "1,1")
        events = next((self.tmp / "campaigns").rglob("events.jsonl")).read_text(encoding="utf-8").splitlines()
        seen = set()
        for line in events:
            ev = json.loads(line) if line.strip() else {}
            body = ev.get("data", ev)
            if (ev.get("type") or body.get("type")) == "map.reveal" and body.get("id") == "dimhall":
                seen |= {tuple(c) for c in body["cells"]}
        self.assertIn((22, 1), seen)       # 105 ft down a dim hall: visible (dim light doesn't limit sight)
        self.assertNotIn((3, 3), seen)     # behind solid wall: not visible

    def _rogue(self, name):
        self.ok("char", "create", "--name", name, "--class", "Rogue", "--species", "Human", "--background", "Criminal",
                "--method", "standard", "--scores", "str=8,dex=15,con=14,int=10,wis=12,cha=13", "--bonus", "dex+1,con+2",
                "--skills", "athletics,perception,deception,acrobatics", "--species-skill", "insight",
                "--species-feat", "Skilled", "--skilled", "persuasion,history,Disguise Kit",
                "--languages", "Elvish,Halfling", "--expertise", "stealth,sleight of hand", "--masteries", "shortsword,dagger")

    def test_magic_items_start_unidentified_and_weapons_work(self):
        import json
        self._rogue("Vex Finder")
        out = self.ok("item", "add", "vex", "Dagger of Venom", "--source", "loot: a drowned smuggler", "--override", "test: rare item")
        self.assertIn("Unidentified magic dagger", out)
        self.ok("item", "equip", "vex", "dagger-of-venom-1")
        sheet = self.ok("char", "show", "vex")
        self.assertIn("UNIDENTIFIED", sheet)
        self.assertIn("Dagger of Venom | +6 | 1d4+4 piercing", sheet)   # a real weapon: Dex +3, PB +2, magic +1 (applies even unidentified)
        self.rule("item", "identify", "vex", "dagger-of-venom", contains="--how")
        out = self.ok("rest", "short", "--who", "vex", "--focus", "vex:dagger-of-venom-1")
        self.assertIn("identifies the Unidentified magic dagger: it is Dagger of Venom", out)
        self.rule("item", "identify", "vex", "dagger-of-venom", "--how", "again", contains="already knows")
        self.ok("coins", "vex", "+60gp", "--source", "reward: test purse")
        self.ok("item", "add", "vex", "Potion of Healing", "--purchase")
        self.assertNotIn("Unidentified potion", self.ok("char", "show", "vex"))   # bought items are known
        from engine import views
        info = views.item_info(None, {"id": "x", "name": "Dagger of Venom", "kind": "weapon", "base_name": "Dagger", "magic": True,
                                      "ref": "dagger-of-venom", "rarity": "Rare", "identified": False, "magic_bonus": 1})
        self.assertEqual(info["name"], "Unidentified magic dagger")
        self.assertIsNone(info["rarity"])
        self.assertEqual(info["rules_md"], "")
        self.assertEqual(json.loads(json.dumps(info))["stats"][0][0], "Damage")   # no +1 shown while unidentified

    def test_points_of_interest(self):
        self.ok("map", "gen", "arena", "--preset", "crypt", "--seed", "3", "--id", "poiroom", "--show")
        out = self.ok("map", "poi", "poiroom", "4,4", "--name", "Weathered Statue", "--text", "A knight in grey stone.")
        self.assertIn("Noted on", out)
        self.rule("map", "poi", "poiroom", "4,4", "--name", "Second", "--text", "x", contains="already has")
        self.rule("map", "poi-move", "poiroom", "5,4", "--id", "poi-1", contains="--reason")
        self.ok("map", "poi-move", "poiroom", "5,4", "--id", "poi-1", "--reason", "the statue was dragged aside")
        svg = Path(self.ok("map", "render", "poiroom", "--dm").strip().splitlines()[-1]).read_text(encoding="utf-8")
        self.assertIn('data-poi="poi-1"', svg)
        self.ok("map", "poi-remove", "poiroom", "--id", "poi-1", "--reason", "carted away")
        svg = Path(self.ok("map", "render", "poiroom", "--dm").strip().splitlines()[-1]).read_text(encoding="utf-8")
        self.assertNotIn('data-poi="poi-1"', svg)

    def test_coins_negative_amount_parses(self):
        self.ok("char", "create", "--name", "Coin Spender", "--class", "Rogue", "--species", "Human", "--background", "Criminal",
                "--method", "standard", "--scores", "str=8,dex=15,con=14,int=10,wis=12,cha=13", "--bonus", "dex+1,con+2",
                "--skills", "athletics,perception,deception,acrobatics", "--species-skill", "insight",
                "--species-feat", "Skilled", "--skilled", "persuasion,history,Disguise Kit",
                "--languages", "Elvish,Halfling", "--expertise", "stealth,sleight of hand", "--masteries", "shortsword,dagger")
        out = self.ok("coins", "coin", "-5gp", "--source", "spent: a bribe")   # as documented in engine-reference
        self.assertIn("spends 5 GP", out)

    def test_unpack_burglars_pack(self):
        from engine import mechanics as M
        self.assertIn(("Candles", 10), M.pack_contents("Burglar's Pack"))
        self.assertIn(("Oil", 7), M.pack_contents("Burglar's Pack"))
        self.assertIn(("Torches", 10), M.pack_contents("Explorer's Pack"))
        self.ok("char", "create", "--name", "Pack Opener", "--class", "Rogue", "--species", "Human", "--background", "Criminal",
                "--method", "standard", "--scores", "str=8,dex=15,con=14,int=10,wis=12,cha=13", "--bonus", "dex+1,con+2",
                "--skills", "athletics,perception,deception,acrobatics", "--species-skill", "insight",
                "--species-feat", "Skilled", "--skilled", "persuasion,history,Disguise Kit",
                "--languages", "Elvish,Halfling", "--expertise", "stealth,sleight of hand", "--masteries", "shortsword,dagger")
        self.ok("item", "unpack", "pack", "burglars-pack")
        sheet = self.ok("char", "show", "pack")
        self.assertNotIn("Burglar's Pack ·", sheet)
        self.assertIn("Hooded Lantern", sheet)
        self.assertIn("10× Candle", sheet)
        self.ok("item", "light", "pack", "hooded-lantern")
        self.rule("item", "unpack", "pack", "crowbar", contains="isn't an equipment pack")


if __name__ == "__main__":
    unittest.main()
