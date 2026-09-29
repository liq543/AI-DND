"""Structured SRD 5.2 data, parsed from the markdown in rules/.

Everything mechanical the engine enforces (class tables, spell lists, monster stat blocks,
weapon and armor stats, prices, XP tables) comes from here, so the rules text is the single
source of truth. Parsed data is cached in engine/.cache/srd.json and rebuilt when rules change.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "rules"
CACHE = Path(__file__).resolve().parent / ".cache" / "srd.json"
CACHE_VERSION = 10

ABILITIES = ["str", "dex", "con", "int", "wis", "cha"]
ABILITY_NAMES = {"strength": "str", "dexterity": "dex", "constitution": "con",
                 "intelligence": "int", "wisdom": "wis", "charisma": "cha"}
SKILLS = {
    "acrobatics": "dex", "animal handling": "wis", "arcana": "int", "athletics": "str",
    "deception": "cha", "history": "int", "insight": "wis", "intimidation": "cha",
    "investigation": "int", "medicine": "wis", "nature": "int", "perception": "wis",
    "performance": "cha", "persuasion": "cha", "religion": "int", "sleight of hand": "dex",
    "stealth": "dex", "survival": "wis",
}
DAMAGE_TYPES = ["acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic",
                "piercing", "poison", "psychic", "radiant", "slashing", "thunder"]
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}


def slug(name):
    s = name.lower().replace("’", "").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def ability_key(word):
    w = word.strip().lower()
    return ABILITY_NAMES.get(w) or (w[:3] if w[:3] in ABILITIES else None)


def num(text, default=None):
    m = re.search(r"-?\d[\d,]*", text or "")
    return int(m.group(0).replace(",", "")) if m else default


def cost_cp(text):
    """'1,500 GP' -> copper pieces. None if not a fixed price."""
    m = re.search(r"([\d,]+)\s*(CP|SP|EP|GP|PP)", text or "", re.I)
    if not m:
        return None
    return int(m.group(1).replace(",", "")) * {"cp": 1, "sp": 10, "ep": 50, "gp": 100, "pp": 1000}[m.group(2).lower()]


def clean(cell):
    return re.sub(r"[*_]", "", cell).strip()


def parse_tables(text):
    """Return [(caption, headers, rows)] for every markdown table; caption from a preceding 'Table:' line."""
    lines = text.splitlines()
    out, i, caption = [], 0, ""
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("Table:"):
            caption = line[6:].strip()
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|\s*:?-{2,}", lines[i + 1].strip()):
            headers = [clean(c) for c in line.strip("|").split("|")]
            rows = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([clean(c) for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append((caption, headers, rows))
            caption = ""
            continue
        if line and not line.startswith("Table:") and not line.startswith("|"):
            if not line.startswith("#"):
                pass
        i += 1
    return out


def read(path):
    return Path(path).read_text(encoding="utf-8")


# ---------------------------------------------------------------- classes

def parse_class(path):
    text = read(path)
    name = re.search(r"^## (.+)$", text, re.M).group(1).strip("* ")
    tables = parse_tables(text)
    core = next(t for t in tables if t[0].startswith("Core"))
    traits = {clean(r[0]): r[1] for r in core[2] if len(r) >= 2}
    feat_table = next(t for t in tables if "Features" in t[0] and "Core" not in t[0])
    headers = feat_table[1]
    levels = {}
    for row in feat_table[2]:
        lv = num(row[0])
        if lv:
            levels[lv] = {headers[j]: row[j] for j in range(min(len(headers), len(row)))}

    skills_txt = traits.get("Skill Proficiencies", "")
    m = re.search(r"Choose (any )?(\d+)", skills_txt)
    skill_n = int(m.group(2)) if m else 0
    if m and m.group(1):
        skill_list = list(SKILLS)
    else:
        after = skills_txt.split(":", 1)[-1].lower().replace(" ", "")  # source has typos like "In sight"
        skill_list = [s for s in SKILLS if s.replace(" ", "") in after]

    saves = [ability_key(w) for w in re.split(r",| and ", traits.get("Saving Throw Proficiencies", "")) if ability_key(w)]
    primary_txt = traits.get("Primary Ability", "")
    primary = [ability_key(w) for w in re.split(r",| and | or ", primary_txt) if ability_key(w)]
    armor_txt = traits.get("Armor Training", "").lower()
    armor = [a for a in ("light", "medium", "heavy") if a in armor_txt] + (["shield"] if "shield" in armor_txt else [])
    weapons_txt = traits.get("Weapon Proficiencies", "").lower()

    caster = None
    slot_cols = [h for h in headers if h.strip() in [str(i) for i in range(1, 10)]]
    if len(slot_cols) == 9:
        caster = "full"
    elif len(slot_cols) == 5:
        caster = "half"
    elif "Slot Level" in headers:
        caster = "pact"
    sc = re.search(r"\*\*Spellcasting Ability\.\*\*\s*(\w+)", text)
    subclasses = {}
    for sm in re.finditer(r"^### \**\w+ Subclass: (.+?)\**\s*$", text, re.M):
        sub_name = sm.group(1).strip("* ")
        body = text[sm.end():]
        nxt = re.search(r"^### ", body, re.M)
        body = body[: nxt.start()] if nxt else body
        feats = [(int(a), b.strip()) for a, b in re.findall(r"^#### Level (\d+): (.+)$", body, re.M)]
        always = {}
        for cap, hdrs, rows in parse_tables(body):
            if hdrs and "Spells" in hdrs[-1]:
                for r in rows:
                    lv = num(r[0])
                    if lv:
                        always[lv] = [slug(s) for s in re.split(r",", r[-1]) if s.strip()]
        subclasses[sub_name] = {"features": feats, "spells": always}
    features = [(int(a), b.strip()) for a, b in re.findall(r"^#### Level (\d+): (.+)$", text.split(" Subclass: ")[0], re.M)]
    return {
        "name": name,
        "hit_die": num(traits.get("Hit Point Die", "d8").lower().split("d", 1)[-1], 8),
        "primary": primary, "primary_any": " or " in primary_txt,
        "saves": saves, "skill_n": skill_n, "skill_list": skill_list,
        "weapons_simple": "simple" in weapons_txt,
        "weapons_martial": "martial weapons" in weapons_txt and "that have" not in weapons_txt,
        "weapons_martial_finesse_light": "that have the finesse or light" in weapons_txt,
        "armor": armor, "starting_equipment": traits.get("Starting Equipment", ""),
        "levels": levels, "caster": caster,
        "spell_ability": ability_key(sc.group(1)) if sc else None,
        "features": features, "subclasses": subclasses,
    }


# ---------------------------------------------------------------- spells

def parse_spell(path):
    text = read(path)
    name = text.splitlines()[0].lstrip("# ").strip().strip("*").strip()
    meta = re.search(r"^\*(?!\*)(.+?)\*\s*$", text, re.M)
    meta = meta.group(1) if meta else ""
    level = 0 if "Cantrip" in meta else num(re.search(r"Level (\d)", meta).group(1)) if re.search(r"Level (\d)", meta) else 0
    school = re.sub(r"Level \d|Cantrip|\(.*\)", "", meta).strip()
    classes = [c.strip() for c in (re.search(r"\((.*)\)", meta) or [None, ""])[1].split(",") if c.strip()]

    def field(label):
        m = re.search(r"\*\*" + label + r":\*\*\s*(.+)", text)
        return m.group(1).strip() if m else ""

    ct, dur = field("Casting Time"), field("Duration")
    rng = field("Range")
    body = text.split(field("Duration"), 1)[-1] if field("Duration") else text
    main, _, higher = re.split(r"\*\*_?(?:Using a Higher-Level Spell Slot|Cantrip Upgrade)", body + "**_Using a Higher-Level Spell Slot", maxsplit=1)[0], None, body
    effect = {"kind": "other"}
    atk = re.search(r"make an? (ranged|melee) spell attack", main, re.I)
    sv = re.search(r"(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma) saving throw", main)
    heal = re.search(r"regains? (?:a number of )?Hit Points equal to (\d+d\d+)( plus your spellcasting ability modifier)?", main)
    dmg = re.search(r"(\d+d\d+(?: ?\+ ?\d+)?) (\w+) damage", main)
    if atk:
        effect = {"kind": "attack", "attack": atk.group(1)}
    elif sv:
        effect = {"kind": "save", "save": ability_key(sv.group(1)), "half": "half as much damage" in main}
        # the condition a failed save inflicts: "...succeed on a Wisdom saving throw or have the Incapacitated condition"
        cm = re.search(r"saving throw[^.]*?(?:or|fail\w*)[^.]*?\bhave the (\w+) condition", main, re.I)
        if cm:
            effect["condition"] = cm.group(1).lower()
        if re.search(r"repeats? the (?:saving throw|save) at the end of each of its turns|"
                     r"at the end of each of its turns, (?:the|a|each) (?:target|creature) (?:repeats|can repeat) the (?:save|saving throw)",
                     main, re.I):
            effect["repeat"] = True
    elif heal:
        effect = {"kind": "heal", "dice": heal.group(1), "add_mod": bool(heal.group(2))}
    if dmg and dmg.group(2).lower() in DAMAGE_TYPES and effect["kind"] in ("attack", "save", "other"):
        effect.update({"dice": dmg.group(1).replace(" ", ""), "type": dmg.group(2).lower()})
        if effect["kind"] == "other":
            effect["kind"] = "damage"
    up = re.search(r"Using a Higher-Level Spell Slot.{0,40}?increases by (\d+d\d+) for each spell slot level above (\d)", higher, re.S)
    if up:
        effect["upcast"] = up.group(1)
    cu = re.search(r"Cantrip Upgrade.{0,20}?increases by (\d+d\d+)", higher, re.S)
    if cu:
        effect["cantrip_scaling"] = True
    if path.stem == "magic-missile":  # auto-hit darts: 3, +1 per slot level above 1
        effect = {"kind": "darts", "count": 3, "count_per_level": 1, "dice": "1d4+1", "type": "force"}
    elif path.stem == "scorching-ray":  # one attack per ray: 3, +1 per slot level above 2
        effect.update({"count": 3, "count_per_level": 1})
    elif re.search(r"creates two beams at level 5, three beams at level 11, and four beams at level 17", higher):
        effect.update({"beams": True})
        effect.pop("cantrip_scaling", None)
    return {
        "effect": effect,
        "name": name, "slug": path.stem, "level": level, "school": school, "classes": classes,
        "casting_time": ct, "ritual": "ritual" in ct.lower(), "range": rng,
        "range_ft": num(rng) if "feet" in rng else (0 if rng.lower().startswith(("self", "touch")) else None),
        "components": field("Components"), "duration": dur,
        "concentration": "concentration" in dur.lower(),
        "bonus_action": ct.lower().startswith("bonus action"),
        "reaction": ct.lower().startswith("reaction"),
    }


# ---------------------------------------------------------------- monsters

def parse_damage_list(text):
    """Damage clauses in a stat block entry. Riders like '... if the attack roll had Advantage' are
    marked conditional so the engine never applies them automatically."""
    out = []
    for m in re.finditer(r"(\d+)(?: \(([^)]+)\))? (\w+) damage", text):
        amt, dice, dtype = m.groups()
        if dtype.lower() in DAMAGE_TYPES:
            tail = text[m.end():m.end() + 120].lstrip(" ,")
            entry = {"avg": int(amt), "dice": (dice or amt).replace(" ", ""), "type": dtype.lower()}
            if re.match(r"(if|while|when|against|to a)\b", tail):
                entry["condition"] = re.split(r"[.;]", tail)[0]
            out.append(entry)
    return out


def parse_monster(path):
    text = read(path)
    lines = text.splitlines()
    name = lines[0].lstrip("# ").strip()
    meta = re.search(r"^\*(?!\*)(.+?)\*\s*$", text, re.M)
    meta = meta.group(1) if meta else ""
    size_type, _, alignment = meta.partition(",")
    parts = size_type.split()
    size = parts[0] if parts else "Medium"
    if len(parts) > 2 and parts[1] == "or":  # "Medium or Small Humanoid"
        size = parts[0]
        ctype = " ".join(parts[3:])
    else:
        ctype = " ".join(parts[1:])

    def stat(label):
        m = re.search(r"^- \*\*" + label + r"(?::\*\*|\*\*:?)\s*(.+)$", text, re.M | re.I)
        return m.group(1).strip() if m else ""

    hp_txt = stat("Hit Points")
    hp_dice = re.search(r"\(([^)]+)\)", hp_txt)
    speed = {}
    for m in re.finditer(r"(?:(Burrow|Climb|Fly|Swim) )?(\d+) ft\.", stat("Speed")):
        speed[(m.group(1) or "walk").lower()] = int(m.group(2))
    abilities = {}
    for m in re.finditer(r"^\|\s*(STR|DEX|CON|INT|WIS|CHA)\s*\|\s*(\d+)\s*\|\s*([+-−]?\d+)\s*\|\s*([+-−]?\d+)\s*\|", text, re.M):
        abilities[m.group(1).lower()] = {"score": int(m.group(2)), "mod": int(m.group(3).replace("−", "-")),
                                         "save": int(m.group(4).replace("−", "-"))}
    skills = {}
    for m in re.finditer(r"([A-Z][a-z]+(?: [a-z]+)?(?: [A-Z][a-z]+)?) ([+-]\d+)", stat("Skills")):
        skills[m.group(1).lower()] = int(m.group(2))

    def defenses(label):
        dmg, cond = [], []
        for tok in re.split(r"[,;]", stat(label)):
            t = tok.strip().lower()
            if t in DAMAGE_TYPES:
                dmg.append(t)
            elif t:
                cond.append(t)
        return dmg, cond

    res, _ = defenses("Resistances")
    imm, cimm = defenses("Immunities")
    vul, _ = defenses("Vulnerabilities")
    cr_m = re.search(r"\*\*CR\*\*\s*([\d/]+)\s*\(XP ([\d,]+)(?:[^;)]*)?(?:; PB \+(\d+))?", text)
    senses = stat("Senses")
    dv = re.search(r"darkvision (\d+)", senses, re.I)
    pp = re.search(r"Passive Perception (\d+)", senses)

    sections, current = {}, None
    for line in lines:
        h = re.match(r"^### (.+)$", line)
        if h:
            current = h.group(1).strip().lower()
            sections[current] = []
            continue
        if current and line.startswith("***"):
            sections[current].append(line)
        elif current and sections[current] and line.strip() and not line.startswith("#"):
            sections[current][-1] += "\n" + line
    actions = []
    multi = 1
    for sec, entries in sections.items():
        for entry in entries:
            m = re.match(r"^\*\*\*(.+?)\.\*\*\*\s*(.*)$", entry, re.S)
            if not m:
                continue
            aname, body = m.group(1).strip(), m.group(2)
            a = {"name": re.sub(r"\s*\(.*\)$", "", aname), "full_name": aname, "section": sec,
                 "text": body.strip()}
            rc = re.search(r"Recharge (\d)(?:[–-](\d))?", aname)
            if rc:
                a["recharge"] = int(rc.group(1))
            per_day = re.search(r"(\d+)/Day", aname)
            if per_day:
                a["per_day"] = int(per_day.group(1))
            atk = re.search(r"\*(Melee or Ranged|Melee|Ranged) Attack Roll:\*\s*([+-]\d+)", body)
            if atk:
                a["kind"] = "attack"
                a["attack_type"] = atk.group(1).lower()
                a["bonus"] = int(atk.group(2))
                reach = re.search(r"reach (\d+) ft", body)
                rng = re.search(r"range (\d+)(?:/(\d+))? ft", body)
                a["reach"] = int(reach.group(1)) if reach else None
                a["range"] = [int(rng.group(1)), int(rng.group(2) or rng.group(1))] if rng else None
                hit_text = re.split(r"\*Hit:\*|ft\.", body, maxsplit=1)[-1]
                # only the first sentence is the hit damage; later sentences are riders the DM adjudicates
                a["damage"] = parse_damage_list(re.split(r"(?<=[.])\s+(?=[A-Z*])", hit_text.strip(), maxsplit=1)[0])
            sv = re.search(r"\*(\w+) Saving Throw\*:?\s*DC (\d+)", body)
            if sv and "kind" not in a:
                a["kind"] = "save"
                a["save_ability"] = ability_key(sv.group(1))
                a["dc"] = int(sv.group(2))
                fail = re.search(r"\*Failure:\*(.*?)(\*Success:\*|\*Failure or Success:\*|$)", body, re.S)
                a["damage"] = parse_damage_list(fail.group(1)) if fail else []
                a["half_on_success"] = bool(re.search(r"\*Success:\*\s*Half", body))
            if a["name"].lower() == "multiattack":
                first = re.split(r"(?<=[.])\s", body.strip(), maxsplit=1)[0].lower()
                counts = [NUM_WORDS[w] for w in re.findall(r"\b(one|two|three|four|five|six|seven|eight)\b", first)]
                multi = max(sum(counts), 1)
            a.setdefault("kind", "other")
            actions.append(a)
    return {
        "name": name, "slug": path.stem, "size": size, "type": ctype, "alignment": alignment.strip(),
        "ac": num(stat("Armor Class"), 10), "hp": num(hp_txt, 1),
        "hp_dice": hp_dice.group(1).replace(" ", "") if hp_dice else None,
        "speed": speed or {"walk": 30}, "init": num(stat("Initiative"), 0),
        "abilities": abilities, "skills": skills,
        "resist": res, "immune": imm, "vulnerable": vul, "condition_immune": cimm,
        "darkvision": int(dv.group(1)) if dv else 0,
        "passive_perception": int(pp.group(1)) if pp else 10,
        "cr": cr_m.group(1) if cr_m else "0", "xp": int(cr_m.group(2).replace(",", "")) if cr_m else 0,
        "pb": int(cr_m.group(3)) if cr_m and cr_m.group(3) else 2,
        "languages": stat("Languages"), "multiattack": multi, "actions": actions,
    }


# ---------------------------------------------------------------- equipment

def parse_equipment():
    text = read(RULES / "core" / "06-equipment.md")
    weapons, armor, gear = {}, {}, {}
    for caption, headers, rows in parse_tables(text):
        cap = caption.lower()
        if "weapons" in cap:
            category = "martial" if "martial" in cap else "simple"
            ranged = "ranged" in cap
            for r in rows:
                if len(r) < 6 or r[0].lower() == "name":
                    continue
                dmg = re.match(r"(\d+d\d+|\d+) (\w+)", r[1])
                props = [p.strip() for p in re.split(r",(?![^()]*\))", r[2]) if p.strip() and p.strip() != "—"]
                rng = re.search(r"Range (\d+)/(\d+)", r[2])
                vers = re.search(r"Versatile \((\d+d\d+)\)", r[2])
                weapons[r[0].lower()] = {
                    "name": r[0], "category": category, "ranged": ranged,
                    "damage": dmg.group(1) if dmg else "1", "type": dmg.group(2).lower() if dmg else "bludgeoning",
                    "properties": [re.sub(r"\s*\(.*\)", "", p).lower() for p in props],
                    "range": [int(rng.group(1)), int(rng.group(2))] if rng else None,
                    "versatile": vers.group(1) if vers else None,
                    "mastery": r[3].lower(), "cost_cp": cost_cp(r[5]), "weight": r[4],
                }
        elif "armor" in cap or "shield" in cap:
            category = "shield" if "shield" in cap else cap.split()[0]
            for r in rows:
                if len(r) < 6:
                    continue
                base = num(r[1], 0)
                dex_max = None if "Dex" in r[1] and "max" not in r[1] else (num(re.search(r"max (\d+)", r[1]).group(1)) if "max" in r[1] else 0)
                armor[r[0].lower()] = {
                    "name": r[0], "category": category, "base": base,
                    "adds_dex": "Dex" in r[1], "dex_max": dex_max,
                    "str_req": num(r[2]) if r[2] not in ("—", "") else None,
                    "stealth_dis": "Disadvantage" in r[3], "cost_cp": cost_cp(r[5]),
                }
        elif headers and headers[0].lower() in ("item", "mount", "service", "animal", "focus", "type", "ship"):
            for r in rows:
                if len(r) >= 2:
                    price = next((cost_cp(c) for c in reversed(r) if cost_cp(c) is not None), None)
                    if price is not None:
                        gear[r[0].lower()] = {"name": r[0], "cost_cp": price}
    for m in re.finditer(r"^#### (.+?) \(([\d,]+ (?:CP|SP|GP|PP))\)", text, re.M):
        gear.setdefault(m.group(1).strip().lower(), {"name": m.group(1).strip(), "cost_cp": cost_cp(m.group(2))})
    # tools priced per variant, e.g. "#### Musical Instrument (Varies)" ... "**Variants:** Bagpipes (30 GP, 6 lb.), drum (6 GP, 3 lb.)"
    for m in re.finditer(r"^#### \**([^\n(*]+?) \(Varies\)\**[ \t]*\n(.*?)(?=^#{2,4} |\Z)", text, re.M | re.S):
        kind = m.group(1).strip()
        var = re.search(r"\*\*Variants:\*\*\s*(.+)", m.group(2))
        if not var:
            continue
        for vm in re.finditer(r"([A-Za-z' -]+?)\s*\(([\d,]+ (?:CP|SP|GP|PP))", var.group(1)):
            vname = vm.group(1).strip(" ,").strip()
            vname = vname[0].upper() + vname[1:]
            gear.setdefault(vname.lower(), {"name": vname, "cost_cp": cost_cp(vm.group(2)), "tool_kind": kind})
    return weapons, armor, gear


# ---------------------------------------------------------------- origins & feats

def parse_origins():
    text = read(RULES / "core" / "04-character-origins.md")
    bg_part, _, sp_part = text.partition("## Character Species")
    backgrounds = {}
    for m in re.finditer(r"^#{2,4} \**(\w[\w' ]+?)\**\s*\n(.*?)(?=^#{2,4} |\Z)", bg_part, re.M | re.S):
        body = m.group(2)
        ab = re.search(r"\*\*Ability Scores:\*\*\s*(.+)", body)
        if not ab:
            continue
        backgrounds[m.group(1).strip()] = {
            "name": m.group(1).strip(),
            "abilities": [ability_key(w) for w in ab.group(1).split(",") if ability_key(w)],
            "feat": re.sub(r"\s*\(see.*", "", re.search(r"\*\*Feat:\*\*\s*(.+)", body).group(1)).strip(),
            "skills": [s.strip().lower() for s in re.split(r",| and ", re.search(r"\*\*Skill Proficiencies:\*\*\s*(.+)", body).group(1)) if s.strip()],
            "tool": re.search(r"\*\*Tool Proficiency:\*\*\s*(.+)", body).group(1).strip(),
            "equipment": re.search(r"\*\*Equipment:\*\*\s*(.+)", body).group(1).strip(),
        }
    species = {}
    for m in re.finditer(r"^#### \**(\w+)\**\s*\n(.*?)(?=^#### |\Z)", sp_part, re.M | re.S):
        body = m.group(2)
        if "**Speed:**" not in body:
            continue
        dv = re.search(r"Darkvision with a range of (\d+) feet", body)
        resist = sorted({d for d in DAMAGE_TYPES if re.search(r"Resistance to " + d.capitalize(), body)})
        species[m.group(1)] = {
            "name": m.group(1),
            "size": "Medium or Small" if "Medium or Small" in body else ("Small" if re.search(r"\*\*Size:\*\* Small", body) else "Medium"),
            "speed": num(re.search(r"\*\*Speed:\*\*\s*(.+)", body).group(1), 30),
            "darkvision": int(dv.group(1)) if dv else 0,
            "resist": resist,
            "traits": re.findall(r"^\*\*(.+?)\.\*\*", body, re.M),
            "hp_per_level": 1 if "Hit Point maximum increases by 1" in body else 0,
        }
    return backgrounds, species


def parse_feats():
    text = read(RULES / "core" / "05-feats.md")
    feats = {}
    for m in re.finditer(r"^#### (.+?)\s*\n\s*\n\*(.+?)\*\s*\n(.*?)(?=^#### |\Z)", text, re.M | re.S):
        meta = m.group(2)
        cat = re.match(r"(Origin|General|Fighting Style|Epic Boon)", meta)
        prereq = re.search(r"Prerequisite: (.+?)\)", meta)
        lvl = re.search(r"Level (\d+)\+", meta)
        feats[m.group(1).strip()] = {
            "name": m.group(1).strip(), "category": cat.group(1).lower() if cat else "general",
            "prereq": prereq.group(1) if prereq else "", "min_level": int(lvl.group(1)) if lvl else 1,
            "repeatable": "Repeatable" in m.group(3),
        }
    return feats


def parse_glossary():
    text = read(RULES / "core" / "08-rules-glossary.md")
    conditions = [c.lower() for c in re.findall(r"^#### (\w+) \[Condition\]", text, re.M)]
    return conditions


def parse_misc():
    cc = read(RULES / "core" / "02-character-creation.md")
    tb = read(RULES / "core" / "09-gameplay-toolbox.md")
    adv, mc, point = {}, {}, {}
    for caption, headers, rows in parse_tables(cc):
        if caption.startswith("Character Advancement"):
            adv = {num(r[0]): num(r[1]) for r in rows}
        elif caption.startswith("Multiclass Spellcaster"):
            mc = {num(r[0]): [num(c, 0) for c in r[1:10]] for r in rows}
        elif caption.startswith("Ability Score Point Costs"):
            for r in rows:
                point[num(r[0])] = num(r[1])
                point[num(r[2])] = num(r[3])
    budget = {}
    for caption, headers, rows in parse_tables(tb):
        if caption.startswith("XP Budget"):
            budget = {num(r[0]): {"low": num(r[1]), "moderate": num(r[2]), "high": num(r[3])} for r in rows}
    sa = re.search(r"Standard Array[^\d]*(\d+), (\d+), (\d+), (\d+), (\d+), (\d+)", cc)
    return {"level_xp": adv, "multiclass_slots": mc, "point_costs": point, "xp_budget": budget,
            "standard_array": sorted([int(x) for x in sa.groups()], reverse=True) if sa else [15, 14, 13, 12, 10, 8]}


def parse_magic_items():
    items = {}
    for f in (RULES / "magic-items").glob("*.md"):
        if f.name.startswith("_"):
            continue
        text = read(f)
        name = text.splitlines()[0].lstrip("# ").strip()
        meta = re.search(r"^\*(?!\*)(.+?)\*\s*$", text, re.M)
        meta = meta.group(1) if meta else ""
        rarities = re.findall(r"\b(Common|Uncommon|Rare|Very Rare|Legendary|Artifact)\b", meta)
        items[f.stem] = {"name": name, "slug": f.stem, "meta": meta,
                         "rarities": list(dict.fromkeys(rarities)) or ["Varies"],
                         "attunement": "Attunement" in meta,
                         "consumable": bool(re.match(r"(Potion|Scroll)", meta))}
    return items


# ---------------------------------------------------------------- build / cache

def _signature():
    files = list(RULES.rglob("*.md"))
    return f"{CACHE_VERSION}:{len(files)}:{max(f.stat().st_mtime for f in files):.0f}:{Path(__file__).stat().st_mtime:.0f}"


def build():
    weapons, armor, gear = parse_equipment()
    backgrounds, species = parse_origins()
    data = {
        "classes": {c["name"]: c for c in (parse_class(f) for f in sorted((RULES / "classes").glob("*.md")))},
        "spells": {s["slug"]: s for s in (parse_spell(f) for f in sorted((RULES / "spells").glob("*.md")) if not f.name.startswith("_"))},
        "monsters": {m["slug"]: m for m in (parse_monster(f) for f in sorted((RULES / "monsters").glob("*.md")) if not f.name.startswith("_"))},
        "weapons": weapons, "armor": armor, "gear": gear,
        "backgrounds": backgrounds, "species": species, "feats": parse_feats(),
        "conditions": parse_glossary(), "magic_items": parse_magic_items(),
    }
    data.update(parse_misc())
    return data


@lru_cache(maxsize=1)
def data():
    sig = _signature()
    if CACHE.exists():
        try:
            cached = json.loads(CACHE.read_text(encoding="utf-8"))
            if cached.get("_sig") == sig:
                return _fix_keys(cached)
        except (ValueError, OSError):
            pass
    d = build()
    d["_sig"] = sig
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(d), encoding="utf-8")
    return _fix_keys(json.loads(json.dumps(d)))


def _fix_keys(d):
    """JSON turns int keys into strings; restore them for the numeric tables."""
    for key in ("level_xp", "multiclass_slots", "point_costs", "xp_budget"):
        d[key] = {int(k): v for k, v in d[key].items()}
    for c in d["classes"].values():
        c["levels"] = {int(k): v for k, v in c["levels"].items()}
        for sub in c["subclasses"].values():
            sub["spells"] = {int(k): v for k, v in sub.get("spells", {}).items()}
    return d


# ---------------------------------------------------------------- lookups

def find(kind, name):
    """Case/format-insensitive lookup in a data table; returns the entry or None."""
    table = data()[kind]
    if name in table:
        return table[name]
    key = slug(name)
    for k, v in table.items():
        if slug(k) == key or slug(v.get("name", "")) == key:
            return v
    return None


def suggest(kind, name, n=5):
    import difflib
    names = [v.get("name", k) for k, v in data()[kind].items()]
    return difflib.get_close_matches(name, names, n=n, cutoff=0.5)
