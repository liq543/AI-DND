"""Character creation and advancement, validated step by step against rules/core/02-character-creation.md."""
import re

from . import srd
from .core import RuleError, abilities, hp_max, level, mod, pb_for_level, spellcasting
from .mechanics import add_item, change_coins, parse_coins, resolve_item, xp_threshold

LANGUAGES = ["Common", "Common Sign Language", "Draconic", "Dwarvish", "Elvish", "Giant", "Gnomish", "Goblin",
             "Halfling", "Orc", "Abyssal", "Celestial", "Deep Speech", "Druidic", "Infernal", "Primordial",
             "Sylvan", "Thieves' Cant", "Undercommon"]
RARE_LANGUAGES = {"Abyssal", "Celestial", "Deep Speech", "Druidic", "Infernal", "Primordial", "Sylvan", "Thieves' Cant", "Undercommon"}


def parse_scores(text):
    out = {}
    for k, v in re.findall(r"(str|dex|con|int|wis|cha)\w*\s*[=:]\s*(\d+)", text.lower()):
        out[k] = int(v)
    if sorted(out) != sorted(srd.ABILITIES):
        raise RuleError("Give all six scores, e.g. --scores str=15,dex=14,con=13,int=12,wis=10,cha=8")
    return out


def parse_bonus(text):
    out = {}
    for k, v in re.findall(r"(str|dex|con|int|wis|cha)\w*\s*\+\s*(\d)", text.lower()):
        out[k] = out.get(k, 0) + int(v)
    return out


def validate_method(g, method, scores, name):
    d = srd.data()
    vals = sorted(scores.values(), reverse=True)
    if method == "standard":
        if vals != d["standard_array"]:
            raise RuleError(f"Standard Array must be exactly {d['standard_array']} assigned to the six abilities; got {vals}.")
        return None
    if method == "pointbuy":
        costs = d["point_costs"]
        for k, v in scores.items():
            if v not in costs:
                raise RuleError(f"Point buy scores must be 8–15 before background bonuses ({k.upper()} = {v}).")
        spent = sum(costs[v] for v in scores.values())
        if spent > 27:
            raise RuleError(f"Point buy total is {spent} points; the budget is 27.")
        return None
    if method.startswith("roll"):
        gid = method.split(":", 1)[1] if ":" in method else None
        groups = {}
        for r in g.state["rolls"]:
            if r.get("purpose", "").startswith("ability scores") and r.get("group"):
                groups.setdefault(r["group"], []).append(r)
        if not gid:
            mine = [k for k, v in groups.items() if v[0].get("who") == name]
            if not mine:
                raise RuleError("No logged ability-score roll for this character. Roll first: `char roll-stats \"Name\"`.")
            gid = mine[-1]
        if gid not in groups:
            raise RuleError(f"No ability-score roll group '{gid}'.")
        used = {e.get("stat_roll") for e in g.entities.values()}
        if gid in used:
            raise RuleError(f"Roll group {gid} was already used by another character. Each set of rolls can be used once.")
        rolled = sorted((r["total"] for r in groups[gid]), reverse=True)
        if vals != rolled:
            raise RuleError(f"Scores must be exactly the rolled values {rolled} (logged as {gid}), each used once; got {vals}.")
        return gid
    raise RuleError("--method must be standard, pointbuy, or roll[:group]")


def validate_background_bonus(bg, bonus):
    allowed = set(bg["abilities"])
    if not set(bonus) <= allowed:
        raise RuleError(f"{bg['name']} can only raise {', '.join(a.upper() for a in bg['abilities'])} (got {', '.join(bonus)}).")
    pattern = sorted(bonus.values(), reverse=True)
    if pattern not in ([2, 1], [1, 1, 1]):
        raise RuleError("Background bonus must be +2 to one and +1 to another, or +1 to all three (e.g. --bonus str+2,con+1).")


def starting_equipment(text, choice):
    """'Choose A, B, or C: (A) Chain Mail, Greatsword, ..., and 4 GP; (B) ...; or (C) 155 GP' -> (items, cp)"""
    opts = dict(re.findall(r"\(([A-C])\)\s*([^;]+?)(?=;|\s*$|\s*or\s*\([A-C]\))", text.replace("*", "")))
    if not opts:
        return [], 0
    if choice not in opts:
        raise RuleError(f"Choose starting equipment option {', '.join(sorted(opts))}.")
    items, cp = [], 0
    for part in re.split(r",\s*|\s+and\s+", opts[choice].strip().rstrip(".")):
        part = re.sub(r"^and\s+", "", part.strip())
        if not part or part.lower() in ("and", "or"):
            continue
        m = re.match(r"^([\d,]+)\s*(GP|SP|CP)$", part, re.I)
        if m:
            cp += parse_coins(part)
            continue
        q = re.match(r"^(\d+)\s+(.+)$", part)
        qty, name = (int(q.group(1)), q.group(2)) if q else (1, part)
        items.append((qty, name))
    return items, cp


