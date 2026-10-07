"""Game state: rebuilt from the signed event log, mutated only through emit(), committed atomically.

A command either succeeds completely (all its events are signed and appended) or raises
RuleError and nothing is written. There is no code path that changes state without an event.
"""
import copy
import json
import re

from . import dice, srd, effects
from .store import Store, TamperError, active_dir


class RuleError(Exception):
    """A command that would break the rules. Message explains why and cites where to look."""


# ============================================================== reducer

def empty_state():
    return {"campaign": {}, "settings": {"player_rolls": "auto", "xp_mode": "xp", "difficulty": "standard"},
            "entities": {}, "combat": None, "maps": {}, "view": {"map": None, "handout": None, "scene": None},
            "time": 0, "session": 0, "requests": {}, "rolls": [], "roll_count": 0, "feed": [],
            "homebrew": {}, "overrides": [], "assets": {}, "encounters": [], "seq": 0}


def set_path(obj, path, value):
    parts = path.split(".")
    for p in parts[:-1]:
        obj = obj.setdefault(p, {})
    if value is None and parts[-1] in obj:
        del obj[parts[-1]]
    elif value is not None:
        obj[parts[-1]] = value


def apply(state, ev):
    t, d = ev["type"], ev.get("data", {})
    state["seq"] = ev.get("seq", state["seq"])
    if t == "campaign.init":
        state["campaign"] = d
    elif t == "setting":
        state["settings"][d["key"]] = d["value"]
    elif t == "entity.add":
        state["entities"][d["entity"]["id"]] = d["entity"]
    elif t == "entity.set":
        ent = state["entities"][d["id"]]
        for path, value in d["set"].items():
            set_path(ent, path, value)
    elif t == "entity.remove":
        state["entities"].pop(d["id"], None)
    elif t == "roll":
        state["roll_count"] += 1
        state["rolls"].append({**d, "seq": ev.get("seq")})
        del state["rolls"][:-300]
    elif t == "request.add":
        state["requests"][d["id"]] = d
    elif t == "request.close":
        state["requests"].pop(d["id"], None)
    elif t == "combat.set":
        state["combat"] = d["combat"]
    elif t == "map.add":
        state["maps"][d["map"]["id"]] = d["map"]
    elif t == "map.set":
        for path, value in d["set"].items():
            set_path(state["maps"][d["id"]], path, value)
    elif t == "map.reveal":
        m = state["maps"][d["id"]]
        rows = [list(r) for r in m["revealed"]]
        for x, y in d["cells"]:
            if 0 <= y < len(rows) and 0 <= x < len(rows[0]):
                rows[y][x] = "0" if d.get("hide") else "1"
        m["revealed"] = ["".join(r) for r in rows]
    elif t == "map.remove":
        state["maps"].pop(d["id"], None)
    elif t == "view.set":
        state["view"].update(d)
    elif t == "journal.add":
        state.setdefault("journal", []).append(d["entry"])
    elif t == "journal.set":
        for e in state.get("journal", []):
            if e["id"] in d["ids"]:
                e.update(d["set"])
    elif t == "time.set":
        state["time"] = d["minutes"]
    elif t == "session.set":
        state["session"] = d["n"]
    elif t == "feed":
        state["feed"].append({**d, "seq": ev.get("seq"), "ts": ev.get("ts")})
        del state["feed"][:-400]
    elif t == "homebrew.add":
        state["homebrew"].setdefault(d["kind"], {})[d["slug"]] = d["entry"]
    elif t == "override":
        state["overrides"].append({**d, "seq": ev.get("seq")})
    elif t == "asset.add":
        state["assets"][d["asset"]["id"]] = d["asset"]
    elif t == "encounter.log":
        state["encounters"].append(d)
    elif t == "agenda.add":
        state.setdefault("agenda", []).append(d["item"])
    elif t == "agenda.set":
        for it in state.get("agenda", []):
            if it["id"] == d["id"]:
                it.update(d["set"])
    return state


def journal_cat(e):
    """Which journal section an entry belongs in: 'clue' (Handouts & clues) or 'place' (Places & objects).
    Map points of interest are places unless filed as clues; everything shown or added on purpose is a clue."""
    return e.get("cat") or ("place" if e.get("poi") else "clue")


