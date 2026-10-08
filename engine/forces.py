"""Standing forces: the companies, garrisons and recruits a character commands.

The engine keeps the numbers, the kit, the pay and the mood of each unit so none of it lives only in notes:
- a unit is a count of identical creatures of one SRD stat block, with a captain and a post;
- `forces equip` issues real gear out of a container (one piece per man) and the unit's AC follows the SRD armor table;
- `forces share` hands out coin; a share worth at least a crown a man moves the unit one step up the Influence
  attitudes (Hostile, Indifferent, Friendly, Helpful), which gives Advantage on Influence checks with them when Friendly
  or better (rules/core/08-rules-glossary.md, Influence);
- `forces muster` puts men on the map as ordinary creatures with the unit's kit, ready for a fight.
"""
import re

from . import srd
from . import mechanics as M
from .core import RuleError

ATTITUDES = ["hostile", "indifferent", "friendly", "helpful"]
ATTITUDE_EFFECT = {"hostile": "Disadvantage on Influence checks with them; desertion likely",
                   "indifferent": "no modifier on Influence checks with them",
                   "friendly": "Advantage on Influence checks with them",
                   "helpful": "Advantage on Influence checks with them; they take risks for you unasked"}


def units(g):
    return g.state.get("forces", {})


def get(g, uid):
    u = units(g).get(uid)
    if not u:
        raise RuleError(f"No unit '{uid}'. Units: " + (", ".join(f"{k} ({v['name']})" for k, v in units(g).items()) or "none"))
    return dict(u)


def stat_block(g, stat):
    mon = g.lookup("monsters", stat)
    if not mon:
        sug = srd.suggest("monsters", stat)
        raise RuleError(f"No stat block '{stat}' in the SRD" + (f" (did you mean {', '.join(sug)}?)" if sug else "") + ".")
    return mon


