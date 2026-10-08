"""Spell walls standing on a map (Wall of Fire).

A wall is a run of squares (a straight line up to its length, or a ring) plus the squares within 10 ft of its
burning side. It is drawn on the table the moment it is cast, blocks sight while it stands (opaque), burns anyone
who ends a turn on its hot side or inside it, burns anyone who enters it (once per turn), and is gone the moment
its caster's Concentration ends. rules/spells: Wall of Fire.
"""
from . import maps
from .core import RuleError

SIDES = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0),
         "northeast": (1, -1), "northwest": (-1, -1), "southeast": (1, 1), "southwest": (-1, 1)}

# spell slug -> how its wall behaves (length in feet, ring diameter in feet, damage per base level, type)
PROFILES = {
    "wall-of-fire": {"length": 60, "ring": 20, "dice": 5, "die": 8, "base": 4, "type": "fire", "reach": 10,
                     "opaque": True},
}


def profile(slug):
    p = PROFILES.get(slug)
    if not p:
        raise RuleError(f"The engine draws walls for: {', '.join(PROFILES)}.")
    return p


def xy(text):
    try:
        x, y = (int(v) for v in str(text).split(","))
    except ValueError:
        raise RuleError(f"'{text}': a square is x,y")
    return x, y


def line(m, ends, p):
    pts = [xy(t) for t in str(ends).split()]
    if len(pts) != 2:
        raise RuleError('--wall "x,y x,y": the two ends of the wall')
    cells = maps.line_cells(*pts[0], *pts[1])
    if len(cells) * 5 > p["length"]:
        raise RuleError(f"That wall is {len(cells) * 5} ft long; it can be at most {p['length']} ft "
                        f"({p['length'] // 5} squares).")
    for c in cells:
        if not (0 <= c[0] < m["w"] and 0 <= c[1] < m["h"]):
            raise RuleError(f"({c[0]},{c[1]}) is off the map.")
        if maps.move_cost(m, *c) is None:
            raise RuleError(f"({c[0]},{c[1]}) is a wall or solid piece: Wall of Fire stands on a solid surface, "
                            f"not inside one. Pick ends that run along open ground.")
    return cells


def ring(m, center, p):
    cx, cy = xy(center)
    r = p["ring"] // 10  # a 20-ft diameter ring: the squares 2 out from its centre
    cells = [(x, y) for x in range(cx - r, cx + r + 1) for y in range(cy - r, cy + r + 1)
             if max(abs(x - cx), abs(y - cy)) == r and 0 <= x < m["w"] and 0 <= y < m["h"]]
    return cells, (cx, cy)


def hot_cells(cells, side, p, center=None):
    """Squares within the spell's reach of the burning side (a ring burns inside or outside)."""
    reach = p["reach"] // 5
    wall = set(cells)
    out = set()
    if center:
        cx, cy = center
        r = p["ring"] // 10
        if side not in ("inside", "outside"):
            raise RuleError("--hot inside|outside for a ring")
        for x in range(cx - r - reach, cx + r + reach + 1):
            for y in range(cy - r - reach, cy + r + reach + 1):
                d = max(abs(x - cx), abs(y - cy))
                if (side == "inside" and d < r) or (side == "outside" and r < d <= r + reach):
                    out.add((x, y))
    else:
        if side not in SIDES:
            raise RuleError(f"--hot {'|'.join(SIDES)}: the side of the wall that burns")
        sx, sy = SIDES[side]
        (ax, ay), (bx, by) = cells[0], cells[-1]
        dx, dy = bx - ax, by - ay
        face = dx * sy - dy * sx          # which way the burning side lies across the wall's line
        if (dx or dy) and face == 0:
            raise RuleError(f"The {side} side runs along the wall, not across it: pick a side facing away from its line.")
        for (x, y) in cells:
            for px in range(x - reach, x + reach + 1):
                for py in range(y - reach, y + reach + 1):
                    # every square within reach that isn't on the cool side burns: the face, and round the ends
                    across = (dx * (py - ay) - dy * (px - ax)) if (dx or dy) else ((px - x) * sx + (py - y) * sy)
                    if across * (face if (dx or dy) else 1) >= 0:
                        out.add((px, py))
    return sorted(out - wall)