def singular(name):
    for plural, single in (("Javelins", "Javelin"), ("Daggers", "Dagger"), ("Handaxes", "Handaxe"), ("Darts", "Dart"),
                           ("Pouches", "Pouch"), ("Arrows", "Arrows"), ("Bolts", "Bolts"), ("Sickles", "Sickle")):
        if name == plural:
            return single
    return name


def grant_starting_items(g, e, items, instrument=None):
    for qty, name in items:
        clean = re.sub(r"\s*\((?:see|same as).*?\)", "", name).strip()
        clean = singular(clean)
        # "Musical Instrument of your choice" (Bard) / "... Musical Instrument chosen for ..." (Monk)
        if re.search(r"musical instrument", clean, re.I) and re.search(r"choice|chosen", clean, re.I):
            inst = srd.find("gear", instrument or "")
            if not inst or inst.get("tool_kind") != "Musical Instrument":
                opts = sorted(v["name"] for v in srd.data()["gear"].values() if v.get("tool_kind") == "Musical Instrument")
                raise RuleError(f"Choose the starting musical instrument: --instrument {'|'.join(opts)}")
            add_item(g, g.get(e["id"]), inst["name"], qty=qty, source="starting equipment")
            continue
        # "Arcane Focus (Quarterstaff)" / "Druidic Focus (Quarterstaff)": the focus is that weapon
        fm = re.match(r"^(arcane|druidic) focus \((.+)\)$", clean, re.I)
        if fm and srd.find("weapons", fm.group(2)):
            add_item(g, g.get(e["id"]), srd.find("weapons", fm.group(2))["name"], qty=qty,
                     source=f"starting equipment ({fm.group(1).title()} Focus)")
            continue
        item = resolve_item(g, clean)
        if not item and "(" in clean:
            base = re.sub(r"\s*\(.*\)", "", clean).strip()
            item = resolve_item(g, base)
            if item:
                clean = base
        if item:
            add_item(g, g.get(e["id"]), clean, qty=qty, source="starting equipment")
        else:
            add_item(g, g.get(e["id"]), clean, qty=qty, source="starting equipment", custom=name)
    # put on the starting armor and shield the character is trained with
    from .mechanics import equip
    ent = g.get(e["id"])
    body = next((i for i in ent["inventory"] if i["kind"] == "armor" and i.get("category") != "shield"
                 and i.get("category") in ent["armor_training"]), None)
    shield = next((i for i in ent["inventory"] if i.get("category") == "shield" and "shield" in ent["armor_training"]), None)
    for it in (body, shield):
        if it:
            equip(g, g.get(e["id"]), it["id"], True)


def tool_names():
    d = srd.data()
    names = {v["name"] for v in d["gear"].values() if v.get("tool_kind")}
    names |= {v["name"] for v in d["gear"].values() if re.search(r"tools|kit|supplies|set\b", v["name"], re.I)}
    return names


def parse_skilled(text, have_skills, have_tools):
    """Skilled feat: any combination of three skills or tools. Returns (skills, tools)."""
    picks = [s.strip() for s in (text or "").split(",") if s.strip()]
    if len(picks) != 3:
        raise RuleError("Skilled: choose any three skills or tools (--skilled stealth,perception,\"Disguise Kit\").")
    tools_by_low = {t.lower(): t for t in tool_names()}
    skills, tools = [], []
    for p in picks:
        low = p.lower()
        if low in srd.SKILLS:
            if low in have_skills or low in skills:
                raise RuleError(f"Already proficient in {low}; choose another for Skilled.")
            skills.append(low)
        elif low in tools_by_low:
            t = tools_by_low[low]
            if t in have_tools or t in tools:
                raise RuleError(f"Already proficient with {t}; choose another for Skilled.")
            tools.append(t)
        else:
            raise RuleError(f"'{p}' is not a skill or SRD tool.")
    return skills, tools


def weapon_mastery_count(cls, lvl=1):
    """How many kinds of weapons the class masters at this level. Fighters and Barbarians have a Weapon Mastery column;
    Paladins, Rangers and Rogues have only the feature, whose SRD text grants two kinds of weapons."""
    row = cls["levels"][max(1, min(lvl, 20))]
    n = srd.num(row.get("Weapon Mastery"), 0) or 0
    if not n and any(f[1] == "Weapon Mastery" and f[0] <= lvl for f in cls.get("features", [])):
        n = 2
    return n


