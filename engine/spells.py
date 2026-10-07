"""Explicit SRD 5.2 spell profiles and resolution, alongside the existing damage parser.

Profiles describe what is automated and expose the remaining DM decisions. Keeping
this separate from text heuristics makes adding a spell reviewable and testable.
"""
from . import effects as E, srd


PROFILES = {}


def register(names, handler, mechanics, *, limit=1, choice=None, remaining="", **fields):
    for name in names.split():
        PROFILES[name] = {"handler": handler, "mechanics": mechanics, "limit": limit,
                          "choice": choice, "remaining": remaining, **fields}


register("bless", "buff", "Attack/save bonus dice and concentration.", limit=3,
         roll_dice={"attack": "+1d4", "save": "+1d4"})
register("bane", "save", "Charisma save; attack/save penalty dice and concentration.", limit=3,
         save="cha", roll_dice={"attack": "-1d4", "save": "-1d4"})
register("guidance", "buff", "Bonus dice on checks using the selected skill.", choice="skill")
register("resistance", "buff", "Selected damage reduction once per turn.", choice="damage")
register("heroism", "buff", "Frightened immunity and temporary HP at the start of each turn.")
register("mage-armor", "buff", "Unarmored AC calculation, eight-hour expiry and ending on donning armor.", mage_armor=True)
register("shield-of-faith", "buff", "AC bonus and concentration.", ac_bonus=2)
register("shield", "buff", "AC bonus, Magic Missile protection and next-caster-turn expiry.",
         ac_bonus=5, turn_boundary="start")
register("barkskin", "buff", "Minimum AC and timed expiry.", ac_floor=17)
register("stoneskin", "buff", "Physical damage resistances and concentration.", resist=["bludgeoning", "piercing", "slashing"])
register("protection-from-energy", "buff", "Selected elemental damage resistance.", choice="energy")
register("protection-from-poison", "buff", "Poisoned removal, poison resistance and poison-condition save advantage.",
         resist=["poison"], poison_save_adv=True)
register("death-ward", "buff", "First damage-induced drop to zero becomes one HP; ward is consumed.", death_ward=True,
         remaining="Instant-death effects without damage still require a DM ruling.")
register("mind-blank", "buff", "Psychic immunity and Charmed immunity, timed capability tracking.",
         immune=["psychic"], condition_immune=["charmed"], mind_blank=True,
         remaining="Information gathering, remote observation and mind control are adjudicated by the DM.")
register("foresight", "buff", "Advantage on checks, saves, attacks and initiative; attacks against target have disadvantage.",
         adv_tests=["check", "save", "attack", "initiative"], attacks_against_dis=True, recast_ends=True)
register("blur", "buff", "Attacks against target have disadvantage, except Blindsight/Truesight.", attacks_against_dis=True, blur=True)
register("longstrider", "buff", "Movement speed bonus and timed expiry.", speed_bonus=10)
register("fly", "buff", "Fly Speed, hover capability, concentration and expiry.", fly_speed=60, hover=True,
         remaining="Altitude and falling after expiry require DM resolution; the map is two-dimensional.")
register("spider-climb", "buff", "Climb Speed equal to Speed and timed climbing capability.", climb=True,
         remaining="Vertical positions and ceilings require DM description.")
register("darkvision", "buff", "Darkvision range used by map reveal and expiry.", darkvision=150)
register("enhance-ability", "buff", "Advantage on checks using selected ability; upcasting adds targets.", choice="enhance")
register("enlarge-reduce", "buff", "Strength check/save advantage or disadvantage and weapon/unarmed damage dice.", choice="size",
         remaining="Size, occupied space, object targets and unwilling-target saves require DM adjudication; creature targets here must be willing.")
register("invisibility greater-invisibility", "buff", "Invisible condition, concentration, duration and distinct break rules.", condition="invisible")
register("blindness-deafness", "save", "Selected condition, Constitution saves and end-of-turn repeat saves.", choice="blindness", save="con", repeat=True)
register("faerie-fire", "save", "Dexterity saves; attack advantage and suppression of Invisible benefits.", limit=None, save="dex",
         attacks_against_adv=True, reveals_invisible=True,
         remaining="DM lists creatures in the cube and describes outlined objects and emitted light.")
