"""The map hierarchy: region > area (a town and its quarters) > section (one quarter) > interior (a building). Where the
party stands opens every map above it; known places one level down show as tabs; nothing else tags along."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class MapHierarchyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-hierarchy-"))
        cls.env = {**os.environ, "DND_CAMPAIGNS": str(cls.tmp / "campaigns"), "DND_ENGINE_HOME": str(cls.tmp / "home"),
                   "PYTHONIOENCODING": "utf-8"}
        cls.ok("campaign", "new", "Hierarchy Test")
        cls.ok("map", "gen", "region", "--id", "realm", "--w", "40", "--h", "30", "--seed", "7")
        cls.ok("map", "set", "realm", "--kv", "world=on")
        cls.ok("map", "gen", "town", "--id", "oakhollow", "--seed", "2")
        cls.ok("map", "gen", "town", "--id", "west-ward", "--seed", "3")
        cls.ok("map", "gen", "interior", "--building", "temple", "--id", "temple", "--seed", "4")
        cls.ok("map", "gen", "interior", "--building", "tavern", "--id", "tavern", "--seed", "5")
        cls.ok("map", "gen", "arena", "--preset", "crypt", "--id", "lair", "--seed", "6", "--show")

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

    def test_hierarchy_opens_the_chain_and_orders_the_tabs(self):
        from engine import views
        self.ok("map", "set", "oakhollow", "--kv", "level=area", "--kv", "parent=realm")
        self.ok("map", "set", "west-ward", "--kv", "level=section", "--kv", "parent=oakhollow")
        self.ok("map", "set", "temple", "--kv", "level=interior", "--kv", "parent=west-ward")
        self.ok("map", "set", "tavern", "--kv", "level=interior", "--kv", "parent=west-ward")
        self.rule("map", "set", "oakhollow", "--kv", "parent=temple", contains="inside itself")
        self.rule("map", "set", "temple", "--kv", "level=castle", contains="level")
        # with the table in the lair, none of the town shows
        self.assertEqual(views.visible_maps(_cli.game(self.env)), {"realm", "lair"})
        # the table on the temple opens its quarter, its town and the region, in hierarchy order
        self.ok("map", "show", "temple")
        g = _cli.game(self.env)
        vis = views.visible_maps(g)
        self.assertTrue({"realm", "oakhollow", "west-ward", "temple"} <= vis)
        self.assertNotIn("tavern", vis)                        # an unknown sibling stays off the table
        order = list(views.player_view(g)["maps"])
        self.assertLess(order.index("realm"), order.index("oakhollow"))
        self.assertLess(order.index("oakhollow"), order.index("west-ward"))
        self.assertLess(order.index("west-ward"), order.index("temple"))
        self.assertEqual(views.player_view(g)["maps"]["temple"]["level"], "interior")
        # on the quarter, the known places inside it show one level down
        self.ok("map", "set", "tavern", "--kv", "known=on")
        self.ok("map", "show", "west-ward")
        self.assertIn("tavern", views.visible_maps(_cli.game(self.env)))
        # back to the lair, and the town closes again: nothing is linked to it for good
        self.ok("map", "show", "lair")
        self.assertEqual(views.visible_maps(_cli.game(self.env)), {"realm", "lair"})

    def test_known_town_opens_from_its_place_on_the_world_map(self):
        from engine import views
        self.ok("map", "settlement", "realm", "6,6", "--name", "Brightwater", "--type", "town")
        self.ok("map", "gen", "town", "--id", "brightwater", "--seed", "8")
        self.ok("map", "set", "brightwater", "--kv", "level=area", "--kv", "parent=realm")
        self.rule("map", "set", "brightwater", "--kv", "anchor=nowhere", contains="anchor")
        self.ok("map", "set", "brightwater", "--kv", "anchor=brightwater")
        self.ok("map", "show", "lair")
        g = _cli.game(self.env)
        self.assertNotIn("brightwater", views.openable_maps(g))     # never visited: the town stays a name on the map
        self.ok("map", "set", "brightwater", "--kv", "known=on")
        self.ok("map", "show", "lair")
        g = _cli.game(self.env)
        self.assertNotIn("brightwater", views.visible_maps(g))      # no tab of its own while the party is elsewhere
        self.assertIn("brightwater", views.openable_maps(g))        # but clicking the town opens it
        pv = views.player_view(g)["maps"]["brightwater"]
        self.assertEqual((pv["anchor"], pv["tab"], pv["parent"]), ("brightwater", False, "realm"))


if __name__ == "__main__":
    unittest.main()