def dex_mod(mon):
    d = (mon.get("abilities") or {}).get("dex", 10)
    if isinstance(d, dict):
        return d.get("mod", (d.get("score", 10) - 10) // 2)
    return (d - 10) // 2


def kit_ac(g, u):
    """(AC, why): the stat block's own AC, or the SRD armor table for armor the unit has been issued (+2 for a shield)."""
    mon = stat_block(g, u["stat"])
    gear = u.get("gear", {})
    if gear.get("armor"):
        a = srd.find("armor", gear["armor"])
        dex = dex_mod(mon)
        part = (dex if a["dex_max"] is None else min(dex, a["dex_max"])) if a["adds_dex"] else 0
        ac, why = a["base"] + part, f"{a['name']} {a['base']}" + (f" + Dex {part}" if a["adds_dex"] else "")
    else:
        ac, why = mon["ac"], "stat block"
    if gear.get("shield"):
        ac, why = ac + 2, why + " + Shield 2"
    return ac, why


def save(g, uid, unit):
    g.emit("forces.set", id=uid, unit=unit)


def describe(g, uid, u):
    ac, why = kit_ac(g, u)
    gear = u.get("gear", {})
    kit = ", ".join(x for x in (gear.get("armor"), "Shield" if gear.get("shield") else None, gear.get("weapon")) if x)
    return (f"{u['name']} (`{uid}`): {u['count']}× {stat_block(g, u['stat'])['name']}, AC {ac} ({why})"
            + (f", kit: {kit}" if kit else "") + (f", at {u['where']}" if u.get("where") else "")
            + (f", captain {u['captain']}" if u.get("captain") else "") + (f", pay {u['pay']}" if u.get("pay") else "")
            + f" · {u.get('attitude', 'indifferent').capitalize()} ({ATTITUDE_EFFECT[u.get('attitude', 'indifferent')]})")


def add(g, uid, name, stat, count, where=None, captain=None, attitude="indifferent", pay=None):
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", uid or ""):
        raise RuleError("A unit id is lowercase letters, digits and dashes, e.g. thornbury-garrison.")
    if uid in units(g):
        raise RuleError(f"There's already a unit '{uid}'.")
    if count < 1:
        raise RuleError("A unit needs at least one man.")
    if attitude not in ATTITUDES:
        raise RuleError(f"--attitude {'|'.join(ATTITUDES)}")
    stat_block(g, stat)
    u = {"name": name, "stat": stat, "count": count, "where": where, "captain": captain, "attitude": attitude,
         "pay": pay, "gear": {}}
    save(g, uid, u)
    g.say(f"⚔ New unit: {describe(g, uid, u)}.", kind="info")


def take_from_box(g, box_id, name, qty):
    """Remove qty of an item (by name) from an opened container; returns the item dict taken."""
    for m in g.state["maps"].values():
        box = next((c for c in m.get("containers", []) if c["id"] == box_id), None)
        if not box:
            continue
        if box.get("sealed"):
            raise RuleError(f"Nobody has opened the {box['name']} yet.")
        floor = [dict(f) for f in m.get("floor", [])]
        want = srd.slug(name)
        have = [f for f in floor if f.get("in") == box_id and srd.slug(f["item"]["name"]) == want]
        total = sum(f["item"].get("qty", 1) for f in have)
        if total < qty:
            raise RuleError(f"The {box['name']} holds {total} {name}, not {qty}. Split the unit (`forces split`) or find more.")
        left = qty
        for f in have:
            n = min(left, f["item"].get("qty", 1))
            f["item"] = dict(f["item"], qty=f["item"].get("qty", 1) - n)
            left -= n
            if not left:
                break
        floor = [f for f in floor if f["item"].get("qty", 1) > 0]
        g.emit("map.set", id=m["id"], set={"floor": floor})
        return have[0]["item"]
    raise RuleError(f"No container '{box_id}'.")


def equip(g, uid, box_id, armor=None, shield=False, weapon=None):
    u = get(g, uid)
    if not (armor or shield or weapon):
        raise RuleError("forces equip <unit> --from <container> [--armor \"Chain Shirt\"] [--shield] [--weapon Spear]")
    gear = dict(u.get("gear", {}))
    before, _ = kit_ac(g, u)
    issued = []
    if armor:
        a = srd.find("armor", armor)
        if not a or a.get("category") == "shield":
            raise RuleError(f"'{armor}' isn't SRD armor.")
        take_from_box(g, box_id, a["name"], u["count"])
        gear["armor"], issued = a["name"], issued + [f"{u['count']} {a['name']}"]
    if shield:
        take_from_box(g, box_id, "Shield", u["count"])
        gear["shield"], issued = True, issued + [f"{u['count']} Shield"]
    if weapon:
        w = srd.find("weapons", weapon)
        if not w:
            raise RuleError(f"'{weapon}' isn't an SRD weapon.")
        take_from_box(g, box_id, w["name"], u["count"])
        gear["weapon"], issued = w["name"], issued + [f"{u['count']} {w['name']}"]
    u["gear"] = gear
    save(g, uid, u)
    after, why = kit_ac(g, u)
    for e in [e for e in g.entities.values() if e.get("unit") == uid and not e.get("dead")]:
        g.set(e, ac=after, armored_ac=None)   # the men on the map wear what they were issued
    g.say(f"🛡 {u['name']} issued {', '.join(issued)}: AC {before} → {after} ({why}).", kind="item")


def share(g, uid, cp, payer_ref, reason):
    """Spoils or a bounty paid out to a unit. A crown a man or more moves them one attitude step up (to Helpful at most)."""
    u = get(g, uid)
    if cp <= 0:
        raise RuleError("Share a positive amount, e.g. --coins 20gp.")
    M.credit_coins(g, payer_ref, -cp, f"spoils shared with {u['name']}")
    per = cp / u["count"]
    old = u.get("attitude", "indifferent")
    new = old
    if per >= 100 and ATTITUDES.index(old) < len(ATTITUDES) - 1:
        new = ATTITUDES[ATTITUDES.index(old) + 1]
    u["attitude"] = new
    save(g, uid, u)
    g.say(f"💰 {u['name']} share {M.fmt_cp(cp)} ({M.fmt_cp(int(per))} a man) — {reason}."
          + (f" Attitude {old.capitalize()} → {new.capitalize()}: {ATTITUDE_EFFECT[new]}." if new != old
             else f" Attitude stays {old.capitalize()}" + (" (a share under a crown a man moves nobody)." if per < 100 else ".")),
          kind="item")


def muster(g, uid, count, map_id, at, instantiate):
    """Put `count` men of the unit on the map as allied creatures wearing the unit's kit."""
    from . import maps
    u = get(g, uid)
    if count < 1 or count > u["count"]:
        raise RuleError(f"{u['name']} has {u['count']} men.")
    mon = stat_block(g, u["stat"])
    ac, _ = kit_ac(g, u)
    m = g.state["maps"].get(map_id)
    if not m:
        raise RuleError(f"No map '{map_id}'.")
    occupied = {(e["token"]["x"], e["token"]["y"]) for e in g.entities.values() if e.get("token", {}).get("map") == map_id}
    spots = maps.free_cells(m, count, __import__("random").Random(g.state["seq"]), near=at, avoid=frozenset(occupied))
    made = []
    for i, (sx, sy) in enumerate(spots):
        e = instantiate(g, mon, f"{u['name']} {i + 1}", "ally", False)
        g.set(e, token={"map": map_id, "x": sx, "y": sy}, ac=ac, unit=uid)
        made.append(e["id"])
    g.say(f"⚔ {len(made)} of {u['name']} muster at {m['name']} (AC {ac}).", kind="creature")
    return made


def enlist(g, uid, ids):
    """Creatures already on the table (recruits, turncoats) join a unit: they wear its kit (AC) from now on."""
    u = get(g, uid)
    ac, why = kit_ac(g, u)
    names = []
    for i in ids:
        e = g.get(i)
        if e["kind"] == "pc":
            raise RuleError("Player characters aren't unit men.")
        g.set(e, unit=uid, ac=ac, armored_ac=None, side="ally")
        names.append(e["name"])
    g.say(f"⚔ {', '.join(names)} enlisted in {u['name']} (AC {ac}: {why}).", kind="creature")