def check_masteries(cls, n, names):
    """Validate a --masteries list: exactly n SRD weapon kinds the class is proficient with.
    Returns (mastery properties, weapon names)."""
    picks = [m.strip() for m in (names or "").split(",") if m.strip()]
    if len(picks) != n:
        raise RuleError(f"{cls['name']} picks {n} kinds of weapons for Weapon Mastery: --masteries a,b")
    weapons = []
    for mname in picks:
        w = srd.find("weapons", mname)
        if not w:
            raise RuleError(f"'{mname}' is not an SRD weapon.")
        finesse_light = bool({"finesse", "light"} & set(w["properties"]))
        if w["category"] == "martial" and not cls.get("weapons_martial") and not (cls.get("weapons_martial_finesse_light") and finesse_light):
            raise RuleError(f"{w['name']} isn't a weapon {cls['name']}s are proficient with.")
        if w["name"] in [x["name"] for x in weapons]:
            raise RuleError(f"{w['name']} is listed twice.")
        weapons.append(w)
    return [w["mastery"] for w in weapons], [w["name"] for w in weapons]


def set_masteries(g, e, names):
    """rules/classes: 'Whenever you finish a Long Rest, you can change the kinds of weapons you chose.'"""
    classes = [c for c in e.get("classes", {}) if weapon_mastery_count(srd.find("classes", c), e["classes"][c])]
    if not classes:
        raise RuleError(f"{e['name']} has no Weapon Mastery feature.")
    cls = srd.find("classes", classes[0])
    n = weapon_mastery_count(cls, e["classes"][classes[0]])
    props, weapons = check_masteries(cls, n, names)
    last_rest, changed = e.get("last_long_rest_end"), e.get("masteries_changed_at")
    repair = len(e.get("mastery_weapons") or []) < n  # a character created before the engine recorded their picks
    if not repair and (last_rest is None or (changed is not None and changed >= last_rest)):
        raise RuleError(f"{e['name']} can change Weapon Mastery choices only after finishing a Long Rest "
                        f"(once per Long Rest).")
    g.set(e, masteries=props, mastery_weapons=weapons, masteries_changed_at=g.state["time"])
    g.say(f"⚔ {e['name']} now uses the mastery properties of: " +
          ", ".join(f"{w} ({p.title()})" for w, p in zip(weapons, props)) + ".", kind="info")


