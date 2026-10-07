"""Spell interactions through the real reducer, dice parser and resolution functions.

Synthetic entities isolate spell behavior from character creation. Dice faces are
controlled only in tests; production continues to use the secure dice source.
No campaign folders or signing keys are accessed by these unit tests.
"""
import _cli  # installs the repository path, as in the other engine tests
import copy
import contextlib
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine import cli, effects as E, mechanics as M, spells as S, srd
from engine.core import Game, RuleError, armor_class, empty_state, hp_max, replay, speed


class SpellEffectsTest(unittest.TestCase):
    def setUp(self):
        self.g = Game.__new__(Game)
        self.g.state, self.g.events, self.g.pending, self.g.out, self.g.cmdline = empty_state(), [], [], [], ""
        # Spell eligibility is deliberately broad in this resolution fixture.
        for ident in ("caster", "ally", "other"):
            self.g.emit("entity.add", entity={
                "id": ident, "name": ident.title(), "kind": "pc", "classes": {"Wizard": 20},
                "abilities": dict(str=10, dex=14, con=14, int=18, wis=10, cha=14),
                "hp": 100, "hp_max": 100, "base_speed": 30, "size": "Medium",
                "inventory": [{"id": "symbol", "name": "Holy Symbol", "value_cp": 500, "kind": "gear"}],
                "conditions": [], "effects": [], "save_profs": [], "skills": [], "feats": [],
                "spells": {"prepared": list(srd.data()["spells"]), "cantrips": list(srd.data()["spells"])}})
        self.c, self.a, self.o = (self.g.get(n) for n in ("caster", "ally", "other"))

    def cast(self, name, target="ally", slot=None, choice=None, caster="caster"):
        return M.cast(self.g, caster, name, slot, [target] if target else [], choice=choice, now=True)

    def fight(self, who="caster"):
        self.g.emit("combat.set", combat={"active": True, "round": 1, "turn": 0, "started": 0,
            "order": [{"id": who}], "economy": {who: {}}})

    def face(self, face=10):
        return patch("engine.dice.d", side_effect=lambda sides: min(face, sides))

    def test_registry_and_self_targeted_capabilities(self):
        self.assertGreaterEqual(len(S.PROFILES), 50)
        for name in S.PROFILES:
            with self.subTest(spell=name):
                self.assertIsNotNone(srd.find("spells", name))
                self.assertNotEqual(S.support(srd.find("spells", name))["status"], "narrative")
        self.cast("comprehend languages", target=None)
        self.assertTrue(E.has(self.c, "comprehend_languages"))
        self.assertFalse(self.a["effects"])

    def test_bless_and_bane_modify_saves_and_spell_attacks(self):
        self.cast("bless", "caster")
        with self.face(1):
            self.cast("bane", "caster", caster="other")
        with self.face(10):
            M.saving_throw(self.g, self.c, "dex", 15, now=True)
        self.assertIn("+1d4-1d4", self.g.state["rolls"][-1]["expr"])
        self.fight()
        with self.face(10):
            self.cast("fire bolt")
        attack = next(r for r in self.g.state["rolls"] if r["purpose"].startswith("spell attack"))
        self.assertIn("+1d4-1d4", attack["expr"])

    def test_guidance_matches_only_selected_skill_and_is_not_consumed(self):
        self.cast("guidance", choice="stealth")
        with self.face():
            for _ in range(2):
                M.ability_check(self.g, self.a, "stealth", now=True)
                self.assertIn("+1d4", self.g.state["rolls"][-1]["expr"])
            M.ability_check(self.g, self.a, "athletics", now=True)
        self.assertNotIn("d4", self.g.state["rolls"][-1]["expr"])

    def test_invalid_choices_and_target_counts_spend_nothing(self):
        for spell, choice in (("guidance", "fire"), ("enhance ability", "con"), ("resistance", None)):
            before = copy.deepcopy(self.g.state)
            with self.assertRaises(RuleError):
                self.cast(spell, choice=choice)
            self.assertEqual(before, self.g.state)
        with self.assertRaises(RuleError):
            M.cast(self.g, "caster", "aid", targets=["ally", "other", "caster", "ally"], now=True)
        self.assertFalse(self.c.get("slots_used"))

    def test_mage_armor_and_longstrider_expire(self):
        self.cast("mage armor")
        self.cast("longstrider")
        self.assertEqual(armor_class(self.a)[0], 15)
        self.assertEqual(speed(self.a)["walk"], 40)
        self.g.emit("time.set", minutes=60)
        M.after_time(self.g)
        self.assertEqual(speed(self.a)["walk"], 30)
        self.assertEqual(armor_class(self.a)[0], 15)
        self.g.emit("time.set", minutes=480)
        M.after_time(self.g)
        self.assertEqual(armor_class(self.a)[0], 12)

    def test_concentration_removes_every_target_effect(self):
        M.cast(self.g, "caster", "bless", targets=["caster", "ally", "other"], now=True)
        self.cast("fly")
        self.assertFalse(self.c["effects"])
        self.assertFalse(self.o["effects"])
        self.assertEqual(speed(self.a)["fly"], 60)
        M.end_concentration(self.g, self.c, "test")
        self.assertNotIn("fly", speed(self.a))

    def test_same_spell_does_not_stack_and_weaker_source_returns(self):
        self.cast("aid", slot=3)
        self.cast("aid", slot=2, caster="other")
        self.assertEqual(hp_max(self.a), 110)
        self.assertEqual(self.a["hp"], 110)
        strong = next(f for f in self.a["effects"] if f["caster"] == "caster")
        E.remove(self.g, self.a, strong)
        self.assertEqual(hp_max(self.a), 105)
        self.assertEqual(self.a["hp"], 105)
        self.g.emit("time.set", minutes=480)
        M.after_time(self.g)
        self.assertEqual(self.a["hp"], 100)

    def test_resistance_cantrip_once_per_turn_before_resistance(self):
        self.cast("resistance", choice="fire")
        self.g.set(self.a, resist=["fire"])
        self.fight()
        with self.face(3):
            self.assertEqual(M.apply_damage(self.g, self.a, [[10, "fire"]]), 3)
            self.assertEqual(M.apply_damage(self.g, self.a, [[10, "fire"]]), 5)
            self.g.emit("combat.set", combat={**self.g.state["combat"], "round": 2})
            self.assertEqual(M.apply_damage(self.g, self.a, [[10, "fire"]]), 3)

    def test_npc_defenses_receive_spell_resistance(self):
        self.g.emit("entity.add", entity={"id": "guard", "name": "Guard", "kind": "npc", "ac": 12,
            "hp": 40, "hp_max": 40, "speed": {"walk": 30}, "side": "ally"})
        self.cast("protection from energy", "guard", choice="cold")
        with self.face():
            self.assertEqual(M.apply_damage(self.g, self.g.get("guard"), [[11, "cold"]]), 5)

    def test_heroism_temp_hp_and_condition_immunity(self):
        self.cast("heroism")
        self.assertFalse(M.add_condition(self.g, self.a, "frightened", caster="other"))
        M.start_of_turn(self.g, self.a)
        self.assertEqual(self.a["temp_hp"], 4)
        M.end_concentration(self.g, self.c, "test")
        self.assertTrue(M.add_condition(self.g, self.a, "frightened", caster="other"))

    def test_enhance_ability_distinct_upcast_choices(self):
        M.cast(self.g, "caster", "enhance ability", 3, ["ally", "other"], choice="strength,wisdom", now=True)
        with self.face():
            M.ability_check(self.g, self.a, "athletics", now=True)
            self.assertEqual(self.g.state["rolls"][-1]["mode"], "adv")
            M.ability_check(self.g, self.o, "perception", now=True)
            self.assertEqual(self.g.state["rolls"][-1]["mode"], "adv")

    def test_shield_expires_on_casters_turn_not_targets(self):
        self.fight()
        self.cast("shield", target=None)
        self.assertEqual(armor_class(self.c)[0], 17)
        M.start_of_turn(self.g, self.a)
        self.assertEqual(armor_class(self.c)[0], 17)
        M.start_of_turn(self.g, self.c)
        self.assertEqual(armor_class(self.c)[0], 12)

    def test_haste_extra_action_is_restricted_and_lethargy_expires(self):
        self.cast("haste")
        self.assertEqual(speed(self.a)["walk"], 60)
        self.fight("ally")
        M.start_of_turn(self.g, self.a)
        M.use_action(self.g, self.a, "action", "cast Fire Bolt")
        with self.assertRaises(RuleError):
            M.use_action(self.g, self.a, "action", "cast Fire Bolt")
        M.use_action(self.g, self.a, "action", "Dash")
        self.assertTrue(M.economy(self.g, "ally")["haste_used"])
        with self.assertRaises(RuleError):
            M.use_action(self.g, self.a, "action", "Dash")
        M.end_concentration(self.g, self.c, "test")
        self.assertEqual(speed(self.a)["walk"], 0)
        self.assertIn("incapacitated", M.condition_names(self.a))
        M.end_of_turn(self.g, self.a)
        self.assertIn("incapacitated", M.condition_names(self.a))
        M.start_of_turn(self.g, self.a)
        M.end_of_turn(self.g, self.a)
        self.assertNotIn("incapacitated", M.condition_names(self.a))

    def test_slow_restrictions_and_repeat_save(self):
        with self.face(1):
            self.cast("slow")
        self.assertEqual(speed(self.a)["walk"], 15)
        self.assertEqual(armor_class(self.a)[0], 10)
        self.fight("ally")
        with self.assertRaises(RuleError):
            M.use_action(self.g, self.a, "reaction", "Shield")
        M.use_action(self.g, self.a, "bonus", "test")
        with self.assertRaises(RuleError):
            M.use_action(self.g, self.a, "action", "Dash")
        with self.face(20):
            M.end_of_turn(self.g, self.a)
        self.assertFalse(E.has(self.a, "slow"))
        self.assertFalse(self.c.get("concentration"))

    def test_stale_deferred_save_cannot_restore_old_concentration(self):
        self.g.emit("setting", key="player_rolls", value="viewer")
        M.cast(self.g, "caster", "bane", targets=["ally"])
        rid = next(iter(self.g.state["requests"]))
        self.cast("bless", "other")
        with self.face(1):
            cli.fulfill(self.g, rid, "test")
        self.assertFalse(self.a["effects"])

    def test_blindness_repeat_save_and_restoration(self):
        with self.face(1):
            self.cast("blindness deafness", choice="deafened")
        self.assertIn("deafened", M.condition_names(self.a))
        with self.face(20):
            M.end_of_turn(self.g, self.a)
        self.assertNotIn("deafened", M.condition_names(self.a))
        M.add_condition(self.g, self.a, "poisoned")
        self.cast("lesser restoration", choice="poisoned")
        self.assertNotIn("poisoned", M.condition_names(self.a))

    def test_riders_hit_only_and_correct_turn_boundaries(self):
        self.fight()
        with self.face(20):
            self.cast("ray of frost")
        self.assertEqual(speed(self.a)["walk"], 20)
        M.start_of_turn(self.g, self.a)
        self.assertEqual(speed(self.a)["walk"], 20)
        M.start_of_turn(self.g, self.c)
        self.assertEqual(speed(self.a)["walk"], 30)
        S.on_hit(self.g, self.c, self.a, srd.find("spells", "chill touch"), 0)
        with self.assertRaises(RuleError):
            M.heal(self.g, self.a, 1, "test")
        M.end_of_turn(self.g, self.c)
        self.assertTrue(E.has(self.a, "no_heal"))
        M.start_of_turn(self.g, self.c)
        M.end_of_turn(self.g, self.c)
        self.assertFalse(E.has(self.a, "no_heal"))

    def test_guiding_bolt_next_attack_advantage_consumed_even_on_miss(self):
        self.fight()
        S.on_hit(self.g, self.c, self.a, srd.find("spells", "guiding bolt"), 1)
        with self.face(1):
            self.cast("fire bolt")
        attack = self.g.state["rolls"][-1]
        self.assertEqual(attack["mode"], "adv")
        self.assertFalse(E.has(self.a, "next_attack_adv"))

    def test_hex_damage_and_ability_check_penalty(self):
        self.fight()
        self.cast("hex", choice="strength", slot=3)
        self.assertEqual(self.c["concentration"]["duration"], "480 minutes")
        with self.face():
            M.ability_check(self.g, self.a, "athletics", now=True)
            self.assertEqual(self.g.state["rolls"][-1]["mode"], "dis")
            M.saving_throw(self.g, self.a, "str", 10, now=True)
            self.assertIsNone(self.g.state["rolls"][-1]["mode"])
        self.fight()
        before = self.a["hp"]
        with self.face(10):
            self.cast("fire bolt")
        self.assertEqual(before - self.a["hp"], 46)  # 4d10 + 1d6

    def test_spell_attacks_wait_for_viewer_and_do_not_spend_twice(self):
        self.cast("bless", "caster")
        self.fight()
        self.g.emit("setting", key="player_rolls", value="viewer")
        M.cast(self.g, "caster", "guiding bolt", targets=["ally"])
        self.assertEqual(self.a["hp"], 100)
        self.assertEqual(self.c["slots_used"]["1"], 2)
        rid = next(iter(self.g.state["requests"]))
        with self.face(10):
            cli.fulfill(self.g, rid, "test")
        self.assertEqual(self.c["slots_used"]["1"], 2)
        self.assertLess(self.a["hp"], 100)
        self.assertTrue(E.has(self.a, "next_attack_adv"))
        attack = next(r for r in self.g.state["rolls"] if r.get("request") == rid)
        self.assertIn("+1d4", attack["expr"])

    def test_mass_heal_allocation_and_construct_healing(self):
        self.g.set(self.a, hp=1, type="construct")
        self.g.set(self.o, hp=10)
        M.add_condition(self.g, self.a, "blinded")
        M.cast(self.g, "caster", "mass heal", targets=["ally", "other"], choice="20,40", now=True)
        self.assertEqual(self.a["hp"], 21)
        self.assertEqual(self.o["hp"], 50)
        self.assertNotIn("blinded", M.condition_names(self.a))
        with self.face(1):
            self.cast("cure wounds")
        self.assertGreater(self.a["hp"], 21)

    def test_death_ward_is_consumed_and_prevents_massive_damage_death(self):
        self.cast("death ward")
        M.apply_damage(self.g, self.a, [[1000, "force"]])
        self.assertEqual(self.a["hp"], 1)
        self.assertFalse(self.a.get("dead"))
        self.assertFalse(E.has(self.a, "death_ward"))

    def test_invisibility_multitarget_break_preserves_others(self):
        M.cast(self.g, "caster", "invisibility", 3, ["ally", "other"], now=True)
        M.break_invisibility(self.g, self.a, "attack")
        self.assertNotIn("invisible", M.condition_names(self.a))
        self.assertIn("invisible", M.condition_names(self.o))
        self.assertTrue(self.c.get("concentration"))
        M.break_invisibility(self.g, self.o, "attack")
        self.assertFalse(self.c.get("concentration"))

    def test_see_invisibility_and_faerie_fire(self):
        self.cast("invisibility")
        self.cast("see invisibility", target=None, caster="other")
        self.assertNotIn("target invisible", M.attack_modes(self.g, self.o, self.a, False, 5)[1])
        with self.face(1):
            self.cast("faerie fire", caster="other")
        adv, dis = M.attack_modes(self.g, self.c, self.a, False, 5)
        self.assertTrue(adv)
        self.assertNotIn("target invisible", dis)

    def test_darkvision_and_freedom_of_movement(self):
        self.cast("darkvision")
        self.assertEqual(M.vision_ft(self.g, self.a, {"lighting": "dark"}), 150)
        with self.face(1):
            self.cast("slow", caster="other")
        self.cast("freedom of movement")
        self.assertEqual(speed(self.a)["walk"], 30)
        self.assertEqual(speed(self.a)["swim"], 30)
        self.assertFalse(M.add_condition(self.g, self.a, "restrained", spell="web"))

    def test_events_replay_reproduces_effect_state(self):
        self.cast("aid", slot=3)
        self.cast("haste")
        reconstructed = replay([{**ev, "seq": i + 1} for i, ev in enumerate(self.g.pending)])
        self.assertEqual(self.g.state, reconstructed)

    def test_every_profile_casts_through_resolution(self):
        options = {"skill": "stealth", "damage": "fire", "energy": "cold", "ability": "str",
                   "enhance": "wis", "size": "enlarge", "blindness": "blinded", "lesser": "poisoned",
                   "greater": "charmed", "allocation": "20", "stand": None}
        for slug, profile in S.PROFILES.items():
            with self.subTest(spell=slug):
                self.setUp()
                spell = srd.find("spells", slug)
                self.g.set(self.c, inventory=self.c["inventory"] + [
                    {"id": "dust", "name": "Diamond dust", "value_cp": 100000, "kind": "gear"},
                    {"id": "water", "name": "Holy Water", "value_cp": 2500, "kind": "gear"}])
                if profile["handler"] == "restore":
                    M.add_condition(self.g, self.a, options[profile["choice"]])
                if profile["handler"] == "stabilize":
                    self.g.set(self.a, hp=0)
                if spell["effect"]["kind"] in ("attack", "darts", "damage"):
                    self.fight()
                target = None if spell["range"].lower() == "self" else "ally"
                with self.face(1):
                    result = self.cast(slug, target, choice=options.get(profile["choice"]))
                self.assertTrue(result.get("ok"))

    def test_weapon_attack_damage_uses_size_effect_and_preserves_distance(self):
        self.cast("enlarge reduce", "caster", choice="enlarge")
        self.fight()
        with self.face(10):
            M.attack(self.g, "caster", "ally", now=True)
        self.assertEqual(self.a["hp"], 95)  # unarmed 1 + enlarged weapon/strike 1d4

    def test_haste_additional_attack_does_not_grant_extra_attack(self):
        self.cast("haste")
        self.g.set(self.a, classes={"Fighter": 5})
        self.fight("ally")
        with self.face(10):
            for _ in range(3):
                M.attack(self.g, "ally", "other", now=True)
            with self.assertRaises(RuleError):
                M.attack(self.g, "ally", "other", now=True)
        self.assertEqual(M.economy(self.g, "ally")["attacks_left"], 0)

    def test_restoration_removes_managed_condition_effect(self):
        with self.face(1):
            self.cast("blindness deafness")
        self.cast("lesser restoration", choice="blinded")
        self.assertFalse(self.a["effects"])
        with self.face(1):
            M.end_of_turn(self.g, self.a)
        self.assertNotIn("blinded", M.condition_names(self.a))

    def test_slow_spell_failure_spends_slot_without_applying_spell(self):
        with self.face(1):
            self.cast("slow", "caster", caster="other")
        self.fight()
        with self.face(1):
            result = self.cast("mage armor")
        self.assertTrue(result["failed"])
        self.assertEqual(self.c["slots_used"]["1"], 1)
        self.assertFalse(E.has(self.a, "mage_armor"))

    def test_elapsed_rounds_expire_concentration_without_ending_combat(self):
        self.cast("bless")
        self.fight()
        self.g.emit("combat.set", combat={**self.g.state["combat"], "round": 11})
        M.start_of_turn(self.g, self.c)
        self.assertFalse(self.c.get("concentration"))
        self.assertFalse(self.a["effects"])

    def test_slow_limits_multi_beam_spells_to_one_attack(self):
        with self.face(1):
            self.cast("slow", "caster", caster="other")
        self.fight()
        with self.face(10):
            self.cast("scorching ray")
        attacks = [r for r in self.g.state["rolls"] if r["purpose"].startswith("spell attack")]
        self.assertEqual(len(attacks), 1)

    def test_freedom_keeps_haste_bonus_and_suppresses_existing_magical_restraint(self):
        self.cast("haste", caster="other")
        # A second source applies Slow without replacing the Haste concentration.
        with self.face(1):
            self.cast("slow")
        self.cast("freedom of movement")
        self.assertEqual(speed(self.a)["walk"], 60)
        self.g.set(self.a, conditions=[{"name": "restrained", "spell": "web"}])
        self.assertNotIn("restrained", M.condition_names(self.a))
        self.assertEqual(speed(self.a)["walk"], 60)

    def test_condition_immunity_suppresses_existing_condition(self):
        M.add_condition(self.g, self.a, "frightened")
        self.cast("heroism")
        self.assertNotIn("frightened", M.condition_names(self.a))
        M.end_concentration(self.g, self.c, "test")
        self.assertIn("frightened", M.condition_names(self.a))

    def test_support_command_needs_no_active_game(self):
        with patch("engine.cli.Game", side_effect=AssertionError("support must not load a campaign")), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(["spells", "support", "guidance"]), 0)
        self.assertIn("selected skill", out.getvalue())

    def test_death_saves_receive_bless_and_foresight(self):
        self.cast("bless")
        self.cast("foresight", caster="other")
        self.g.set(self.a, hp=0)
        with self.face(10):
            M.death_save(self.g, self.a, now=True)
        roll = self.g.state["rolls"][-1]
        self.assertIn("+1d4", roll["expr"])
        self.assertEqual(roll["mode"], "adv")
        self.assertEqual(self.a["death"]["success"], 1)

    def test_recasting_replaces_legacy_untimed_mage_armor(self):
        self.g.set(self.a, effects=[{"name": "mage armor", "spell": "mage-armor", "caster": "other"}])
        M.add_condition(self.g, self.a, "prone")
        self.cast("mage armor")
        self.assertEqual(len(self.a["effects"]), 1)
        self.assertIn("prone", M.condition_names(self.a))
        self.g.emit("time.set", minutes=480)
        M.after_time(self.g)
        self.assertEqual(armor_class(self.a)[0], 12)

    def test_donning_armor_ends_mage_armor_permanently(self):
        self.cast("mage armor")
        self.g.set(self.a, inventory=[{"id": "leather", "name": "Leather Armor", "base_name": "Leather Armor",
                                     "kind": "armor", "category": "light"}], armor_training=["light"])
        M.equip(self.g, self.a, "leather")
        self.assertFalse(E.has(self.a, "mage_armor"))
        M.equip(self.g, self.a, "leather", on=False)
        self.assertEqual(armor_class(self.a)[0], 12)


