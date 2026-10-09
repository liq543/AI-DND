"""Loot the engine remembers, and the DM's own reminders.

Treasure is decided before anyone searches, and the engine keeps the DM to it:
- a notable foe defeated in combat leaves a "loot owed" entry until its gear is decided (`loot body` / `loot none`);
- a sealed cache keeps its contents off the table until a character opens it (`loot open`);
- a party companion run by the DM gets a DM-only list of its whole kit at the start of each of its turns.
"""
import re

from . import srd
from . import mechanics as M
from .core import RARITY_ORDER, TIER_MAX_RARITY, RuleError, derive, item_display_name, resources, tier

CONSUMABLE_RE = re.compile(r"(?i)\b(potion|scroll|oil of|elixir|philter|dust of|antitoxin|alchemist's fire|holy water|"
                           r"healer's kit|bead of|ointment|poison)\b")


def cr_number(cr):
    text = str(cr or "0")
    if "/" in text:
        a, b = text.split("/", 1)
        return srd.num(a, 0) / max(1, srd.num(b, 1))
    return float(srd.num(text, 0))


def notable_foe(e):
    """A foe whose gear is worth deciding: CR 1 or more, a named creature (not just 'Bandit B'), or a custom stat block."""
    if e.get("kind") == "pc" or e.get("side") in ("ally", "party"):
        return False
    if not e.get("srd"):
        return True
    if cr_number(e.get("cr")) >= 1:
        return True
    base = srd.find("monsters", e["srd"])
    base_name = (base or {}).get("name", e["srd"]).lower()
    return not e["name"].lower().startswith(base_name)


def owe(g, ids):
    """After a fight: every notable defeated foe gets a loot-owed entry (once)."""
    have = {x["foe"] for x in g.state.get("loot", [])}
    added = []
    for i in ids:
        e = g.entities.get(i)
        if not e or i in have or not notable_foe(e):
            continue
        t = e.get("token") or {}
        g.emit("loot.add", item={"foe": i, "name": e["name"], "cr": e.get("cr"), "map": t.get("map"), "x": t.get("x"),
                                 "y": t.get("y"), "time": g.state["time"], "status": "owed"})
        added.append(e["name"])
    if added:
        g.note(f"💰 DM: loot owed for {', '.join(added)}. Decide each before the party searches: "
               "`loot body <id> --items \"...\" [--coins ...]` or `loot none <id> --reason \"...\"` (`loot suggest` lists tier-fit magic).")
    return added


def owed(g):
    return [x for x in g.state.get("loot", []) if x.get("status") == "owed"]


def reminder(g):
    """DM-only nag while any loot is undecided (printed whenever time passes)."""
    left = owed(g)
    if left:
        g.note("💰 DM reminder: loot still undecided for " + ", ".join(f"{x['name']} (`{x['foe']}`)" for x in left) +
               " — `loot body` / `loot none`.")


def build_items(g, spec, override=None):
    """'Longsword +1; 2x Potion of Healing; Ledger=a merchant's ledger' -> item dicts for a container (tier cap checked)."""
    out = []
    for part in [p.strip() for p in re.split(r"[;\n]", spec or "") if p.strip()]:
        qty = 1
        m = re.match(r"^(\d+)\s*[x×]\s*(.+)$", part)
        if m:
            qty, part = int(m.group(1)), m.group(2).strip()
        name, _, custom = part.partition("=")
        name = name.strip()
        item = M.resolve_item(g, name)
        if not item:
            if not custom.strip():
                sug = srd.suggest("magic_items", name) + srd.suggest("gear", name) + srd.suggest("weapons", name)
                raise RuleError(f"'{name}' isn't an SRD item" + (f" (did you mean: {', '.join(sug[:5])}?)" if sug else "") +
                                ". For a mundane oddity write it as Name=description.")
            item = {"name": name, "kind": "gear", "custom": True, "description": custom.strip(), "value_cp": 0}
        if item.get("needs_base"):
            raise RuleError(f"{item['name']} can be {item['needs_base']} — name the base item, e.g. \"{item['name']} (Longsword)\".")
        if item.get("magic"):
            M.check_magic_allowed(g, item, override)
            item = {**item, "identified": False}
        out.append({**item, "qty": qty, "equipped": False, "attuned": False})
    return out