def create(g, a):
    d = srd.data()
    name = a.name.strip()
    cid = g.new_id(name.split()[0])
    cls = g.require("classes", a.cls, "Class")
    sp = g.require("species", a.species, "Species")
    bg = g.require("backgrounds", a.background, "Background")
    scores = parse_scores(a.scores)
    gid = validate_method(g, a.method, scores, name)
    bonus = parse_bonus(a.bonus or "")
    validate_background_bonus(bg, bonus)
    final = {k: scores[k] + bonus.get(k, 0) for k in srd.ABILITIES}
    if max(final.values()) > 20:
        raise RuleError("No ability score can exceed 20.")
    # skills
    chosen = [s.strip().lower() for s in (a.skills or "").split(",") if s.strip()]
    for s in chosen:
        if s not in srd.SKILLS:
            raise RuleError(f"Unknown skill '{s}'.")
    if len(chosen) != cls["skill_n"]:
        raise RuleError(f"{cls['name']} chooses exactly {cls['skill_n']} skills from: {', '.join(cls['skill_list'])}")
    bad = [s for s in chosen if s not in cls["skill_list"]]
    if bad:
        raise RuleError(f"{', '.join(bad)} not on the {cls['name']} skill list: {', '.join(cls['skill_list'])}")
    dup = set(chosen) & set(bg["skills"])
    if dup:
        raise RuleError(f"{', '.join(dup)} already come from the {bg['name']} background — choose different class skills.")
    skills = sorted(set(chosen) | set(bg["skills"]))
    feats = [{"name": bg["feat"], "source": f"{bg['name']} background"}]
    extra = [s.strip().lower() for s in (a.species_skill or "").split(",") if s.strip()]
    if sp["name"] == "Human":
        if len(extra) != 1 or extra[0] not in srd.SKILLS:
            raise RuleError("Human (Skillful) gains proficiency in one skill of your choice: --species-skill <skill>")
        if not a.species_feat:
            raise RuleError("Human (Versatile) gains an Origin feat: --species-feat <feat>")
        f = srd.find("feats", a.species_feat)
        if not f or f["category"] != "origin":
            raise RuleError(f"'{a.species_feat}' is not an Origin feat. Origin feats: " +
                            ", ".join(k for k, v in d["feats"].items() if v["category"] == "origin"))
        feats.append({"name": f["name"], "source": "Human (Versatile)"})
    elif sp["name"] == "Elf":
        if len(extra) != 1 or extra[0] not in ("insight", "perception", "survival"):
            raise RuleError("Elf (Keen Senses) gains Insight, Perception, or Survival: --species-skill <one>")
    elif extra:
        raise RuleError(f"{sp['name']} doesn't grant a free skill choice.")
    for s in extra:
        if s in skills:
            raise RuleError(f"Already proficient in {s}; choose another.")
    skills = sorted(set(skills) | set(extra))
    # Skilled (Origin feat): three skills or tools of your choice
    skilled_tools = []
    if any(f["name"] == "Skilled" for f in feats):
        picks, skilled_tools = parse_skilled(a.skilled, skills, [bg["tool"]])
        skills = sorted(set(skills) | set(picks))
    elif a.skilled:
        raise RuleError("--skilled is only for characters with the Skilled feat.")
    # expertise at level 1 (Rogue)
    expertise = [s.strip().lower() for s in (a.expertise or "").split(",") if s.strip()]
    if cls["name"] == "Rogue":
        if len(expertise) != 2 or any(s not in skills for s in expertise):
            raise RuleError("Rogue level 1 Expertise: choose two of your skill proficiencies (--expertise a,b).")
    elif expertise:
        raise RuleError(f"{cls['name']} doesn't get Expertise at level 1.")
    # fighting style
    if cls["name"] == "Fighter":
        fs = srd.find("feats", a.fighting_style or "")
        if not fs or fs["category"] != "fighting style":
            raise RuleError("Fighter level 1 Fighting Style: --fighting-style " +
                            "|".join(k for k, v in d["feats"].items() if v["category"] == "fighting style"))
        feats.append({"name": fs["name"], "source": "Fighting Style"})
    # weapon masteries
    wm_n = weapon_mastery_count(cls, 1)
    masteries, mastery_weapons = check_masteries(cls, wm_n, a.masteries) if wm_n else ([], [])
    # languages
    langs = [l.strip() for l in (a.languages or "").split(",") if l.strip()]
    for l in langs:
        if l not in LANGUAGES:
            raise RuleError(f"Unknown language '{l}'. Standard: {', '.join(x for x in LANGUAGES if x not in RARE_LANGUAGES)}")
        if l in RARE_LANGUAGES:
            raise RuleError(f"{l} is a rare language — not available at creation without a feature granting it.")
    if len([l for l in langs if l != "Common"]) != 2:
        raise RuleError("Choose two standard languages besides Common (--languages Elvish,Dwarvish).")
    langs = ["Common"] + [l for l in langs if l != "Common"]
    if cls["name"] == "Rogue":
        langs.append("Thieves' Cant")
    if cls["name"] == "Druid":
        langs.append("Druidic")
    # HP
    con = mod(final["con"])
    hp = cls["hit_die"] + con + sp["hp_per_level"] + (2 if any(f["name"] == "Tough" for f in feats) else 0)
    # size
    size = "Medium"
    if sp["size"] == "Small":
        size = "Small"
    elif sp["size"] == "Medium or Small":
        size = (a.size or "Medium").title()
        if size not in ("Medium", "Small"):
            raise RuleError(f"{sp['name']} can be Medium or Small.")
    ent = {
        "id": cid, "kind": "pc", "name": name, "player": a.player or "Player", "species": sp["name"],
        "background": bg["name"], "classes": {cls["name"]: 1}, "subclasses": {}, "class_order": [cls["name"]],
        "abilities": final, "base_scores": scores, "bg_bonus": bonus, "method": a.method, "stat_roll": gid,
        "save_profs": cls["saves"], "skills": skills, "expertise": expertise, "languages": langs,
        "tools": [bg["tool"]] + skilled_tools, "armor_training": cls["armor"], "weapon_profs": [], "masteries": masteries,
        "mastery_weapons": mastery_weapons, "feats": feats, "species_traits": sp["traits"],
        "resist": sp["resist"], "darkvision": sp["darkvision"], "base_speed": sp["speed"], "size": size,
        "hp_max": hp, "hp": hp, "temp_hp": 0, "hd_spent": {}, "hp_log": [{"level": 1, "gain": hp, "how": "max at level 1"}],
        "slots_used": {}, "pact_used": 0, "resources_used": {}, "conditions": [], "exhaustion": 0,
        "death": {"success": 0, "fail": 0, "stable": False}, "inventory": [], "coins": {"gp": 0},
        "xp": 0, "milestones": 0, "spells": {"cantrips": [], "prepared": [], "spellbook": []}, "granted_spells": [],
        "effects": [], "bio": {}, "inspiration": False, "last_long_rest_end": None,
        "choices": ({"skilled": [s for s in skills if s not in chosen and s not in bg["skills"] and s not in extra] + skilled_tools}
                    if any(f["name"] == "Skilled" for f in feats) else {}),
    }
    if sp["name"] == "Dragonborn" and a.ancestry:
        anc = {"black": "acid", "blue": "lightning", "brass": "fire", "bronze": "lightning", "copper": "acid", "gold": "fire",
               "green": "poison", "red": "fire", "silver": "cold", "white": "cold"}
        if a.ancestry.lower() not in anc:
            raise RuleError(f"Draconic Ancestry: {', '.join(anc)}")
        ent["resist"] = [anc[a.ancestry.lower()]]
        ent["ancestry"] = a.ancestry.title()
    if sp["name"] == "Tiefling" and a.ancestry:
        leg = {"abyssal": "poison", "chthonic": "necrotic", "infernal": "fire"}
        if a.ancestry.lower() not in leg:
            raise RuleError("Fiendish Legacy: abyssal, chthonic, or infernal (--ancestry)")
        ent["resist"] = [leg[a.ancestry.lower()]]
        ent["ancestry"] = a.ancestry.title()
    from .mechanics import party_xp
    ent["xp"], ent["milestones"] = party_xp(g)   # joins at the party's XP, so the whole party levels up together
    g.emit("entity.add", entity=ent)
    g.say(f"🧙 {name} joins the party: {sp['name']} {cls['name']} ({bg['name']}), {hp} HP"
          + (f", at the party's {ent['xp']} XP (`char levelup` until they match the party's level)" if ent["xp"] else "") + ".",
          kind="party")
    # starting equipment
    items, cp = starting_equipment(cls["starting_equipment"], (a.equipment or "A").upper())
    bitems, bcp = starting_equipment(bg["equipment"], (a.bg_equipment or "A").upper())
    grant_starting_items(g, g.get(cid), items + bitems, instrument=getattr(a, "instrument", None))
    if cp + bcp:
        change_coins(g, g.get(cid), cp + bcp, "starting gold")
        g.say(f"   {name} starts with {(cp + bcp) // 100} GP.")
    # Magic Initiate from background (or Human Versatile)
    for f in feats:
        m = re.match(r"Magic Initiate \((\w+)\)", f["name"])
        if m or f["name"] == "Magic Initiate":
            lst = m.group(1) if m else (a.mi_list or "Wizard")
            grant_magic_initiate(g, g.get(cid), lst, a.mi_cantrips, a.mi_spell, f["source"])
    return g.get(cid)