register("haste", "buff", "Doubled speed, AC, Dexterity save advantage, restricted additional action and ending lethargy.",
         haste=True, speed_multiplier=2, ac_bonus=2, adv_saves=["dex"])
register("slow", "save", "Speed, AC/save penalties, reaction/action restrictions, spell-failure chance and repeat saves.",
         limit=6, save="wis", repeat=True, slow=True, speed_multiplier=.5, ac_bonus=-2, save_bonuses={"dex": -2},
         remaining="DM lists creatures inside the cube.")
register("aid", "aid", "Upcast maximum/current HP increase, nonstacking and timed expiry.", limit=3)
register("false-life", "temp", "Temporary HP roll and upcasting; temporary HP do not stack.")
register("heal", "heal", "Fixed healing with upcasting and removal of Blinded, Deafened and Poisoned.")
register("power-word-heal", "heal", "Full healing and condition removal; optional reaction to stand.", choice="stand")
register("mass-heal", "heal", "Allocated healing pool and condition removal.", limit=None, choice="allocation")
register("lesser-restoration", "restore", "Remove one selected eligible condition.", choice="lesser")
register("greater-restoration", "restore", "Remove one supported condition or one Exhaustion level.", choice="greater",
         remaining="Curses, attunement and ability/max-HP reductions without a structured engine source require DM resolution.")
register("spare-the-dying", "stabilize", "Stabilization and level-scaled range.")
register("ray-of-frost ray-of-sickness chill-touch shocking-grasp guiding-bolt", "rider",
         "Damage plus the specific on-hit rider with the correct turn owner and expiry.")
register("hex", "buff", "Extra damage on weapon/spell attack hits; selected ability-check disadvantage and slot-scaled duration.", choice="ability",
         remaining="Moving the curse to a new target is not automated in this release.")
register("hunters-mark", "mark", "Extra Force damage on attack hits and concentration duration.",
         remaining="Retargeting and tracking-check advantage are not automated.")
register("pass-without-trace", "aura", "Selected creatures gain a Stealth bonus only within the caster's aura.", limit=None,
         remaining="Tracks and environmental detection are described by the DM.")
register("freedom-of-movement", "buff", "Swim Speed, magical slowdown suppression and immunity to new magical Paralysis/Restraint.",
         freedom=True, swim=True, remaining="Terrain costs and escape from existing nonmagical restraints require DM resolution.")
register("protection-from-evil-and-good", "buff", "Specified creature types attack with disadvantage; sourced Charmed/Frightened immunity.",
         protected_types=["aberration", "celestial", "elemental", "fey", "fiend", "undead"],
         remaining="Possession and saves against unsourced existing effects need DM resolution.")
register("see-invisibility", "buff", "Invisible attack penalties are suppressed for the observer; timed sight capability.", see_invisible=True,
         remaining="Ethereal-plane visibility is narrated.")
register("expeditious-retreat", "buff", "Immediate Dash and bonus-action Dash while concentrating.", bonus_dash=True)
register("water-breathing", "buff", "Underwater breathing capability with target limit and duration.", limit=10, water_breathing=True,
         remaining="Underwater environment and suffocation hazards require DM resolution.")
register("water-walk", "buff", "Liquid-surface walking capability with target limit and duration.", limit=10, water_walk=True,
         remaining="Liquid transitions, heat and terrain are adjudicated by the DM.")
register("tongues", "buff", "Timed spoken/signed language comprehension and communication capability.", tongues=True,
         remaining="Dialogue, knowledge and cooperation are narrated.")
register("comprehend-languages", "buff", "Timed literal language comprehension capability.", comprehend_languages=True,
         remaining="Touching written surfaces, reading time and secret messages are adjudicated by the DM.")