def walls(m):
    return m.get("spell_walls", [])


def wall_squares(m, all_walls=False):
    return {tuple(c) for w in walls(m) if all_walls or w.get("opaque") for c in w["cells"]}


def creatures_on(g, map_id, cells):
    from .mechanics import alive, token_pos
    sq = set(map(tuple, cells))
    return [e for e in g.entities.values() if e.get("token") and e["token"].get("map") == map_id and alive(e)
            and not e.get("offstage") and token_pos(e) in sq]


def add(g, caster, spell, map_id, cells, hot, side, level):
    p = profile(spell["slug"])
    m = g.state["maps"][map_id]
    n = 1
    while any(w["id"] == f"wall-{n}" for w in walls(m)):
        n += 1
    w = {"id": f"wall-{n}", "spell": spell["slug"], "name": spell["name"], "caster": caster["id"],
         "cells": [list(c) for c in cells], "hot": [list(c) for c in hot], "side": side,
         "dice": f"{p['dice'] + max(0, level - p['base'])}d{p['die']}", "type": p["type"], "opaque": p["opaque"]}
    g.emit("map.set", id=map_id, set={"spell_walls": walls(m) + [w]})
    g.say(f"🔥 {spell['name']} roars up on {m['name']}: {len(cells) * 5} ft of {p['type']}, its {side} side burning "
          f"({w['dice']} {p['type']} to anyone ending a turn within {p['reach']} ft of it or inside it).",
          kind="spell", map=map_id, cells=w["cells"])
    return w


def burn(g, e, w, why):
    from .mechanics import apply_damage
    r = g.roll(w["dice"], f"{w['name']} ({why})", e["id"])
    g.say(f"🔥 {e['name']} {why} and takes {r['total']} {w['type']} damage from {w['name']}.", kind="damage", who=e["id"])
    apply_damage(g, g.get(e["id"]), [[r["total"], w["type"]]], source=w["name"], attacker=g.get(w["caster"]))


def end_turn(g, e):
    """A creature that ends its turn inside the wall or within reach of its burning side takes the damage."""
    from .mechanics import alive, token_pos
    if not e.get("token") or not alive(e):
        return
    m = g.state["maps"].get(e["token"]["map"])
    if not m:
        return
    pos = token_pos(e)
    for w in walls(m):
        if list(pos) in w["cells"]:
            burn(g, e, w, "ends its turn inside the wall")
        elif list(pos) in w["hot"]:
            burn(g, e, w, "ends its turn beside the wall's burning side")
        e = g.get(e["id"])
        if not alive(e):
            return


def entered(g, e, path):
    """Entering the wall burns, the first time on a turn. Returns the index in path where the creature
    fell if the fire killed or dropped it, else None."""
    from .mechanics import alive
    m = g.state["maps"].get(e["token"]["map"]) if e.get("token") else None
    if not m or not walls(m):
        return None
    c = g.state.get("combat") or {}
    stamp = [c.get("round", 0), e.get("turns_started", 0)]
    for i, sq in enumerate(path[1:], 1):
        for w in walls(m):
            if list(sq) not in w["cells"]:
                continue
            seen = dict(e.get("walls_entered") or {})
            if seen.get(w["id"]) == stamp:
                continue
            seen[w["id"]] = stamp
            g.set(e, walls_entered=seen)
            burn(g, e, w, "passes into the wall")
            e = g.get(e["id"])
            if not alive(e) or e.get("hp", 1) <= 0:
                return i
    return None


def remove_for(g, caster_id, spell_slug):
    for mid, m in g.state["maps"].items():
        gone = [w for w in walls(m) if w["caster"] == caster_id and w["spell"] == spell_slug]
        if gone:
            g.emit("map.set", id=mid, set={"spell_walls": [w for w in walls(m) if w not in gone]})
            for w in gone:
                g.say(f"🔥 {w['name']} gutters out and is gone from {m['name']}.", kind="spell", map=mid)
