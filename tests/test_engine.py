"""End-to-end tests of the rules engine through its real CLI, in an isolated temp directory.

Run:  python -m unittest discover -s tests -v
"""
import _cli  # noqa: E402  (in-process CLI runner)
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class EngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-"))
        cls.env = {**os.environ, "DND_CAMPAIGNS": str(cls.tmp / "campaigns"), "DND_ENGINE_HOME": str(cls.tmp / "home"),
                   "PYTHONIOENCODING": "utf-8"}
        cls.ok("campaign", "new", "Test Realm")
        cls.ok("char", "create", "--name", "Kira Vale", "--class", "Fighter", "--species", "Human", "--background", "Soldier",
               "--method", "standard", "--scores", "str=15,dex=13,con=14,int=8,wis=12,cha=10", "--bonus", "str+2,con+1",
               "--skills", "perception,survival", "--languages", "Elvish,Dwarvish", "--species-skill", "insight",
               "--species-feat", "Alert", "--fighting-style", "Defense", "--masteries", "longsword,javelin,greatsword")
        cls.ok("char", "create", "--name", "Wren Ashdown", "--class", "Wizard", "--species", "Elf", "--background", "Sage",
               "--method", "pointbuy", "--scores", "str=8,dex=14,con=14,int=15,wis=12,cha=8", "--bonus", "int+2,con+1",
               "--skills", "investigation,medicine", "--languages", "Elvish,Draconic", "--species-skill", "perception",
               "--mi-cantrips", "light,mage hand", "--mi-spell", "shield")
        cls.ok("spells", "set", "wren", "--cantrips", "fire bolt,ray of frost,minor illusion",
               "--prepared", "magic missile,sleep,burning hands,mage armor",
               "--spellbook", "magic missile,shield,sleep,burning hands,detect magic,mage armor")
        cls.ok("map", "gen", "arena", "--preset", "crypt", "--seed", "3", "--id", "arena", "--show")

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
        self.assertIn("nothing was changed", out)
        if contains:
            self.assertIn(contains, out)
        return out

    def state(self):
        return _cli.game(self.env)

    # ------------------------------------------------------------------ character creation
    def test_standard_array_enforced(self):
        self.rule("char", "create", "--name", "Cheater", "--class", "Fighter", "--species", "Dwarf", "--background", "Soldier",
                  "--method", "standard", "--scores", "str=18,dex=14,con=13,int=12,wis=10,cha=8", "--bonus", "str+2,con+1",
                  "--skills", "perception,survival", "--languages", "Elvish,Giant", "--fighting-style", "Defense",
                  "--masteries", "longsword,javelin,greatsword", contains="Standard Array")

    def test_point_buy_budget(self):
        self.rule("char", "create", "--name", "Cheater", "--class", "Fighter", "--species", "Dwarf", "--background", "Soldier",
                  "--method", "pointbuy", "--scores", "str=15,dex=15,con=15,int=15,wis=8,cha=8", "--bonus", "str+2,con+1",
                  "--skills", "perception,survival", "--languages", "Elvish,Giant", "--fighting-style", "Defense",
                  "--masteries", "longsword,javelin,greatsword", contains="27")

    def test_background_bonus_limits(self):
        self.rule("char", "create", "--name", "Cheater", "--class", "Fighter", "--species", "Dwarf", "--background", "Soldier",
                  "--method", "standard", "--scores", "str=15,dex=14,con=13,int=12,wis=10,cha=8", "--bonus", "cha+2,con+1",
                  "--skills", "perception,survival", "--languages", "Elvish,Giant", "--fighting-style", "Defense",
                  "--masteries", "longsword,javelin,greatsword", contains="can only raise")

    def test_no_stat_rerolls(self):
        self.ok("char", "roll-stats", "Rolly")
        self.rule("char", "roll-stats", "Rolly", contains="No rerolls")

    def test_derived_stats(self):
        g = self.state()
        from engine.core import derive
        k = derive(g.get("kira"))
        self.assertEqual(k["ac"], 17)             # chain mail 16 + Defense 1
        self.assertEqual(k["abilities"]["str"], 17)
        self.assertEqual(k["hp_max"], 12)          # d10 + Con 2
        self.assertEqual(k["saves"]["str"], 5)
        w = derive(g.get("wren"))
        self.assertEqual(w["spellcasting"]["Wizard"]["dc"], 8 + 3 + 2)
        self.assertEqual(w["slots"], {1: 2})

    # ------------------------------------------------------------------ spells & items
    def test_spell_restrictions(self):
        self.rule("cast", "wren", "cure wounds", "--targets", "kira", contains="prepared")
        self.rule("spells", "set", "wren", "--prepared", "cure wounds", contains="not on the Wizard spell list")
        self.rule("cast", "wren", "mage armor", "--level", "2", "--targets", "wren", contains="no level 2 spell slot")

    def test_treasure_limits(self):
        self.rule("item", "add", "kira", "Vorpal Sword", "--source", "loot: dragon", contains="ceiling is Uncommon")
        self.rule("coins", "kira", "9000gp", "--source", "loot: chest", contains="guideline")
        self.rule("item", "add", "kira", "Longsword", "--source", "because I said so", contains="--source must start")
        self.rule("heal", "kira", "10", "--source", "vibes", contains="must come from a mechanic")

    def test_purchase_costs_money(self):
        g = self.state()
        from engine.mechanics import coins_total_cp
        before = coins_total_cp(g.get("wren"))
        self.ok("item", "add", "wren", "Dagger", "--purchase")
        g = self.state()
        self.assertEqual(coins_total_cp(g.get("wren")), before - 200)
        self.rule("item", "add", "wren", "Plate Armor", "--purchase", contains="afford")

    # ------------------------------------------------------------------ combat
    def test_combat_flow(self):
        self.ok("place", "kira", "5,5", "--map", "arena")
        self.ok("place", "wren", "6,6", "--map", "arena")
        self.ok("npc", "add", "goblin-warrior", "--name", "Snag", "--at", "12,10", "--map", "arena")
        self.rule("encounter", "spawn", "ogre:3", contains="exceeds the High budget")
        self.ok("item", "equip", "kira", "greatsword-1")
        self.ok("combat", "start")
        try:
            g = self.state()
            from engine import mechanics as M
            order = [o["id"] for o in g.state["combat"]["order"]]
            cur = M.current_id(g)
            other = next(i for i in order if i != cur)
            self.rule("move", other, "7,7", contains="not")
            if cur == "kira":
                self.rule("attack", "kira", "snag", "greatsword", contains="reach")
                self.rule("move", "kira", "20,5", contains="movement")
            self.ok("combat", "next")
        finally:
            self.ok("combat", "end")
        self.rule("rest", "long", contains=None) if False else None

    def test_nick_mastery_keeps_the_bonus_action(self):
        self.ok("char", "create", "--name", "Nix Quill", "--class", "Rogue", "--species", "Human", "--background", "Criminal",
                "--method", "standard", "--scores", "str=8,dex=15,con=14,int=10,wis=12,cha=13", "--bonus", "dex+2,con+1",
                "--skills", "perception,investigation,deception,acrobatics", "--languages", "Elvish,Halfling",
                "--species-skill", "insight", "--species-feat", "Alert", "--expertise", "stealth,perception",
                "--masteries", "dagger,shortbow")
        g = self.state()
        nix = g.get("nix")
        self.assertEqual(nix["mastery_weapons"], ["Dagger", "Shortbow"])
        self.ok("item", "add", "nix", "Dagger", "--source", "found: a second blade")
        inv = self.state().get("nix")["inventory"]
        daggers = [i["id"] for i in inv if i.get("base_name") == "Dagger"]
        self.assertTrue(len(daggers) > 1 or next(i for i in inv if i["id"] == daggers[0])["qty"] >= 2)
        for d in daggers:
            self.ok("item", "equip", "nix", d)
        self.ok("place", "nix", "3,3", "--map", "arena")
        self.ok("npc", "add", "bandit", "--name", "Mark", "--at", "4,3", "--map", "arena")
        self.ok("combat", "start")
        try:
            from engine import mechanics as M
            for _ in range(6):
                if M.current_id(self.state()) == "nix":
                    break
                self.ok("combat", "next")
            if M.current_id(self.state()) == "nix":
                self.rule("attack", "nix", "mark", daggers[0], "--offhand", contains="attacked with a Light weapon")
                self.ok("attack", "nix", "mark", daggers[0])
                out = self.ok("attack", "nix", "mark", daggers[-1], "--offhand")  # a second dagger from the pair
                self.assertIn("Nick", out)
                self.assertFalse(M.economy(self.state(), "nix").get("bonus_used"))
                self.rule("attack", "nix", "mark", daggers[-1], "--offhand", contains="only one extra attack")
        finally:
            self.ok("combat", "end")
            self.ok("npc", "remove", "mark")
            self.ok("char", "remove", "nix")

    def test_alert_initiative_swap(self):
        self.ok("place", "kira", "5,5", "--map", "arena")
        self.ok("place", "wren", "6,6", "--map", "arena")
        self.ok("combat", "start")
        try:
            before = {o["id"]: o["init"] for o in self.state().state["combat"]["order"]}
            self.rule("combat", "swap", "wren,kira", contains="Alert")      # Wren has no Alert feat
            self.ok("combat", "swap", "kira,wren")
            after = {o["id"]: o["init"] for o in self.state().state["combat"]["order"]}
            self.assertEqual((after["kira"], after["wren"]), (before["wren"], before["kira"]))
            self.rule("combat", "swap", "kira,wren", contains="immediately after")
        finally:
            self.ok("combat", "end")

    def test_sleep_is_two_stage(self):
        from engine import srd
        fx = srd.find("spells", "Sleep")["effect"]
        self.assertEqual((fx["condition"], fx.get("repeat"), fx.get("escalate")), ("incapacitated", True, "unconscious"))
        from engine import mechanics as M
        import engine.core as core
        g = self.state()
        e = g.get("kira")
        M.add_condition(g, e, "incapacitated", source="Sleep", save="wis:30", escalate="unconscious", quiet=True)
        M.end_of_turn(g, g.get("kira"))   # a DC 30 save fails: Incapacitated deepens to Unconscious
        names = core.condition_names(g.get("kira"))
        self.assertIn("unconscious", names)
        self.assertNotIn("incapacitated", [c["name"] for c in g.get("kira")["conditions"]])

    def test_sleep_cast_carries_the_second_stage(self):
        # the real path: a cast Sleep's condition must remember that a second failure means Unconscious
        self.ok("npc", "add", "commoner", "--name", "Sleepy Tam", "--at", "7,7", "--map", "arena")
        self.ok("place", "wren", "6,6", "--map", "arena")
        try:
            self.ok("cast", "wren", "sleep", "--targets", "sleepy-tam")
            t = self.state().get("sleepy-tam")
            inc = [c for c in t["conditions"] if c["name"] == "incapacitated"]
            if inc:   # it failed the first save
                self.assertEqual(inc[0].get("escalate"), "unconscious")
        finally:
            self.ok("npc", "remove", "sleepy-tam")

    def test_heavy_armor_stealth_disadvantage(self):
        from engine import srd
        self.assertTrue(srd.find("armor", "Chain Mail")["stealth_dis"])
        self.assertFalse(srd.find("armor", "Leather Armor")["stealth_dis"])
        inv = self.state().get("kira")["inventory"]
        armor = next(i for i in inv if i.get("kind") == "armor")
        self.ok("item", "equip", "kira", armor["id"])
        out = self.ok("check", "kira", "stealth", "--dc", "10")
        if srd.find("armor", armor.get("base_name") or armor["name"]).get("stealth_dis"):
            self.assertIn("Stealth Disadvantage", out)

    def test_grapple_and_shove(self):
        self.ok("place", "kira", "3,3", "--map", "arena")
        self.ok("npc", "add", "bandit", "--name", "Oswin Hale", "--at", "4,3", "--map", "arena")
        try:
            out = self.ok("action", "kira", "grapple", "--target", "oswin-hale")
            self.assertIn("tries to grapple", out)
            dc = 8 + 3 + 2   # Kira: STR 17 (+3), proficiency +2
            self.assertIn(f"DC {dc}", out)
            e = self.state().get("oswin-hale")
            if any(c["name"] == "grappled" for c in e["conditions"]):
                self.assertEqual(next(c for c in e["conditions"] if c["name"] == "grappled")["escape_dc"], dc)
            self.rule("action", "kira", "escape", contains="isn't Grappled")
            self.ok("place", "kira", "9,9", "--map", "arena")
            self.rule("action", "kira", "shove", "--target", "oswin-hale", contains="out of reach")
        finally:
            self.ok("npc", "remove", "oswin-hale")

    def test_dagger_of_venom_coats_once_per_dawn(self):
        from engine.mechanics import next_dawn
        self.assertEqual(next_dawn(300), 360)          # 05:00 -> 06:00 the same day
        self.assertEqual(next_dawn(400), 1440 + 360)   # 06:40 -> 06:00 the next day
        self.ok("item", "add", "wren", "Dagger of Venom", "--source", "loot: a cultist's belt", "--override", "test item")
        dv = next(i["id"] for i in self.state().get("wren")["inventory"] if "Venom" in i["name"])
        out = self.ok("item", "use", "wren", dv)
        self.assertIn("coats", out)
        self.rule("item", "use", "wren", dv, contains="next dawn")
        self.ok("item", "remove", "wren", dv)

    def test_a_character_can_leave_and_rejoin_the_party(self):
        from engine import views
        self.ok("char", "leave", "wren", "parts ways at the crossroads")
        try:
            g = self.state()
            self.assertNotIn("wren", [p["id"] for p in g.pcs()])
            v = views.player_view(g)
            self.assertNotIn("wren", [p["id"] for p in v["party"]])
            self.assertIn("wren", [o["id"] for o in v["offstage"]])     # her face stays in the log
            self.rule("char", "leave", "wren", "")
        finally:
            self.ok("char", "rejoin", "wren", "back for the test")
        self.assertIn("wren", [p["id"] for p in self.state().pcs()])

    def test_creatures_who_left_stay_out_of_combat(self):
        self.ok("place", "kira", "3,3", "--map", "arena")
        self.ok("npc", "add", "commoner", "--name", "Oswin Hale", "--at", "5,5", "--map", "arena")
        self.ok("npc", "add", "bandit", "--name", "Captain Rhosk", "--at", "6,6", "--map", "arena")
        try:
            self.ok("npc", "leave", "oswin-hale")
            self.ok("combat", "start")
            order = [o["id"] for o in self.state().state["combat"]["order"]]
            self.assertNotIn("oswin-hale", order)
            self.assertIn("captain-rhosk", order)
        finally:
            self.ok("combat", "end")
            self.ok("npc", "remove", "oswin-hale,captain-rhosk")

    def test_thrown_weapon_lands_by_the_target(self):
        from engine import mechanics as M
        self.ok("item", "add", "kira", "Handaxe", "--source", "found: a woodpile")
        self.ok("place", "kira", "3,3", "--map", "arena")
        self.ok("npc", "add", "bandit", "--name", "Oswin Hale", "--at", "6,3", "--map", "arena")
        try:
            self.ok("combat", "start")
            for _ in range(6):
                if M.current_id(self.state()) == "kira":
                    break
                self.ok("combat", "next")
            if M.current_id(self.state()) == "kira":
                inv = self.state().get("kira")["inventory"]
                for i in inv:
                    if i.get("equipped") and i.get("kind") == "weapon":
                        self.ok("item", "unequip", "kira", i["id"])
                axe = next(i for i in self.state().get("kira")["inventory"] if i["name"] == "Handaxe")
                self.ok("item", "equip", "kira", axe["id"])
                self.ok("attack", "kira", "oswin-hale", axe["id"])
                g = self.state()
                self.assertFalse(any(i["id"] == axe["id"] for i in g.get("kira")["inventory"]))
                self.assertTrue(any(f["item"]["name"] == "Handaxe" and (f["x"], f["y"]) == (6, 3)
                                    for f in g.state["maps"]["arena"]["floor"]))
        finally:
            self.ok("combat", "end")
            self.ok("npc", "remove", "oswin-hale")

    def test_npc_alignment(self):
        self.ok("npc", "add", "bandit", "--name", "Captain Rhosk", "--at", "9,9", "--map", "arena")
        try:
            self.ok("npc", "alignment", "captain-rhosk", "--text", "chaotic evil")
            g = self.state()
            self.assertEqual(g.get("captain-rhosk")["alignment"], "Chaotic Evil")
            from engine import views
            self.assertEqual(views.creature_info(g, g.get("captain-rhosk"))["alignment"], "Chaotic Evil")
            self.rule("npc", "alignment", "captain-rhosk", "--text", "grumpy")
            self.rule("npc", "alignment", "kira", "--text", "neutral", contains="player character")
        finally:
            self.ok("npc", "remove", "captain-rhosk")

    def test_no_fighting_outside_combat(self):
        self.ok("place", "kira", "3,3", "--map", "arena")
        self.ok("npc", "add", "bandit", "--name", "Lurker", "--at", "4,3", "--map", "arena")
        self.rule("attack", "kira", "lurker", "greatsword", contains="combat start")
        self.rule("cast", "wren", "fire bolt", "--targets", "lurker", contains="combat start")
        self.ok("npc", "remove", "lurker")

    def test_viewer_roll_requests(self):
        self.ok("set", "player_rolls=viewer")
        out = self.ok("check", "kira", "athletics", "--dc", "10")
        self.assertIn("request", out)
        g = self.state()
        rid = next(iter(g.state["requests"]))
        self.ok("request", "roll", rid)
        g = self.state()
        self.assertNotIn(rid, g.state["requests"])
        self.rule("request", "roll", rid, contains="No pending request")  # a request can only be rolled once
        self.ok("set", "player_rolls=auto")

    # ------------------------------------------------------------------ rests & time
    def test_long_rest_spacing(self):
        self.ok("rest", "long")
        self.rule("rest", "long", contains="16 hours")
        self.ok("time", "16h")
        self.ok("rest", "long")

    def test_levelup_requires_xp(self):
        self.rule("char", "levelup", "kira", contains="XP")

    # ------------------------------------------------------------------ integrity
    def test_tamper_detection(self):
        g = self.state()
        path = Path(g.dir) / "engine" / "events.jsonl"
        original = path.read_text(encoding="utf-8")
        try:
            path.write_text(original.replace('"hp_max":12', '"hp_max":120', 1), encoding="utf-8")
            code, out = self.run_cli("status")
            self.assertEqual(code, 3)
            self.assertIn("TAMPERING", out)
            code, out = self.run_cli("repair")
            self.assertIn("backup", out)
        finally:
            path.write_text(original, encoding="utf-8")
        self.ok("verify")

    def test_deleting_events_detected(self):
        g = self.state()
        path = Path(g.dir) / "engine" / "events.jsonl"
        original = path.read_text(encoding="utf-8")
        try:
            lines = original.splitlines()
            path.write_text("\n".join(lines[:5] + lines[6:]) + "\n", encoding="utf-8")
            self.assertEqual(self.run_cli("status")[0], 3)
        finally:
            path.write_text(original, encoding="utf-8")

    def test_rekey_after_lost_key(self):
        g = self.state()
        engine_dir = Path(g.dir) / "engine"
        key, path = engine_dir / "signing.key", engine_dir / "events.jsonl"
        self.assertTrue(key.exists())
        key.unlink()
        self.assertEqual(self.run_cli("status")[0], 3)
        # a broken chain is still refused without the key
        original = path.read_text(encoding="utf-8")
        lines = original.splitlines()
        path.write_text("\n".join(lines[:5] + lines[6:]) + "\n", encoding="utf-8")
        self.assertEqual(self.run_cli("rekey")[0], 3)
        path.write_text(original, encoding="utf-8")
        self.assertIn("Re-signed", self.ok("rekey"))
        self.ok("verify")
        self.ok("roll", "1d20", "--purpose", "after rekey")
        self.assertIn("nothing to repair", self.ok("repair"))
        # with the key present, rekey still refuses a modified log
        edited = path.read_text(encoding="utf-8")
        try:
            path.write_text(edited.replace('"hp_max":12', '"hp_max":120', 1), encoding="utf-8")
            self.assertEqual(self.run_cli("rekey")[0], 3)
        finally:
            path.write_text(edited, encoding="utf-8")
        self.ok("verify")

    # ------------------------------------------------------------------ player view hides secrets
    def test_player_view_hides_secrets(self):
        self.ok("npc", "add", "bandit-captain", "--name", "Hidden Boss", "--hidden", "--at", "2,2", "--map", "arena")
        self.ok("roll", "1d20", "--hidden", "--purpose", "secret ambush timer")
        g = self.state()
        from engine import views
        pv = json.dumps(views.player_view(g))
        self.assertNotIn("Hidden Boss", pv)
        self.assertNotIn("secret ambush timer", pv)
        svg = views.map_svg(g, "arena", "player")
        self.assertNotIn("Hidden Boss", svg)

    # ------------------------------------------------------------------ maps & assets
    def test_all_generators_render(self):
        from engine import maps, render
        for kind, kw in [("dungeon", {}), ("cave", {}), ("wilderness", {"biome": "swamp"}), ("town", {}),
                         ("interior", {"kind": "temple"}), ("region", {})] + [("arena", {"preset": p}) for p in
                         ("road-ambush", "forest-clearing", "bridge", "ruins", "crypt", "cave-chamber", "tavern-brawl")]:
            m = maps.GENERATORS[kind](1234, **kw)
            m["id"] = kind
            svg = render.render_map(m, "player")
            self.assertTrue(svg.startswith("<svg") and svg.endswith("</svg>"), kind)
            m2 = maps.GENERATORS[kind](1234, **kw)
            self.assertEqual(m["grid"], m2["grid"], f"{kind} not deterministic")

    def test_grid_geometry(self):
        from engine import maps
        m = maps.new_map("battle", "t", 10, 10)
        m["grid"][5] = "..#......."
        self.assertEqual(maps.distance_squares((0, 0), (3, 4)), 4)
        dist, parent = maps.pathfind(m, (1, 5), (3, 5))
        # diagonals may not cut a wall's corner, so going around a single wall square takes 4 moves, not 2
        self.assertEqual(dist[(3, 5)], 4)
        m["grid"][4] = "..#......."
        m["grid"][6] = "..#......."
        dist, _ = maps.pathfind(m, (1, 5), (3, 5))
        self.assertGreater(dist[(3, 5)], 4)
        m["grid"][5] = "..t......."  # difficult terrain costs double
        m["grid"][4] = m["grid"][6] = ".........."
        dist, _ = maps.pathfind(m, (1, 5), (2, 5))
        self.assertEqual(dist[(2, 5)], 2)

    def test_icons_and_cards(self):
        from engine import assets
        self.assertGreater(len(assets.icons()), 4000)
        self.assertTrue(assets.item_card({"name": "Longsword", "kind": "weapon", "base_name": "Longsword"}).startswith("<svg"))

    def test_dice_are_fair(self):
        from engine import dice
        counts = [0] * 20
        for _ in range(20000):
            counts[dice.roll("1d20")["total"] - 1] += 1
        self.assertTrue(all(800 < c < 1200 for c in counts), counts)

    def test_weapon_mastery_without_a_table_column(self):
        from engine import chargen, srd
        self.assertEqual(chargen.weapon_mastery_count(srd.find("classes", "Rogue"), 1), 2)
        self.assertEqual(chargen.weapon_mastery_count(srd.find("classes", "Ranger"), 1), 2)
        self.assertEqual(chargen.weapon_mastery_count(srd.find("classes", "Fighter"), 1), 3)
        self.assertEqual(chargen.weapon_mastery_count(srd.find("classes", "Wizard"), 1), 0)
        props, names = chargen.check_masteries(srd.find("classes", "Rogue"), 2, "rapier,dagger")
        self.assertEqual((props, names), (["vex", "nick"], ["Rapier", "Dagger"]))
        with self.assertRaises(Exception):
            chargen.check_masteries(srd.find("classes", "Rogue"), 2, "longsword,dagger")  # not proficient
        # one swap per Long Rest: after any change, a second one must wait for the next rest
        self.run_cli("char", "masteries", "kira", "--masteries", "longsword,javelin,greatsword")
        self.rule("char", "masteries", "kira", "--masteries", "longsword,javelin,dagger", contains="Long Rest")
        self.rule("char", "masteries", "wren", "--masteries", "dagger,quarterstaff", contains="no Weapon Mastery")

    def test_concentration_expires_with_duration(self):
        from engine.mechanics import concentration_minutes
        self.assertEqual(concentration_minutes({"duration": "Concentration, up to 1 minute"}), 1)
        self.assertEqual(concentration_minutes({"duration": "Concentration, up to 10 minutes"}), 10)
        self.assertEqual(concentration_minutes({"duration": "Concentration, up to 8 hours"}), 480)
        self.assertIsNone(concentration_minutes({"duration": "Concentration, until dispelled"}))
        if self.state().state.get("combat"):
            self.ok("combat", "end")
        self.ok("cast", "wren", "detect magic", "--ritual")
        self.assertEqual(self.state().get("wren")["concentration"]["spell"], "detect-magic")
        self.ok("time", "5m")
        self.assertIsNotNone(self.state().get("wren")["concentration"])
        out = self.ok("time", "5m")
        self.assertIn("duration ran out", out)
        self.assertIsNone(self.state().get("wren").get("concentration"))


if __name__ == "__main__":
    unittest.main()
