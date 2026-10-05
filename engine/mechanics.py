"""Rules resolution: d20 tests, attacks, damage, healing, spells, conditions, movement, rests,
items, coins and XP. Every public function validates against the SRD and raises RuleError
rather than bending a rule. Anything that benefits the party beyond what the rules produce
requires an explicit, publicly-logged DM override.
"""
import json
import math
import re

from . import dice, maps, srd
from .core import item_display_name
from .core import (MAGIC_EFFECTS, RARITY_ORDER, TIER_MAX_GP_AWARD, TIER_MAX_RARITY, RuleError,
                   abilities, amod, armor_class, attacks_per_action, condition_names, derive, fmt_mod,
                   has_feat, has_feature, hp_max, level, mod, pact_slots, pb, resources, save_mod,
                   skill_mod, speed, spell_slots, spellcasting, tier, weapon_attack, equipped,
                   initiative_mod, exhaustion_penalty, max_spell_level_for_class, parse_duration, fmt_time)

AUTO_FAIL_STR_DEX = {"paralyzed", "petrified", "stunned", "unconscious"}
ATTACKER_DIS = {"blinded", "frightened", "poisoned", "prone", "restrained"}
TARGET_ADV = {"blinded", "paralyzed", "petrified", "restrained", "stunned", "unconscious"}
CHECK_DIS = {"poisoned", "frightened"}
# SRD magic items that grant Advantage on Dexterity (Stealth) checks while worn → requires attunement?
STEALTH_ADV_ITEMS = {"boots of elvenkind": False, "cloak of elvenkind": True}
POTIONS = {"potion of healing": ("2d4+2", "Common"), "potion of healing (greater)": ("4d4+4", "Uncommon"),
           "potion of greater healing": ("4d4+4", "Uncommon"), "potion of healing (superior)": ("8d4+8", "Rare"),
           "potion of superior healing": ("8d4+8", "Rare"), "potion of healing (supreme)": ("10d4+20", "Very Rare"),
           "potion of supreme healing": ("10d4+20", "Very Rare")}
MAGIC_VALUE_GP = {"Common": 100, "Uncommon": 400, "Rare": 4000, "Very Rare": 40000, "Legendary": 200000}
SCROLL_RARITY = {0: "Common", 1: "Common", 2: "Uncommon", 3: "Uncommon", 4: "Rare", 5: "Rare",
                 6: "Very Rare", 7: "Very Rare", 8: "Very Rare", 9: "Legendary"}
PLUS_RARITY = {"weapon": {1: "Uncommon", 2: "Rare", 3: "Very Rare"}, "ammunition": {1: "Uncommon", 2: "Rare", 3: "Very Rare"},
               "armor": {1: "Rare", 2: "Very Rare", 3: "Legendary"}, "shield": {1: "Uncommon", 2: "Rare", 3: "Very Rare"}}
COIN_CP = {"cp": 1, "sp": 10, "ep": 50, "gp": 100, "pp": 1000}


# ====================================================================== combat helpers

def combat(g):
    c = g.state.get("combat")
    return c if c and c.get("active") else None


def current_id(g):
    c = combat(g)
    if not c or not c.get("order"):
        return None
    return c["order"][c["turn"]]["id"]


def economy(g, ent_id):
    c = combat(g)
    return (c or {}).get("economy", {}).get(ent_id, {})


def set_economy(g, ent_id, **kw):
    c = dict(combat(g))
    econ = dict(c.get("economy", {}))
    econ[ent_id] = {**econ.get(ent_id, {}), **kw}
    c["economy"] = econ
    g.emit("combat.set", combat=c)


def use_action(g, e, kind="action", what=""):
    """Spend an action / bonus action / reaction in combat. Outside combat this is free."""
    c = combat(g)
    if not c:
        return
    ec = economy(g, e["id"])
    if kind == "reaction":
        if ec.get("reaction_used"):
            raise RuleError(f"{e['name']} has already used their Reaction this round.")
        if "incapacitated" in condition_names(e):
            raise RuleError(f"{e['name']} is Incapacitated and can't take reactions.")
        set_economy(g, e["id"], reaction_used=True)
        return
    if current_id(g) != e["id"]:
        raise RuleError(f"It's not {e['name']}'s turn (current: {current_id(g)}). Off-turn you can only use a Reaction.")
    if "incapacitated" in condition_names(e):
        raise RuleError(f"{e['name']} is Incapacitated and can't take actions or bonus actions.")
    key = "action_used" if kind == "action" else "bonus_used"
    if ec.get(key):
        if kind == "action" and ec.get("action_surge"):
            set_economy(g, e["id"], action_surge=False)
            return
        raise RuleError(f"{e['name']} has already used their {'Action' if kind == 'action' else 'Bonus Action'} this turn"
                        f"{' (' + ec.get(key + '_for', '') + ')' if ec.get(key + '_for') else ''}.")
    set_economy(g, e["id"], **{key: True, key + "_for": what})


def token_pos(e):
    t = e.get("token")
    return (t["x"], t["y"]) if t else None


def same_map(a, b):
    return a.get("token") and b.get("token") and a["token"]["map"] == b["token"]["map"]


def dist_ft(a, b):
    if not same_map(a, b):
        return None
    return maps.distance_squares(token_pos(a), token_pos(b), a.get("cells", 1), b.get("cells", 1)) * 5


def hostile(a, b):
    sa = "party" if a["kind"] == "pc" or a.get("side") == "ally" else a.get("side", "enemy")
    sb = "party" if b["kind"] == "pc" or b.get("side") == "ally" else b.get("side", "enemy")
    return sa != sb and "neutral" not in (sa, sb)


def alive(e):
    return not e.get("dead") and e.get("hp", 1) > 0


# ====================================================================== d20 tests

def _mode(adv, dis):
    return dice.combine_modes(adv, dis)


def _fmt_mode(mode, adv, dis):
    if adv and dis:
        return " (advantage and disadvantage cancel)"
    if mode == "adv":
        return f" with Advantage ({', '.join(adv)})"
    if mode == "dis":
        return f" with Disadvantage ({', '.join(dis)})"
    return ""


def move_speed(e):
    """Best movement mode for a move: a flier uses its Fly Speed (e.g. Animated Flying Sword: walk 5, fly 50)."""
    sp = speed(e)
    return max(sp.get("walk", 0), sp.get("fly", 0))


def _has_feature(e, name):
    from .core import has_feature
    return has_feature(e, name)


def wants_request(g, e, now=False):
    return (not now and e["kind"] == "pc" and g.state["settings"].get("player_rolls") == "viewer")


def make_request(g, e, label, spec):
    rid = f"q{len(g.events) + len(g.pending) + 1}"
    g.emit("request.add", id=rid, who=e["id"], label=label, spec=spec)
    g.say(f"🎲 {e['name']}: roll {label} — click Roll in the viewer (request {rid})", kind="request", request=rid, who=e["id"])
    return rid


def ability_check(g, e, what, dc=None, adv=(), dis=(), hidden=False, purpose=None, now=False, request=None):
    what = what.lower().strip()
    if what in srd.SKILLS:
        m, label = skill_mod(g_ent(g, e), what), f"{srd.SKILLS[what].upper()} ({what.title()})"
    elif (srd.find("gear", what) or {}).get("tool_ability"):
        tool = srd.find("gear", what)
        ab = tool["tool_ability"]
        prof = e["kind"] == "pc" and any(tool["name"].lower() == t.lower() or (tool.get("tool_kind") or "").lower() == t.lower()
                                         for t in e.get("tools", []))
        m = amod(e, ab) + (pb(e) if prof else (skill_bonus_jack(e) if e["kind"] == "pc" else 0))
        label = f"{ab.upper()} ({tool['name']}{', proficient' if prof else ''})"
        if e["kind"] == "pc" and not any(i["name"].lower() == tool["name"].lower() for i in e.get("inventory", [])):
            raise RuleError(f"{e['name']} needs {tool['name']} in hand for that check.")
    else:
        ab = srd.ability_key(what)
        if not ab:
            raise RuleError(f"'{what}' is not a skill, ability or tool. Skills: {', '.join(srd.SKILLS)}")
        m, label = amod(e, ab) + (skill_bonus_jack(e) if e["kind"] == "pc" else 0), f"{ab.upper()} check"
    adv, dis = list(adv), list(dis)
    if what == "athletics" and e["kind"] == "pc" and _has_feature(e, "Remarkable Athlete"):
        adv.append("Remarkable Athlete")
    names = condition_names(e)
    for c in CHECK_DIS & names:
        dis.append(c)
    if any(fx.get("name") == "untrained armor" for fx in e.get("effects", [])) and (srd.SKILLS.get(what) in ("str", "dex") or what in ("str", "dex", "strength", "dexterity")):
        dis.append("armor without training")
    if what == "stealth":  # rules/core/06-equipment.md: armor with "Disadvantage" in its Stealth column
        for it in e.get("inventory", []):
            if it.get("equipped") and it.get("kind") == "armor":
                arm = srd.find("armor", it.get("base_name") or it["name"]) or {}
                if arm.get("stealth_dis"):
                    dis.append(f"{arm['name']} (Stealth Disadvantage)")
        # rules/magic-items: worn items whose text grants Advantage on Dexterity (Stealth) checks
        for it in e.get("inventory", []):
            base = (it.get("base_name") or it.get("name") or "").lower()
            need = STEALTH_ADV_ITEMS.get(base)
            if need is not None and it.get("equipped") and (not need or it.get("attuned")):
                adv.append(it.get("base_name") or it["name"])
    m -= exhaustion_penalty(e)
    if wants_request(g, e, now) and not request:
        return {"request": make_request(g, e, f"{label}" + (f" DC {dc}" if dc and not hidden else ""),
                                        {"op": "check", "who": e["id"], "what": what, "dc": dc, "adv": adv, "dis": dis,
                                         "hidden": hidden, "purpose": purpose})}
    mode = _mode(adv, dis)
    r = g.roll(f"1d20{fmt_mod(m) if m else ''}", purpose or label, e["id"], mode, hidden=hidden, request=request)
    ok = None if dc is None else r["total"] >= dc
    txt = f"{e['name']} — {label}{_fmt_mode(mode, adv, dis)}: {r['text']}" + ("" if dc is None else f" vs DC {dc} → {'SUCCESS' if ok else 'FAILURE'}")
    if hidden:
        g.say(f"🎲 The DM rolls a secret check for {e['name']}.", kind="roll-hidden")
        g.note("[secret] " + txt)
    else:
        g.say(txt, kind="roll", roll=r["id"])
    return {"total": r["total"], "success": ok, "nat": r["nat"], "roll": r}


def g_ent(g, e):
    return e


def skill_bonus_jack(e):
    return pb(e) // 2 if e.get("classes", {}).get("Bard", 0) >= 2 else 0


def saving_throw(g, e, ability, dc, adv=(), dis=(), source=None, spell=False, now=False, request=None, effect=None, purpose=None):
    ab = srd.ability_key(ability) or ability
    names = condition_names(e)
    label = f"{ab.upper()} save DC {dc}"
    if ab in ("str", "dex") and names & AUTO_FAIL_STR_DEX:
        cond = sorted(names & AUTO_FAIL_STR_DEX)[0]
        g.say(f"{e['name']} automatically fails the {label} ({cond}).", kind="roll")
        res = {"success": False, "auto": True}
        if effect:
            apply_save_effect(g, e, res, effect)
        return res
    adv, dis = list(adv), list(dis)
    if ab == "dex" and "restrained" in names:
        dis.append("restrained")
    if ab == "dex" and any(c["name"] == "dodging" for c in e.get("conditions", [])):
        adv.append("Dodge")
    if spell and any(a["name"].lower() == "magic resistance" for a in e.get("actions", [])):
        adv.append("Magic Resistance")
    if e["kind"] == "pc" and "Dwarf" == e.get("species") and source and "poison" in str(source).lower():
        adv.append("Dwarven Resilience")
    if any(fx.get("name") == "untrained armor" for fx in e.get("effects", [])) and ab in ("str", "dex"):
        dis.append("armor without training")
    m = save_mod(e, ab) - exhaustion_penalty(e)
    if e["kind"] == "pc" and e.get("classes", {}).get("Paladin", 0) >= 6:
        pass  # Aura of Protection is positional; DM applies with --bonus
    if wants_request(g, e, now) and not request:
        return {"request": make_request(g, e, label, {"op": "save", "who": e["id"], "ability": ab, "dc": dc, "adv": adv,
                                                      "dis": dis, "source": source, "spell": spell, "effect": effect})}
    mode = _mode(adv, dis)
    r = g.roll(f"1d20{fmt_mod(m) if m else ''}", purpose or f"{ab.upper()} save" + (f" vs {source}" if source else ""), e["id"], mode, request=request)
    ok = r["total"] >= dc
    g.say(f"{e['name']} — {label}{_fmt_mode(mode, adv, dis)}: {r['text']} → {'SUCCESS' if ok else 'FAILURE'}", kind="roll", roll=r["id"],
          who=e["id"], save=ab, success=ok)
    res = {"success": ok, "total": r["total"], "nat": r["nat"]}
    if not ok and e["kind"] != "pc" and (e.get("legendary_resistance") or 0) > e.get("legendary_resistance_used", 0):
        g.note(f"  {e['name']} may use Legendary Resistance ({e['legendary_resistance'] - e.get('legendary_resistance_used', 0)} left): "
               f"python -m engine legendary-resist {e['id']}")
    if effect:
        apply_save_effect(g, e, res, effect)
    return res


