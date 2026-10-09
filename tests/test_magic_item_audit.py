"""SRD magic items that need the engine's help (rules/magic-items): magic ammunition fired from a magic weapon, worn
items that change attack rolls and Perception, attunement limits and prerequisites, items that cast spells (charges,
at will) and Spell Scrolls (the scroll's own save DC)."""
import _cli  # noqa: E402  (in-process CLI runner)
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from engine import mechanics as M
from engine.core import armor_class, derive, weapon_attack


class MagicItemTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd-test-items-"))
        self.env = {**os.environ, "DND_CAMPAIGNS": str(self.tmp / "campaigns"), "DND_ENGINE_HOME": str(self.tmp / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.ok("campaign", "new", "Item Test")
        self.ok("char", "create", "--name", "Kira Vale", "--class", "Fighter", "--species", "Human", "--background", "Soldier",
                "--method", "standard", "--scores", "str=15,dex=13,con=14,int=8,wis=12,cha=10", "--bonus", "str+2,con+1",
                "--skills", "perception,survival", "--equipment", "A", "--bg-equipment", "A",
                "--species-skill", "insight", "--species-feat", "Alert", "--fighting-style", "Defense",
                "--masteries", "longsword,greatsword,javelin", "--languages", "Elvish,Dwarvish")
        # Int 10: her own spell save DC (8 + 0 + 2 = 10) differs from a scroll's DC 13
        self.ok("char", "create", "--name", "Wren Ashdown", "--class", "Wizard", "--species", "Dwarf", "--background", "Sage",
                "--method", "standard", "--scores", "str=8,dex=13,con=14,int=10,wis=12,cha=15", "--bonus", "con+2,wis+1",
                "--skills", "investigation,insight", "--languages", "Dwarvish,Draconic",
                "--mi-cantrips", "light,prestidigitation", "--mi-spell", "shield")
        self.ok("spells", "set", "wren", "--cantrips", "fire bolt,ray of frost,minor illusion",
                "--prepared", "magic missile,sleep,burning hands,mage armor",
                "--spellbook", "magic missile,shield,sleep,burning hands,detect magic,mage armor")
        self.ok("map", "gen", "wilderness", "--biome", "plains", "--w", "20", "--h", "14", "--id", "field", "--seed", "2", "--show")
        self.ok("place", "kira", "5,5", "--map", "field")
        self.ok("place", "wren", "5,7", "--map", "field")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, *args):
        code, out = _cli.run(self.env, *args)
        self.assertEqual(code, 0, f"{args} failed:\n{out}")
        return out

    def rule(self, *args, contains=""):
        code, out = _cli.run(self.env, *args)
        self.assertNotEqual(code, 0, f"{args} should have been refused:\n{out}")
        self.assertIn(contains, out)
        return out

    def g(self):
        return _cli.game(self.env)

    def get(self, who):
        return self.g().get(who)

    def add(self, who, name, qty=1):
        before = {i["id"] for i in self.get(who)["inventory"]}
        self.ok("item", "add", who, name, "--qty", str(qty), "--source", "loot: test hoard", "--identified",
                "--override", "test fixture item")
        new = [i["id"] for i in self.get(who)["inventory"] if i["id"] not in before]
        return new[0] if new else next(i["id"] for i in self.get(who)["inventory"] if i["name"] == name)

    def item(self, who, item_id):
        return next((i for i in self.get(who)["inventory"] if i["id"] == item_id), None)

    def fight(self, *foes):
        for foe, at in foes:
            self.ok("npc", "add", foe[0], "--at", at, "--map", "field", "--name", foe[1], "--side", "enemy")
        self.ok("combat", "start")

    def turn(self, who):
        for _ in range(12):
            if M.current_id(self.g()) == who:
                return
            self.ok("combat", "next")
        self.fail(f"never reached {who}'s turn")

    # ------------------------------------------------------------------ ammunition
    def test_magic_ammunition_stacks_with_a_magic_bow_and_is_chosen_with_ammo(self):
        bow = self.add("kira", "Shortbow +2")
        plus = self.add("kira", "Arrows +1", 20)
        self.ok("item", "unequip", "kira", "greatsword-1")
        self.ok("item", "equip", "kira", bow)
        kira = self.get("kira")
        plain = weapon_attack(kira, self.item("kira", bow))
        magic = weapon_attack(kira, self.item("kira", bow), ammo_bonus=1)
        self.assertEqual(magic["bonus"] - plain["bonus"], 1)               # +2 bow and +1 arrow: +3 in all
        self.assertEqual(plain["bonus"], 1 + 2 + 2)                         # Dex +1, proficiency +2, bow +2
        self.assertTrue(magic["damage"].endswith("+4"))                     # Dex +1, bow +2, arrow +1
        self.fight((("ogre", "Big Ogre"), "12,5"))
        self.turn("kira")
        plain_arrows = next(i["id"] for i in self.get("kira")["inventory"] if i["name"] == "Arrows")
        n_plain = self.item("kira", plain_arrows)["qty"]
        out = self.ok("attack", "kira", "big-ogre", bow, "--now")         # default: plain arrows first
        self.assertIn("1d20(", out)
        self.assertNotIn("Arrows +1", out)
        self.assertEqual(self.item("kira", plain_arrows)["qty"], n_plain - 1)
        self.assertEqual(self.item("kira", plus)["qty"], 20)
        self.ok("combat", "next")
        self.turn("kira")
        out = self.ok("attack", "kira", "big-ogre", bow, "--now", "--ammo", plus)
        self.assertIn("Shortbow +2 (Arrows +1)", out)
        self.assertIn(f"+{plain['bonus'] + 1} =", out)
        self.assertEqual(self.item("kira", plus)["qty"], 19)
        self.ok("combat", "next")
        self.turn("kira")
        self.rule("attack", "kira", "big-ogre", bow, "--now", "--ammo", "javelin-1", contains="isn't ammunition")

    def test_player_roll_keeps_the_chosen_ammunition(self):
        bow = self.add("kira", "Shortbow +2")
        plus = self.add("kira", "Arrows +1", 2)
        self.ok("item", "unequip", "kira", "greatsword-1")
        self.ok("item", "equip", "kira", bow)
        self.fight((("ogre", "Big Ogre"), "12,5"))
        self.turn("kira")
        self.ok("set", "player_rolls=viewer")
        self.ok("attack", "kira", "big-ogre", bow, "--ammo", plus)
        self.assertEqual(self.item("kira", plus)["qty"], 1)                # spent when the shot is declared
        rid = next(iter(self.g().state["requests"]))
        out = self.ok("request", "roll", rid)
        self.assertIn("Shortbow +2 (Arrows +1)", out)

    def test_magic_ammunition_that_missed_is_recovered_as_magic(self):
        bow = self.add("kira", "Shortbow +2")
        plus = self.add("kira", "Arrows +1", 10)
        self.ok("item", "unequip", "kira", "greatsword-1")
        self.ok("item", "equip", "kira", bow)
        self.fight((("ogre", "Big Ogre"), "12,5"))
        for _ in range(4):
            self.turn("kira")
            self.ok("attack", "kira", "big-ogre", bow, "--now", "--ammo", plus)
            self.ok("combat", "next")
        c = self.g().state["combat"]
        hits = c.get("ammo_magic_hits", {}).get("kira", {}).get("Arrows +1", 0)
        self.ok("combat", "end")
        misses = 4 - hits
        if misses // 2:
            self.ok("item", "recover-ammo", "kira", "Arrows +1")
            self.assertEqual(self.item("kira", plus)["qty"], 6 + misses // 2)
        else:
            self.rule("item", "recover-ammo", "kira", "Arrows +1", contains="Too little")
        if (4 - misses) // 2:
            self.ok("item", "recover-ammo", "kira", "Arrows")               # the pieces that hit come back plain

    # ------------------------------------------------------------------ armor, AC, saves
    def test_plate_plus_one_needs_no_attunement(self):
        plate = self.add("kira", "Plate Armor +1")
        self.ok("item", "equip", "kira", plate)
        ac, why = armor_class(self.get("kira"))
        self.assertEqual(ac, 18 + 1 + 1)                                    # Plate 18, +1, Defense style +1
        self.rule("item", "attune", "kira", plate, contains="doesn't require attunement")
        cloak = self.add("kira", "Cloak of Protection")
        self.ok("item", "equip", "kira", cloak)
        self.assertEqual(armor_class(self.get("kira"))[0], 20)              # not attuned: no bonus
        before = derive(self.get("kira"))["saves"]["wis"]
        self.ok("item", "attune", "kira", cloak)
        self.assertEqual(armor_class(self.get("kira"))[0], 21)
        self.assertEqual(derive(self.get("kira"))["saves"]["wis"], before + 1)

    def test_one_cloak_at_a_time(self):
        prot = self.add("kira", "Cloak of Protection")
        disp = self.add("kira", "Cloak of Displacement")
        self.ok("item", "attune", "kira", prot)
        self.rule("item", "attune", "kira", disp, contains="only one cloak")
        self.rule("item", "equip", "kira", disp, contains="only one cloak")
        boots = self.add("kira", "Boots of Elvenkind")
        self.ok("item", "equip", "kira", boots)                             # a different slot is fine

    def test_bracers_of_defense_only_without_armor_or_shield(self):
        bracers = self.add("kira", "Bracers of Defense")
        self.ok("item", "attune", "kira", bracers)
        armored = armor_class(self.get("kira"))[0]
        self.ok("item", "unequip", "kira", "chain-mail-1")
        dex = derive(self.get("kira"))["mods"]["dex"]
        self.assertEqual(armor_class(self.get("kira"))[0], 10 + dex + 2)
        self.assertLess(armor_class(self.get("kira"))[0], armored)
        shield = self.add("kira", "Shield")
        self.ok("item", "unequip", "kira", "greatsword-1")
        self.ok("item", "equip", "kira", shield)
        self.assertEqual(armor_class(self.get("kira"))[0], 10 + dex + 2)  # Shield +2, bracers off

    def test_dagger_of_venom_respects_poison_immunity(self):
        dagger = self.add("kira", "Dagger of Venom")
        self.ok("item", "unequip", "kira", "greatsword-1")
        self.ok("item", "equip", "kira", dagger)
        self.assertEqual(self.item("kira", dagger)["magic_bonus"], 1)
        self.fight((("skeleton", "Old Bones"), "6,5"))
        out = ""
        for _ in range(10):
            self.turn("kira")
            if not self.item("kira", dagger).get("venom"):
                self.ok("item", "use", "kira", dagger)
            out = self.ok("attack", "kira", "old-bones", dagger, "--now")
            if "HIT" in out or self.get("old-bones").get("dead"):
                break
            self.ok("combat", "next")
        if "CON save DC 15" in out:
            if "FAILURE" in out:
                self.assertIn("immune to poison", out)
            self.assertNotIn("poisoned", [c["name"] for c in self.get("old-bones").get("conditions", [])])
            self.assertFalse(self.item("kira", dagger).get("venom"))       # the hit spent the coat

    # ------------------------------------------------------------------ Cloak of Displacement
    def test_cloak_of_displacement(self):
        disp = self.add("kira", "Cloak of Displacement")
        self.ok("item", "equip", "kira", disp)
        self.assertFalse(M.displaced(self.get("kira")))                     # needs attunement
        self.ok("item", "attune", "kira", disp)
        self.assertTrue(M.displaced(self.get("kira")))
        self.fight((("bandit", "Bandit"), "6,5"))
        self.turn("bandit")
        out = self.ok("attack", "bandit", "kira", "scimitar")
        self.assertIn("Cloak of Displacement", out)
        kira = self.get("kira")
        if kira["hp"] < derive(kira)["hp_max"]:
            self.assertTrue(kira.get("displacement_off"))                   # damage switches it off...
            self.assertFalse(M.displaced(kira))
        self.ok("damage", "kira", "1", "bludgeoning", "--source", "falling rock")
        self.assertFalse(M.displaced(self.get("kira")))
        self.turn("kira")                                                   # ...until the start of her next turn
        self.assertTrue(M.displaced(self.get("kira")))
        self.ok("condition", "add", "kira", "grappled", "--source", "test grip")    # Speed 0: suppressed
        self.assertFalse(M.displaced(self.get("kira")))

    # ------------------------------------------------------------------ attunement
    def test_long_rest_attunes_and_the_limit_holds(self):
        items = [self.add("kira", n) for n in ("Cloak of Protection", "Stone of Good Luck (Luckstone)", "Robe of Eyes",
                                               "Bracers of Defense")]
        out = self.ok("rest", "long", "--attune", f"kira:{items[0]}")
        self.assertIn("through the Long Rest", out)
        self.assertTrue(self.item("kira", items[0])["attuned"])
        self.ok("item", "attune", "kira", items[1])
        self.ok("rest", "short", "--attune", f"kira:{items[2]}")
        self.rule("item", "attune", "kira", items[3], contains="3 items")
        self.ok("time", "16h", "--reason", "a day of travel")
        self.rule("rest", "long", "--attune", f"kira:{items[3]}", contains="3 items")
        self.assertFalse(self.item("kira", items[3]).get("attuned"))

    def test_one_copy_and_spellcaster_prerequisite(self):
        a = self.add("wren", "Stone of Good Luck (Luckstone)")
        b = self.add("wren", "Stone of Good Luck (Luckstone)")
        self.ok("item", "attune", "wren", a)
        self.rule("item", "attune", "wren", b, contains="copy")
        pearl = self.add("kira", "Pearl of Power")
        self.rule("item", "attune", "kira", pearl, contains="spellcaster")  # a level 1 Fighter casts no spells

    # ------------------------------------------------------------------ Perception, Stealth
    def test_elvenkind_and_robe_of_eyes_perception(self):
        cloak = self.add("wren", "Cloak of Elvenkind")
        boots = self.add("wren", "Boots of Elvenkind")
        self.ok("item", "equip", "wren", boots)                             # no attunement needed
        self.assertIn("Boots of Elvenkind", self.ok("check", "wren", "stealth"))
        self.ok("item", "attune", "wren", cloak)
        out = self.ok("contest", "kira", "perception", "--vs", "wren", "--vs-skill", "stealth")
        self.assertIn("Cloak of Elvenkind", out)                            # Perception to perceive her: Disadvantage
        passive = 10 + derive(self.get("kira"))["skills"]["perception"]
        out = self.ok("contest", "wren", "stealth", "--vs", "kira", "--vs-skill", "perception", "--passive")
        self.assertIn(f"passive Perception {passive - 5}", out)
        self.assertIn("Cloak of Elvenkind", self.ok("action", "kira", "search", "--target", "wren", "--dc", "15"))
        robe = self.add("kira", "Robe of Eyes")
        self.ok("item", "attune", "kira", robe)
        self.assertEqual(derive(self.get("kira"))["passive_perception"], passive + 5)
        out = self.ok("contest", "wren", "stealth", "--vs", "kira", "--vs-skill", "perception", "--passive")
        self.assertIn(f"passive Perception {passive}", out)                 # Advantage and Disadvantage cancel

    def test_ring_of_mind_shielding_blocks_detect_thoughts(self):
        ring = self.add("kira", "Ring of Mind Shielding")
        self.ok("npc", "add", "doppelganger", "--at", "8,5", "--map", "field", "--name", "Stranger", "--side", "enemy")
        self.ok("item", "attune", "kira", ring)
        out = self.ok("cast", "stranger", "detect thoughts", "--targets", "kira")
        self.assertIn("immune to Detect Thoughts (Ring of Mind Shielding)", out)
        self.assertNotIn("Kira Vale — WIS save", out)

    # ------------------------------------------------------------------ items that cast spells
    def test_pearl_of_power(self):
        pearl = self.add("wren", "Pearl of Power")
        self.rule("item", "use", "wren", pearl, contains="attunement")
        self.ok("item", "attune", "wren", pearl)
        self.rule("item", "use", "wren", pearl, contains="no expended spell slot")
        self.ok("cast", "wren", "mage armor", "--targets", "wren")
        self.assertEqual(self.get("wren")["slots_used"].get("1"), 1)
        out = self.ok("item", "use", "wren", pearl)
        self.assertIn("regains one expended level 1", out)
        self.assertEqual(self.get("wren")["slots_used"].get("1"), 0)
        self.ok("cast", "wren", "mage armor", "--targets", "wren")
        self.ok("cast", "wren", "mage armor", "--targets", "wren")
        self.rule("item", "use", "wren", pearl, contains="next dawn")
        self.ok("time", "24h", "--reason", "a day passes")
        self.ok("item", "use", "wren", pearl)

    def test_eyes_of_charming_and_hat_of_disguise(self):
        eyes = self.add("wren", "Eyes of Charming")
        hat = self.add("wren", "Hat of Disguise")
        self.ok("npc", "add", "bandit", "--at", "9,7", "--map", "field", "--name", "Bandit", "--side", "enemy")
        self.rule("cast", "wren", "disguise self", "--item", hat, contains="attunement")
        self.ok("item", "attune", "wren", eyes)
        self.ok("item", "attune", "wren", hat)
        out = self.ok("cast", "wren", "disguise self", "--item", hat)
        self.assertIn("from Hat of Disguise (at will)", out)
        self.ok("cast", "wren", "disguise self", "--item", hat)            # again: no charges
        self.assertEqual(self.get("wren").get("slots_used", {}).get("1", 0), 0)
        out = self.ok("cast", "wren", "charm person", "--item", eyes, "--targets", "bandit")
        self.assertIn("1 charge(s) spent, 2 left", out)
        self.assertIn("WIS save DC 13", out)                               # the lenses' DC, not Wren's 10
        self.rule("cast", "wren", "charm person", "--item", eyes, "--level", "3", "--targets", "bandit",
                  contains="2 charge(s) left")
        self.ok("time", "24h", "--reason", "a day passes")
        out = self.ok("cast", "wren", "charm person", "--item", eyes, "--level", "3", "--targets", "bandit")
        self.assertIn("regains all its charges", out)
        self.assertIn("3 charge(s) spent, 0 left", out)

    def test_spell_scrolls_use_the_scrolls_dc(self):
        self.ok("npc", "add", "bandit", "--at", "9,7", "--map", "field", "--name", "Bandit", "--side", "enemy")
        charm = self.add("wren", "Spell Scroll (Charm Person)")
        out = self.ok("cast", "wren", "charm person", "--scroll", charm, "--targets", "bandit")
        self.assertIn("WIS save DC 13", out)                               # Wren's own DC would be 10
        self.assertIsNone(self.item("wren", charm))
        resto = self.add("wren", "Spell Scroll (Lesser Restoration)")
        self.ok("condition", "add", "kira", "poisoned", "--source", "bad stew")
        self.rule("cast", "wren", "lesser restoration", "--scroll", resto, "--targets", "kira", "--choice", "poisoned",
                  contains="unintelligible")                                # not on the Wizard list
        hold = self.add("wren", "Spell Scroll (Hold Person)")
        out = self.ok("cast", "wren", "hold person", "--scroll", hold, "--targets", "bandit")
        self.assertIn("INT check", out)                                     # level 2: above what she can cast
        self.assertIsNone(self.item("wren", hold))
        if "fizzles" in out:
            self.assertIsNone(self.get("wren").get("concentration"))       # a fizzled scroll casts nothing
        else:
            self.assertIn("WIS save DC 13", out)
            self.assertEqual(self.get("wren")["concentration"]["spell"], "hold-person")

    def test_potions_heal_their_dice(self):
        self.assertEqual(M.resolve_item(self.g(), "Potion of Healing")["heal"], "2d4+2")
        self.assertEqual(M.resolve_item(self.g(), "Potion of Greater Healing")["heal"], "4d4+4")
        self.assertEqual(M.resolve_item(self.g(), "Potion of Healing (greater)")["heal"], "4d4+4")
        p = self.add("kira", "Potion of Greater Healing")
        self.ok("damage", "kira", "11", "bludgeoning", "--source", "falling rock")
        out = self.ok("item", "use", "kira", p)
        self.assertRegex(out, r"regains \d+ HP from Potion of Greater Healing")


if __name__ == "__main__":
    unittest.main()