def grant_magic_initiate(g, e, lst, cantrips, spell, source):
    if lst not in ("Cleric", "Druid", "Wizard"):
        raise RuleError("Magic Initiate draws from the Cleric, Druid, or Wizard list.")
    cs = [srd.find("spells", c.strip()) for c in (cantrips or "").split(",") if c.strip()]
    s1 = srd.find("spells", spell or "")
    if len(cs) != 2 or any(c is None or c["level"] != 0 or lst not in c["classes"] for c in cs):
        raise RuleError(f"Magic Initiate ({lst}): choose two {lst} cantrips with --mi-cantrips a,b")
    if not s1 or s1["level"] != 1 or lst not in s1["classes"]:
        raise RuleError(f"Magic Initiate ({lst}): choose one level 1 {lst} spell with --mi-spell")
    granted = e.get("granted_spells", []) + [{"slug": c["slug"], "source": f"Magic Initiate ({lst})", "cantrip": True} for c in cs] + \
              [{"slug": s1["slug"], "source": f"Magic Initiate ({lst})", "free_used": False}]
    g.set(e, granted_spells=granted, mi_ability=a_mi_ability(lst))
    g.say(f"   Magic Initiate ({lst}): {', '.join(c['name'] for c in cs)}, {s1['name']} (1 free casting per Long Rest).")


def a_mi_ability(lst):
    return {"Cleric": "wis", "Druid": "wis", "Wizard": "int"}[lst]