def make_cache(g, map_id, x, y, name, items, coins_cp=0, lock_dc=None, text="", box_id=None, source="loot"):
    """A sealed container whose contents stay off the table until a character opens it (`loot open`).
    A sealed cache already on that tile takes the new things too."""
    m = g.state["maps"].get(map_id)
    if not m:
        raise RuleError(f"No map '{map_id}'.")
    if not (0 <= x < m["w"] and 0 <= y < m["h"]):
        raise RuleError(f"({x},{y}) is off the {m['name']} map.")
    boxes = [dict(c) for c in m.get("containers", [])]
    box = next((c for c in boxes if (c["x"], c["y"]) == (x, y)), None)
    if box and not box.get("sealed"):
        raise RuleError(f"There's already an open container at ({x},{y}): {box['name']} (`{box['id']}`). Use `item stash`, "
                        "or put the cache on another tile.")
    if not box:
        taken = {c["id"] for mm in g.state["maps"].values() for c in mm.get("containers", [])}
        n = 1
        while f"box-{n}" in taken:  # unique across every map, so `coins --from box-N` can't pick the wrong one
            n += 1
        box = {"id": box_id or f"box-{n}", "x": x, "y": y, "name": name, "text": text or "", "sealed": True}
        if any(c["id"] == box["id"] for c in boxes):
            raise RuleError(f"Container id '{box['id']}' is already used on {m['name']}.")
        if lock_dc:
            box["lock_dc"] = int(lock_dc)
        boxes.append(box)
    if coins_cp:
        box["coins_cp"] = box.get("coins_cp", 0) + coins_cp
    boxes = [box if c["id"] == box["id"] else c for c in boxes]
    floor = [dict(f) for f in m.get("floor", [])]
    for it in items:
        n = 1
        while any(f["id"] == f"floor-{n}" for f in floor):
            n += 1
        floor.append({"id": f"floor-{n}", "x": x, "y": y, "item": {**it, "source": f"{source}: {name}"}, "note": f"in {box['name']}",
                      "in": box["id"]})
    g.emit("map.set", id=map_id, set={"containers": boxes, "floor": floor})
    return box


def sealed_box(m, box_id):
    return next((c for c in m.get("containers", []) if c["id"] == box_id and c.get("sealed")), None)


def open_cache(g, e, box_id, unlocked=None):
    t = e.get("token")
    if not t:
        raise RuleError(f"{e['name']} isn't on a map.")
    m = g.state["maps"][t["map"]]
    box = next((c for c in m.get("containers", []) if c["id"] == box_id), None)
    if not box:
        raise RuleError(f"No container '{box_id}' on {m['name']}. Containers: " +
                        (", ".join(f"{c['id']} {c['name']} at ({c['x']},{c['y']})" for c in m.get("containers", [])) or "none"))
    if not box.get("sealed"):
        raise RuleError(f"The {box['name']} is already open.")
    if max(abs(box["x"] - t["x"]), abs(box["y"] - t["y"])) > 1:
        raise RuleError(f"{e['name']} must be in or next to square ({box['x']},{box['y']}) to open the {box['name']}.")
    if box.get("lock_dc") and not unlocked:
        raise RuleError(f"The {box['name']} is locked (DC {box['lock_dc']}). Beat the lock first (a Dexterity check with "
                        f"Thieves' Tools, a Strength (Athletics) check to force it, or its key), then "
                        f"`loot open {e['id']} {box['id']} --unlocked \"how\"`.")
    if M.combat(g):
        ec = M.economy(g, e["id"])
        if ec.get("object_used"):
            raise RuleError(f"{e['name']} has already used their free object interaction this turn.")
        M.set_economy(g, e["id"], object_used=True)
    opened = {k: v for k, v in box.items() if k not in ("sealed", "lock_dc")}
    opened["opened_by"] = e["id"]
    g.emit("map.set", id=m["id"], set={"containers": [opened if c["id"] == box["id"] else c for c in m.get("containers", [])]})
    inside = [f for f in m.get("floor", []) if f.get("in") == box["id"]]
    what = [f"{f['item'].get('qty', 1)}× {item_display_name(f['item'])}" for f in inside]
    if box.get("coins_cp"):
        what.append(M.fmt_cp(box["coins_cp"]))
    g.say(f"🧰 {e['name']} opens {M.the(box['name'])}" + (f" ({unlocked})" if unlocked else "") + ": " +
          (", ".join(what) if what else "it's empty") + ".", kind="item", who=e["id"])
    if inside or box.get("coins_cp"):
        g.note(f"  take with `item pickup {e['id']} <floor-id>` ({', '.join(f['id'] for f in inside)})"
               + (f" and `coins {e['id']} <amount> --from {box['id']}`" if box.get("coins_cp") else ""))