def replay(events):
    state = empty_state()
    for ev in events:
        apply(state, ev)
    return state


# ============================================================== helpers

def mod(score):
    return (int(score) - 10) // 2


def fmt_mod(n):
    return f"{n:+d}"


def pb_for_level(level):
    return 2 + (max(1, level) - 1) // 4


def parse_duration(text):
    """'10m', '2h', '1d', '8 hours', '30' (minutes) -> minutes"""
    total = 0
    for n, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([a-z]*)", str(text).lower()):
        n = float(n)
        if unit.startswith(("d",)):
            total += n * 1440
        elif unit.startswith(("h",)):
            total += n * 60
        elif unit.startswith(("r",)):  # rounds
            total += n / 10
        else:
            total += n
    return int(round(total))


def parse_when(text):
    """'Day 7 08:00', 'day 7', 'Day 7, 8:30' -> minutes since Day 1 00:00 (None if it isn't a date)."""
    m = re.match(r"\s*day\s*(\d+)\s*,?\s*(?:(\d{1,2}):(\d{2}))?\s*$", str(text), re.I)
    if not m:
        return None
    return (int(m.group(1)) - 1) * 1440 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def fmt_time(minutes):
    day, rem = divmod(int(minutes), 1440)
    h, m = divmod(rem, 60)
    return f"Day {day + 1}, {h:02d}:{m:02d}"


SIZE_ORDER = ["Tiny", "Small", "Medium", "Large", "Huge", "Gargantuan"]
SIZE_CELLS = {"Tiny": 1, "Small": 1, "Medium": 1, "Large": 2, "Huge": 3, "Gargantuan": 4}

# Known mechanical effects of SRD magic items (others are tracked narratively by the DM).
MAGIC_EFFECTS = {
    "ring-of-protection": {"ac": 1, "saves": 1},
    "cloak-of-protection": {"ac": 1, "saves": 1},
    "bracers-of-defense": {"ac_unarmored": 2},
    "amulet-of-health": {"set": {"con": 19}},
    "gauntlets-of-ogre-power": {"set": {"str": 19}},
    "headband-of-intellect": {"set": {"int": 19}},
    "belt-of-hill-giant-strength": {"set": {"str": 21}},
    "belt-of-frost-giant-strength": {"set": {"str": 23}},
    "belt-of-fire-giant-strength": {"set": {"str": 25}},
    "belt-of-cloud-giant-strength": {"set": {"str": 27}},
    "belt-of-storm-giant-strength": {"set": {"str": 29}},
    "boots-of-speed": {},
    "stone-of-good-luck-luckstone": {"checks": 1, "saves": 1},
}
RARITY_ORDER = ["Common", "Uncommon", "Rare", "Very Rare", "Legendary", "Artifact"]
TIER_MAX_RARITY = {1: "Uncommon", 2: "Rare", 3: "Very Rare", 4: "Legendary"}
TIER_MAX_GP_AWARD = {1: 300, 2: 3000, 3: 30000, 4: 200000}


def tier(level):
    return 1 if level <= 4 else 2 if level <= 10 else 3 if level <= 16 else 4


# ============================================================== Game