def set_spells(g, e, cls_name, cantrips, prepared, spellbook=None):
    sc = spellcasting(e)
    if cls_name not in sc:
        raise RuleError(f"{e['name']} has no Spellcasting from {cls_name}.")
    info = sc[cls_name]
    cs = [g.require("spells", c.strip(), "Spell") for c in cantrips if c.strip()]
    ps = [g.require("spells", c.strip(), "Spell") for c in prepared if c.strip()]
    for s in cs:
        if s["level"] != 0:
            raise RuleError(f"{s['name']} is not a cantrip.")
    for s in cs + ps:
        if cls_name not in s["classes"]:
            raise RuleError(f"{s['name']} is not on the {cls_name} spell list.")
    for s in ps:
        if s["level"] == 0:
            raise RuleError(f"{s['name']} is a cantrip — list it under --cantrips.")
        if s["level"] > info["max_level"]:
            raise RuleError(f"{s['name']} is level {s['level']}; {e['name']} can prepare up to level {info['max_level']} {cls_name} spells.")
    if len(cs) > info["cantrips"]:
        raise RuleError(f"{cls_name} level {e['classes'][cls_name]} knows {info['cantrips']} cantrips; you listed {len(cs)}.")
    if len(ps) > info["prepared"]:
        raise RuleError(f"{cls_name} level {e['classes'][cls_name]} prepares {info['prepared']} spells; you listed {len(ps)}.")
    book = e.get("spells", {}).get("spellbook", [])
    if cls_name == "Wizard":
        if spellbook is not None:
            if book and not set(book) <= set(s["slug"] for s in spellbook):
                raise RuleError("A spellbook can't lose spells this way.")
            if not book:
                if len(spellbook) != 6 or any(s["level"] != 1 or "Wizard" not in s["classes"] for s in spellbook):
                    raise RuleError("A new Wizard's spellbook holds six level 1 Wizard spells (--spellbook a,b,c,d,e,f).")
                book = [s["slug"] for s in spellbook]
        if not book:
            raise RuleError("Set the Wizard's starting spellbook first (--spellbook with six level 1 Wizard spells).")
        missing = [s["name"] for s in ps if s["slug"] not in book]
        if missing:
            raise RuleError(f"Wizards prepare from their spellbook; not in it: {', '.join(missing)}")
    old_c = set(e.get("spells", {}).get("cantrips", []))
    if old_c and not old_c <= {s["slug"] for s in cs} and len(old_c - {s["slug"] for s in cs}) > 1:
        raise RuleError("Only one cantrip can be swapped at a time (on a Long Rest / level up).")
    g.set(e, spells={"cantrips": [s["slug"] for s in cs], "prepared": [s["slug"] for s in ps], "spellbook": book})
    g.say(f"📖 {e['name']} prepares: {', '.join(s['name'] for s in cs + ps) or 'nothing'}.", kind="spell")


SCHOLAR_SKILLS = ("arcana", "history", "investigation", "medicine", "nature", "religion")


def apply_level_choices(e, cls, cls_name, new_cl, feats_here, patch, a):
    """Level-gained proficiency choices the class tables name but don't spell out as Expertise."""
    skills = list(patch.get("skills", e["skills"]))
    expertise = list(patch.get("expertise", e.get("expertise", [])))
    choices = dict(e.get("choices", {}))
    if cls_name == "Wizard" and "Scholar" in feats_here:
        s = (a.scholar or "").strip().lower()
        if s not in SCHOLAR_SKILLS or s not in skills or s in expertise:
            raise RuleError("Wizard 2 Scholar: Expertise in one proficient skill among "
                            f"{', '.join(SCHOLAR_SKILLS)} (--scholar <skill>).")
        expertise.append(s)
        choices["scholar"] = s
    sub = patch.get("subclasses", e.get("subclasses", {})).get(cls_name)
    subf = [f for lv, f in cls["subclasses"].get(sub, {}).get("features", []) if lv == new_cl] if sub else []
    if "Bonus Proficiencies" in subf and cls_name == "Bard":
        picks = [s.strip().lower() for s in (a.bonus_skills or "").split(",") if s.strip()]
        if len(picks) != 3 or any(p not in srd.SKILLS or p in skills for p in picks) or len(set(picks)) != 3:
            raise RuleError("College of Lore 3 Bonus Proficiencies: three new skills (--bonus-skills a,b,c).")
        skills += picks
        choices["lore_bonus"] = picks
    if skills != e["skills"]:
        patch["skills"] = sorted(skills)
    if expertise != e.get("expertise", []):
        patch["expertise"] = expertise
    if choices != e.get("choices", {}):
        patch["choices"] = choices


