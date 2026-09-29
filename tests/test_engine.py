"""End-to-end tests of the rules engine through its real CLI, in an isolated temp directory.

Run:  python -m unittest discover -s tests -v
"""
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
        self.assertIn("nothing was changed", out)
        if contains:
            self.assertIn(contains, out)
        return out

    def state(self):
        from importlib import reload
        os.environ.update({k: v for k, v in self.env.items() if k.startswith("DND_")})
        import engine.store as st
        reload(st)
        import engine.core as core
        reload(core)
        return core.Game(st.active_dir())

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


if __name__ == "__main__":
    unittest.main()
