"""Wall of Fire stands on the map: drawn when cast, creatures on its squares save, its burning side hurts anyone who
ends a turn within 10 ft of it, entering it burns, it blocks sight, and it is gone when Concentration ends."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class WallOfFireTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-wof-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Wall Test")
        self.ok("char", "create", "--name", "Wren Ashdown", "--class", "Wizard", "--species", "Elf", "--background", "Sage",
                "--method", "pointbuy", "--scores", "str=8,dex=14,con=14,int=15,wis=12,cha=8", "--bonus", "int+2,con+1",
                "--skills", "investigation,medicine", "--languages", "Elvish,Draconic", "--species-skill", "perception",
                "--mi-cantrips", "light,mage hand", "--mi-spell", "shield")
        g = _cli.game(self.env)
        g.set(g.get("wren"), granted_spells=[{"slug": "wall-of-fire", "source": "test fixture", "ability": "int"}])
        g.commit()
        self.ok("map", "gen", "wilderness", "--biome", "plains", "--w", "24", "--h", "16", "--id", "field", "--seed", "2", "--show")
        self.ok("map", "paint", "field", " ".join(f"{x},{y}" for x in range(24) for y in range(16)), "--char", ".")
        self.ok("place", "wren", "2,2", "--map", "field")
        self.ok("npc", "add", "ogre", "--at", "8,8", "--map", "field", "--name", "Grub")      # on the wall
        self.ok("npc", "add", "ogre", "--at", "10,10", "--map", "field", "--name", "Mash")    # 10 ft south of it
        self.ok("npc", "add", "ogre", "--at", "10,5", "--map", "field", "--name", "Bok")      # north: the cool side
        self.ok("combat", "start")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def to_turn(self, who):
        for _ in range(12):
            g = _cli.game(self.env)
            c = g.state["combat"]
            if c["order"][c["turn"]]["id"] == who:
                return
            self.ok("combat", "next")
        self.fail(f"never reached {who}'s turn")

    def cast(self):
        self.to_turn("wren")
        return self.ok("cast", "wren", "wall of fire", "--free", "test fixture", "--wall", "5,8 16,8", "--hot", "south")

    def test_drawn_and_saves_on_its_squares(self):
        out = self.cast()
        self.assertIn("Grub", out)
        self.assertNotIn("Mash — DEX", out)
        g = _cli.game(self.env)
        w = g.state["maps"]["field"]["spell_walls"][0]
        self.assertEqual(len(w["cells"]), 12)
        self.assertIn([10, 10], w["hot"])
        self.assertNotIn([10, 5], w["hot"])
        # round the ends: level with the wall or on the burning side, within 10 ft, burns; the cool side never does
        for sq in ([4, 8], [3, 8], [17, 8], [3, 10], [18, 9]):
            self.assertIn(sq, w["hot"])
        for sq in ([4, 7], [17, 6], [2, 8], [19, 8]):
            self.assertNotIn(sq, w["hot"])
        svg = self.ok("map", "render", "field")
        self.assertTrue(svg)

    def test_burning_side_hurts_at_end_of_turn_and_cool_side_does_not(self):
        self.cast()
        hp_mash = _cli.game(self.env).get("mash")["hp"]
        hp_bok = _cli.game(self.env).get("bok")["hp"]
        self.to_turn("mash")
        self.ok("combat", "next")
        self.assertLess(_cli.game(self.env).get("mash")["hp"], hp_mash)
        self.to_turn("bok")
        self.ok("combat", "next")
        self.assertEqual(_cli.game(self.env).get("bok")["hp"], hp_bok)

    def test_blocks_sight(self):
        from engine import maps
        self.cast()
        m = _cli.game(self.env).state["maps"]["field"]
        self.assertFalse(maps.has_los(m, (10, 5), (10, 11)))
        self.assertTrue(maps.has_los(m, (2, 5), (2, 11)))

    def test_entering_burns_once(self):
        self.cast()
        self.to_turn("bok")
        hp = _cli.game(self.env).get("bok")["hp"]
        self.ok("move", "bok", "10,7")
        self.ok("move", "bok", "10,8")
        after = _cli.game(self.env).get("bok")["hp"]
        self.assertLess(after, hp)

    def test_auto_route_goes_round_the_wall(self):
        self.cast()
        self.to_turn("mash")
        hp = _cli.game(self.env).get("mash")["hp"]
        self.ok("move", "mash", "4,9")          # alongside the wall, west: the route must not cut through it
        g = _cli.game(self.env)
        self.assertEqual(g.get("mash")["hp"], hp)
        code, out = _cli.run(self.env, "move", "mash", "10,6")   # across it: only through the fire, so refused
        self.assertNotEqual(code, 0)

    def test_a_creature_the_wall_kills_stops_there_and_moves_no_more(self):
        self.cast()
        self.to_turn("bok")
        g = _cli.game(self.env)
        g.set(g.get("bok"), hp=1)
        g.commit()
        self.ok("move", "bok", "10,9", "--path", "10,6 10,7 10,8 10,9")
        g = _cli.game(self.env)
        self.assertEqual((g.get("bok")["token"]["x"], g.get("bok")["token"]["y"]), (10, 8))
        code, out = _cli.run(self.env, "move", "bok", "10,10")
        self.assertNotEqual(code, 0)

    def test_gone_when_concentration_ends(self):
        import engine.mechanics as M
        self.cast()
        g = _cli.game(self.env)
        M.end_concentration(g, g.get("wren"), "test")
        g.commit()
        self.assertFalse(_cli.game(self.env).state["maps"]["field"].get("spell_walls"))

    def test_ending_a_short_fight_leaves_the_wall_its_minute(self):
        self.cast()
        self.ok("combat", "end")
        g = _cli.game(self.env)
        self.assertTrue(g.state["maps"]["field"].get("spell_walls"))
        self.assertEqual((g.get("wren").get("concentration") or {}).get("spell"), "wall-of-fire")

    def test_too_long_is_refused(self):
        self.to_turn("wren")
        code, out = _cli.run(self.env, "cast", "wren", "wall of fire", "--free", "test fixture", "--wall", "1,8 20,8", "--hot", "south")
        self.assertNotEqual(code, 0)
        self.assertIn("60 ft", out)


if __name__ == "__main__":
    unittest.main()