register("speak-with-animals speak-with-plants", "buff", "Timed communication capability with the corresponding creatures.", communicate=True,
         remaining="Creature knowledge, cooperation and plant-terrain changes are narrated.")
register("detect-magic detect-evil-and-good detect-poison-and-disease", "buff",
         "Timed detection capability and concentration lifecycle.", detection=True,
         remaining="What is detected, obstruction and auras require DM narration.")


def support(spell):
    p = PROFILES.get(spell["slug"])
    if p:
        return {"status": "partial" if p["remaining"] else "mechanical", "mechanics": p["mechanics"],
                "remaining": p["remaining"], "choice": p["choice"]}
    fx = spell["effect"]
    if fx.get("kind") in ("attack", "save", "heal", "darts", "damage"):
        return {"status": "partial", "mechanics": "Existing parsed attack/save/damage/healing resolution.",
                "remaining": "Additional clauses, areas, recurring effects and special targets require DM adjudication.", "choice": None}
    return {"status": "narrative", "mechanics": "Casting resources and concentration are tracked.",
            "remaining": "Resolve the spell description with the DM.", "choice": None}


def prepare(g, caster, spell, targets, slot, choice=None):
    """Validate profile choices and target count before any cast resources are spent."""
    from .core import RuleError
    p = PROFILES.get(spell["slug"])
    if not p:
        if choice:
            raise RuleError(f"{spell['name']} has no automated --choice option. Read its support entry.")
        return targets, None
    if spell["range"].lower() == "self":
        if targets and any(t["id"] != caster["id"] for t in targets) and p["handler"] != "aura":
            raise RuleError(f"{spell['name']} affects the caster; it can't be cast on another creature.")
        if p["handler"] != "aura":
            targets = [caster]
    if not targets:
        if p["handler"] == "aura" or spell["slug"] == "shield":
            targets = [caster]
        else:
            raise RuleError(f"{spell['name']} needs --targets (use --targets none for an empty area).")
    if len({t["id"] for t in targets}) != len(targets):
        raise RuleError(f"List each target of {spell['name']} only once.")
    maximum = p["limit"]
    if maximum is not None:
        maximum += max(0, slot - spell["level"]) * spell["effect"].get("targets_per_level", 0)
        if len(targets) > maximum:
            raise RuleError(f"{spell['name']} affects at most {maximum} creature(s) at this level.")
    options = [x.strip().lower() for x in (choice or "").split(",") if x.strip()]
    kind = p["choice"]
    valid = {"skill": set(srd.SKILLS), "damage": set(srd.DAMAGE_TYPES),
             "energy": {"acid", "cold", "fire", "lightning", "thunder"}, "ability": set(srd.ABILITIES),
             "enhance": {"str", "dex", "int", "wis", "cha"}, "size": {"enlarge", "reduce"},
             "blindness": {"blinded", "deafened"}, "lesser": {"blinded", "deafened", "paralyzed", "poisoned"},
             "greater": {"charmed", "petrified", "exhaustion"}, "stand": {"stand"}}
    if kind in ("enhance", "ability"):
        options = [srd.ability_key(x) or x for x in options]
    if kind == "blindness" and not options:
        options = ["blinded"]
    if kind == "stand" and not options:
        return targets, options
    if kind == "allocation":
        if len(options) != len(targets) or any(not n.isdecimal() for n in options) or sum(map(int, options)) > 700:
            raise RuleError("Mass Heal needs --choice with healing allocations in target order, totalling at most 700.")
        return targets, list(map(int, options))
    if kind and kind in valid:
        if not options or any(x not in valid[kind] for x in options):
            raise RuleError(f"{spell['name']} needs --choice from: {', '.join(sorted(valid[kind]))}.")
        if len(options) != 1 and not (kind == "enhance" and len(options) == len(targets)):
            raise RuleError("Choose one option, or one ability per target for Enhance Ability.")
    elif choice:
        raise RuleError(f"{spell['name']} has no --choice option.")
    if spell["slug"] == "mage-armor" and any(i.get("equipped") and i.get("kind") == "armor" and
                                              i.get("category") != "shield" for t in targets for i in t.get("inventory", [])):
        raise RuleError("Mage Armor's target must not be wearing armor.")
    if p["handler"] == "stabilize" and any(t["hp"] != 0 or t.get("dead") for t in targets):
        raise RuleError("Spare the Dying needs a creature at zero HP that isn't dead.")
    if spell["slug"] == "greater-restoration" and options == ["exhaustion"] and not targets[0].get("exhaustion"):
        raise RuleError("The target has no Exhaustion level to remove.")
    if p["handler"] == "restore" and options != ["exhaustion"] and not any(
            c["name"] == options[0] for c in targets[0].get("conditions", [])):
        raise RuleError(f"The target doesn't have {options[0]}.")
    if spell["slug"] in ("enlarge-reduce", "haste", "fly", "heroism", "freedom-of-movement"):
        from .mechanics import hostile
        if any(hostile(caster, t) for t in targets):
            raise RuleError(f"{spell['name']}: this handler requires willing targets. Resolve an unwilling use with the DM.")
    return targets, options