class SpellCliTest(unittest.TestCase):
    """CLI choices, signed commit/reload and generated effect projection."""
    def test_guidance_choice_persists_and_modifies_requested_roll(self):
        tmp = Path(tempfile.mkdtemp(prefix="dnd-spells-"))
        env = {**os.environ, "DND_CAMPAIGNS": str(tmp / "campaigns"), "DND_ENGINE_HOME": str(tmp / "home")}

        def ok(*args):
            code, out = _cli.run(env, *args)
            self.assertEqual(code, 0, out)
            return out

        try:
            ok("campaign", "new", "Spell CLI Test")
            ok("char", "create", "--name", "Wren Ashdown", "--class", "Wizard", "--species", "Elf", "--background", "Sage",
               "--method", "pointbuy", "--scores", "str=8,dex=14,con=14,int=15,wis=12,cha=8", "--bonus", "int+2,con+1",
               "--skills", "investigation,medicine", "--languages", "Elvish,Draconic", "--species-skill", "perception",
               "--mi-cantrips", "light,mage hand", "--mi-spell", "shield")
            g = _cli.game(env)
            g.set(g.get("wren"), granted_spells=[{"slug": "guidance", "source": "test fixture", "ability": "int"}])
            g.commit()
            ok("cast", "wren", "guidance", "--targets", "wren", "--choice", "perception")
            g = _cli.game(env)
            self.assertTrue(E.active(g.get("wren"))[0]["managed_spell"])
            ok("set", "player_rolls=viewer")
            ok("check", "wren", "perception")
            g = _cli.game(env)
            rid = next(iter(g.state["requests"]))
            ok("request", "roll", rid)
            g = _cli.game(env)
            self.assertIn("+1d4", g.state["rolls"][-1]["expr"])
            self.assertFalse(g.state["requests"])
            sheet = (g.dir / "party" / "wren.md").read_text(encoding="utf-8")
            self.assertIn("Active spell effects", sheet)
            self.assertIn("Guidance", sheet)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