def suggest(g, rarity=None, kind=None, n=40):
    """SRD magic items the party's tier allows (DM aid for deciding loot)."""
    cap = TIER_MAX_RARITY[tier(g.party_level())]
    allowed = RARITY_ORDER[:RARITY_ORDER.index(cap) + 1]
    want = [rarity] if rarity else allowed
    rows = []
    for v in srd.data()["magic_items"].values():
        rs = [r for r in v["rarities"] if r in want]
        if not rs or (kind and kind.lower() not in v["meta"].lower()):
            continue
        rows.append((RARITY_ORDER.index(rs[-1]), v["name"], rs[-1], v["meta"]))
    rows.sort()
    return cap, [f"{r[2]:<9} {r[1]} — {r[3]}" for r in rows[:n]], len(rows)


def companion_kit(g, e):
    """DM-only: everything a party companion run by the DM could use this turn, so nothing sits forgotten."""
    d = derive(e)
    parts = []
    used = e.get("slots_used", {})
    slots = [f"L{k} {v - used.get(str(k), 0)}/{v}" for k, v in d["slots"].items() if v]
    if slots:
        parts.append("slots " + " ".join(slots))
    feats = [f"{n} {r['max'] - r['used']}/{r['max']}" for n, r in resources(e).items() if r["max"] - r["used"] > 0]
    if feats:
        parts.append("features " + ", ".join(feats))
    cons, items = [], []
    for it in e.get("inventory", []):
        if CONSUMABLE_RE.search(it["name"]):
            cons.append(f"{it['name']} ×{it.get('qty', 1)} (`{it['id']}`)")
        spec = M.charged_spec(it) if it.get("magic") else None
        if spec and spec.get("at_will") and (it.get("attuned") or not spec["attunement"]):
            items.append(f"{it['name']} ({spec['spell'].replace('-', ' ').title()} at will: `cast --item {it['id']}`)")
        elif spec and not spec.get("at_will"):
            left = it.get("charges", spec["max"])
            if left:
                items.append(f"{it['name']} {left}/{spec['max']} charges (`cast --item {it['id']}`)")
        if "flame tongue" in it["name"].lower() and it.get("equipped") and not it.get("lit"):
            items.append(f"{it['name']} unlit (bonus action: `item light`)")
    if cons:
        parts.append("consumables " + ", ".join(cons))
    if items:
        parts.append("items " + "; ".join(items))
    if e["hp"] <= e["hp_max"] // 2 and any("healing" in c.lower() for c in cons):
        parts.append(f"⚠ bloodied ({e['hp']}/{e['hp_max']}) with healing in the pack")
    if parts:
        g.note(f"🧭 DM — {e['name']}'s whole kit this turn: " + " · ".join(parts))