def apply_save_effect(g, e, res, effect):
    """effect = {'damage': [[amount, type]], 'half': bool, 'condition': name, 'source': str, 'caster': id, 'spell': slug}"""
    if effect.get("concentration_check"):
        after_concentration_save(g, g.get(e["id"]), res)
        return
    if effect.get("damage"):
        parts = effect["damage"]
        if res["success"]:
            parts = [[a // 2, t] for a, t in parts] if effect.get("half") else []
        if parts:
            apply_damage(g, e, parts, source=effect.get("source"))
    if effect.get("condition") and not res["success"]:
        add_condition(g, e, effect["condition"], source=effect.get("source"), caster=effect.get("caster"),
                      spell=effect.get("spell"), save=effect.get("repeat_save"), escalate=effect.get("escalate"))


# ====================================================================== damage & healing

def defenses(e):
    if e["kind"] == "pc":
        res = set(e.get("resist", []))
        if any(c["name"] == "raging" for c in e.get("conditions", [])):
            res |= {"bludgeoning", "piercing", "slashing"}
        for fx in e.get("effects", []):
            res |= set(fx.get("resist", []))
        return res, set(e.get("immune", [])), set(e.get("vulnerable", []))
    return set(e.get("resist", [])), set(e.get("immune", [])), set(e.get("vulnerable", []))


def apply_damage(g, e, parts, source=None, crit=False, attacker=None, melee_within_5=False, knockout=False):
    """parts = [[amount, type], ...]. Applies immunity, resistance, vulnerability, temp HP, 0 HP rules."""
    if e.get("dead"):
        g.note(f"{e['name']} is already dead.")
        return 0
    res, imm, vul = defenses(e)
    total, notes = 0, []
    for amount, dtype in parts:
        dtype = (dtype or "").lower()
        a = max(0, int(amount))
        if dtype in imm:
            notes.append(f"immune to {dtype}")
            a = 0
        else:
            if dtype in res:
                a //= 2
                notes.append(f"resists {dtype}")
            if dtype in vul:
                a *= 2
                notes.append(f"vulnerable to {dtype}")
        total += a
    temp = e.get("temp_hp", 0)
    absorbed = min(temp, total)
    remaining = total - absorbed
    hp_before = e["hp"]
    new_hp = max(0, hp_before - remaining)
    patch = {"temp_hp": temp - absorbed, "hp": new_hp}
    msg = f"💥 {e['name']} takes {total} damage" + (f" ({', '.join(sorted(set(notes)))})" if notes else "") + \
          (f", {absorbed} absorbed by temporary HP" if absorbed else "") + (f" from {source}" if source else "")
    if e["kind"] == "pc":
        if hp_before == 0 and remaining > 0:
            fails = e.get("death", {}).get("fail", 0) + (2 if crit else 1)
            patch["death.fail"] = min(3, fails)
            patch["death.stable"] = False
            msg += f" while at 0 HP → {'2 death save failures (critical)' if crit else '1 death save failure'}"
            if fails >= 3:
                patch["dead"] = True
                msg += f". {e['name']} has DIED."
        elif new_hp == 0:
            overflow = remaining - hp_before
            if overflow >= hp_max(e):
                patch["dead"] = True
                msg += f" — massive damage ({overflow} over 0 ≥ max HP {hp_max(e)}): {e['name']} DIES instantly."
            elif "relentless endurance" in [t.lower() for t in e.get("species_traits", [])]                     and not e.get("resources_used", {}).get("Relentless Endurance"):
                # Orc trait (rules/core/04-character-origins.md): drop to 1 HP instead, once per Long Rest
                new_hp = 1
                patch["hp"] = 1
                patch["resources_used"] = {**e.get("resources_used", {}), "Relentless Endurance": 1}
                msg += f" and would drop to 0 HP — Relentless Endurance: {e['name']} stays up at 1 HP."
            else:
                msg += f" and drops to 0 HP — Unconscious, making death saving throws."
                patch["death"] = {"success": 0, "fail": 0, "stable": False}
        else:
            msg += f" ({new_hp}/{hp_max(e)} HP)."
    else:
        if new_hp == 0:
            if knockout and melee_within_5:
                # SRD Knocking Out a Creature: 1 HP and Unconscious; it starts a Short Rest, at the end of which the
                # condition ends (sooner if it regains any HP).
                patch["hp"] = 1
                patch["knockout_wake_at"] = g.state["time"] + 60
                msg += " and is knocked out (1 HP, Unconscious until the end of a Short Rest, not dead)."
                add_condition(g, e, "unconscious", source="knocked out", quiet=True)
            else:
                patch["dead"] = True
                msg += " and is defeated!"
            c = combat(g)  # knocked out counts as defeated too (XP)
            if c and e.get("side", "enemy") == "enemy":
                cc = dict(c)
                cc["defeated"] = sorted(set(c.get("defeated", [])) | {e["id"]})
                g.emit("combat.set", combat=cc)
        else:
            frac = new_hp / max(1, hp_max(e))
            msg += " — " + ("bloodied." if frac <= .5 else "still standing.")
    g.set(e, **{k.replace(".", "__"): v for k, v in patch.items()})
    if new_hp == 0 and not patch.get("dead") and e["kind"] == "pc" and hp_before > 0:
        add_condition(g, e, "unconscious", source="0 HP", quiet=True)
        fall_inert(g, g.get(e["id"]))
    if patch.get("dead"):
        end_concentration(g, e, "died")
    g.say(msg, kind="damage", who=e["id"], amount=total, dtype=(parts[0][1] if parts else None), crit=bool(crit),
          down=new_hp == 0, dead=bool(patch.get("dead")), hp=new_hp, hp_max=hp_max(e))
    # concentration
    if total > 0 and e.get("concentration") and not patch.get("dead"):
        if new_hp == 0:
            end_concentration(g, e, "dropped to 0 HP")
        else:
            dc = min(30, max(10, total // 2))
            g.note(f"  Concentration check needed for {e['name']} (DC {dc}).")
            saving_throw(g, e, "con", dc, source=f"Concentration ({e['concentration']['spell']})",
                         effect={"concentration_check": True})
    return total


def after_concentration_save(g, e, res):
    if not res.get("success") and e.get("concentration"):
        end_concentration(g, e, "failed Concentration save")


def heal(g, e, amount, source):
    if e.get("dead"):
        raise RuleError(f"{e['name']} is dead. Only magic that explicitly returns the dead to life (e.g. Revivify) can help.")
    if any(c["name"] == "cursed-no-heal" for c in e.get("conditions", [])):
        raise RuleError(f"{e['name']} can't regain hit points right now.")
    mx = hp_max(e)
    new = min(mx, e["hp"] + max(0, int(amount)))
    gained = new - e["hp"]
    was_zero = e["hp"] == 0
    patch = {"hp": new}
    if was_zero and new > 0:
        patch["death"] = {"success": 0, "fail": 0, "stable": False}
    g.set(e, **patch)
    e = g.get(e["id"])
    # Regaining HP wakes a creature from 0 HP, and ends a knockout's Unconscious condition early (SRD).
    if new > 0 and (was_zero or (gained > 0 and any(c["name"] == "unconscious" and c.get("source") in ("0 HP", "knocked out")
                                                    for c in e.get("conditions", [])))):
        remove_condition(g, e, "unconscious", quiet=True)
    g.say(f"💚 {e['name']} regains {gained} HP from {source} ({new}/{mx}).", kind="heal", who=e["id"], amount=gained, hp=new, hp_max=mx)
    return gained


def temp_hp(g, e, amount, source):
    cur = e.get("temp_hp", 0)
    if amount <= cur:
        g.say(f"{e['name']} keeps {cur} temporary HP (temporary HP don't stack; {amount} from {source} is not higher).")
        return
    g.set(e, temp_hp=int(amount))
    g.say(f"🛡 {e['name']} gains {amount} temporary HP from {source}.", kind="heal", who=e["id"], temp=int(amount))


# ====================================================================== conditions

def add_condition(g, e, name, source=None, until=None, caster=None, spell=None, save=None, quiet=False, rounds=None,
                  escalate=None):
    name = name.lower().strip()
    valid = set(srd.data()["conditions"]) | {"raging", "dodging", "concentrating", "hidden", "surprised", "blessed",
                                             "baned", "hasted", "slowed", "marked", "disengaged", "helped"}
    if name not in valid:
        raise RuleError(f"'{name}' is not an SRD condition. Conditions: {', '.join(srd.data()['conditions'])}")
    if name == "exhaustion":
        raise RuleError("Use `exhaustion add` — Exhaustion has levels.")
    if name in e.get("condition_immune", []):
        g.say(f"{e['name']} is immune to the {name.title()} condition.", kind="info")
        return False
    conds = [c for c in e.get("conditions", []) if c["name"] != name]
    entry = {"name": name}
    for k, v in (("source", source), ("until", until), ("caster", caster), ("spell", spell), ("save", save), ("rounds", rounds),
                 ("escalate", escalate)):
        if v:
            entry[k] = v
    conds.append(entry)
    g.set(e, conditions=conds)
    if not quiet:
        g.say(f"{e['name']} is now {name.title()}" + (f" ({source})" if source else "") + (f" until {until}" if until else "") + ".", kind="condition",
              who=e["id"], cond=name, on=True)
    if name in ("incapacitated", "paralyzed", "stunned", "unconscious", "petrified") and e.get("concentration"):
        end_concentration(g, e, f"became {name.title()}")
    if name == "unconscious" and "prone" not in [c["name"] for c in g.get(e["id"]).get("conditions", [])]:
        # rules glossary, Unconscious (Inert): the creature also has the Prone condition and drops what it's holding
        add_condition(g, g.get(e["id"]), "prone", source="fell Unconscious", quiet=quiet)
        if e["kind"] != "pc":
            g.say(f"  {e['name']} drops whatever it was holding (pick it up again with an object interaction).", kind="condition")
    return True


def break_invisibility(g, e, why):
    """The Invisibility spell and the Hide action end right after the creature makes an attack roll (rules/spells/
    invisibility.md; Hide in rules/core). Greater Invisibility and innate invisibility don't."""
    for c in list(e.get("conditions", [])):
        if c["name"] != "invisible":
            continue
        src, sp = (c.get("source") or "").lower(), (c.get("spell") or "").lower()
        if sp == "invisibility" or src.startswith("hide") or ("invisibility" in src and "greater" not in src):
            remove_condition(g, e, "invisible", quiet=True)
            g.say(f"{e['name']} is no longer Invisible ({why}).", kind="condition", who=e["id"], cond="invisible", on=False)
            if sp == "invisibility" and c.get("caster"):
                ce = g.entities.get(c["caster"])
                if ce and (ce.get("concentration") or {}).get("spell") == "invisibility":
                    end_concentration(g, ce, "the invisible creature attacked")
            return


def remove_condition(g, e, name, quiet=False):
    name = name.lower()
    conds = [c for c in e.get("conditions", []) if c["name"] != name]
    if len(conds) == len(e.get("conditions", [])):
        if not quiet:
            raise RuleError(f"{e['name']} doesn't have {name}.")
        return
    g.set(e, conditions=conds)
    if not quiet:
        g.say(f"{e['name']} is no longer {name.title()}.", kind="condition", who=e["id"], cond=name, on=False)


def release_spell_if_unused(g, cond):
    """A spell whose last affected target shook it off is over: the caster stops concentrating on it."""
    caster, spell = cond.get("caster"), cond.get("spell")
    if not caster or not spell or caster not in g.entities:
        return
    ce = g.get(caster)
    if (ce.get("concentration") or {}).get("spell") != spell:
        return
    still = any(c.get("caster") == caster and c.get("spell") == spell
                for o in g.entities.values() for c in o.get("conditions", []))
    if not still:
        end_concentration(g, ce, "no creature is still affected")


def end_concentration(g, e, why):
    conc = e.get("concentration")
    if not conc:
        return
    g.set(e, concentration=None)
    g.say(f"{e['name']} loses Concentration on {conc['spell_name']} ({why}).", kind="condition")
    for other in list(g.entities.values()):
        linked = [c for c in other.get("conditions", []) if c.get("caster") == e["id"] and c.get("spell") == conc["spell"]]
        if linked:
            g.set(other, conditions=[c for c in other["conditions"] if c not in linked])
            g.say(f"  {other['name']}: {', '.join(c['name'] for c in linked)} from {conc['spell_name']} ends.", kind="condition")
        fx = [f for f in other.get("effects", []) if f.get("caster") == e["id"] and f.get("spell") == conc["spell"]]
        if fx:
            g.set(other, effects=[f for f in other["effects"] if f not in fx])


# ====================================================================== attacks

def find_weapon(e, name):
    if not name or name.lower() in ("unarmed", "unarmed strike", "punch"):
        return None, "unarmed"
    wielded = equipped(e, "weapon")
    key = srd.slug(name)
    for it in wielded:
        if srd.slug(it["name"]) == key or srd.slug(it["base_name"]) == key or it["id"] == name:
            return it, "equipped"
    for it in e.get("inventory", []):
        if it.get("kind") == "weapon" and (srd.slug(it["name"]) == key or it["id"] == name):
            raise RuleError(f"{e['name']} has a {it['name']} but it isn't in hand. Equip it first (drawing a weapon "
                            f"is part of an attack or your free object interaction): `item equip {e['id']} {it['id']}`")
    raise RuleError(f"{e['name']} has no weapon '{name}'. Wielded: {', '.join(i['name'] for i in wielded) or 'nothing'}")


def monster_action(e, name, kinds=("attack",)):
    acts = [a for a in e.get("actions", []) if a.get("kind") in kinds]
    if not name:
        if not acts:
            raise RuleError(f"{e['name']} has no attack actions in its stat block.")
        return acts[0]
    key = srd.slug(name)
    for a in e.get("actions", []):
        if srd.slug(a["name"]) == key or srd.slug(a["full_name"]) == key:
            return a
    raise RuleError(f"{e['name']}'s stat block has no action '{name}'. Actions: {', '.join(a['name'] for a in e.get('actions', []))}")


def attack_modes(g, att, tgt, ranged, dist, extra_adv=(), extra_dis=()):
    adv, dis = list(extra_adv), list(extra_dis)
    an, tn = condition_names(att), condition_names(tgt)
    for c in ATTACKER_DIS & an:
        dis.append(f"attacker {c}")
    if "invisible" in an:
        adv.append("attacker invisible")
    if "invisible" in tn:
        dis.append("target invisible")
    for c in TARGET_ADV & tn:
        adv.append(f"target {c}")
    if "prone" in tn:
        if dist is not None and dist <= 5 and not ranged:
            adv.append("target prone (within 5 ft)")
        elif ranged or (dist and dist > 5):
            dis.append("target prone (beyond 5 ft)")
    if any(c["name"] == "dodging" for c in tgt.get("conditions", [])) and "incapacitated" not in tn:
        dis.append("target Dodging")
    if any(c["name"] == "helped" for c in att.get("conditions", [])):
        adv.append("Help")
    if any(fx.get("name") == "untrained armor" for fx in att.get("effects", [])):
        dis.append("armor without training")
    if ranged and same_map(att, tgt):
        for other in g.entities.values():
            if other["id"] != att["id"] and alive(other) and hostile(att, other) and same_map(att, other) \
                    and not ({"incapacitated", "blinded"} & condition_names(other)) and dist_ft(att, other) <= 5:
                # rules glossary, Ranged Attack: only an enemy "who can see you" and isn't Incapacitated imposes this
                dis.append(f"hostile {other['name']} within 5 ft")
                break
    return adv, dis


def attack(g, att_ref, tgt_ref, weapon=None, adv=(), dis=(), reaction=False, offhand=False, versatile=False,
           sneak=False, smite=None, now=False, request=None, bonus_action=False, knockout=False):
    att, tgt = g.get(att_ref), g.get(tgt_ref)
    if not combat(g) and not request:
        raise RuleError("Attacking a creature starts a fight: `combat start` first (use --surprised for an ambush), "
                        "so turns and the action economy apply.")
    if not alive(att):
        raise RuleError(f"{att['name']} is at 0 HP / dead and can't attack.")
    if att["id"] == tgt["id"]:
        raise RuleError("A creature can't attack itself.")
    # ---------------------------------------------------------------- profile
    if att["kind"] == "pc":
        item, _ = find_weapon(att, weapon)
        prof = weapon_attack(att, item, versatile=versatile, offhand=offhand)
        reach, rng, ranged = prof["reach"], prof["range"], prof["ranged"]
        bonus, dmg_parts = prof["bonus"], [[prof["damage"], prof["type"]]]
        name = prof["name"]
        is_spell = False
    else:
        act = monster_action(att, weapon)
        if act.get("kind") == "save":
            return monster_save_action(g, att, act, [tgt_ref], now=now)
        if act.get("kind") != "attack":
            raise RuleError(f"'{act['name']}' isn't an attack roll; narrate it or use `save` with its DC. Text: {act['text'][:200]}")
        if act.get("recharge") and not att.get("recharge_ready", {}).get(act["name"], True):
            raise RuleError(f"{act['name']} hasn't recharged yet (Recharge {act['recharge']}–6, rolled at the start of {att['name']}'s turn).")
        reach, rng = act.get("reach"), act.get("range")
        ranged = act["attack_type"] == "ranged" or (act["attack_type"] == "melee or ranged" and rng and dist_ft(att, tgt) and dist_ft(att, tgt) > (reach or 5))
        bonus = act["bonus"]
        dmg_parts = [[d["dice"], d["type"]] for d in act.get("damage", []) if "condition" not in d]
        riders = [d for d in act.get("damage", []) if "condition" in d]
        name, item, prof = act["name"], None, {"ammo": False, "thrown": False, "mastery": None}
        is_spell = False
    # ---------------------------------------------------------------- position, range, cover
    d = dist_ft(att, tgt)
    cover = None
    if d is not None:
        m = g.state["maps"][att["token"]["map"]]
        oa_ok = reaction and combat(g) and economy(g, att["id"]).get("oa_window") == tgt["id"]
        if oa_ok:
            if request or not wants_request(g, att, now):  # keep the window open until the player's Roll resolves it
                set_economy(g, att["id"], oa_window=None)
            d = min(d, reach or 5)  # resolved at the moment the target stepped out of reach
        if not ranged and d > (reach or 5):
            if prof.get("thrown") and rng and reaction:
                # rules glossary, Opportunity Attacks: "make one melee attack". Never turn a reaction into a throw.
                raise RuleError(f"{tgt['name']} is {d} ft away, out of {name}'s {reach or 5} ft reach. An opportunity attack is a "
                                "melee attack made as the target leaves reach: resolve it before moving the target on.")
            if prof.get("thrown") and rng:
                ranged = True
            else:
                raise RuleError(f"{tgt['name']} is {d} ft away — out of {name}'s {reach or 5} ft reach. Move first or use a ranged attack.")
        if ranged and rng:
            if d > rng[1]:
                raise RuleError(f"{tgt['name']} is {d} ft away — beyond {name}'s long range ({rng[1]} ft).")
        creatures = [token_pos(o) for o in g.entities.values() if same_map(o, att) and alive(o)]
        cover = maps.cover_between(m, token_pos(att), token_pos(tgt), creatures)
        if cover == "total":
            raise RuleError(f"{tgt['name']} has Total Cover from {att['name']} — it can't be targeted directly.")
    extra_dis = list(dis)
    if ranged and rng and d is not None and d > rng[0]:
        extra_dis.append(f"long range ({d} ft > {rng[0]} ft)")
    if att["kind"] == "pc" and item and "heavy" in prof.get("properties", []) and att.get("size") == "Small":
        extra_dis.append("Heavy weapon, Small creature")
    # ---------------------------------------------------------------- action economy
    c = combat(g)
    ec = economy(g, att["id"]) if c else {}
    if c and not request:
        if reaction:
            use_action(g, att, "reaction", f"opportunity attack with {name}")
        elif offhand or bonus_action:
            if offhand and not ec.get("attacked_light"):
                raise RuleError("An off-hand attack requires having attacked with a Light weapon this turn (Light property).")
            if offhand and "light" not in prof.get("properties", []):
                raise RuleError(f"The Light property's extra attack must be made with a Light weapon — {name} isn't one.")
            if offhand and item and ec.get("light_item") == item.get("id") and item.get("qty", 1) < 2:
                raise RuleError(f"The extra attack must be made with a different Light weapon than {name}.")
            if offhand and ec.get("light_extra_done"):
                raise RuleError("The Light property grants only one extra attack per turn.")
            if offhand and current_id(g) != att["id"]:
                raise RuleError(f"It's not {att['name']}'s turn. Off-turn attacks must be reactions (--reaction).")
            if offhand and prof.get("mastery") == "nick" and ec.get("attacks_left") is not None:
                # Nick mastery: the Light extra attack is part of the Attack action instead of a Bonus Action (once per turn)
                g.note(f"  Nick: {att['name']}'s extra attack is part of the Attack action — the Bonus Action stays free.")
            else:
                use_action(g, att, "bonus", f"{'off-hand ' if offhand else ''}attack with {name}")
            if offhand:
                set_economy(g, att["id"], light_extra_done=True)
        else:
            if current_id(g) != att["id"]:
                raise RuleError(f"It's not {att['name']}'s turn. Off-turn attacks must be reactions (--reaction).")
            left = ec.get("attacks_left")
            if left is None or left <= 0:
                use_action(g, att, "action", f"Attack ({name})")
                left = attacks_per_action(att)
            light = "light" in prof.get("properties", [])
            set_economy(g, att["id"], attacks_left=left - 1,
                        attacked_light=ec.get("attacked_light") or light,
                        light_item=(item or {}).get("id") if light else ec.get("light_item"))
    # ---------------------------------------------------------------- ammunition
    if att["kind"] == "pc" and prof.get("ammo") and not request:
        use_ammo(g, att, item)
    # ---------------------------------------------------------------- roll
    a_adv, a_dis = attack_modes(g, att, tgt, ranged, d, adv, extra_dis)
    if wants_request(g, att, now) and not request:
        return {"request": make_request(g, att, f"attack with {name} vs {tgt['name']}",
                                        {"op": "attack", "att": att["id"], "tgt": tgt["id"], "weapon": weapon,
                                         "adv": list(adv), "dis": list(dis), "offhand": offhand, "versatile": versatile,
                                         "sneak": sneak, "smite": smite, "reaction": reaction})}
    mode = _mode(a_adv, a_dis)
    exh = exhaustion_penalty(att)
    total_bonus = bonus - exh
    r = g.roll(f"1d20{fmt_mod(total_bonus)}", f"attack: {name} vs {tgt['name']}", att["id"], mode, request=request)
    ac, _ = armor_class(tgt)
    cover_bonus = {"half": 2, "three-quarters": 5}.get(cover, 0)
    eff_ac = ac + cover_bonus
    crit = r["nat"] == 20 or (att["kind"] == "pc" and r["nat"] == 19 and att.get("subclasses", {}).get("Fighter") == "Champion" and att["classes"].get("Fighter", 0) >= 3) \
        or (r["nat"] == 18 and att.get("subclasses", {}).get("Fighter") == "Champion" and att["classes"].get("Fighter", 0) >= 15)
    hit = crit or (r["nat"] != 1 and r["total"] >= eff_ac)
    if hit and not crit and d is not None and d <= 5 and condition_names(tgt) & {"paralyzed", "unconscious"}:
        crit = True
    line = (f"⚔ {att['name']} attacks {tgt['name']} with {name}{_fmt_mode(mode, a_adv, a_dis)}: {r['text']} vs AC {eff_ac}"
            + (f" ({cover} cover +{cover_bonus})" if cover_bonus else "") + " → " +
            ("CRITICAL HIT!" if crit else "HIT" if hit else "MISS" + (" (natural 1)" if r["nat"] == 1 else "")))
    g.say(line, kind="attack", roll=r["id"], who=att["id"], target=tgt["id"], hit=hit, crit=crit, ranged=bool(ranged),
          weapon=name, dtype=(dmg_parts[0][1] if dmg_parts else None), nat=r["nat"])
    break_invisibility(g, att, "made an attack roll")
    if item and ranged and prof.get("thrown") and not prof.get("ammo") and att.get("inventory") and att.get("token") and tgt.get("token"):
        # a thrown weapon leaves the hand and ends up by the target (pick it up with `item pickup`)
        remove_item(g, att, item["id"], 1, "thrown")
        put_on_floor(g, tgt["token"]["map"], tgt["token"]["x"], tgt["token"]["y"],
                     dict(item, qty=1, equipped=False, attuned=False, venom=bool(item.get("venom")) and not hit),
                     f"thrown by {att['name']}")
    if not hit:
        if att["kind"] == "pc" and prof.get("mastery") == "graze" and prof["mastery"] in [m.lower() for m in att.get("masteries", [])]:
            gd = max(0, amod(att, prof["ability"]))
            if gd:
                apply_damage(g, tgt, [[gd, prof["type"]]], source=f"{name} (Graze mastery)")
        return {"hit": False, "roll": r}
    # ---------------------------------------------------------------- damage
    parts = []
    for expr, dtype in dmg_parts:
        dr = g.roll(expr, f"damage: {name}", att["id"], crit=crit)
        parts.append([dr["total"], dtype])
    notes = []
    if att["kind"] == "pc":
        if any(cn["name"] == "raging" for cn in att.get("conditions", [])) and prof.get("ability") == "str" and not ranged:
            rd = srd.num(srd.find("classes", "Barbarian")["levels"][att["classes"]["Barbarian"]].get("Rage Damage"), 2)
            parts.append([rd, prof["type"]])
            notes.append(f"Rage +{rd}")
        if sneak:
            if "Rogue" not in att["classes"]:
                raise RuleError("Only Rogues have Sneak Attack.")
            if economy(g, att["id"]).get("sneak_used"):
                raise RuleError("Sneak Attack can be used only once per turn.")
            if not (ranged or "finesse" in prof.get("properties", [])):
                raise RuleError("Sneak Attack requires a Finesse or Ranged weapon.")
            ally_adjacent = any(o["id"] not in (att["id"], tgt["id"]) and alive(o) and not hostile(att, o) and
                                "incapacitated" not in condition_names(o) and dist_ft(o, tgt) is not None and dist_ft(o, tgt) <= 5
                                for o in g.entities.values())
            if mode != "adv" and not (ally_adjacent and mode != "dis"):
                raise RuleError("Sneak Attack needs Advantage on the roll, or an ally within 5 ft of the target (and no Disadvantage).")
            sd = srd.find("classes", "Rogue")["levels"][att["classes"]["Rogue"]].get("Sneak Attack", "1d6")
            sr = g.roll(sd, "Sneak Attack", att["id"], crit=crit)
            parts.append([sr["total"], prof["type"]])
            notes.append(f"Sneak Attack {sr['text']}")
            if combat(g):
                set_economy(g, att["id"], sneak_used=True)
        if smite:
            smite_level = int(smite)
            if ranged:
                raise RuleError("Divine Smite requires a melee weapon or Unarmed Strike hit.")
            spend_slot(g, att, smite_level, "divine-smite", require_known=True)
            if combat(g):
                use_action(g, att, "bonus", "Divine Smite")
            extra = 1 if any(t in (tgt.get("type") or "").lower() for t in ("fiend", "undead")) else 0
            sr = g.roll(f"{2 + (smite_level - 1) + extra}d8", "Divine Smite", att["id"], crit=crit)
            parts.append([sr["total"], "radiant"])
            notes.append(f"Divine Smite (level {smite_level}) {sr['text']}")
        conc = att.get("concentration") or {}
        if conc.get("spell") == "hunters-mark" and tgt["id"] in conc.get("targets", []):
            hm = g.roll("1d6", "Hunter's Mark", att["id"], crit=crit)
            parts.append([hm["total"], "force"])
            notes.append(f"Hunter's Mark {hm['text']}")
    else:
        for rd in riders:
            notes.append(f"possible extra {rd['dice']} {rd['type']} {rd['condition']} — DM applies with `damage` if it applies")
    if notes:
        g.say("   + " + "; ".join(notes), kind="attack")
    apply_damage(g, tgt, parts, source=name, crit=crit, attacker=att, knockout=knockout,
                 melee_within_5=(not ranged and (d is None or d <= 5)))
    if item and item.get("venom") and g.state["time"] <= item.get("venom_until", -1):
        # the poison is spent on this hit (Dagger of Venom)
        att = g.get(att["id"])
        g.set(att, inventory=[dict(i, venom=False) if i["id"] == item["id"] else dict(i) for i in att["inventory"]])
        t2 = g.get(tgt["id"])
        if not t2.get("dead"):
            pr = g.roll("2d10", f"{name} poison", att["id"])
            saving_throw(g, t2, "con", 15, source=f"{name} poison", now=True,
                         effect={"damage": [[pr["total"], "poison"]], "half": False, "condition": "poisoned",
                                 "source": f"{name} poison (1 minute)"})
    if att["kind"] == "pc" and prof.get("mastery") and prof["mastery"] in [m.lower() for m in att.get("masteries", [])]:
        g.note(f"  Weapon Mastery available: {prof['mastery'].title()} (see rules/core/06-equipment.md → Mastery Properties)")
    return {"hit": True, "crit": crit, "roll": r}


def grapple_or_shove(g, att, tgt, kind, prone=False, reaction=False):
    """rules/core/08-rules-glossary.md → Unarmed Strike: Grapple / Shove. One attack of the Attack action. The target
    makes a Strength or Dexterity save (its better one) against 8 + the attacker's Strength modifier + Proficiency Bonus."""
    from .core import SIZE_ORDER
    if not tgt:
        raise RuleError(f"{kind.title()} needs --target.")
    d = dist_ft(att, tgt)
    if d is None or d > 5:
        raise RuleError(f"{tgt['name']} is out of reach ({d} ft) — a {kind} needs the target within 5 ft.")
    sz = lambda e: SIZE_ORDER.index(e.get("size", "Medium")) if e.get("size", "Medium") in SIZE_ORDER else 2  # noqa: E731
    if sz(tgt) > sz(att) + 1:
        raise RuleError(f"{tgt['name']} is too big to {kind} (more than one size larger than {att['name']}).")
    if kind == "grapple" and any(c["name"] == "grappled" and c.get("grappler") == att["id"] for c in tgt.get("conditions", [])):
        raise RuleError(f"{att['name']} is already grappling {tgt['name']}.")
    c = combat(g)
    if c and reaction:  # as an Opportunity Attack: an Unarmed Strike is a melee attack, and Grapple/Shove are its options
        use_action(g, att, "reaction", f"opportunity {kind}")
    elif c:  # it replaces one attack of the Attack action
        if current_id(g) != att["id"]:
            raise RuleError(f"It's not {att['name']}'s turn.")
        ec = economy(g, att["id"])
        left = ec.get("attacks_left")
        if left is None or left <= 0:
            use_action(g, att, "action", f"Attack ({kind})")
            left = attacks_per_action(att)
        set_economy(g, att["id"], attacks_left=left - 1)
    dc = 8 + amod(att, "str") + pb(att)
    ab = "str" if save_mod(tgt, "str") >= save_mod(tgt, "dex") else "dex"
    g.say(f"🤼 {att['name']} tries to {kind} {tgt['name']} ({ab.upper()} save DC {dc}).", kind="attack", who=att["id"], target=tgt["id"])
    res = saving_throw(g, tgt, ab, dc, source=f"{att['name']}'s {kind}", now=True)
    if res.get("success"):
        g.say(f"   {tgt['name']} breaks free of it.", kind="attack")
        return res
    tgt = g.get(tgt["id"])
    if kind == "grapple":
        conds = [x for x in tgt.get("conditions", []) if x["name"] != "grappled"]
        conds.append({"name": "grappled", "source": f"grappled by {att['name']} (escape DC {dc})", "grappler": att["id"], "escape_dc": dc})
        g.set(tgt, conditions=conds)
        g.say(f"{tgt['name']} is now Grappled by {att['name']} (Speed 0; escape: Athletics or Acrobatics DC {dc}).",
              kind="condition", who=tgt["id"], cond="grappled", on=True)
    elif prone:
        add_condition(g, tgt, "prone", source=f"shoved by {att['name']}")
    else:
        (ax, ay), (tx, ty) = token_pos(att), token_pos(tgt)
        dest = (tx + (tx > ax) - (tx < ax), ty + (ty > ay) - (ty < ay))
        move(g, tgt["id"], dest, force=f"shoved by {att['name']}")
    return res


def use_ammo(g, e, item):
    w = srd.find("weapons", item["base_name"])
    kind = {"bow": "arrow", "crossbow": "bolt", "sling": "bullet", "blowgun": "needle"}
    want = next((v for k, v in kind.items() if k in w["name"].lower()), "arrow")
    inv = e.get("inventory", [])
    for it in inv:
        if want in it["name"].lower() and it.get("qty", 1) > 0:
            new_inv = [dict(x) for x in inv]
            for x in new_inv:
                if x["id"] == it["id"]:
                    x["qty"] = x.get("qty", 1) - 1
            new_inv = [x for x in new_inv if x.get("qty", 1) > 0]
            g.set(e, inventory=new_inv)
            if combat(g):
                set_economy(g, e["id"], ammo_spent=economy(g, e["id"]).get("ammo_spent", 0) + 1, ammo_item=it["name"])
                # the turn economy resets every turn, so keep a fight-long tally for recovering ammunition afterwards
                c = dict(combat(g))
                tally = dict(c.get("ammo_total", {}))
                tally[e["id"]] = tally.get(e["id"], 0) + 1
                c["ammo_total"] = tally
                g.emit("combat.set", combat=c)
            return
    raise RuleError(f"{e['name']} is out of ammunition ({want}s) for the {item['name']}.")


def monster_save_action(g, att, act, targets, now=False):
    if act.get("recharge") and not att.get("recharge_ready", {}).get(act["name"], True):
        raise RuleError(f"{act['name']} hasn't recharged yet.")
    if act.get("per_day") and att.get("per_day_used", {}).get(act["name"], 0) >= act["per_day"]:
        raise RuleError(f"{act['name']} has no uses left today ({act['per_day']}/Day).")
    if combat(g):
        use_action(g, att, "bonus" if act["section"] == "bonus actions" else "reaction" if act["section"] == "reactions" else "action", act["name"])
    area = re.search(r"(\d+)-foot(?:-long)?[ -](Cone|Line|Emanation|Sphere|Cube|Cylinder)", act["text"])
    tgts = [g.get(t) for t in targets]
    if area and area.group(2) in ("Cone", "Line", "Emanation"):
        for t in tgts:
            dd = dist_ft(att, t)
            if dd is not None and dd > int(area.group(1)):
                raise RuleError(f"{t['name']} is {dd} ft away — outside {act['name']}'s {area.group(1)}-foot {area.group(2)}.")
    parts = []
    for dmg in act.get("damage", []):
        if "condition" in dmg:
            continue
        r = g.roll(dmg["dice"], f"{act['name']} damage", att["id"])
        parts.append([r["total"], dmg["type"]])
    g.say(f"🔥 {att['name']} uses {act['full_name']}! DC {act['dc']} {act['save_ability'].upper()} save" +
          (f" — {' + '.join(f'{a} {t}' for a, t in parts)} damage" if parts else ""), kind="attack")
    if act.get("recharge"):
        g.set(att, **{f"recharge_ready__{act['name']}": False})
    if act.get("per_day"):
        g.set(att, **{f"per_day_used__{act['name']}": att.get("per_day_used", {}).get(act["name"], 0) + 1})
    cond = None
    mc = re.search(r"\*Failure:\*.*?(?:has|have) the (\w+) condition", act["text"], re.S)
    if mc:
        cond = mc.group(1).lower()
    for t in tgts:
        saving_throw(g, t, act["save_ability"], act["dc"], source=act["name"], now=now,
                     effect={"damage": parts, "half": act.get("half_on_success"), "condition": cond, "source": act["name"]})
    return {"ok": True}


# ====================================================================== spells

def known_spell(e, spell):
    s = spell["slug"]
    sp = e.get("spells", {})
    if s in sp.get("cantrips", []) or s in sp.get("prepared", []):
        return "prepared"
    for gr in e.get("granted_spells", []):
        if gr["slug"] == s:
            return "granted"
    for cls, sub in e.get("subclasses", {}).items():
        c = srd.find("classes", cls)
        if c and sub in c["subclasses"]:
            for lv, lst in c["subclasses"][sub].get("spells", {}).items():
                if lv <= e["classes"][cls] and s in lst:
                    return "always"
    if s == "divine-smite" and e.get("classes", {}).get("Paladin", 0) >= 2:
        return "always"
    if s == "hunters-mark" and e.get("classes", {}).get("Ranger", 0) >= 1:
        return "always"
    return None


def spend_slot(g, e, slot_level, spell_slug, require_known=False):
    if e["kind"] != "pc":
        return
    slots = spell_slots(e)
    used = e.get("slots_used", {})
    pact = pact_slots(e)
    if combat(g) and current_id(g) == e["id"] and economy(g, e["id"]).get("slot_spell_cast"):  # own turn only; reactions (Shield) on others' turns are fine
        raise RuleError("A creature can expend only one spell slot to cast a spell per turn (rules/core/07-spellcasting-rules.md).")
    if slots.get(slot_level, 0) - used.get(str(slot_level), 0) > 0:
        g.set(e, **{f"slots_used__{slot_level}": used.get(str(slot_level), 0) + 1})
    elif pact and pact["level"] == slot_level and pact["count"] - e.get("pact_used", 0) > 0:
        g.set(e, pact_used=e.get("pact_used", 0) + 1)
    else:
        have = {lv: n - used.get(str(lv), 0) for lv, n in slots.items()}
        if pact:
            have[f"pact L{pact['level']}"] = pact["count"] - e.get("pact_used", 0)
        raise RuleError(f"{e['name']} has no level {slot_level} spell slot left. Remaining: " +
                        (", ".join(f"L{k}: {v}" for k, v in have.items()) or "none"))
    if combat(g):
        set_economy(g, e["id"], slot_spell_cast=True)


def scaled_dice(expr, times):
    m = re.match(r"(\d+)d(\d+)(.*)", expr)
    if not m:
        return expr
    return f"{int(m.group(1)) * times}d{m.group(2)}{m.group(3)}"


def add_dice(expr, extra, n):
    if not n:
        return expr
    m1 = re.match(r"(\d+)d(\d+)(.*)", expr)
    m2 = re.match(r"(\d+)d(\d+)", extra)
    if m1 and m2 and m1.group(2) == m2.group(2):
        return f"{int(m1.group(1)) + int(m2.group(1)) * n}d{m1.group(2)}{m1.group(3)}"
    return expr + "".join(f"+{extra}" for _ in range(n))


def cast(g, caster_ref, spell_name, slot_level=None, targets=(), ritual=False, free=None, adv=(), dis=(),
         condition=None, component=None, now=False, scroll=None, request=None):
    e = g.get(caster_ref)
    spell = g.require("spells", spell_name, "Spell")
    base = spell["level"]
    empty_area = any(str(t).lower() == "none" for t in targets)  # an area spell placed where no creature is (Web in a doorway)
    tgts = [g.get(t) for t in targets if str(t).lower() != "none"]
    harmful = spell["effect"].get("kind") in ("attack", "darts", "damage") or \
        (spell["effect"].get("kind") == "save" and spell["effect"].get("dice"))
    if not combat(g) and harmful and any(t["id"] != e["id"] for t in tgts):
        raise RuleError(f"Casting {spell['name']} at a creature starts a fight: `combat start` first (--surprised for an ambush).")
    if not alive(e):
        raise RuleError(f"{e['name']} can't cast spells at 0 HP.")
    if "incapacitated" in condition_names(e) and not spell["reaction"]:
        raise RuleError(f"{e['name']} is Incapacitated.")
    if any(fx.get("name") == "untrained armor" for fx in e.get("effects", [])):
        raise RuleError(f"{e['name']} is wearing armor without training and can't cast spells.")
    how = None
    if e["kind"] == "pc":
        if scroll:
            it = next((i for i in e.get("inventory", []) if i["id"] == scroll), None)
            if not it or "scroll" not in it["name"].lower() or srd.slug(it.get("spell", "")) != spell["slug"]:
                raise RuleError(f"{e['name']} has no Spell Scroll of {spell['name']} (item id {scroll}).")
            classes_ok = any(cls in spell["classes"] for cls in e["classes"])
            if not classes_ok:
                raise RuleError(f"{spell['name']} isn't on {e['name']}'s spell list — the scroll is unintelligible to them.")
            how = "scroll"
        else:
            how = known_spell(e, spell)
            if not how and ritual and spell.get("ritual") and "Wizard" in e.get("classes", {}) \
                    and spell["slug"] in e.get("spells", {}).get("spellbook", []):
                how = "ritual from spellbook (Ritual Adept)"  # rules/classes/wizard.md: Level 1 Ritual Adept
            if not how:
                raise RuleError(f"{e['name']} doesn't have {spell['name']} prepared (or granted by a feature). "
                                f"Prepared: {', '.join(e.get('spells', {}).get('prepared', [])) or 'none'}")
    else:
        source_act = next((a for a in e.get("actions", []) if spell["name"].lower() in a["text"].lower()
                           and re.search(r"\bcasts?\b", a["text"], re.I)), None)
        if not source_act:
            raise RuleError(f"{e['name']}'s stat block can't cast {spell['name']}.")
        how = "innate"
        if source_act.get("per_day"):
            used = e.get("per_day_used", {}).get(source_act["name"], 0)
            if used >= source_act["per_day"]:
                raise RuleError(f"{e['name']} has used {source_act['full_name']} {used}/{source_act['per_day']} times today.")
            g.set(e, **{f"per_day_used__{source_act['name']}": used + 1})
        m1 = re.search(r"(\d)/Day Each:\*\*\s*(.*)", source_act["text"])
        if m1 and spell["name"].lower() in m1.group(2).lower():
            key = f"{spell['slug']}-day"
            used = e.get("per_day_used", {}).get(key, 0)
            if used >= int(m1.group(1)):
                raise RuleError(f"{e['name']} can cast {spell['name']} only {m1.group(1)}/day.")
            g.set(e, **{f"per_day_used__{key}": used + 1})
    # --------------------------------------------------------------- how many creatures the slot allows
    maxt = spell["effect"].get("max_targets")
    if maxt:
        lvl = base if (ritual or free or scroll) else (slot_level or base)
        allowed = maxt + max(0, lvl - base) * spell["effect"].get("targets_per_level", 1)
        if len(tgts) > allowed:
            raise RuleError(f"{spell['name']} at level {lvl} affects at most {allowed} creature(s); you listed {len(tgts)}. "
                            f"Each slot level above {base} adds one more.")
    # --------------------------------------------------------------- slot / ritual / free cast
    if base == 0:
        slot_level = 0
    elif ritual:
        if not spell["ritual"]:
            raise RuleError(f"{spell['name']} doesn't have the Ritual tag.")
        if combat(g):
            raise RuleError("Ritual casting takes 10 extra minutes — not possible in combat.")
        slot_level = base
        g.emit("time.set", minutes=g.state["time"] + 10)
    elif how == "scroll":
        slot_level = base
    elif free:
        gr = next((x for x in e.get("granted_spells", []) if x["slug"] == spell["slug"] and x["source"].lower().startswith(free.lower())), None)
        if not gr:
            raise RuleError(f"{e['name']} has no free casting of {spell['name']} from '{free}'.")
        if gr.get("free_used"):
            raise RuleError(f"The free casting of {spell['name']} from {gr['source']} is used until a Long Rest.")
        new = [dict(x, free_used=True) if x is gr or (x["slug"] == gr["slug"] and x["source"] == gr["source"]) else x for x in e["granted_spells"]]
        g.set(e, granted_spells=new)
        slot_level = base
    elif e["kind"] == "pc":
        slot_level = slot_level or base
        if slot_level < base:
            raise RuleError(f"{spell['name']} is level {base}; it can't be cast with a level {slot_level} slot.")
        spend_slot(g, e, slot_level, spell["slug"])
    else:
        slot_level = slot_level or base
    # --------------------------------------------------------------- costly components
    comp = spell["components"]
    cost = re.search(r"worth (\d[\d,]*)\+? GP", comp)
    if cost and how != "scroll" and e["kind"] == "pc":
        need = int(cost.group(1).replace(",", ""))
        consumed = "consume" in comp.lower()
        inv = e.get("inventory", [])
        it = next((i for i in inv if i["id"] == component), None) if component else None
        if not it and not consumed:
            it = next((i for i in inv if any(w in i["name"].lower() for w in ("focus", "holy symbol", "component pouch", "arcane", "druidic", "amulet", "emblem", "reliquary", "staff", "wand", "orb", "crystal", "rod"))), None) \
                if not consumed and need <= 0 else None
        if not it:
            words = [w for w in re.findall(r"[a-z]+", comp.lower()) if len(w) > 4 and w not in ("worth", "which", "spell", "consumes")]
            it = next((i for i in inv if any(w in i["name"].lower() for w in words) and i.get("value_cp", 0) >= need * 100), None)
        if not it:
            raise RuleError(f"{spell['name']} needs a material component worth {need}+ GP ({comp}). "
                            f"{e['name']} has none — buy or find one (the component's value is tracked).")
        if consumed:
            g.set(e, inventory=[i for i in inv if i["id"] != it["id"]])
            g.say(f"  ({it['name']} is consumed by the spell.)")
    # --------------------------------------------------------------- action economy
    if combat(g) and not request:
        kind = "reaction" if spell["reaction"] else "bonus" if spell["bonus_action"] else "action"
        if spell["casting_time"].lower().startswith(("1 minute", "10 minutes", "1 hour", "8 hours", "12 hours", "24 hours")):
            raise RuleError(f"{spell['name']} takes {spell['casting_time']} to cast — not in combat rounds.")
        use_action(g, e, kind, f"cast {spell['name']}")
    if how == "scroll":
        g.set(e, inventory=[i for i in e["inventory"] if i["id"] != scroll])
    # --------------------------------------------------------------- range check
    if spell.get("range_ft") is not None:
        for t in tgts:
            dd = dist_ft(e, t)
            rng = spell["range_ft"] if spell["range_ft"] else 5
            if dd is not None and dd > rng and not spell["range"].lower().startswith("self"):
                raise RuleError(f"{t['name']} is {dd} ft away — beyond {spell['name']}'s range ({spell['range']}).")
    # --------------------------------------------------------------- concentration
    if spell["concentration"]:
        if e.get("concentration"):
            end_concentration(g, e, f"began concentrating on {spell['name']}")
        g.set(e, concentration={"spell": spell["slug"], "spell_name": spell["name"], "targets": [t["id"] for t in tgts],
                                "since": g.state["time"], "duration": spell["duration"]})
    sc = spellcasting(e).get(next(iter(c for c in e.get("classes", {}) if c in spell["classes"]), None) or next(iter(spellcasting(e) or {"x": 0}), None), {}) if e["kind"] == "pc" else {}
    if e["kind"] == "pc" and not sc and spellcasting(e):
        sc = next(iter(spellcasting(e).values()))
    if e["kind"] != "pc":
        text = " ".join(a["text"] for a in e.get("actions", []) if a["name"].lower() == "spellcasting")
        mdc = re.search(r"spell save DC (\d+)", text)
        mat = re.search(r"([+-]\d+) to hit with spell attacks", text)
        sc = {"dc": int(mdc.group(1)) if mdc else 10 + e.get("pb", 2), "attack": int(mat.group(1)) if mat else e.get("pb", 2),
              "ability": "int"}
    if how == "scroll" and base > max((spellcasting(e).get(c, {}).get("max_level", 0) for c in e["classes"]), default=0):
        chk = ability_check(g, e, sc["ability"], dc=10 + base, now=True, purpose=f"read scroll of {spell['name']}")
        if not chk.get("success"):
            g.say(f"The magic of the scroll fizzles — {spell['name']} vanishes from it.")
            return {"failed": True}
    g.say(f"✨ {e['name']} casts {spell['name']}" + (f" at level {slot_level}" if base and slot_level > base else "") +
          (" as a ritual" if ritual else "") + (f" (from {how})" if how in ("scroll", "granted") else "") +
          (f" targeting {', '.join(t['name'] for t in tgts)}" if tgts else "") + ".", kind="spell", who=e["id"],
          spell=spell["slug"], targets=[t["id"] for t in tgts], dtype=(spell.get("effect") or {}).get("type"),
          fxkind=(spell.get("effect") or {}).get("kind"))
    # --------------------------------------------------------------- effects
    fx = spell["effect"]
    char_level = level(e) if e["kind"] == "pc" else max(1, int(srd.num(str(e.get("cr", "1")).split("/")[0], 1)))
    upcast_n = max(0, slot_level - base) if base else 0

    def damage_expr():
        expr = fx.get("dice")
        if not expr:
            return None
        if fx.get("cantrip_scaling"):
            expr = scaled_dice(expr, 1 + (char_level >= 5) + (char_level >= 11) + (char_level >= 17))
        if fx.get("upcast") and upcast_n:
            expr = add_dice(expr, fx["upcast"], upcast_n)
        return expr

    kind = fx.get("kind")
    if kind == "heal":
        maxt = 6 if "mass" in spell["slug"] or "prayer" in spell["slug"] else 1
        if not tgts:
            raise RuleError(f"{spell['name']} needs a target (--targets).")
        if len(tgts) > maxt:
            raise RuleError(f"{spell['name']} can target at most {maxt} creature(s).")
        expr = fx["dice"]
        if fx.get("upcast") and upcast_n:
            expr = add_dice(expr, fx["upcast"], upcast_n)
        m = amod(e, sc["ability"]) if fx.get("add_mod") and sc else 0
        for t in tgts:
            if (t.get("type") or "").lower().startswith(("undead", "construct")):
                g.say(f"{spell['name']} has no effect on {t['name']} ({t['type']}).")
                continue
            r = g.roll(f"{expr}{fmt_mod(m) if m else ''}", f"{spell['name']} healing", e["id"])
            heal(g, t, r["total"], spell["name"])
    elif kind in ("attack",):
        if not tgts:
            raise RuleError(f"{spell['name']} needs a target (--targets).")
        count = 1
        if fx.get("beams"):
            count = 1 + (char_level >= 5) + (char_level >= 11) + (char_level >= 17)
        if fx.get("count"):
            count = fx["count"] + upcast_n * fx.get("count_per_level", 0)
        if len(tgts) > count:
            raise RuleError(f"{spell['name']} makes {count} attack(s); you listed {len(tgts)} targets.")
        seq = [tgts[i % len(tgts)] for i in range(count)] if len(tgts) < count and count > 1 else tgts
        for t in seq:
            spell_attack(g, e, t, spell, sc, damage_expr(), fx, adv, dis, now)
    elif kind == "save" and not tgts and empty_area:
        g.say(f"   {spell['name']} fills an area with no creatures in it — no saving throws yet.", kind="spell")
    elif kind == "save":
        if not tgts:
            raise RuleError(f"{spell['name']} needs targets (--targets) — list every creature in the area, or --targets none.")
        parts = []
        expr = damage_expr()
        if expr:
            r = g.roll(expr, f"{spell['name']} damage", e["id"])
            parts = [[r["total"], fx["type"]]]
        # the condition the SRD text says a failed save inflicts (e.g. Sleep → Incapacitated), unless the DM names one
        condition = condition or fx.get("condition")
        for t in tgts:
            saving_throw(g, t, fx["save"], sc["dc"], source=spell["name"], spell=True, now=now,
                         effect={"damage": parts, "half": fx.get("half"), "condition": condition, "source": spell["name"],
                                 "caster": e["id"], "spell": spell["slug"],
                                 "repeat_save": f"{fx['save']}:{sc['dc']}" if fx.get("repeat") and condition else None,
                                 "escalate": fx.get("escalate") if condition == fx.get("condition") else None})
    elif kind == "darts":
        if not tgts:
            raise RuleError("Magic Missile needs targets (--targets a,b; repeat a name to send more darts).")
        count = fx["count"] + upcast_n
        seq = list(targets) if len(targets) == count else [targets[i % len(targets)] for i in range(count)]
        r = g.roll(fx["dice"], "Magic Missile dart", e["id"])
        g.say(f"   {count} darts × {r['total']} force damage (one roll for all darts).")
        for tref in seq:
            t = g.get(tref)
            # rules/spells: Shield — "you take no damage from Magic Missile" while it lasts
            if any(c["name"] == "shielded" for c in t.get("conditions", [])) or                     any(x.get("spell") == "shield" for x in t.get("effects", [])):
                g.say(f"   🛡 {t['name']}'s Shield: no damage from Magic Missile.")
                continue
            apply_damage(g, t, [[r["total"], "force"]], source="Magic Missile")
    elif kind == "damage" and tgts and spell["slug"] != "divine-smite":
        expr = damage_expr()
        r = g.roll(expr, f"{spell['name']} damage", e["id"])
        for t in tgts:
            apply_damage(g, t, [[r["total"], fx["type"]]], source=spell["name"])
    else:
        if condition and tgts:
            for t in tgts:
                add_condition(g, t, condition, source=spell["name"], caster=e["id"], spell=spell["slug"])
        g.note(f"  {spell['name']}: effect is narrative — read rules/spells/{spell['slug']}.md and adjudicate. "
               f"Duration: {spell['duration']}.")
        if spell["slug"] == "mage-armor" and tgts:
            for t in tgts:
                g.set(t, effects=[f for f in t.get("effects", []) if f["name"] != "mage armor"] + [{"name": "mage armor", "caster": e["id"], "spell": "mage-armor"}])
        if spell["slug"] == "shield-of-faith" and tgts:
            for t in tgts:
                g.set(t, effects=t.get("effects", []) + [{"name": "Shield of Faith", "ac_bonus": 2, "caster": e["id"], "spell": "shield-of-faith"}])
        if spell["slug"] == "shield":
            g.set(e, effects=e.get("effects", []) + [{"name": "Shield", "ac_bonus": 5, "until": "start of your next turn", "spell": "shield", "caster": e["id"]}])
    return {"ok": True}


def spell_attack(g, e, t, spell, sc, expr, fx, adv, dis, now):
    ranged = fx.get("attack") == "ranged"
    d = dist_ft(e, t)
    cover = None
    if d is not None:
        m = g.state["maps"][e["token"]["map"]]
        cover = maps.cover_between(m, token_pos(e), token_pos(t), [token_pos(o) for o in g.entities.values() if same_map(o, e) and alive(o)])
        if cover == "total":
            raise RuleError(f"{t['name']} has Total Cover.")
    a_adv, a_dis = attack_modes(g, e, t, ranged, d, adv, dis)
    mode = _mode(a_adv, a_dis)
    r = g.roll(f"1d20{fmt_mod(sc['attack'] - exhaustion_penalty(e))}", f"spell attack: {spell['name']} vs {t['name']}", e["id"], mode)
    ac = armor_class(t)[0] + {"half": 2, "three-quarters": 5}.get(cover, 0)
    crit = r["nat"] == 20
    hit = crit or (r["nat"] != 1 and r["total"] >= ac)
    g.say(f"✨ {spell['name']} → {t['name']}{_fmt_mode(mode, a_adv, a_dis)}: {r['text']} vs AC {ac} → " +
          ("CRITICAL HIT!" if crit else "HIT" if hit else "MISS"), kind="attack", roll=r["id"], who=e["id"], target=t["id"],
          hit=hit, crit=crit, ranged=ranged, spell=spell["slug"], dtype=fx.get("type"), nat=r["nat"])
    break_invisibility(g, e, "made an attack roll")
    if hit and expr:
        dr = g.roll(expr, f"{spell['name']} damage", e["id"], crit=crit)
        apply_damage(g, t, [[dr["total"], fx["type"]]], source=spell["name"], crit=crit)


# ====================================================================== death saves

def death_save(g, e, now=False, request=None):
    if e["kind"] != "pc" or e["hp"] > 0 or e.get("dead"):
        raise RuleError(f"{e['name']} isn't dying.")
    if e.get("death", {}).get("stable"):
        raise RuleError(f"{e['name']} is Stable and doesn't make death saves.")
    if wants_request(g, e, now) and not request:
        return {"request": make_request(g, e, "a Death Saving Throw", {"op": "death", "who": e["id"]})}
    r = g.roll("1d20", "Death Saving Throw", e["id"], request=request)
    ds = dict(e.get("death", {"success": 0, "fail": 0}))
    if r["nat"] == 20:
        g.say(f"☀ {e['name']} rolls a natural 20 on a death save and regains 1 HP!", kind="roll", roll=r["id"])
        heal(g, e, 1, "natural 20 death save")
        return {"total": 20}
    if r["nat"] == 1:
        ds["fail"] = ds.get("fail", 0) + 2
    elif r["total"] >= 10:
        ds["success"] = ds.get("success", 0) + 1
    else:
        ds["fail"] = ds.get("fail", 0) + 1
    txt = f"💀 {e['name']} — Death Saving Throw: {r['text']} → successes {ds['success']}/3, failures {min(3, ds['fail'])}/3"
    patch = {"death": ds}
    if ds["fail"] >= 3:
        patch["dead"] = True
        txt += f". {e['name']} has DIED."
    elif ds["success"] >= 3:
        ds["stable"] = True
        txt += f". {e['name']} is Stable."
    g.set(e, **patch)
    g.say(txt, kind="roll", roll=r["id"], who=e["id"], death=("dead" if patch.get("dead") else "stable" if ds.get("stable") else
                                                            "fail" if r["nat"] == 1 or r["total"] < 10 else "success"))
    return {"total": r["total"]}


# ====================================================================== initiative & turns

def roll_initiative(g, e, surprised=False, now=False, request=None):
    dis = ["surprised"] if surprised else []
    adv = ["Remarkable Athlete"] if e["kind"] == "pc" and _has_feature(e, "Remarkable Athlete") else []
    m = initiative_mod(e) - exhaustion_penalty(e)
    if wants_request(g, e, now) and not request:
        return {"request": make_request(g, e, "Initiative", {"op": "initiative", "who": e["id"], "surprised": surprised})}
    r = g.roll(f"1d20{fmt_mod(m) if m else ''}", "Initiative", e["id"], _mode(adv, dis), request=request)
    return {"total": r["total"], "mod": m, "text": r["text"]}


def start_of_turn(g, e):
    """Recharge rolls, effects ending at start of turn, death saves."""
    for a in e.get("actions", []):
        if a.get("recharge") and not e.get("recharge_ready", {}).get(a["name"], True):
            r = g.roll("1d6", f"recharge {a['name']}", e["id"])
            if r["total"] >= a["recharge"]:
                g.set(e, **{f"recharge_ready__{a['name']}": True})
                g.say(f"🔄 {e['name']}'s {a['name']} recharges ({r['total']}).", kind="roll")
            else:
                g.note(f"  {a['name']} recharge: {r['total']} — not ready")
    fx = [f for f in e.get("effects", []) if f.get("until") == "start of your next turn"]
    if fx:
        g.set(e, effects=[f for f in e["effects"] if f not in fx])
    conds = [c for c in e.get("conditions", []) if c.get("until") in ("start of its next turn", "start of your next turn")] + \
            [c for c in e.get("conditions", []) if c["name"] == "dodging"]
    for c in conds:
        remove_condition(g, e, c["name"], quiet=True)
    if e.get("legendary_actions"):
        g.set(e, legendary_used=0)
    if e["kind"] == "pc" and e["hp"] == 0 and not e.get("dead") and not e.get("death", {}).get("stable"):
        g.say(f"{e['name']} is dying and must make a Death Saving Throw.", kind="info")
        death_save(g, e)


def end_of_turn(g, e):
    conds = [c for c in e.get("conditions", []) if c.get("until") in ("end of its next turn", "end of your next turn", "end of turn")]
    for c in conds:
        remove_condition(g, e, c["name"], quiet=True)
        g.say(f"{e['name']}'s {c['name'].title()} ends.", kind="condition")
    for c in e.get("conditions", []):
        if c.get("save"):
            ab, dc = c["save"].split(":")
            res = saving_throw(g, e, ab, int(dc), source=f"end {c['name']}", now=True)
            if res.get("success"):
                remove_condition(g, e, c["name"])
                release_spell_if_unused(g, c)
            elif c.get("escalate"):
                # second failed save: the effect deepens (Sleep: Incapacitated → Unconscious for the duration)
                # the deeper condition first, so the spell still has a target and the caster keeps Concentration
                add_condition(g, g.get(e["id"]), c["escalate"], source=c.get("source"), caster=c.get("caster"), spell=c.get("spell"))
                ee = g.get(e["id"])
                g.set(ee, conditions=[x for x in ee.get("conditions", []) if x is not c and x != c])
    rounds = [c for c in e.get("conditions", []) if c.get("rounds")]
    if rounds:
        new = []
        for c in e.get("conditions", []):
            if c.get("rounds"):
                c = dict(c, rounds=c["rounds"] - 1)
                if c["rounds"] <= 0:
                    g.say(f"{e['name']}'s {c['name'].title()} ends.", kind="condition")
                    continue
            new.append(c)
        g.set(e, conditions=new)


# ====================================================================== movement

def move(g, ref, dest=None, path=None, dash=False, force=None, crawl=False, jump=False, group=None):
    e = g.get(ref)
    if not e.get("token"):
        raise RuleError(f"{e['name']} isn't placed on a map. Use `place`.")
    m = g.state["maps"][e["token"]["map"]]
    start = token_pos(e)
    others = {o["id"]: o for o in g.entities.values()
              if o["id"] != e["id"] and same_map(o, e) and alive(o) and not o.get("offstage")}  # left the scene: not in the way
    hostile_sq = set()
    for o in others.values():
        if hostile(e, o):
            ox, oy = token_pos(o)
            n = o.get("cells", 1)
            hostile_sq |= {(ox + i, oy + j) for i in range(n) for j in range(n)}
    ally_sq = {token_pos(o) for o in others.values() if not hostile(e, o)}
    names = condition_names(e)
    prone = "prone" in names
    mult = 2 if (prone and crawl) else 1
    c = combat(g)
    if force:
        cost_sq = 0
        dest = tuple(dest)
        if maps.move_cost(m, *dest) is None:
            raise RuleError("Forced movement can't end inside an impassable square.")
        full = [start, dest]
    else:
        if prone and not crawl:
            raise RuleError(f"{e['name']} is Prone: `stand {e['id']}` (costs half Speed) or move with --crawl (double cost).")
        if path:
            full = [start] + [tuple(p) for p in path]
            try:
                cost_sq = maps.path_cost(m, full, mult)
            except ValueError as err:
                raise RuleError(str(err))
            for sq in full[1:]:
                if sq in hostile_sq:
                    raise RuleError(f"Square {sq} is occupied by a hostile creature — you can't move through it.")
        else:
            dest = tuple(dest)
            dist, parent = maps.pathfind(m, start, dest, blocked=frozenset(hostile_sq), cost_mult=mult)
            if dest not in dist:
                raise RuleError(f"No path from {start} to {dest} (walls, impassable terrain or hostile creatures in the way).")
            full = maps.path_to(parent, start, dest)
            cost_sq = dist[dest]
        if full[-1] in ally_sq or full[-1] in hostile_sq:
            raise RuleError(f"{full[-1]} is occupied — you can move through an ally's space but can't end your move there.")
    feet = cost_sq * 5
    if c and not force:
        ec = economy(g, e["id"])
        if current_id(g) != e["id"]:
            raise RuleError(f"It's not {e['name']}'s turn — creatures move on their own turn (or via a reaction/forced movement with --force).")
        sp = move_speed(e)
        budget = sp * (2 if ec.get("dashed") else 1) + (sp if ec.get("dashed2") else 0)
        used = ec.get("move_used", 0)
        if used + feet > budget:
            steps = len(full) - 1
            why = []
            if cost_sq > steps * mult:
                why.append("difficult terrain on the way costs double")
            if mult == 2:
                why.append("crawling costs double")
            route = " ".join(f"{x},{y}" for x, y in full[1:])
            why.append(f"route: {route}; no cutting diagonally past a wall corner or door frame")
            raise RuleError(f"{e['name']} has {budget - used} ft of movement left this turn; that path costs {feet} ft "
                            f"({'; '.join(why)}). Dash to move farther.")
        # opportunity attack warnings: leaving a hostile's reach
        if not ec.get("disengaged"):
            for o in others.values():
                if not hostile(e, o) or "incapacitated" in condition_names(o):
                    continue
                reach = max([a.get("reach") or 5 for a in o.get("actions", []) if a.get("kind") == "attack"] or [5])
                if o["kind"] == "pc":
                    reach = max([a["reach"] for a in derive(o)["attacks"] if not a["ranged"]] or [5])
                was_in = maps.distance_squares(start, token_pos(o)) * 5 <= reach
                for sq in full[1:]:
                    if was_in and maps.distance_squares(sq, token_pos(o)) * 5 > reach:
                        g.say(f"⚠ {e['name']} leaves {o['name']}'s reach — {o['name']} may make an Opportunity Attack "
                              f"(`attack {o['id']} {e['id']} --reaction`).", kind="warning")
                        # the attack happens as the target leaves reach: remember the window so the reaction can resolve
                        set_economy(g, o["id"], oa_window=e["id"])
                        break
                    was_in = maps.distance_squares(sq, token_pos(o)) * 5 <= reach
        set_economy(g, e["id"], move_used=used + feet)
    end = full[-1]
    g.set(e, token={**e["token"], "x": end[0], "y": end[1]})
    trap_hits = [f for f in m.get("features", []) if f.get("type") == "trap" and f.get("hidden") and (f["x"], f["y"]) in set(full[1:])]
    g.say(f"🚶 {e['name']} moves {feet} ft to ({end[0]},{end[1]})" + (" (forced)" if force else "") + ".", kind="move", who=e["id"],
          path=[list(p) for p in full], map=e["token"]["map"], forced=bool(force), **({"group": group} if group else {}))
    for t in trap_hits:
        g.note(f"  ⚠ TRAP: {e['name']} entered ({t['x']},{t['y']}) — {t['name']}. {t.get('note', '')} (passive Perception {derive(e).get('passive_perception', 10)})")
    reveal_for(g, e)
    return {"feet": feet, "path": full}


def stand(g, ref):
    e = g.get(ref)
    if "prone" not in condition_names(e):
        raise RuleError(f"{e['name']} isn't Prone.")
    if combat(g):
        ec = economy(g, e["id"])
        half = move_speed(e) // 2
        if ec.get("move_used", 0) + half > move_speed(e) * (2 if ec.get("dashed") else 1):
            raise RuleError(f"Standing up costs {half} ft of movement; {e['name']} doesn't have enough left.")
        set_economy(g, e["id"], move_used=ec.get("move_used", 0) + half)
    remove_condition(g, e, "prone")


def vision_ft(g, e, m):
    light = m.get("lighting", "bright")
    dv = e.get("darkvision", 0)
    carried = 0
    for it in e.get("inventory", []):
        n = it["name"].lower()
        if it.get("lit"):
            carried = max(carried, 40 if "torch" in n else 60 if "lantern" in n else 10)
    if light in ("bright", "dim"):
        # SRD: dim light only makes an area Lightly Obscured (Disadvantage on sight-based Perception); it doesn't limit
        # how far you can see, so dim is revealed like bright light. Walls and doors still block line of sight.
        return max(120, dv, carried)
    return max(dv, carried)


def reveal_for(g, e):
    t = e.get("token")
    if not t:
        return
    m = g.state["maps"][t["map"]]
    if not m.get("fog") or (e["kind"] != "pc" and e.get("side") != "ally"):
        return
    r = vision_ft(g, e, m) // 5
    if r <= 0:
        return
    cells = maps.visible_cells(m, (t["x"], t["y"]), r)
    new = [[x, y] for x, y in cells if m["revealed"][y][x] != "1"]
    # walls adjacent to visible floor
    if new:
        g.emit("map.reveal", id=m["id"], cells=new)


# ====================================================================== rests

def concentration_minutes(conc):
    """'Concentration, up to 1 minute' -> 1; None if the duration isn't a length of time."""
    text = re.sub(r"(?i)^\s*concentration,\s*up to\s*", "", str(conc.get("duration") or ""))
    if not re.match(r"\s*\d", text):
        return None
    return parse_duration(text)


def after_time(g):
    """Things that happen as in-world time passes: concentration spells run out at the end of their duration,
    and stable creatures regain 1 HP after 1d4 hours."""
    for e in list(g.entities.values()):
        conc = e.get("concentration")
        if not conc or conc.get("since") is None:
            continue
        mins = concentration_minutes(conc)
        if mins is not None and g.state["time"] >= conc["since"] + mins:
            end_concentration(g, e, "its duration ran out")
    for e in list(g.entities.values()):
        wake = e.get("knockout_wake_at")
        if wake is not None and not e.get("dead") and g.state["time"] >= wake and                 any(c["name"] == "unconscious" and c.get("source") == "knocked out" for c in e.get("conditions", [])):
            remove_condition(g, e, "unconscious", quiet=True)
            g.say(f"{e['name']} comes round: the knockout's Short Rest is over.", kind="heal", who=e["id"])
    for e in g.pcs():
        wake = e.get("death", {}).get("wake_at")
        if e["hp"] == 0 and not e.get("dead") and wake is not None and g.state["time"] >= wake:
            g.set(e, hp=1, death={"success": 0, "fail": 0, "stable": False})
            remove_condition(g, g.get(e["id"]), "unconscious", quiet=True)
            g.say(f"{e['name']} regains 1 HP and wakes up.", kind="heal")


def require_no_dying(g, what):
    dying = [e["name"] for e in g.pcs() if e["hp"] == 0 and not e.get("dead") and not e.get("death", {}).get("stable")]
    if dying:
        raise RuleError(f"{', '.join(dying)} {'is' if len(dying) == 1 else 'are'} dying (0 HP, not stable). Stabilize or heal them "
                        f"before {what} — time doesn't skip past death saves.")


def short_rest(g, members, hit_dice=None, focus=None):
    if combat(g):
        raise RuleError("You can't rest during combat.")
    require_no_dying(g, "resting")
    hit_dice = hit_dice or {}
    g.emit("time.set", minutes=g.state["time"] + 60)
    g.say(f"⏳ The party takes a Short Rest (1 hour). Now {fmt_time(g.state['time'])}.", kind="rest")
    after_time(g)
    for e in members:
        if e.get("dead"):
            continue
        n = int(hit_dice.get(e["id"], 0))
        spent = dict(e.get("hd_spent", {}))
        if n and not e.get("classes"):
            # monsters / NPCs: Hit Point Dice come from the stat block's HP expression, e.g. 65 (10d8 + 20) → ten d8s
            mon = srd.find("monsters", e.get("srd") or e.get("srd_name") or "") or {}
            m = re.match(r"(\d+)d(\d+)", str(mon.get("hp_dice") or ""))
            if not m:
                raise RuleError(f"{e['name']} has no Hit Point Dice in its stat block.")
            total, die = int(m.group(1)), int(m.group(2))
            if spent.get("monster", 0) + n > total:
                raise RuleError(f"{e['name']} has only {total - spent.get('monster', 0)} Hit Point Dice left.")
            for _ in range(n):
                r = g.roll(f"1d{die}{fmt_mod(amod(e, 'con'))}", "Hit Point Die", e["id"])
                spent["monster"] = spent.get("monster", 0) + 1
                g.set(e, hd_spent=spent)
                heal(g, g.get(e["id"]), max(0, r["total"]), f"Hit Point Die ({r['text']})")
            n = 0
        for _ in range(n):
            if g.get(e["id"])["hp"] >= hp_max(e):
                g.say(f"{e['name']} is at full HP and keeps the rest of their Hit Point Dice.", kind="info")
                break
            cls = max(e["classes"], key=lambda c: e["classes"][c] - spent.get(c, 0))
            if e["classes"][cls] - spent.get(cls, 0) <= 0:
                raise RuleError(f"{e['name']} has no Hit Point Dice left.")
            die = srd.find("classes", cls)["hit_die"]
            r = g.roll(f"1d{die}{fmt_mod(amod(e, 'con'))}", "Hit Point Die", e["id"])
            spent[cls] = spent.get(cls, 0) + 1
            g.set(e, hd_spent=spent)
            heal(g, g.get(e["id"]), max(0, r["total"]), f"Hit Point Die ({r['text']})")
        e = g.get(e["id"])
        used = dict(e.get("resources_used", {}))
        for name, info in resources(e).items():
            if info["short"] == "all":
                used[name] = 0
            elif info["short"] == "one":
                used[name] = max(0, used.get(name, 0) - 1)
            elif info["short"] == "font" and e["classes"].get("Bard", 0) >= 5:
                used[name] = 0
        g.set(e, resources_used=used, pact_used=0)
    for eid, ref in (focus or {}).items():
        # SRD: focus on one magic item during a Short Rest while in contact with it; at the end you learn its properties
        identify_item(g, g.get(eid), ref, "focused on it through a Short Rest")


def long_rest(g, members):
    if combat(g):
        raise RuleError("You can't rest during combat.")
    now = g.state["time"]
    for e in members:
        last = e.get("last_long_rest_end")
        if last is not None and now - last < 16 * 60:
            raise RuleError(f"{e['name']} finished a Long Rest {fmt_duration(now - last)} ago — you must wait at least 16 hours "
                            f"before starting another (rules/core/08-rules-glossary.md → Long Rest).")
        if e["hp"] < 1 and not e.get("dead"):
            raise RuleError(f"{e['name']} has 0 HP — a creature needs at least 1 HP to start a Long Rest.")
    g.emit("time.set", minutes=now + 8 * 60)
    g.say(f"🌙 The party takes a Long Rest (8 hours). Now {fmt_time(g.state['time'])}.", kind="rest")
    after_time(g)
    for e in members:
        if e.get("dead"):
            continue
        patch = {"hp": hp_max(e), "hd_spent": {}, "slots_used": {}, "pact_used": 0, "resources_used": {},
                 "exhaustion": max(0, e.get("exhaustion", 0) - 1), "last_long_rest_end": g.state["time"],
                 "death": {"success": 0, "fail": 0, "stable": False}}
        if e.get("granted_spells"):
            patch["granted_spells"] = [dict(x, free_used=False) for x in e["granted_spells"]]
        if "Resourceful" in e.get("species_traits", []) and not e.get("inspiration"):
            patch["inspiration"] = True  # Human: Resourceful
        g.set(e, **patch)
        if patch.get("inspiration"):
            g.say(f"🌟 {e['name']} gains Heroic Inspiration — Resourceful (Human).", kind="xp")
        g.say(f"   {e['name']}: HP {hp_max(e)}/{hp_max(e)}, spell slots and features restored" +
              (f", Exhaustion {e.get('exhaustion', 0)} → {max(0, e.get('exhaustion', 0) - 1)}" if e.get("exhaustion") else "") + ".")


def fmt_duration(minutes):
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m}m" if h else f"{m}m"


# ====================================================================== items & coins

def coins_total_cp(e):
    return sum(e.get("coins", {}).get(k, 0) * v for k, v in COIN_CP.items())


def parse_coins(text):
    """'10gp 5sp' / '+3 gp' / '-2pp' -> copper (signed)."""
    total, found = 0, False
    for sign, n, unit in re.findall(r"([+-]?)\s*(\d[\d,]*)\s*(cp|sp|ep|gp|pp)", str(text).lower()):
        total += (-1 if sign == "-" else 1) * int(n.replace(",", "")) * COIN_CP[unit]
        found = True
    if not found:
        raise RuleError(f"Can't read coins from '{text}' (use e.g. 25gp, 3sp).")
    return total


def cp_to_coins(cp):
    out = {}
    for k in ("pp", "gp", "sp", "cp"):
        if k == "pp":
            continue
        out[k], cp = divmod(cp, COIN_CP[k])
    return {k: v for k, v in out.items()}


def change_coins(g, e, delta_cp, reason):
    total = coins_total_cp(e) + delta_cp
    if total < 0:
        raise RuleError(f"{e['name']} can't afford that: has {fmt_cp(coins_total_cp(e))}, needs {fmt_cp(-delta_cp)}.")
    coins = dict(e.get("coins", {}))
    if delta_cp >= 0:
        # add in gp/sp/cp denominations
        for k in ("gp", "sp", "cp"):
            n, delta_cp = divmod(delta_cp, COIN_CP[k])
            coins[k] = coins.get(k, 0) + n
    else:
        coins = cp_to_coins(total)
        coins["pp"] = 0
    g.set(e, coins=coins)
    return coins


def fmt_cp(cp):
    gp, rem = divmod(int(cp), 100)
    sp, c = divmod(rem, 10)
    return " ".join(p for p in (f"{gp} GP" if gp else "", f"{sp} SP" if sp else "", f"{c} CP" if c else "") if p) or "0 GP"


def resolve_item(g, name):
    """Identify an item from the SRD (or homebrew). Returns a dict describing it."""
    raw = name.strip()
    low = raw.lower()
    hb = g.state["homebrew"].get("items", {}).get(srd.slug(raw))
    if hb:
        return {**hb, "homebrew": True}
    # +N weapon / armor / shield / ammunition, e.g. "Longsword +1", "+2 Chain Mail", "Shield +1"
    pm = re.search(r"\+([123])", low)
    if pm:
        n = int(pm.group(1))
        base_name = re.sub(r"\s*\+[123]\s*", " ", raw).strip(" ,")
        base_name = re.sub(r"^(weapon|armor)\s*,?\s*", "", base_name, flags=re.I).strip()
        w = srd.find("weapons", base_name)
        a = srd.find("armor", base_name)
        if w:
            return {"name": f"{w['name']} +{n}", "kind": "weapon", "base_name": w["name"], "magic": True, "magic_bonus": n,
                    "ref": "weapon-1-2-or-3", "rarity": PLUS_RARITY["weapon"][n], "value_cp": (MAGIC_VALUE_GP[PLUS_RARITY["weapon"][n]] * 100) + (w["cost_cp"] or 0)}
        if a:
            k = "shield" if a["category"] == "shield" else "armor"
            return {"name": f"{a['name']} +{n}", "kind": "armor", "base_name": a["name"], "category": a["category"],
                    "magic": True, "magic_bonus": n, "ref": "shield-1-2-or-3" if k == "shield" else "armor-1-2-or-3",
                    "rarity": PLUS_RARITY[k][n], "value_cp": MAGIC_VALUE_GP[PLUS_RARITY[k][n]] * 100 + (a["cost_cp"] or 0)}
        if re.search(r"arrow|bolt|bullet|needle|ammunition", low):
            return {"name": raw, "kind": "gear", "magic": True, "magic_bonus": n, "ref": "ammunition-1-2-or-3",
                    "rarity": PLUS_RARITY["ammunition"][n], "value_cp": MAGIC_VALUE_GP[PLUS_RARITY["ammunition"][n]] * 100 // 10}
    for pn, (dice_expr, rarity) in POTIONS.items():
        if low == pn:
            return {"name": raw.title().replace("Of", "of"), "kind": "consumable", "magic": True, "ref": "potions-of-healing",
                    "rarity": rarity, "heal": dice_expr, "value_cp": MAGIC_VALUE_GP[rarity] * 50}
    sm = re.match(r"spell scroll(?: of| \()?\s*([^)]*)\)?$", low)
    if sm and sm.group(1):
        sp = srd.find("spells", sm.group(1))
        if not sp:
            raise RuleError(f"No SRD spell '{sm.group(1)}' for a spell scroll.")
        rar = SCROLL_RARITY[sp["level"]]
        return {"name": f"Spell Scroll ({sp['name']})", "kind": "consumable", "magic": True, "ref": "spell-scroll",
                "spell": sp["slug"], "rarity": rar, "value_cp": MAGIC_VALUE_GP[rar] * 100}
    w = srd.find("weapons", raw)
    if w:
        return {"name": w["name"], "kind": "weapon", "base_name": w["name"], "value_cp": w["cost_cp"] or 0}
    a = srd.find("armor", raw)
    if a:
        return {"name": a["name"], "kind": "armor", "base_name": a["name"], "category": a["category"], "value_cp": a["cost_cp"] or 0}
    named_base = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", raw)   # "Flame Tongue (Longsword)"
    mi = srd.find("magic_items", raw) or (srd.find("magic_items", named_base.group(1)) if named_base else None)
    if mi:
        rar = mi["rarities"][0] if len(mi["rarities"]) == 1 else None
        if not rar:
            raise RuleError(f"{mi['name']} comes in several rarities ({', '.join(mi['rarities'])}) — name the specific version.")
        out = {"name": mi["name"], "kind": "consumable" if mi["consumable"] else "magic", "magic": True, "ref": mi["slug"],
               "rarity": rar, "needs_attunement": mi["attunement"], "meta": mi["meta"],
               "value_cp": MAGIC_VALUE_GP.get(rar, 0) * (50 if mi["consumable"] else 100)}
        # a magic weapon or armor is still that weapon/armor: "Weapon (Dagger)", "Armor (Plate Armor)", "Weapon (Any Sword)"
        wm = re.match(r"\W*(Weapon|Armor)\s*\(([^)]+)\)", mi.get("meta") or "")
        if wm:
            text = (srd.RULES / "magic-items" / f"{mi['slug']}.md")
            text = text.read_text(encoding="utf-8") if text.exists() else ""
            want = named_base.group(2) if named_base else wm.group(2)
            table = "weapons" if wm.group(1) == "Weapon" else "armor"
            base = srd.find(table, want)
            if not base:
                out["needs_base"] = wm.group(2)   # reported after the treasure-limit check (add_item)
                return out
            out.update({"kind": "weapon" if table == "weapons" else "armor", "base_name": base["name"],
                        "name": mi["name"] if not named_base or wm.group(2).lower() == base["name"].lower() else f"{mi['name']} ({base['name']})"})
            if table == "armor":
                out["category"] = base["category"]
            bm = re.search(r"\+(\d) bonus to attack rolls and damage rolls" if table == "weapons" else r"\+(\d) bonus to Armor Class", text)
            if bm:
                out["magic_bonus"] = int(bm.group(1))
        return out
    gear = srd.find("gear", raw)
    if gear:
        return {"name": gear["name"], "kind": "gear", "value_cp": gear["cost_cp"]}
    return None


def check_magic_allowed(g, item, override):
    if not item.get("magic"):
        return
    lvl = g.party_level()
    cap = TIER_MAX_RARITY[tier(lvl)]
    rar = item.get("rarity", "Common")
    if RARITY_ORDER.index(rar) > RARITY_ORDER.index(cap):
        if not override:
            raise RuleError(f"{item['name']} is {rar}; for a party of level {lvl} (tier {tier(lvl)}) the ceiling is {cap}. "
                            f"Rarer treasure needs `--override \"story reason\"` (shown to the player).")
        g.override(override, f"{rar} item {item['name']} at party level {lvl}")


def new_item_id(e, name):
    base = srd.slug(name)[:24] or "item"
    ids = {i["id"] for i in e.get("inventory", [])}
    n = 1
    while f"{base}-{n}" in ids:
        n += 1
    return f"{base}-{n}"


def add_item(g, e, name, qty=1, source="found", price=None, purchase=False, override=None, custom=None, identified=None):
    if qty < 1:
        raise RuleError("Quantity must be at least 1.")
    item = resolve_item(g, name)
    if not item:
        if custom is None:
            sug = srd.suggest("gear", name) + srd.suggest("magic_items", name) + srd.suggest("weapons", name)
            raise RuleError(f"'{name}' isn't an SRD item" + (f" (did you mean: {', '.join(sug[:5])}?)" if sug else "") +
                            ". For a mundane oddity use --custom \"description\" (worth nothing unless priced) or register homebrew.")
        if str(custom).lstrip().startswith("{"):  # a homebrew-style JSON blob passed as --custom: keep just its text
            try:
                custom = json.loads(custom).get("description") or custom
            except (ValueError, AttributeError):
                pass
        item = {"name": name, "kind": "gear", "custom": True, "description": custom, "value_cp": 0}
    if item.get("magic"):
        check_magic_allowed(g, item, override)
    if item.get("needs_base"):
        raise RuleError(f"{item['name']} can be {item['needs_base']} — name the base item, e.g. \"{item['name']} (Longsword)\".")
    if purchase:
        # rules/core/10-magic-item-rules.md: Common items can often be bought in a town; rarer ones are rarely for sale
        if item.get("magic") and item.get("rarity") != "Common" and not override:
            raise RuleError(f"{item.get('rarity')} magic items aren't sold in ordinary shops. A purchase needs "
                            "--override \"where/why it's for sale\" (shown to the player).")
        cost = (price if price is not None else item.get("value_cp"))
        if cost is None or cost == 0 and not item.get("custom"):
            raise RuleError(f"No listed price for {item['name']}; pass --price (the DM's quoted price, public).")
        if price is not None and item.get("value_cp") and price < item["value_cp"] // 2 and not override:
            raise RuleError(f"{fmt_cp(price)} is less than half the listed price ({fmt_cp(item['value_cp'])}). "
                            f"A discount that large needs --override with the reason (haggling result, favour...).")
        change_coins(g, e, -cost * qty, f"buy {item['name']}")
        source = f"purchased for {fmt_cp(cost * qty)}"
    if item.get("magic"):
        # SRD: learning a magic item's properties isn't automatic (Identify, or a Short Rest focused on it). Bought and
        # starting items are known; anything found, looted, stolen or given starts unidentified unless the DM says otherwise.
        known = identified if identified is not None else (purchase or bool(re.match(r"^(starting|purchase|crafted)", source or "", re.I)))
        item = {**item, "identified": bool(known)}
    inv = [dict(i) for i in e.get("inventory", [])]
    stackable = (item["kind"] in ("gear", "consumable") or (item["kind"] == "weapon" and not item.get("magic"))) and not item.get("custom")
    existing = next((i for i in inv if stackable and i["name"] == item["name"] and i.get("identified", True) == item.get("identified", True)), None)
    if existing:
        existing["qty"] = existing.get("qty", 1) + qty
    else:
        inv.append({"id": new_item_id(e, item["name"]), **item, "qty": qty, "equipped": False, "source": source})
    g.set(e, inventory=inv)
    label = item["name"] + (f" ({item['rarity']})" if item.get("rarity") else "")
    if item.get("magic") and not item.get("identified"):
        label = f"{item_display_name(item)} (its properties are unknown until identified)"
    g.say(f"🎒 {e['name']} gains {qty}× {label} — {source}.", kind="item", who=e["id"])
    return item


def identify_item(g, e, ref, how):
    it = find_item(e, ref)
    if not it.get("magic"):
        raise RuleError(f"{it['name']} isn't magical — there's nothing to identify.")
    if it.get("identified", True):
        raise RuleError(f"{e['name']} already knows what the {it['name']} does.")
    g.set(e, inventory=[dict(i, identified=True) if i["id"] == it["id"] else i for i in e["inventory"]])
    g.say(f"🔍 {e['name']} identifies the {item_display_name(it)}: it is {it['name']}" +
          (f" ({it['rarity']})" if it.get("rarity") else "") + f" — {how}. Its properties are now known.", kind="item", who=e["id"])


def pack_contents(pack_name):
    """[(name, qty)] from the SRD text 'A Burglar's Pack contains the following items: Backpack, ..., and Waterskin.'"""
    text = (srd.RULES / "core" / "06-equipment.md").read_text(encoding="utf-8")
    m = re.search(rf"An? {re.escape(pack_name)} contains the following items:\s*(.+?)\.\s", text, re.S)
    if not m:
        return None
    out = []
    for part in re.split(r",\s*(?:and\s+)?|\s+and\s+", " ".join(m.group(1).split())):
        part = part.strip()
        if not part:
            continue
        q = re.match(r"(\d+)\s+(?:(?:flasks|days|sheets|pieces|feet)\s+of\s+)?(.+)", part)
        out.append((q.group(2), int(q.group(1))) if q else (part, 1))
    return out


def unpack(g, e, ref):
    """Open an equipment pack: replace it with the SRD items it contains (same source)."""
    it = find_item(e, ref)
    contents = pack_contents(it["name"])
    if not contents:
        raise RuleError(f"{it['name']} isn't an equipment pack with listed contents (rules/core/06-equipment.md).")
    remove_item(g, e, it["id"], 1, "unpacked")
    src = f"{it.get('source', '')} (unpacked from {it['name']})".strip()
    for name, qty in contents:
        cand = [name, name[:-1] if name.endswith("s") else name, name[:-2] if name.endswith("es") else name]
        hit = next((c for c in cand if resolve_item(g, c)), None)
        add_item(g, g.get(e["id"]), hit or name, qty=qty, source=src, custom=None if hit else f"From the SRD {it['name']}.")


def find_item(e, ref):
    for it in e.get("inventory", []):
        if it["id"] == ref:
            return it
    key = srd.slug(ref)
    hits = [it for it in e.get("inventory", []) if srd.slug(it["name"]) == key or srd.slug(it["name"]).startswith(key)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise RuleError(f"'{ref}' matches several items: {', '.join(h['id'] for h in hits)}")
    raise RuleError(f"{e['name']} has no item '{ref}'. Inventory: {', '.join(i['id'] for i in e.get('inventory', [])) or 'empty'}")


def equip(g, e, ref, on=True):
    it = find_item(e, ref)
    inv = [dict(i) for i in e["inventory"]]
    target = next(i for i in inv if i["id"] == it["id"])
    if not on:
        target["equipped"] = False
        effects = [f for f in e.get("effects", []) if f.get("name") != "untrained armor" or f.get("item") != it["id"]]
        g.set(e, inventory=inv, effects=effects)
        g.say(f"{e['name']} unequips {it['name']}.")
        return
    if it["kind"] not in ("weapon", "armor", "magic"):
        raise RuleError(f"{it['name']} isn't something you equip.")
    effects = list(e.get("effects", []))
    if it["kind"] == "armor":
        cat = it.get("category")
        if combat(g) and cat != "shield":
            raise RuleError("Donning armor takes minutes (1 / 5 / 10 for light / medium / heavy) — not during combat.")
        for i in inv:
            if i.get("kind") == "armor" and i.get("equipped") and ((i.get("category") == "shield") == (cat == "shield")):
                i["equipped"] = False
        trained = cat in e.get("armor_training", [])
        if not trained:
            effects.append({"name": "untrained armor", "item": it["id"]})
            g.say(f"⚠ {e['name']} lacks training with {cat} armor: Disadvantage on Strength/Dexterity d20 tests and can't cast spells.", kind="warning")
    if it["kind"] == "weapon":
        hands = sum(2 if "two-handed" in (srd.find("weapons", i["base_name"]) or {}).get("properties", []) else 1
                    for i in inv if i.get("kind") == "weapon" and i.get("equipped") and i["id"] != it["id"])
        hands += sum(1 for i in inv if i.get("category") == "shield" and i.get("equipped"))
        need = 2 if "two-handed" in srd.find("weapons", it["base_name"])["properties"] else 1
        if hands + need > 2:
            raise RuleError(f"{e['name']}'s hands are full. Unequip something first (two hands max; shields use one).")
    target["equipped"] = True
    g.set(e, inventory=inv, effects=effects)
    g.say(f"{e['name']} equips {it['name']}.", kind="item")


def attune(g, e, ref, on=True):
    it = find_item(e, ref)
    if on:
        if not it.get("needs_attunement"):
            raise RuleError(f"{it['name']} doesn't require attunement.")
        if sum(1 for i in e["inventory"] if i.get("attuned")) >= 3:
            raise RuleError(f"{e['name']} is already attuned to 3 items (the maximum).")
        if combat(g):
            raise RuleError("Attuning takes a Short Rest focused on the item — not in combat.")
        g.emit("time.set", minutes=g.state["time"] + 60)
    inv = [dict(i, attuned=on, equipped=True if on else i.get("equipped")) if i["id"] == it["id"] else dict(i) for i in e["inventory"]]
    g.set(e, inventory=inv)
    g.say(f"{e['name']} {'attunes to' if on else 'ends attunement with'} {it['name']}" + (" (1 hour)." if on else "."), kind="item")


def fall_inert(g, e):
    """Unconscious (rules/core/08-rules-glossary.md): Incapacitated and Prone, and you drop whatever you're holding."""
    add_condition(g, e, "prone", source="fell Unconscious", quiet=True)
    for it in [i for i in e.get("inventory", []) if i.get("equipped") and i.get("kind") == "weapon"]:
        remove_item(g, g.get(e["id"]), it["id"], min(it.get("qty", 1), 2), "dropped")


def remove_item(g, e, ref, qty=1, reason="dropped", sell=False, to=None):
    it = find_item(e, ref)
    have = it.get("qty", 1)
    if qty > have:
        raise RuleError(f"{e['name']} only has {have}× {it['name']}.")
    inv = []
    for i in e["inventory"]:
        if i["id"] == it["id"]:
            if have - qty > 0:
                inv.append(dict(i, qty=have - qty))
        else:
            inv.append(i)
    g.set(e, inventory=inv)
    if sell:
        value = it.get("value_cp", 0)
        if not value:
            raise RuleError(f"{it['name']} has no market value.")
        price = value * qty // (1 if it.get("kind") == "treasure" else 2)
        change_coins(g, g.get(e["id"]), price, f"sold {it['name']}")
        g.say(f"💰 {e['name']} sells {qty}× {it['name']} for {fmt_cp(price)} (equipment sells for half its cost).", kind="item")
    elif to:
        tgt = to
        tinv = [dict(i) for i in tgt.get("inventory", [])]
        new = dict(it, qty=qty, equipped=False, attuned=False, id=new_item_id(tgt, it["name"]))
        tinv.append(new)
        g.set(tgt, inventory=tinv)
        g.say(f"{e['name']} gives {qty}× {it['name']} to {tgt['name']}.", kind="item")
    else:
        g.say(f"{e['name']}: {qty}× {it['name']} {reason}.", kind="item")
        if reason == "dropped" and e.get("token"):
            put_on_floor(g, e["token"]["map"], e["token"]["x"], e["token"]["y"], dict(it, qty=qty, equipped=False, attuned=False),
                         f"dropped by {e['name']}")


def put_on_floor(g, map_id, x, y, item, note, into=None):
    m = g.state["maps"][map_id]
    floor = [dict(f) for f in m.get("floor", [])]
    n = 1
    while any(f["id"] == f"floor-{n}" for f in floor):
        n += 1
    entry = {"id": f"floor-{n}", "x": x, "y": y, "item": item, "note": note}
    if into:
        entry["in"] = into["id"]
    floor.append(entry)
    g.emit("map.set", id=map_id, set={"floor": floor})
    g.say(f"⬇ {item.get('qty', 1)}× {item['name']} " + (f"goes into the {into['name']}" if into else f"lies on the floor at ({x},{y})")
          + f" — {note}.", kind="item")
    return f"floor-{n}"


def stash_item(g, e, ref, box_id, qty=1):
    """Put an item into a container on the map (a chest, a strongbox, a cache): it stays on that tile, listed inside it."""
    t = e.get("token")
    if not t:
        raise RuleError(f"{e['name']} isn't on a map.")
    m = g.state["maps"][t["map"]]
    box = next((c for c in m.get("containers", []) if c["id"] == box_id), None)
    if not box:
        raise RuleError(f"No container '{box_id}' on this map. Containers: " +
                        (", ".join(f"{c['id']} {c['name']} at ({c['x']},{c['y']})" for c in m.get("containers", [])) or "none"))
    if max(abs(box["x"] - t["x"]), abs(box["y"] - t["y"])) > 1:
        raise RuleError(f"{e['name']} must be in or next to square ({box['x']},{box['y']}) to reach the {box['name']}.")
    it = find_item(e, ref)
    if combat(g):
        ec = economy(g, e["id"])
        if ec.get("object_used"):
            raise RuleError(f"{e['name']} has already used their free object interaction this turn.")
        set_economy(g, e["id"], object_used=True)
    remove_item(g, e, it["id"], qty, "stashed")
    put_on_floor(g, t["map"], box["x"], box["y"], dict(it, qty=qty, equipped=False, attuned=False), f"stashed by {e['name']}", into=box)


def pick_up(g, e, floor_id, with_attack=False):
    t = e.get("token")
    if not t:
        raise RuleError(f"{e['name']} isn't on a map.")
    m = g.state["maps"][t["map"]]
    f = next((x for x in m.get("floor", []) if x["id"] == floor_id), None)
    if not f:
        raise RuleError(f"No item '{floor_id}' on this map. On the floor: " +
                        (", ".join(f"{x['id']} {x['item']['name']} at ({x['x']},{x['y']})" for x in m.get("floor", [])) or "nothing"))
    if max(abs(f["x"] - t["x"]), abs(f["y"] - t["y"])) > 1:
        raise RuleError(f"{e['name']} must be in or next to square ({f['x']},{f['y']}) to pick up the {f['item']['name']}.")
    if combat(g) and with_attack:
        # rules glossary, Attack action: equip (draw or pick up) one weapon with each attack you make, before or after it
        ec = economy(g, e["id"])
        if f["item"].get("kind") != "weapon":
            raise RuleError("Only a weapon can be picked up as part of an attack.")
        if ec.get("action_used") and ec.get("action_used_for", "").startswith("Attack") is False:
            raise RuleError(f"{e['name']} used their action for something other than the Attack action.")
        allowed = (derive(e).get("attacks_per_action", 1) if e["kind"] == "pc" else 1) + 1  # +1: a Light/Nick extra attack
        if ec.get("attack_equips", 0) >= allowed:
            raise RuleError(f"{e['name']} has already equipped a weapon with each attack this turn.")
        set_economy(g, e["id"], attack_equips=ec.get("attack_equips", 0) + 1)
    elif combat(g) and economy(g, e["id"]).get("object_used") and economy(g, e["id"]).get("utilize_credit"):
        set_economy(g, e["id"], utilize_credit=economy(g, e["id"])["utilize_credit"] - 1)  # paid for with the Utilize action
    elif combat(g):
        ec = economy(g, e["id"])
        if ec.get("object_used"):
            raise RuleError(f"{e['name']} has already used their free object interaction this turn (picking something up needs it, "
                            "the Utilize action, or `--with-attack` to pick up a weapon as part of an attack).")
        set_economy(g, e["id"], object_used=True)
    inv = [dict(i) for i in e.get("inventory", [])]
    item = dict(f["item"])
    if item.get("kind") == "weapon":
        item["equipped"] = True  # picking a weapon up puts it in hand (rules glossary: equipping includes picking it up)
    same = next((i for i in inv if i["name"] == item["name"] and not i.get("custom") and item.get("kind") in ("weapon", "gear", "consumable")
                 and not item.get("magic")), None)
    if same:
        same["qty"] = same.get("qty", 1) + item.get("qty", 1)
    else:
        item["id"] = new_item_id(e, item["name"])
        inv.append(item)
    g.set(e, inventory=inv)
    g.emit("map.set", id=t["map"], set={"floor": [x for x in m.get("floor", []) if x["id"] != floor_id]})
    g.say(f"⬆ {e['name']} picks up {item.get('qty', 1)}× {item['name']}.", kind="item", who=e["id"])


def recover_thrown(g, e, floor_id, how):
    """Public repair: a weapon the engine treated as thrown when the attacker meant a melee strike goes back into the
    attacker's hand (the roll itself stands). Only for a weapon on the floor marked as thrown by this creature."""
    t = e.get("token")
    if not t:
        raise RuleError(f"{e['name']} isn't on a map.")
    m = g.state["maps"][t["map"]]
    f = next((x for x in m.get("floor", []) if x["id"] == floor_id), None)
    if not f or f.get("note") != f"thrown by {e['name']}":
        raise RuleError(f"No weapon '{floor_id}' thrown by {e['name']} on this map.")
    if not how:
        raise RuleError('item recover-thrown <who> <floor-id> --how "why it was never thrown" (shown publicly)')
    item = dict(f["item"], equipped=True)
    item["id"] = new_item_id(e, item["name"])
    g.set(e, inventory=[dict(i) for i in e.get("inventory", [])] + [item])
    g.emit("map.set", id=t["map"], set={"floor": [x for x in m.get("floor", []) if x["id"] != floor_id]})
    what = f"{e['name']}'s {item['name']} was never thrown; it stays in hand (the attack roll stands)"
    g.override(how, what)
    g.say(f"⚖ DM ruling: {what} — {how}", kind="info")


def use_item(g, e, ref, target=None):
    it = find_item(e, ref)
    tgt = g.get(target) if target else e
    if it.get("heal"):
        if combat(g):
            use_action(g, e, "bonus", f"drink/administer {it['name']}")
        remove_item(g, e, it["id"], 1, "used")
        r = g.roll(it["heal"], it["name"], e["id"])
        heal(g, tgt, r["total"], it["name"])
        return
    if it.get("kind") == "consumable":
        if combat(g):
            use_action(g, e, "bonus" if "potion" in it["name"].lower() else "action", f"use {it['name']}")
        remove_item(g, e, it["id"], 1, "used")
        g.note(f"  Effect of {it['name']}: see rules/magic-items/{it.get('ref', '')}.md — adjudicate.")
        return
    if it.get("ref") == "dagger-of-venom" or (it.get("base_name") == "Dagger" and "venom" in (it.get("name") or "").lower()):
        # rules/magic-items: "You can take a Bonus Action to magically coat the blade with poison. The poison remains for
        # 1 minute or until an attack using this weapon hits a creature... can't be used this way again until the next dawn."
        now = g.state["time"]
        used = it.get("venom_used_at")
        if used is not None and now < next_dawn(used):
            raise RuleError(f"{it['name']} can't coat itself again until the next dawn ({fmt_time(next_dawn(used))}).")
        if combat(g):
            use_action(g, e, "bonus", f"coat {it['name']} with poison")
        inv = [dict(i, venom_used_at=now, venom_until=now + 1, venom=True) if i["id"] == it["id"] else dict(i) for i in e["inventory"]]
        g.set(e, inventory=inv)
        g.say(f"🐍 {e['name']} coats the {it['name']} with poison (1 minute, or until it hits: DC 15 Con save or 2d10 poison and Poisoned).",
              kind="action", who=e["id"])
        return
    raise RuleError(f"{it['name']} isn't a consumable. Use `feature` or narrate its use.")


def venom_hit(g, e, item_id, tgt_id, how):
    """Public repair: the blade was coated (Bonus Action) BEFORE an attack that already hit, but the coat was recorded
    after it. Resolve that hit's poison now, exactly as the attack would have, and spend the coat (Dagger of Venom)."""
    it = next((i for i in e["inventory"] if i["id"] == item_id), None)
    if not it:
        raise RuleError(f"{e['name']} has no item '{item_id}'.")
    if not (it.get("venom") and g.state["time"] <= it.get("venom_until", -1)):
        raise RuleError(f"{it['name']} isn't coated with poison right now (`item use` it first, as the Bonus Action it took).")
    if not how:
        raise RuleError('item venom-hit <who> <item> --to <target> --how "why the coat came first" (shown publicly)')
    tgt = g.get(tgt_id)
    g.set(e, inventory=[dict(i, venom=False) if i["id"] == item_id else dict(i) for i in e["inventory"]])
    what = f"{e['name']}'s {it['name']} was already coated when it hit {tgt['name']}; the poison applies to that hit"
    g.override(how, what)
    g.say(f"⚖ DM ruling: {what} — {how}", kind="info")
    if not tgt.get("dead"):
        pr = g.roll("2d10", f"{it['name']} poison", e["id"])
        saving_throw(g, tgt, "con", 15, source=f"{it['name']} poison", now=True,
                     effect={"damage": [[pr["total"], "poison"]], "half": False, "condition": "poisoned",
                             "source": f"{it['name']} poison (1 minute)"})


def next_dawn(t):
    """The first dawn (06:00) after in-world minute t."""
    dawn = (t // 1440) * 1440 + 360
    return dawn if t < dawn else dawn + 1440


# ====================================================================== XP

def xp_threshold(lvl):
    return srd.data()["level_xp"].get(lvl, 10 ** 9)


def party_xp(g, exclude=None):
    """The XP (and milestones) a character joining now should have: the party's, i.e. the most any living member has,
    so everyone crosses each level threshold together."""
    others = [p for p in g.pcs() if p["id"] != exclude and not p.get("dead")]
    return (max((p.get("xp", 0) for p in others), default=0), max((p.get("milestones", 0) for p in others), default=0))


def award_xp(g, members, total, reason):
    alive_members = [m for m in members if not m.get("dead")]
    if not alive_members:
        raise RuleError("No living characters to receive XP.")
    each = total // len(alive_members)
    for m in alive_members:
        new = m.get("xp", 0) + each
        g.set(m, xp=new)
        lv = level(m)
        ready = lv < 20 and new >= xp_threshold(lv + 1)
        g.say(f"⭐ {m['name']} gains {each} XP ({reason}) — total {new}" + (f". LEVEL UP available (level {lv + 1})!" if ready else "."), kind="xp")
    return each