class Game:
    def __init__(self, campaign_dir=None, verify=True):
        self.dir = campaign_dir or active_dir()
        self.store = Store(self.dir)
        self.events = self.store.load(verify=verify)
        self.state = replay(self.events)
        self.pending = []
        self.out = []
        self.cmdline = ""

    def caught_up(self):
        """A new Game that has caught up with events another process appended (the live table after a DM command),
        verifying and applying only the new ones. This one is left untouched, so readers on other threads never see
        it change. None when the log changed some other way (a quickload, a repair): build a fresh Game instead."""
        if self.pending:
            return None
        store = Store(self.dir)
        store._seen = dict(getattr(self.store, "_seen", None) or {})
        if not store._seen:
            return None
        new = store.load_new()
        if new is None:
            return None
        import pickle
        g = copy.copy(self)
        g.store, g.pending, g.out, g.cmdline = store, [], [], ""
        g.state = pickle.loads(pickle.dumps(self.state, -1))
        for ev in new:
            apply(g.state, ev)
        g.events = self.events + new
        return g

    # ------------------------------------------------------------ event plumbing
    def emit(self, type_, **data):
        ev = {"type": type_, "data": copy.deepcopy(data)}
        if self.cmdline:
            ev["cmd"] = self.cmdline
        self.pending.append(ev)
        apply(self.state, {**ev, "seq": self.state["seq"] + 1})
        return ev

    def commit(self):
        if not self.pending:
            return []
        written = self.store.append_many(self.pending, expected_seq=len(self.events))
        self.events.extend(written)
        self.pending = []
        return written

    def say(self, text, kind="info", **extra):
        """Public line in the viewer feed + CLI output."""
        self.emit("feed", text=text, kind=kind, **extra)
        self.out.append(text)

    def note(self, text):
        """CLI-only output for the DM (not shown to the player)."""
        self.out.append(text)

    def override(self, reason, what):
        if not reason or len(reason.strip()) < 8:
            raise RuleError("An override needs a real reason (8+ characters). Overrides are shown publicly to the player.")
        self.emit("override", reason=reason.strip(), what=what)
        self.say(f"⚠ DM override — {what}. Reason: {reason.strip()}", kind="override")

    # ------------------------------------------------------------ rolling
    def roll(self, expr, purpose, who=None, mode=None, crit=False, hidden=False, request=None):
        try:
            r = dice.roll(expr, mode=mode, crit=crit)
        except dice.DiceError as e:
            raise RuleError(str(e))
        rid = f"r{self.state['roll_count'] + 1}"
        self.emit("roll", id=rid, who=who, purpose=purpose, expr=r["expr"], mode=mode, crit=crit,
                  total=r["total"], nat=r["nat"], terms=r["terms"], text=r["text"], hidden=hidden,
                  request=request)
        return {**r, "id": rid}

    # ------------------------------------------------------------ entities
    @property
    def entities(self):
        return self.state["entities"]

    def get(self, ref):
        if ref in self.entities:
            return self.entities[ref]
        key = srd.slug(ref)
        hits = [e for e in self.entities.values() if e["id"] == key or srd.slug(e["name"]) == key]
        if not hits:
            hits = [e for e in self.entities.values() if srd.slug(e["name"]).startswith(key) or e["id"].startswith(key)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise RuleError(f"'{ref}' is ambiguous: {', '.join(e['id'] for e in hits)}")
        raise RuleError(f"No creature '{ref}'. Known: {', '.join(self.entities) or 'none'}")

    def set(self, ent, **fields):
        """Patch an entity. Keys use '__' for nested paths (e.g. death__fail=1)."""
        patch = {k.replace("__", "."): v for k, v in fields.items()}
        self.emit("entity.set", id=ent["id"], set=patch)

    def pcs(self):
        return [e for e in self.entities.values() if e["kind"] == "pc" and not e.get("departed")]

    def party_level(self):
        pcs = [p for p in self.pcs() if not p.get("dead")]
        return max(1, round(sum(level(p) for p in pcs) / len(pcs))) if pcs else 1

    def new_id(self, base):
        base = srd.slug(base) or "x"
        if base not in self.entities:
            return base
        i = 2
        while f"{base}-{i}" in self.entities:
            i += 1
        return f"{base}-{i}"

    # ------------------------------------------------------------ homebrew-aware lookups
    def lookup(self, kind, name):
        hb = self.state["homebrew"].get(kind, {})
        key = srd.slug(name)
        if key in hb:
            return hb[key]
        return srd.find(kind, name)

    def require(self, kind, name, label=None):
        v = self.lookup(kind, name)
        if not v:
            sug = srd.suggest(kind, name)
            raise RuleError(f"{label or kind[:-1].title()} '{name}' is not in the SRD" +
                            (f" (did you mean: {', '.join(sug)}?)" if sug else "") +
                            ". Homebrew must be registered first with `homebrew add` (publicly logged).")
        return v


# ============================================================== derived character stats

def level(e):
    return sum(e.get("classes", {}).values()) if e["kind"] == "pc" else 0


def pb(e):
    if e["kind"] != "pc":
        return e.get("pb", 2)
    return pb_for_level(level(e))


def class_row(cls, lvl):
    c = srd.find("classes", cls)
    return c["levels"].get(lvl, {}) if c else {}


def abilities(e):
    """Final ability scores including item effects that set a score."""
    if e["kind"] != "pc":
        return {k: v["score"] for k, v in e.get("abilities", {}).items()} or {a: 10 for a in srd.ABILITIES}
    scores = dict(e["abilities"])
    for it in e.get("inventory", []):
        eff = MAGIC_EFFECTS.get(it.get("ref"), {})
        if eff.get("set") and (it.get("attuned") or not it.get("needs_attunement")) and it.get("equipped", True):
            for k, v in eff["set"].items():
                scores[k] = max(scores[k], v)
    return scores


def amod(e, ability):
    if e["kind"] != "pc" and e.get("abilities"):
        return e["abilities"][ability]["mod"]
    return mod(abilities(e)[ability])


def item_bonus(e, key):
    total = 0
    for it in e.get("inventory", []):
        eff = MAGIC_EFFECTS.get(it.get("ref"), {})
        active = it.get("attuned") if it.get("needs_attunement") else it.get("equipped")
        if active and key in eff:
            total += eff[key]
    return total


def has_feature(e, name):
    name = name.lower()
    for cls, lv in e.get("classes", {}).items():
        c = srd.find("classes", cls)
        if not c:
            continue
        if any(f.lower() == name for l, f in c["features"] if l <= lv):
            return True
        sub = e.get("subclasses", {}).get(cls)
        if sub and sub in c["subclasses"]:
            if any(f.lower() == name for l, f in c["subclasses"][sub]["features"] if l <= lv):
                return True
        for row_lv in range(1, lv + 1):
            feats = [f.strip().lower() for f in c["levels"].get(row_lv, {}).get("Class Features", "").split(",")]
            if name in feats:
                return True
    return any(f["name"].lower() == name for f in e.get("feats", [])) or name in [t.lower() for t in e.get("species_traits", [])]


def has_feat(e, name):
    return any(f["name"].lower().startswith(name.lower()) for f in e.get("feats", []))


def equipped(e, kind):
    return [it for it in e.get("inventory", []) if it.get("kind") == kind and it.get("equipped")]


def armor_class(e):
    """Returns (ac, explanation)."""
    if e["kind"] != "pc":
        bonus = sum(c.get("ac_bonus", 0) for c in effects.active(e))
        base = max(e["ac"], 13 + amod(e, "dex") if effects.has(e, "mage_armor") else 0)
        return max(base + bonus, max((f.get("ac_floor", 0) for f in effects.active(e)), default=0)), "stat block and spell effects"
    dex = amod(e, "dex")
    armors = [it for it in equipped(e, "armor") if it.get("category") != "shield"]
    shields = [it for it in equipped(e, "armor") if it.get("category") == "shield"]
    options = []
    if armors:
        a = armors[0]
        base = srd.find("armor", a["base_name"])
        dexpart = 0
        if base["adds_dex"]:
            dexpart = dex if base["dex_max"] is None else min(dex, base["dex_max"])
        options.append((base["base"] + dexpart + a.get("magic_bonus", 0), f"{a['name']} {base['base']}" +
                        (f" + Dex {dexpart}" if base["adds_dex"] else "") + (f" + {a['magic_bonus']}" if a.get("magic_bonus") else "")))
    else:
        options.append((10 + dex, f"unarmored 10 + Dex {dex}"))
        if "Barbarian" in e["classes"]:
            options.append((10 + dex + amod(e, "con"), f"Unarmored Defense 10 + Dex {dex} + Con {amod(e, 'con')}"))
        if "Monk" in e["classes"] and not shields:
            options.append((10 + dex + amod(e, "wis"), f"Unarmored Defense 10 + Dex {dex} + Wis {amod(e, 'wis')}"))
        if effects.has(e, "mage_armor") or any(x.get("name") == "mage armor" for x in e.get("effects", [])):
            options.append((13 + dex, f"Mage Armor 13 + Dex {dex}"))
    ac, why = max(options, key=lambda o: o[0])
    if shields:
        s = shields[0]
        ac += 2 + s.get("magic_bonus", 0)
        why += f" + shield {2 + s.get('magic_bonus', 0)}"
    if armors and has_feat(e, "Defense"):
        ac += 1
        why += " + Defense style 1"
    ib = item_bonus(e, "ac")
    if ib:
        ac += ib
        why += f" + items {ib}"
    if not armors and not shields:
        ub = item_bonus(e, "ac_unarmored")
        if ub:
            ac += ub
            why += f" + bracers {ub}"
    for fx in effects.active(e):
        if fx.get("ac_bonus"):
            ac += fx["ac_bonus"]
            why += f" + {fx['name']} {fx['ac_bonus']}"
    floor = max((f.get("ac_floor", 0) for f in effects.active(e)), default=0)
    return max(ac, floor), why + (f"; spell minimum {floor}" if floor > ac else "")


def save_mod(e, ability):
    if e["kind"] != "pc":
        return e["abilities"][ability]["save"] if e.get("abilities") else 0
    m = amod(e, ability) + (pb(e) if ability in e.get("save_profs", []) else 0) + item_bonus(e, "saves")
    return m


def skill_mod(e, skill):
    skill = skill.lower()
    ability = srd.SKILLS[skill]
    if e["kind"] != "pc":
        return e.get("skills", {}).get(skill, amod(e, ability))
    m = amod(e, ability)
    if skill in e.get("expertise", []):
        m += 2 * pb(e)
    elif skill in e.get("skills", []):
        m += pb(e)
    elif "Bard" in e.get("classes", {}) and e["classes"]["Bard"] >= 2:
        m += pb(e) // 2  # Jack of All Trades
    return m + item_bonus(e, "checks")


def initiative_mod(e):
    if e["kind"] != "pc":
        return e.get("init", amod(e, "dex"))
    return amod(e, "dex") + (pb(e) if has_feat(e, "Alert") else 0)


def exhaustion_penalty(e):
    return 2 * e.get("exhaustion", 0)


def speed(e):
    if e["kind"] != "pc":
        sp = dict(e.get("speed", {"walk": 30}))
    else:
        sp = {"walk": e.get("base_speed", 30)}
        heavy = any(it.get("category") == "heavy" for it in equipped(e, "armor"))
        wearing = any(it.get("category") != "shield" for it in equipped(e, "armor"))
        if "Monk" in e["classes"] and not wearing and not equipped(e, "armor"):
            um = class_row("Monk", e["classes"]["Monk"]).get("Unarmored Movement", "")
            sp["walk"] += srd.num(um, 0) or 0
        if "Barbarian" in e["classes"] and e["classes"]["Barbarian"] >= 5 and not heavy:
            sp["walk"] += 10
        for it in equipped(e, "armor"):
            base = srd.find("armor", it.get("base_name", ""))
            if base and base.get("str_req") and abilities(e)["str"] < base["str_req"]:
                sp["walk"] -= 10
    names = condition_names(e)
    freedom = effects.has(e, "freedom")
    zero = any(f.get("speed_zero") and not (freedom and f.get("spell")) for f in effects.active(e))
    if names & {"grappled", "restrained", "paralyzed", "petrified", "stunned", "unconscious"} or _spellbound(e) or zero:
        return {k: 0 for k in sp}
    pen = 5 * e.get("exhaustion", 0)
    multiplier, bonus = 1, 0
    for fx in effects.active(e):
        if not (freedom and fx.get("spell")):
            pen += fx.get("speed_penalty", 0)
        bonus += fx.get("speed_bonus", 0)
        factor = fx.get("speed_multiplier", 1)
        if not (freedom and fx.get("spell") and factor < 1):
            multiplier *= factor
        speeds = dict(fx.get("speeds", {}))
        if fx.get("fly_speed"):
            speeds["fly"] = fx["fly_speed"]
        if fx.get("climb"):
            speeds["climb"] = "walk"
        if fx.get("swim"):
            speeds["swim"] = "walk"
        for mode, value in speeds.items():
            sp[mode] = max(sp.get(mode, 0), sp["walk"] if value == "walk" else value)
    return {k: max(0, int((v + bonus) * multiplier) - pen) for k, v in sp.items()}


# Spells whose Charmed condition also brings Incapacitated and a Speed of 0 (SRD Hypnotic Pattern).
SPELLBOUND_CHARMS = {"hypnotic-pattern"}


def _spellbound(e):
    if any("charmed" in f.get("condition_immune", []) for f in effects.active(e)):
        return False
    return any(c["name"] == "charmed" and srd.slug(str(c.get("spell") or c.get("source") or "")) in SPELLBOUND_CHARMS
               or (c["name"] == "charmed" and "hypnotic pattern" in str(c.get("source", "")).lower())
               for c in e.get("conditions", []))


def condition_names(e):
    immune = {name for f in effects.active(e) for name in f.get("condition_immune", [])}
    freedom = effects.has(e, "freedom")
    names = {c["name"] for c in e.get("conditions", []) if c["name"] not in immune and not (
        freedom and c.get("spell") and c["name"] in ("paralyzed", "restrained"))}
    for implied in ("paralyzed", "petrified", "stunned", "unconscious"):
        if implied in names:
            names.add("incapacitated")
    if _spellbound(e):
        names.add("incapacitated")
    return names


def hp_max(e):
    return e["hp_max"] + e.get("hp_max_bonus", 0) + sum(f.get("hp_max_bonus", 0) for f in effects.active(e))


def spell_slots(e):
    """Max slots {level: n} from Spellcasting classes (multiclass table when needed) — excludes Pact Magic."""
    casters = []
    for cls, lv in e.get("classes", {}).items():
        c = srd.find("classes", cls)
        if c and c["caster"] in ("full", "half"):
            casters.append((c, lv))
    if not casters:
        return {}
    if len(casters) == 1:
        c, lv = casters[0]
        row = c["levels"][lv]
        return {i: srd.num(row.get(str(i), "—"), 0) for i in range(1, 10) if srd.num(row.get(str(i), "—"), 0)}
    caster_level = sum(lv if c["caster"] == "full" else -(-lv // 2) for c, lv in casters)
    table = srd.data()["multiclass_slots"].get(caster_level, [0] * 9)
    return {i + 1: n for i, n in enumerate(table) if n}


def pact_slots(e):
    lv = e.get("classes", {}).get("Warlock")
    if not lv:
        return None
    row = class_row("Warlock", lv)
    return {"count": srd.num(row.get("Spell Slots"), 0), "level": srd.num(row.get("Slot Level"), 1)}


def max_spell_level_for_class(e, cls):
    c = srd.find("classes", cls)
    lv = e["classes"].get(cls, 0)
    if not c or not lv:
        return -1
    if c["caster"] == "pact":  # Mystic Arcanum spells (6th+) are granted separately, not prepared
        return pact_slots(e)["level"]
    row = c["levels"][lv]
    lvls = [i for i in range(1, 10) if srd.num(row.get(str(i), "—"), 0)]
    return max(lvls) if lvls else 0


def spellcasting(e):
    """Per-class spellcasting numbers."""
    out = {}
    for cls, lv in e.get("classes", {}).items():
        c = srd.find("classes", cls)
        if not c or not c["spell_ability"]:
            continue
        row = c["levels"][lv]
        m = amod(e, c["spell_ability"])
        out[cls] = {"ability": c["spell_ability"], "dc": 8 + m + pb(e), "attack": m + pb(e),
                    "cantrips": srd.num(row.get("Cantrips"), 0) or 0,
                    "prepared": srd.num(row.get("Prepared Spells"), 0) or 0,
                    "max_level": max_spell_level_for_class(e, cls)}
    return out


# ------------------------------------------------------------ limited-use resources

def _col(cls, col):
    def f(e):
        return srd.num(class_row(cls, e["classes"][cls]).get(col), 0) or 0
    return f


# name: (class, max(e), short-rest behaviour: 'all' | 'one' | None)
RESOURCES = {
    "Rage": ("Barbarian", _col("Barbarian", "Rages"), "one"),
    "Second Wind": ("Fighter", _col("Fighter", "Second Wind"), "one"),
    "Action Surge": ("Fighter", lambda e: 2 if e["classes"]["Fighter"] >= 17 else 1, "all"),
    "Indomitable": ("Fighter", lambda e: 0 if e["classes"]["Fighter"] < 9 else 1 if e["classes"]["Fighter"] < 13 else 2 if e["classes"]["Fighter"] < 17 else 3, None),
    "Channel Divinity": ("Cleric|Paladin", lambda e: max(_col("Cleric", "Channel Divinity")(e) if "Cleric" in e["classes"] else 0,
                                                       _col("Paladin", "Channel Divinity")(e) if "Paladin" in e["classes"] else 0), "one"),
    "Wild Shape": ("Druid", _col("Druid", "Wild Shape"), "one"),
    "Focus Points": ("Monk", _col("Monk", "Focus Points"), "all"),
    "Sorcery Points": ("Sorcerer", _col("Sorcerer", "Sorcery Points"), None),
    "Innate Sorcery": ("Sorcerer", lambda e: 2, None),
    "Bardic Inspiration": ("Bard", lambda e: max(1, amod(e, "cha")), "font"),
    "Lay On Hands": ("Paladin", lambda e: 5 * e["classes"]["Paladin"], None),
    "Arcane Recovery": ("Wizard", lambda e: 1, None),
    "Magical Cunning": ("Warlock", lambda e: 1 if e["classes"]["Warlock"] >= 2 else 0, None),
    "Favored Enemy": ("Ranger", _col("Ranger", "Favored Enemy"), None),
    "Divine Intervention": ("Cleric", lambda e: 1 if e["classes"]["Cleric"] >= 10 else 0, None),
    "Heroic Inspiration": (None, lambda e: 1, None),
}


def resources(e):
    """{name: {'max': n, 'used': k, 'short': rule}} for every pool this character actually has."""
    out = {}
    for name, (cls, fmax, short) in RESOURCES.items():
        if name == "Heroic Inspiration":
            continue
        if not any(c in e.get("classes", {}) for c in (cls or "").split("|")):
            continue
        if not has_feature(e, name):
            continue
        n = fmax(e)
        if n:
            out[name] = {"max": n, "used": e.get("resources_used", {}).get(name, 0), "short": short}
    return out


def attacks_per_action(e):
    if effects.has(e, "slow"):
        return 1
    if e["kind"] != "pc":
        return e.get("multiattack", 1)
    n = 1
    f = e["classes"].get("Fighter", 0)
    if f >= 20:
        n = 4
    elif f >= 11:
        n = 3
    elif f >= 5:
        n = 2
    for cls in ("Barbarian", "Monk", "Paladin", "Ranger"):
        if e["classes"].get(cls, 0) >= 5:
            n = max(n, 2)
    return n


def weapon_proficient(e, weapon):
    for cls in e.get("classes", {}):
        c = srd.find("classes", cls)
        if not c:
            continue
        if weapon["category"] == "simple" and c["weapons_simple"]:
            return True
        if weapon["category"] == "martial" and c["weapons_martial"]:
            return True
        if weapon["category"] == "martial" and c["weapons_martial_finesse_light"] and \
                ({"finesse", "light"} & set(weapon["properties"])):
            return True
    return weapon["name"].lower() in [w.lower() for w in e.get("weapon_profs", [])]


def item_known(it):
    """Magic items start unidentified (SRD: handling one tells you it's extraordinary, not what it does)."""
    return it.get("identified", True) or not it.get("magic")


def item_display_name(it):
    """What the characters call an item: the DM's alias, else the real name once identified, else a vague label."""
    if it.get("alias"):
        return it["alias"]
    if item_known(it):
        return it["name"]
    base = it.get("base_name")
    if base:
        return f"Unidentified magic {base.lower()}"
    return {"consumable": "Unidentified potion" if "potion" in it["name"].lower() else "Unidentified magic consumable",
            "armor": "Unidentified magic armor"}.get(it.get("kind"), "Unidentified magic item")


def weapon_attack(e, item, versatile=False, offhand=False):
    """Compute attack bonus and damage for a PC wielding an inventory weapon (or unarmed)."""
    if item is None:  # Unarmed Strike
        ability = "str"
        if "Monk" in e["classes"]:
            ability = "dex" if amod(e, "dex") > amod(e, "str") else "str"
            die = class_row("Monk", e["classes"]["Monk"]).get("Martial Arts", "1d6")
            dmg = f"{die}{fmt_mod(amod(e, ability))}"
        else:
            dmg = str(max(0, 1 + amod(e, ability)))
        return {"name": "Unarmed Strike", "bonus": amod(e, ability) + pb(e), "damage": dmg, "type": "bludgeoning",
                "reach": 5, "range": None, "ranged": False, "properties": [], "mastery": None, "ability": ability}
    w = srd.find("weapons", item["base_name"])
    props = set(w["properties"])
    if w["ranged"]:
        ability = "dex"
    elif "finesse" in props:
        ability = "dex" if amod(e, "dex") >= amod(e, "str") else "str"
    else:
        ability = "str"
    if "Monk" in e["classes"] and not w["ranged"] and (w["category"] == "simple" or "light" in props):
        ability = "dex" if amod(e, "dex") > amod(e, ability) else ability
    m = amod(e, ability)
    bonus = m + (pb(e) if weapon_proficient(e, w) else 0) + item.get("magic_bonus", 0)
    if w["ranged"] and has_feat(e, "Archery"):
        bonus += 2
    die = w["versatile"] if versatile and w["versatile"] else w["damage"]
    dmg_mod = m + item.get("magic_bonus", 0)
    if offhand and m > 0 and not has_feat(e, "Two-Weapon Fighting"):
        dmg_mod = item.get("magic_bonus", 0)
    if has_feat(e, "Dueling") and not w["ranged"] and not versatile and "two-handed" not in props:
        dmg_mod += 2
    rng = w["range"]
    return {"name": item["name"], "item": item.get("id"), "bonus": bonus, "damage": f"{die}{fmt_mod(dmg_mod) if dmg_mod else ''}",
            "type": w["type"], "reach": 10 if "reach" in props else 5, "range": rng, "ranged": w["ranged"],
            "thrown": "thrown" in props, "properties": sorted(props),
            # mastery is per weapon kind: only the weapons the character picked (e.g. a Rogue who chose Shortsword and Dagger gets no Shortbow mastery)
            "mastery": w["mastery"] if e["kind"] != "pc" or w["name"] in e.get("mastery_weapons", []) else None,
            "ability": ability,
            "ammo": "ammunition" in props}


def derive(e):
    """Everything computed about a creature — used by the sheet, viewer and resolvers."""
    ac, ac_why = armor_class(e)
    out = {"ac": ac, "ac_why": ac_why, "hp": e.get("hp"), "hp_max": hp_max(e), "temp_hp": e.get("temp_hp", 0),
           "speed": speed(e), "init": initiative_mod(e), "conditions": sorted(condition_names(e)),
           "exhaustion": e.get("exhaustion", 0)}
    if e["kind"] == "pc":
        ab = abilities(e)
        out.update({
            "level": level(e), "pb": pb(e), "abilities": ab, "mods": {a: mod(v) for a, v in ab.items()},
            "saves": {a: save_mod(e, a) for a in srd.ABILITIES},
            "skills": {s: skill_mod(e, s) for s in srd.SKILLS},
            "passive_perception": 10 + skill_mod(e, "perception"),
            "slots": spell_slots(e), "pact": pact_slots(e), "spellcasting": spellcasting(e),
            "resources": resources(e), "attacks_per_action": attacks_per_action(e),
            "attacks": [weapon_attack(e, it) for it in equipped(e, "weapon")] + [weapon_attack(e, None)],
            "attuned": sum(1 for it in e.get("inventory", []) if it.get("attuned")),
        })
    return out
