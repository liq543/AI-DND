"""Generated art (characters, creatures, items), DM-controlled table animation (`fx`), and the animation cues the
live table receives. Cues must never show what the players can't see.

Run:  python -m unittest discover -s tests -v
"""
import _cli  # noqa: E402  (in-process CLI runner)
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import art, itemart  # noqa: E402


def well_formed(svg):
    ET.fromstring(svg)
    return True


class ArtUnitTest(unittest.TestCase):
    def pc(self, **kw):
        base = {"id": "kira", "kind": "pc", "name": "Kira Vale", "species": "Human", "classes": {"Fighter": 3}, "inventory": [], "bio": {}}
        return {**base, **kw}

    def test_every_species_and_class_draws_valid_svg(self):
        for sp in ("Human", "Elf", "Dwarf", "Halfling", "Gnome", "Orc", "Tiefling", "Dragonborn", "Goliath"):
            for cls in art.CLASS_STYLE:
                e = self.pc(id=f"{sp}-{cls}", name=f"{sp} {cls}", species=sp, classes={cls: 1})
                self.assertTrue(well_formed(art.portrait_svg(e)))
                self.assertTrue(well_formed(art.face_svg(e)))

    def test_description_drives_the_look(self):
        e = self.pc(bio={"appearance": "Short auburn hair, green eyes, a scar across her left cheek, and an eyepatch over her right eye."})
        L = art.look_of(e)
        self.assertEqual(L["hair_color"], art.HAIR_COLORS["auburn"])
        self.assertEqual(L["hair_style"], "short")
        self.assertEqual(L["eye_color"], art.EYE_COLORS["green"])
        self.assertEqual(L["scars"][0], {"side": "left", "where": "cheek"})
        self.assertEqual(L["eyepatch"], "right")
        self.assertEqual(L["presentation"], "feminine")

    def test_look_fields_override_the_description(self):
        e = self.pc(bio={"appearance": "black hair"}, look={"hair": "long silver braid", "eyes": "glowing violet", "headwear": "hood"})
        L = art.look_of(e)
        self.assertEqual(L["hair_color"], art.HAIR_COLORS["silver"])
        self.assertEqual(L["hair_style"], "braid")
        self.assertTrue(L["eye_glow"])
        self.assertEqual(L["headwear"], "hood")

    def test_headwear_needs_the_whole_word(self):
        for text in ("A clerk, fifty crowns richer.", "The captain's cape snaps in the wind.", "She climbs out of the hatch."):
            self.assertNotIn(art.read_description(text).get("headwear"), ("crown", "hat"), text)
        self.assertEqual(art.read_description("A tarnished crown on his brow.")["headwear"], "crown")
        self.assertEqual(art.read_description("Two battered caps.")["headwear"], "hat")
        self.assertEqual(art.read_description("Sixty, grey hair wild and loose.")["age"], "old")

    def test_body_scars_and_spectacles(self):
        self.assertNotIn("scars", art.read_description("A thin white scar across his left palm, scarred knuckles."))
        self.assertEqual(art.read_description("A duelling scar through one eyebrow.")["scars"][0]["where"], "eye")
        L = art.look_of(self.pc(bio={"appearance": "Half-moon spectacles and a silver eyepatch over his left eye."}))
        self.assertEqual((L["spectacles"], L["eyepatch"], L["eyepatch_color"]), ("half-moon", "left", "#c9cdd2"))
        self.assertIn("<svg", art.portrait_svg(self.pc(bio={"appearance": "round spectacles"})))

    def test_worn_armor_sets_the_outfit(self):
        e = self.pc(inventory=[{"kind": "armor", "equipped": True, "category": "heavy", "name": "Plate Armor"}])
        self.assertEqual(art.look_of(e)["outfit"], "plate")

    def test_art_is_deterministic_and_versioned(self):
        e = self.pc()
        self.assertEqual(art.portrait_svg(e), art.portrait_svg(dict(e)))
        v1 = art.art_version(e)
        self.assertNotEqual(v1, art.art_version(self.pc(look={"hair": "red"})))

    def test_creatures_get_creature_art(self):
        wolf = {"id": "wolf", "kind": "npc", "name": "Dire Wolf", "type": "beast", "side": "enemy", "size": "Large"}
        guard = {"id": "g", "kind": "npc", "name": "Guard", "srd_name": "Guard", "type": "humanoid", "side": "neutral"}
        self.assertFalse(art.is_humanlike(wolf))
        self.assertTrue(art.is_humanlike(guard))
        self.assertTrue(well_formed(art.portrait_svg(wolf)) and well_formed(art.face_svg(wolf)))
        self.assertEqual(art.look_of(guard)["outfit"], "chain")

    def test_every_item_form_draws_valid_svg(self):
        for key, form in itemart.FORMS:
            it = {"id": key, "name": key.title(), "kind": "gear", "magic": True, "rarity": "Rare", "identified": True}
            self.assertEqual(itemart.form_of(it), form, key)
            self.assertTrue(well_formed(itemart.item_svg(it)), key)
        self.assertEqual(itemart._lint(), [])

    def test_unidentified_items_keep_their_secrets(self):
        it = {"id": "p1", "name": "Potion of Fire Breath", "kind": "consumable", "magic": True, "rarity": "Uncommon", "identified": False}
        fire = itemart.lighten("#f06a1a", .45)    # fire-breath orange comes from the true name
        svg = itemart.item_svg(it)
        self.assertNotIn(fire, svg)
        self.assertNotIn(itemart.RARITY_GLOW["Uncommon"], svg)
        self.assertIn(">?<", svg)
        known = itemart.item_svg(dict(it, identified=True))
        self.assertIn(fire, known)
        self.assertIn(itemart.RARITY_GLOW["Uncommon"], known)

    def test_materials_from_name_and_note(self):
        pal = itemart.palette({"id": "d", "name": "Dagger", "note": "a silver blade with a ruby pommel", "kind": "weapon"})
        self.assertEqual(pal["metal"], itemart.METALS["silver"])
        self.assertEqual(pal["gem"], itemart.GEMS["ruby"])


class VisualsCliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-vis-"))
        cls.env = {**os.environ, "DND_CAMPAIGNS": str(cls.tmp / "campaigns"), "DND_ENGINE_HOME": str(cls.tmp / "home"),
                   "PYTHONIOENCODING": "utf-8"}
        cls.ok("campaign", "new", "Visual Test")
        cls.ok("char", "create", "--name", "Kira Vale", "--class", "Fighter", "--species", "Human", "--background", "Soldier",
               "--method", "standard", "--scores", "str=15,dex=13,con=14,int=8,wis=12,cha=10", "--bonus", "str+2,con+1",
               "--skills", "perception,survival", "--languages", "Elvish,Dwarvish", "--species-skill", "insight",
               "--species-feat", "Alert", "--fighting-style", "Defense", "--masteries", "longsword,javelin,greatsword")
        cls.ok("map", "gen", "arena", "--preset", "crypt", "--seed", "3", "--id", "arena", "--show")
        cls.ok("place", "kira", "5,5", "--map", "arena")
        cls.ok("npc", "add", "goblin-warrior", "--name", "Snag", "--at", "6,5", "--map", "arena")
        cls.ok("npc", "add", "goblin-warrior", "--name", "Lurker", "--at", "9,8", "--map", "arena", "--hidden")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def run_engine(cls, *args):
        return _cli.run(cls.env, *args)

    @classmethod
    def ok(cls, *args):
        code, out = cls.run_engine(*args)
        assert code == 0, f"{args} failed:\n{out}"
        return out

    def rule(self, *args):
        code, out = self.run_engine(*args)
        self.assertEqual(code, 2, out)
        return out

    def game(self):
        return _cli.game(self.env)

    def view(self):
        from engine import views
        return views.player_view(self.game())

    def test_journal_files_map_objects_apart_from_clues(self):
        # map objects (points of interest) go to "Places & objects", never into "Handouts & clues"
        self.ok("map", "poi", "arena", "1,1", "--name", "Old Well", "--text", "A mossy well with a rusted chain.")
        self.ok("map", "poi", "arena", "2,1", "--name", "Bloodied Altar", "--text", "Fresh blood on the stone.", "--clue")
        self.ok("journal", "add", "The ferryman owes money to the guild.", "--title", "The Ferryman's Debt")
        j = {e["title"]: e for e in self.view()["journal"]}
        self.assertEqual(j["Old Well"]["cat"], "place")
        self.assertTrue(j["Old Well"]["where"])
        self.assertEqual(j["Bloodied Altar"]["cat"], "clue")
        self.assertEqual(j["The Ferryman's Debt"]["cat"], "clue")
        # the DM can refile an entry either way
        self.ok("journal", "file", j["Old Well"]["id"], "--as", "clue")
        self.ok("journal", "file", j["The Ferryman's Debt"]["id"], "--as", "place")
        j = {e["title"]: e for e in self.view()["journal"]}
        self.assertEqual(j["Old Well"]["cat"], "clue")
        self.assertEqual(j["The Ferryman's Debt"]["cat"], "place")
        self.rule("journal", "file", "j9999", "--as", "clue")
        self.rule("journal", "file", j["Old Well"]["id"])

    def test_journal_edit_corrects_a_handout_and_says_so(self):
        self.ok("journal", "add", "The ferry runs at dawn.", "--title", "Ferry Times")
        jid = next(e["id"] for e in self.view()["journal"] if e["title"] == "Ferry Times")
        out = self.ok("journal", "edit", jid, "--text", "The ferry runs at dusk.")
        self.assertIn("revised", out)
        j = {e["title"]: e for e in self.view()["journal"]}
        self.assertEqual(j["Ferry Times"]["text"], "The ferry runs at dusk.")
        self.ok("journal", "edit", jid, "--title", "Ferry Timetable")
        self.assertIn("Ferry Timetable", {e["title"] for e in self.view()["journal"]})
        self.rule("journal", "edit", "j9999", "--text", "nothing")
        self.rule("journal", "edit", jid)

    def test_doors_line_up_with_the_wall_or_bars_they_hang_in(self):
        from engine.render import door_horizontal
        grid = ["#######",
                "#.....#",
                "#NNDNN#",     # a cell door in a row of bars
                "#.....#",
                "##ddd##",     # a triple door in a wall
                "#.....#",
                "d.....#",     # a door in a side wall
                "#######"]
        self.assertTrue(door_horizontal(grid, 3, 2))
        self.assertTrue(all(door_horizontal(grid, x, 4) for x in (2, 3, 4)))
        self.assertFalse(door_horizontal(grid, 0, 6))

    def test_map_unlabel_removes_a_stale_label(self):
        self.ok("map", "label", "arena", "3,3", "--name", "Gate (down)")
        self.ok("map", "label", "arena", "4,4", "--name", "Old Mill")
        self.ok("map", "unlabel", "arena", "3,3")
        texts = [l["text"] for l in self.game().state["maps"]["arena"]["labels"]]
        self.assertNotIn("Gate (down)", texts)
        self.assertIn("Old Mill", texts)
        self.rule("map", "unlabel", "arena", "3,3")

    def test_map_set_takes_several_settings(self):
        self.ok("map", "set", "arena", "--kv", "theme=stone", "--kv", "walls=ashlar", "--kv", "lighting=dim")
        m = self.game().state["maps"]["arena"]
        self.assertEqual((m.get("theme"), m.get("style_walls"), m.get("lighting")), ("stone", "ashlar", "dim"))

    def test_asset_look_and_art(self):
        out = self.ok("asset", "look", "kira", "--hair", "long silver braid", "--eyes", "green")
        self.assertIn("hair braid", out)
        g = self.game()
        self.assertEqual(g.state["entities"]["kira"]["look"], {"hair": "long silver braid", "eyes": "green"})
        self.ok("asset", "look", "kira", "--clear", "eyes")
        self.assertEqual(self.game().state["entities"]["kira"]["look"], {"hair": "long silver braid"})
        self.rule("asset", "look", "kira", "--clear", "nose")
        path = self.tmp / "kira.svg"
        self.ok("asset", "art", "kira", "--out", str(path))
        self.assertTrue(well_formed(path.read_text(encoding="utf-8")))
        self.ok("asset", "art", "srd:potion-of-healing", "--out", str(self.tmp / "p.svg"))

    def test_fx_settings_and_validation(self):
        self.ok("fx", "preset", "quick")
        self.assertEqual(self.game().state["view"]["anim"]["speed"], 2.0)
        self.ok("fx", "set", "speed=0.5", "camera=off", "tokens=icon")
        a = self.game().state["view"]["anim"]
        self.assertEqual((a["speed"], a["camera"], a["tokens"]), (0.5, "off", "icon"))
        self.rule("fx", "set", "speed=9")
        self.rule("fx", "set", "wobble=on")
        self.rule("fx", "play", "burst")                 # needs a place
        self.rule("fx", "play", "beam", "--from", "kira")
        self.rule("fx", "play", "burst", "--on", "kira", "--color", "plaid")
        self.ok("fx", "ambient", "rain", "--intensity", "0.4")
        self.ok("fx", "preset", "standard")
        self.ok("fx", "set", "tokens=art", "camera=follow")

    def test_cues_follow_play_and_hide_secrets(self):
        self.ok("fx", "play", "burst", "--on", "snag", "--color", "fire", "--radius", "10")
        self.ok("fx", "play", "banner", "--text", "The floor shakes")
        self.ok("fx", "play", "ping", "--on", "lurker")      # the DM may point at a hidden creature, but players don't see it
        self.ok("move", "lurker", "9,9", "--force", "test: it creeps")
        self.ok("combat", "start")
        try:
            v = self.view()
            cues = v["cues"]
            fx = [c for c in cues if c["k"] == "fx"]
            self.assertEqual(fx[-2]["fx"], "burst")
            self.assertEqual(fx[-2]["at"], {"id": "snag"})
            self.assertEqual(fx[-1]["label"], "The floor shakes")
            self.assertFalse(any(c.get("who") == "lurker" or c.get("target") == "lurker" for c in cues))
            self.assertFalse(any((c.get("at") or {}) == {"id": "lurker"} for c in cues if c["k"] == "fx"))
            self.assertTrue(any(c["k"] == "combat" and c.get("phase") == "start" for c in cues))
            from engine import mechanics as M
            g = self.game()
            if not g.get(M.current_id(g)).get("hidden"):  # a hidden creature's turn is (rightly) not announced
                self.assertTrue(any(c["k"] == "turn" for c in cues))
            self.assertIn("art", v["party"][0])
            self.assertTrue(all("art" in i for i in v["party"][0]["inventory"]))
        finally:
            self.ok("combat", "end")

    def test_story_lines_anchor_to_visible_tokens(self):
        self.ok("place", "kira", "5,5", "--map", "arena")
        self.ok("say", "--as", "Kira", "Stay behind me.")
        self.ok("say", "--at", "snag", "The goblin edges toward the door.")
        self.ok("say", "--at", "lurker", "Something moves in the dark.")     # hidden: no anchor, no leak
        cues = [c for c in self.view()["cues"] if c["k"] in ("speech", "narration")][-3:]
        self.assertEqual((cues[0]["k"], cues[0]["who"]), ("speech", "kira"))
        self.assertEqual((cues[1]["k"], cues[1]["who"]), ("narration", "snag"))
        self.assertIsNone(cues[2]["who"])
        self.assertTrue(all(c.get("ts") for c in cues))
        self.ok("say", "--at", "kira-vale", "Kira checks her straps.")        # a hyphenated name finds its token too
        self.assertEqual([c for c in self.view()["cues"] if c["k"] == "narration"][-1]["who"], "kira")
        self.ok("npc", "add", "commoner", "--name", "Marta, the smith", "--at", "8,5", "--map", "arena")
        self.ok("say", "--as", "Marta", "I heard every word.")               # a comma after the first name still finds her
        self.assertEqual([c for c in self.view()["cues"] if c["k"] == "speech"][-1]["who"], "marta-the-smith")

    def test_token_names_are_readable_and_never_overlap(self):
        from engine import render
        sl = lambda n: render.short_label({"name": n, "id": "x"})  # noqa: E731
        self.assertEqual([sl("Old Brenna Holt"), sl("The Lamplighter"), sl("Goblin Warrior B"), sl("Stone Guardian (east)"),
                          sl("Oswin Hale (Night Clerk)"), sl("Captain Rhosk"), sl("Kira Vale")],
                         ["Brenna", "Lamplighter", "Warrior B", "Guardian E", "Oswin", "Rhosk", "Kira"])
        # four creatures shoulder to shoulder, and a block of nine: no two name tags may overlap
        for layout in ([(x, 5) for x in range(4)], [(x, y) for x in range(3) for y in range(3)]):
            toks = []
            for i, (x, y) in enumerate(layout):
                e = {"id": f"t{i}", "name": f"Longname Person{i}", "kind": "pc", "token": {"x": x, "y": y}}
                toks.append((e, x * 32 + 16, y * 32 + 16, 16))
            placed = render._layout_labels(toks, 32)
            boxes = [(lx - w / 2, ly - 8.5, lx + w / 2, ly + 2.5) for _, lx, ly, w in placed.values()]
            for i, a in enumerate(boxes):
                for b in boxes[i + 1:]:
                    self.assertFalse(a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1], (layout, a, b))

    def test_containers_and_stacked_floor_items(self):
        from engine import views
        self.ok("place", "kira", "5,5", "--map", "arena")
        self.ok("item", "add", "kira", "Torch", "--qty", "2", "--source", "found: a sconce")
        self.ok("item", "add", "kira", "Rope", "--source", "found: a peg")
        inv = self.game().get("kira")["inventory"]
        torch = next(i["id"] for i in inv if i["name"] == "Torch")
        rope = next(i["id"] for i in inv if i["name"].startswith("Rope"))
        self.ok("item", "drop", "kira", torch)                 # two different items on one tile
        self.ok("item", "drop", "kira", rope)
        m = self.view()["maps"]["arena"]
        self.assertEqual(sum(1 for f in m["floor"] if (f["x"], f["y"]) == (5, 5)), 2)
        svg = views.map_svg(self.game(), "arena", "player")
        self.assertEqual(svg.count('data-tile="5,5"'), 1)      # one marker for the tile, not one per item
        # turning the tile into a chest puts what's already there inside it
        self.ok("map", "container", "arena", "5,5", "--name", "Old sea-chest", "--id", "chest-t")
        m = self.view()["maps"]["arena"]
        self.assertEqual(m["containers"][0]["name"], "Old sea-chest")
        self.assertTrue(all(f["in"] == "chest-t" for f in m["floor"] if (f["x"], f["y"]) == (5, 5)))
        self.ok("item", "add", "kira", "Torch", "--source", "found: another sconce")
        torch2 = next(i["id"] for i in self.game().get("kira")["inventory"] if i["name"] == "Torch")
        self.ok("item", "stash", "kira", torch2, "--to", "chest-t")
        self.assertEqual(sum(1 for f in self.view()["maps"]["arena"]["floor"] if f.get("in") == "chest-t"), 3)
        self.assertIn('data-box="chest-t"', views.map_svg(self.game(), "arena", "player"))
        self.rule("item", "stash", "kira", "longsword-1", "--to", "nope")
        for f in [f for f in self.game().state["maps"]["arena"]["floor"] if (f["x"], f["y"]) == (5, 5)]:
            self.ok("item", "pickup", "kira", f["id"])
        self.ok("map", "container-remove", "arena", "--id", "chest-t", "--reason", "test cleanup")

    def test_creatures_who_leave_keep_their_faces(self):
        self.ok("npc", "add", "commoner", "--name", "Oswin Hale", "--at", "8,8", "--map", "arena")
        self.ok("npc", "add", "bandit", "--name", "Never Seen", "--hidden", "--at", "9,9", "--map", "arena")
        try:
            self.ok("say", "--as", "Oswin Hale", "I'm off, then.")
            self.ok("npc", "hide", "oswin-hale")                    # he walks off the table
            from engine import views
            off = {o["id"] for o in self.view()["offstage"]}
            self.assertIn("oswin-hale", off)
            self.assertNotIn("never-seen", off)
            g = self.game()
            self.assertTrue(views.seen_by_players(g, g.get("oswin-hale")))
            self.assertFalse(views.seen_by_players(g, g.get("never-seen")))
        finally:
            self.ok("npc", "remove", "oswin-hale")
            self.ok("npc", "remove", "never-seen")

    def test_renaming_a_hidden_creature_stays_secret(self):
        self.ok("npc", "add", "bandit", "--name", "Captain Rhosk", "--hidden", "--at", "3,3")
        try:
            self.ok("npc", "rename", "captain-rhosk", "--name", "A Hooded Stranger")
            self.assertFalse(any("Rhosk" in (f.get("text") or "") for f in self.view()["feed"]))
        finally:
            self.ok("npc", "remove", "captain-rhosk")

    def test_server_serves_art(self):
        _cli.point_at(self.env)
        import engine.server as server
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            state = json.loads(urllib.request.urlopen(base + "/api/state").read())
            item = state["party"][0]["inventory"][0]["id"]
            for path in ("/api/art/portrait/kira.svg", "/api/art/face/snag.svg", "/api/token/kira.svg", f"/api/art/item/kira/{item}.svg",
                         "/api/art/item/srd/potion-of-healing.svg", "/api/map/arena.svg"):
                body = urllib.request.urlopen(base + path).read().decode()
                self.assertTrue(well_formed(body), path)
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(base + "/api/art/face/lurker.svg")      # hidden creatures stay hidden
            live_map = urllib.request.urlopen(base + "/api/map/arena.svg").read().decode()
            self.assertTrue("/api/art/face/kira.svg" in live_map, "live map tokens use generated faces")
            # an item on the floor (or in a container) has an info card too
            self.ok("place", "kira", "5,5", "--map", "arena")
            self.ok("item", "add", "kira", "Crowbar", "--source", "found: a toolbox")
            bar = next(i["id"] for i in self.game().get("kira")["inventory"] if i["name"] == "Crowbar")
            self.ok("item", "drop", "kira", bar)
            fl = next(f["id"] for f in self.game().state["maps"]["arena"]["floor"] if f["item"]["name"] == "Crowbar")
            card = json.loads(urllib.request.urlopen(f"{base}/api/item/floor~arena/{fl}").read())
            self.assertEqual(card["name"], "Crowbar")
            self.assertTrue(well_formed(urllib.request.urlopen(f"{base}/api/art/floor/arena/{fl}.svg").read().decode()))
            self.ok("item", "pickup", "kira", fl)
        finally:
            httpd.shutdown()


if __name__ == "__main__":
    unittest.main()