def catch_up(g, e, a):
    """Apply choices a character missed because an older engine didn't ask for them (beta fixes)."""
    patch, done = {}, []
    cls_rows = {c: srd.find("classes", c) for c in e["classes"]}
    ch = e.get("choices", {})
    w = e["classes"].get("Wizard", 0)
    if w >= 2 and "scholar" not in ch:
        apply_level_choices(e, cls_rows["Wizard"], "Wizard", 2, ["Scholar"], patch, a)
        done.append(f"Scholar: Expertise in {a.scholar.title()}")
    if e["classes"].get("Bard", 0) >= 3 and e.get("subclasses", {}).get("Bard") and "lore_bonus" not in ch:
        e2 = {**e, **patch}
        apply_level_choices(e2, cls_rows["Bard"], "Bard", 3, [], patch, a)
        done.append(f"Bonus Proficiencies: {a.bonus_skills}")
    if any(f["name"] == "Skilled" for f in e["feats"]) and "skilled" not in ch:
        sk, tl = parse_skilled(a.skilled, patch.get("skills", e["skills"]), e.get("tools", []))
        patch["skills"] = sorted(set(patch.get("skills", e["skills"])) | set(sk))
        patch["tools"] = e.get("tools", []) + tl
        patch["choices"] = {**patch.get("choices", ch), "skilled": sk + tl}
        done.append(f"Skilled: {', '.join(sk + tl)}")
    start = g.state["settings"].get("start_level", 1)
    lv = level(e)
    if lv <= start and e.get("xp", 0) < xp_threshold(lv):
        patch["xp"] = xp_threshold(lv)
        done.append(f"starting XP for level {lv}: {xp_threshold(lv)}")
    if not done:
        raise RuleError(f"{e['name']} has no missed choices to catch up.")
    g.set(e, **patch)
    g.say(f"🔧 Engine fix applied to {e['name']}: " + "; ".join(done) + ".", kind="party")


