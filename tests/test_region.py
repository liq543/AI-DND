"""Hand-authored region maps: the world map of record, always open on the table, with towns and sites the players can
click for what they know, hidden places that appear when discovered, and roads the travel command follows."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class RegionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-region-"))
        cls.env = {**os.environ, "DND_CAMPAIGNS": str(cls.tmp / "campaigns"), "DND_ENGINE_HOME": str(cls.tmp / "home"),
                   "PYTHONIOENCODING": "utf-8"}
        cls.ok("campaign", "new", "Region Test")
        cls.ok("map", "gen", "region", "--id", "realm", "--w", "40", "--h", "30", "--seed", "7")
        grid = cls.tmp / "realm.txt"
        rows = ["M" * 40] + ["M" + "f" * 18 + "p" * 20 + "M" for _ in range(28)] + ["M" * 40]
        rows[15] = "M" + "F" * 38 + "M"
        grid.write_text("\n".join(rows) + "\n", encoding="utf-8")
        cls.ok("map", "import-grid", "realm", "--out", str(grid))
        cls.ok("map", "gen", "arena", "--preset", "crypt", "--seed", "3", "--id", "inn", "--show")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def ok(cls, *args):
        code, out = _cli.run(cls.env, *args)
        assert code == 0, f"{args} failed:\n{out}"
        return out

    def rule(self, *args, contains=None):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 2, f"expected a rule refusal for {args}, got:\n{out}")
        if contains:
            self.assertIn(contains, out)
        return out

    def game(self):
        return _cli.game(self.env)

    def test_world_map_towns_sites_roads_and_discovery(self):
        from engine import views
        # a region grid is checked against the region's own terrain codes
        bad = self.tmp / "bad.txt"
        bad.write_text("fff\n#ff\n", encoding="utf-8")
        self.rule("map", "import-grid", "realm", "--out", str(bad), contains="region codes")
        self.ok("map", "settlement", "realm", "5,5", "--name", "Oakhollow", "--type", "village",
                "--text", "A charcoal-burners' village under the eaves of the wood.")
        self.ok("map", "settlement", "realm", "30,20", "--name", "Kingsholt", "--type", "capital", "--text", "The royal city.")
        self.ok("map", "site", "realm", "10,25", "--name", "The Grey Barrow", "--type", "barrow", "--hidden",
                "--text", "An old hill-tomb in the deep wood, its door sealed with stone.")
        self.rule("map", "settlement", "realm", "5,5", "--name", "Twice", "--type", "town", contains="already holds")
        self.rule("map", "settlement", "realm", "6,6", "--name", "Nowhere", "--type", "metropolis", contains="--type")
        self.ok("map", "route", "realm", "road", "--path", "5,5 20,10 30,20", "--name", "the King's Road")
        # the world map is open on the table whatever the scene's map is
        self.ok("map", "set", "realm", "--kv", "world=on")
        g = self.game()
        self.assertEqual(g.state["view"]["map"], "inn")
        self.assertIn("realm", views.visible_maps(g))
        pv = views.player_view(g)
        names = {p["name"] for p in pv["maps"]["realm"]["pois"]}
        self.assertIn("Oakhollow", names)
        self.assertNotIn("The Grey Barrow", names)          # hidden until discovered
        svg = views.map_svg(g, "realm", "player")
        self.assertIn('data-poi="oakhollow"', svg)
        self.assertNotIn("Grey Barrow", svg)
        self.assertEqual(len(g.state["maps"]["realm"]["roads"]), 1)
        self.assertIn([20, 10], g.state["maps"]["realm"]["roads"][0])
        # discovering the barrow puts it on the party's map with its journal entry
        self.ok("map", "discover", "realm", "the-grey-barrow")
        g = self.game()
        self.assertIn("Grey Barrow", views.map_svg(g, "realm", "player"))
        self.assertTrue(any(j["title"] == "The Grey Barrow" for j in g.state["journal"]))
        # travel goes over the world map, faster on the road
        self.ok("map", "party", "5,5")
        out = self.ok("travel", "--to", "30,20")
        self.assertIn("miles", out)
        self.assertEqual(self.game().state["view"]["party_pos"], [30, 20])
        # and places can be struck off it
        self.rule("map", "region-remove", "realm", "--id", "oakhollow", contains="--reason")
        self.ok("map", "region-remove", "realm", "--id", "oakhollow", "--reason", "burned to the ground")
        self.assertNotIn("Oakhollow", views.map_svg(self.game(), "realm", "player"))
        self.ok("map", "region-remove", "realm", "--id", "road-1", "--reason", "the road was abandoned")
        self.assertEqual(self.game().state["maps"]["realm"]["roads"], [])


if __name__ == "__main__":
    unittest.main()