FIELDS = {"roll_dice", "condition", "mage_armor", "ac_bonus", "ac_floor", "resist", "immune", "condition_immune",
          "poison_save_adv", "death_ward", "mind_blank", "adv_tests", "adv_saves", "attacks_against_dis", "blur",
          "speed_bonus", "fly_speed", "hover", "climb", "darkvision", "attacks_against_adv", "reveals_invisible",
          "haste", "slow", "speed_multiplier", "save_bonuses", "freedom", "swim", "protected_types", "see_invisible",
          "bonus_dash", "water_breathing", "water_walk", "tongues", "comprehend_languages", "communicate", "detection",
          "turn_boundary"}


def resolve(g, caster, spell, slot, targets, sc, choices, now=False):
    from . import mechanics as M
    from .core import amod, hp_max
    p = PROFILES.get(spell["slug"])
    if not p or p["handler"] == "rider":
        return False
    slug, handler = spell["slug"], p["handler"]

    def restore_condition(target, condition):
        for f in list(target.get("effects", [])):
            if f.get("managed_spell") and f.get("condition") == condition:
                E.remove(g, target, f, "ends through restoration")
                M.release_spell_if_unused(g, f)
        M.remove_condition(g, target, condition, quiet=True)

    if handler == "temp":
        r = g.roll(f"2d4+{4 + 5 * max(0, slot - 1)}", spell["name"], caster["id"])
        M.temp_hp(g, caster, r["total"], spell["name"])
        return True
    if handler == "heal":
        for i, t in enumerate(targets):
            amount = 70 + 10 * max(0, slot - 6) if slug == "heal" else hp_max(t) if slug == "power-word-heal" else choices[i]
            M.heal(g, t, amount, spell["name"])
            conditions = ["blinded", "deafened", "poisoned"] if slug != "power-word-heal" else ["charmed", "frightened", "paralyzed", "poisoned", "stunned"]
            for condition in conditions:
                restore_condition(t, condition)
            if slug == "power-word-heal" and choices == ["stand"] and "prone" in M.condition_names(t):
                M.use_action(g, t, "reaction", "stand after Power Word Heal")
                M.remove_condition(g, t, "prone", quiet=True)
        return True
    if handler == "restore":
        t = targets[0]
        if choices[0] == "exhaustion":
            g.set(t, exhaustion=max(0, t.get("exhaustion", 0) - 1))
            g.say(f"   {t['name']}: one Exhaustion level removed.", kind="spell-effect")
        else:
            restore_condition(t, choices[0])
        return True
    if handler == "stabilize":
        t = targets[0]
        r = g.roll("1d4", "Stable recovery time (hours)", t["id"], hidden=True)
        g.set(t, death={"success": 0, "fail": 0, "stable": True, "wake_at": g.state["time"] + r["total"] * 60})
        g.say(f"   {t['name']} is Stable.", kind="spell-effect", who=t["id"])
        return True
    if p.get("recast_ends"):
        for e in list(g.entities.values()):
            for fx in list(e.get("effects", [])):
                if fx.get("managed_spell") and fx.get("caster") == caster["id"] and fx.get("spell") == slug:
                    E.remove(g, e, fx, "ends on recasting")
    if handler == "aura":
        E.add(g, caster, E.template(g, caster, spell, slot, stealth_aura=True,
                                   targets=list({caster["id"], *(t["id"] for t in targets)})))
        return True
    for i, t in enumerate(targets):
        fields = {k: v for k, v in p.items() if k in FIELDS}
        choice = choices[i] if len(choices or []) > 1 else (choices or [None])[0]
        if slug == "guidance":
            fields.update(skill=choice, roll_dice={"check": "+1d4"})
        elif slug == "resistance":
            fields.update(damage_reduce=choice)
        elif slug == "heroism":
            fields.update(condition_immune=["frightened"], turn_temp_hp=max(0, amod(caster, sc["ability"])))
        elif slug == "protection-from-energy":
            fields.update(resist=[choice])
        elif slug == "enhance-ability":
            fields.update(adv_checks=[choice])
        elif slug == "enlarge-reduce":
            fields.update(adv_checks=["str"] if choice == "enlarge" else [], adv_saves=["str"] if choice == "enlarge" else [],
                          dis_checks=["str"] if choice == "reduce" else [], dis_saves=["str"] if choice == "reduce" else [],
                          weapon_damage_dice="+1d4" if choice == "enlarge" else "-1d4")
        elif slug == "blindness-deafness":
            fields.update(condition=choice)
        elif slug == "aid":
            fields.update(hp_max_bonus=5 * (slot - 1))
        elif slug == "hex":
            fields.update(dis_checks=[choice], hit_damage=["1d6", "necrotic"])
        elif slug == "hunters-mark":
            fields.update(hit_damage=["1d6", "force"])
        fx = E.template(g, caster, spell, slot, **fields)
        if slug in ("hex", "hunters-mark"):
            minutes = (60 if slot == 1 else 240 if slot == 2 else 480 if slot <= 4 else 1440) if slug == "hex" else (60 if slot < 3 else 480 if slot <= 4 else 1440)
            fx["expires_at"] = E.clock(g) + minutes
            g.set(caster, concentration={**caster["concentration"], "duration": f"{int(fx['expires_at'] - E.clock(g))} minutes"})
        if handler == "save":
            if p.get("repeat"):
                fx["repeat_save"] = f"{p['save']}:{sc['dc']}"
            M.saving_throw(g, t, p["save"], sc["dc"], source=spell["name"], spell=True, now=now,
                           effect={"spell_effect": fx, "caster": caster["id"]})
        else:
            E.add(g, t, fx)
        if slug == "protection-from-poison":
            restore_condition(t, "poisoned")
    if slug == "expeditious-retreat" and M.combat(g):
        ec = M.economy(g, caster["id"])
        M.set_economy(g, caster["id"], **({"dashed2": True} if ec.get("dashed") else {"dashed": True}))
    return True


def on_hit(g, caster, target, spell, slot):
    p = PROFILES.get(spell["slug"])
    if not p or p["handler"] != "rider":
        return
    slug = spell["slug"]
    owner, boundary = caster["id"], "start"
    fields = {}
    if slug == "ray-of-frost":
        fields = {"speed_penalty": 10}
    elif slug == "ray-of-sickness":
        fields, boundary = {"condition": "poisoned"}, "end"
    elif slug == "chill-touch":
        fields, boundary = {"no_heal": True}, "end"
    elif slug == "shocking-grasp":
        fields, owner = {"no_oa": True}, target["id"]
    elif slug == "guiding-bolt":
        fields, boundary = {"attacks_against_adv": True, "next_attack_adv": True}, "end"
    E.add(g, target, E.template(g, caster, spell, slot, turn_owner=owner, turn_boundary=boundary, **fields))