def levelup(g, e, a):
    d = srd.data()
    cur = level(e)
    if cur >= 20:
        raise RuleError("Level 20 is the maximum.")
    start = g.state["settings"].get("start_level", 1)
    mode = g.state["settings"].get("xp_mode", "xp")
    reason = None
    if cur < start:
        reason = f"campaign starts at level {start}"
    elif mode == "milestone":
        if e.get("milestones", 0) < 1:
            raise RuleError(f"{e['name']} has no milestone level-up available (milestones are awarded with `xp milestone`).")
        reason = "milestone"
    else:
        need = xp_threshold(cur + 1)
        if e.get("xp", 0) < need:
            raise RuleError(f"{e['name']} has {e.get('xp', 0)} XP; level {cur + 1} needs {need} XP.")
        reason = f"{e.get('xp', 0)} XP"
    cls_name = a.cls or e["class_order"][0]
    cls = g.require("classes", cls_name, "Class")
    cls_name = cls["name"]
    if cls_name not in e["classes"]:
        for c in list(e["classes"]) + [cls_name]:
            prim = srd.find("classes", c)["primary"]
            ab = abilities(e)
            ok = any(ab[p] >= 13 for p in prim) if srd.find("classes", c)["primary_any"] else all(ab[p] >= 13 for p in prim)
            if not ok:
                raise RuleError(f"Multiclassing needs 13+ in the primary ability of every class: {c} needs "
                                f"{' or '.join(p.upper() for p in prim) if srd.find('classes', c)['primary_any'] else ' and '.join(p.upper() for p in prim)} 13.")
    new_cl = e["classes"].get(cls_name, 0) + 1
    row = cls["levels"][new_cl]
    feats_here = [f.strip() for f in row.get("Class Features", "").split(",")]
    patch = {"classes": {**e["classes"], cls_name: new_cl}}
    if cls_name not in e["classes"]:
        patch["class_order"] = e["class_order"] + [cls_name]
        patch["armor_training"] = sorted(set(e["armor_training"]) | ({"light", "medium", "shield"} & set(cls["armor"])))
    # HP
    con = mod(abilities(e)["con"])
    die = cls["hit_die"]
    if (a.hp or "avg") == "roll":
        r = g.roll(f"1d{die}", f"level {cur + 1} Hit Points", e["id"])
        gain_base, how = r["total"], f"rolled {r['text']}"
    else:
        gain_base, how = die // 2 + 1, "fixed average"
    sp = srd.find("species", e["species"]) or {"hp_per_level": 0}
    gain = max(1, gain_base + con) + sp["hp_per_level"] + (2 if any(f["name"] == "Tough" for f in e["feats"]) else 0)
    patch["hp_max"] = e["hp_max"] + gain
    patch["hp"] = e["hp"] + gain
    patch["hp_log"] = e.get("hp_log", []) + [{"level": cur + 1, "gain": gain, "how": how}]
    # subclass
    if any("Subclass" in f and "feature" not in f for f in feats_here):
        subs = list(cls["subclasses"]) + list(g.state["homebrew"].get("subclasses", {}).get(srd.slug(cls_name), {}).keys())
        if not a.subclass:
            raise RuleError(f"{cls_name} {new_cl}: choose a subclass (--subclass). SRD: {', '.join(cls['subclasses'])}")
        match = next((s for s in subs if srd.slug(s) == srd.slug(a.subclass)), None)
        if not match:
            raise RuleError(f"'{a.subclass}' isn't an available {cls_name} subclass: {', '.join(subs)} (homebrew must be registered).")
        patch["subclasses"] = {**e.get("subclasses", {}), cls_name: match}
    feats = list(e["feats"])
    ab = dict(e["abilities"])
    if "Ability Score Improvement" in feats_here or "Epic Boon" in feats_here:
        epic = "Epic Boon" in feats_here
        if a.feat:
            f = srd.find("feats", a.feat)
            if not f:
                raise RuleError(f"No SRD feat '{a.feat}'.")
            if epic and f["category"] != "epic boon":
                raise RuleError("Level 19 grants an Epic Boon feat.")
            if not epic and f["category"] not in ("general", "origin", "fighting style"):
                raise RuleError(f"{f['name']} can't be taken here.")
            if f["min_level"] > cur + 1:
                raise RuleError(f"{f['name']} requires level {f['min_level']}+.")
            if not f["repeatable"] and any(x["name"] == f["name"] for x in feats):
                raise RuleError(f"{f['name']} can't be taken twice.")
            if f["name"] == "Ability Score Improvement" or a.asi:
                inc = parse_bonus(a.asi or "")
                if sorted(inc.values(), reverse=True) not in ([2], [1, 1]):
                    raise RuleError("Ability Score Improvement: +2 to one score or +1 to two (--asi str+2 or --asi str+1,con+1).")
                for k, v in inc.items():
                    ab[k] += v
                    if ab[k] > 20 and not epic:
                        raise RuleError(f"{k.upper()} would exceed 20.")
            feats.append({"name": f["name"], "source": f"{cls_name} {new_cl}"})
        else:
            raise RuleError(f"{cls_name} {new_cl}: choose --feat \"Ability Score Improvement\" --asi str+2 (or another feat).")
    if "Fighting Style" in feats_here:
        fs = srd.find("feats", a.fighting_style or "")
        if not fs or fs["category"] != "fighting style":
            raise RuleError("Choose --fighting-style " + "|".join(k for k, v in d["feats"].items() if v["category"] == "fighting style"))
        feats.append({"name": fs["name"], "source": "Fighting Style"})
    if "Expertise" in feats_here:
        ex = [s.strip().lower() for s in (a.expertise or "").split(",") if s.strip()]
        if len(ex) != 2 or any(s not in e["skills"] or s in e.get("expertise", []) for s in ex):
            raise RuleError("Expertise: choose two proficient skills without Expertise (--expertise a,b).")
        patch["expertise"] = e.get("expertise", []) + ex
    apply_level_choices(e, cls, cls_name, new_cl, feats_here, patch, a)
    if reason and reason.startswith("campaign starts") and e.get("xp", 0) < xp_threshold(cur + 1):
        patch["xp"] = xp_threshold(cur + 1)  # a character built at level N starts with that level's XP
    patch["feats"] = feats
    patch["abilities"] = ab
    # a higher Constitution modifier raises max HP by 1 per character level (retroactively)
    con_diff = mod(ab["con"]) - mod(e["abilities"]["con"])
    if con_diff:
        patch["hp_max"] += con_diff * (cur + 1)
        patch["hp"] += con_diff * (cur + 1)
        gain += con_diff * (cur + 1)
    if any(f["name"] == "Tough" for f in feats) and not any(f["name"] == "Tough" for f in e["feats"]):
        patch["hp_max"] += 2 * cur  # Tough taken now applies to previous levels too
        patch["hp"] += 2 * cur
    if mode == "milestone" and reason == "milestone":
        patch["milestones"] = e.get("milestones", 0) - 1
    g.set(e, **patch)
    e = g.get(e["id"])
    g.say(f"🎉 {e['name']} reaches level {cur + 1} ({cls_name} {new_cl}) — {reason}. +{gain} HP ({how}). "
          f"New: {', '.join(f for f in feats_here if f and f != '—')}", kind="party")
    return e
