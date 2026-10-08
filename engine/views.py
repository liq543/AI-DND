"""Projections of game state.

player_view(): exactly what the players may see — no hidden creatures, no secret rolls, no enemy
HP numbers or stat blocks, no undiscovered map features. The live viewer only ever receives this.
write_snapshots(): human-readable state.md + party/<id>.md regenerated after every command.
"""
from pathlib import Path
import re as _re

from . import art, itemart, render, srd, effects
from .core import derive, fmt_time, item_display_name, item_known, journal_cat, level, pb, resources, condition_names
from .mechanics import coins_total_cp, combat, current_id, economy, fmt_cp, xp_threshold


def status_band(e):
    if e.get('dead'):
        return 'Dead'
    if any(c['name']=='unconscious' for c in e.get('conditions',[])):
        return 'Unconscious'
    if e.get("hp", 1) <= 0:
        return "Down"
    frac = e["hp"] / max(1, e.get("hp_max", 1))
    return "Unhurt" if frac >= 1 else "Hurt" if frac > .5 else "Bloodied" if frac > .25 else "Near death"


_TEXT_CACHE = {}


def _section_text(path, heading_re):
    """Body of the markdown section whose heading matches heading_re (up to the next heading of same/higher level)."""
    import re as _re
    key = (str(path), heading_re)
    if key in _TEXT_CACHE:
        return _TEXT_CACHE[key]
    text = Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""
    m = _re.search(r"^(#{2,5}) \**" + heading_re + r"\**\s*$", text, _re.M | _re.I)
    body = ""
    if m:
        lvl = len(m.group(1))
        rest = text[m.end():]
        stop = _re.search(r"^#{2," + str(lvl) + r"} ", rest, _re.M)
        body = rest[:stop.start()] if stop else rest
    _TEXT_CACHE[key] = body.strip()
    return _TEXT_CACHE[key]


def features_of(e):
    """Every class/subclass feature, feat and species trait the character has, with its SRD text."""
    import re as _re
    rules = Path(__file__).resolve().parent.parent / "rules"
    out = []
    skip = {"Ability Score Improvement", "Epic Boon", "Subclass feature"}
    for cls, lv in e.get("classes", {}).items():
        c = srd.find("classes", cls)
        if not c:
            continue
        cfile = rules / "classes" / f"{srd.slug(cls)}.md"
        sub = e.get("subclasses", {}).get(cls)
        for l, name in c["features"]:
            if l > lv or name in skip or name.endswith("Subclass"):
                continue
            out.append({"name": name, "source": f"{cls} {l}", "level": l,
                        "text": _section_text(cfile, rf"Level {l}: {_re.escape(name)}(?: \(.*\))?")})
        if sub and sub in c["subclasses"]:
            for l, name in c["subclasses"][sub]["features"]:
                if l > lv:
                    continue
                out.append({"name": name, "source": f"{sub} {l}", "level": l,
                            "text": _section_text(cfile, rf"Level {l}: {_re.escape(name)}")})
    for f in e.get("feats", []):
        base = _re.sub(r"\s*\(.*\)", "", f["name"])
        out.append({"name": f["name"], "source": f.get("source", "feat"), "level": 0,
                    "text": _section_text(rules / "core" / "05-feats.md", _re.escape(base))})
    origins = (rules / "core" / "04-character-origins.md").read_text(encoding="utf-8")
    for t in e.get("species_traits", []):
        m = _re.search(r"\*\*" + _re.escape(t) + r"\.\*\*\s*(.+?)(?=\n\n\*\*[A-Z][^*]+\.\*\*|\n#{2,4} |\Z)", origins, _re.S)
        out.append({"name": t, "source": e.get("species", "species"), "level": 0, "text": m.group(1).strip() if m else ""})
    return out


def player_item(it):
    """An inventory item as the players know it: unidentified magic keeps its secrets (name, rarity, rules)."""
    known = item_known(it)
    out = {k: it.get(k) for k in ("id", "qty", "equipped", "attuned", "kind", "note", "source", "magic", "lit", "category", "base_name")}
    out.update({"name": it["name"] if known else item_display_name(dict(it, alias=None)), "alias": it.get("alias"),
                "rarity": it.get("rarity") if known else None, "identified": known, "art": itemart.item_art_version(it),
                "custom_art": bool(it.get("art"))})
    return out


def item_info(g, it, owner=None):
    """Everything the item card shows, respecting identification: display name, what it is, stats, rules text."""
    known = item_known(it)
    kind = it.get("kind", "gear")
    stats, base = [], it.get("base_name") or (it["name"] if kind in ("weapon", "armor") else None)
    if kind == "weapon" and base:
        w = srd.find("weapons", base) or {}
        bonus = it.get("magic_bonus", 0) if known else 0
        stats = [("Damage", f"{w.get('damage', '?')}{f' +{bonus}' if bonus else ''} {w.get('type', '')}".strip()),
                 ("Properties", ", ".join(p.title() for p in w.get("properties", [])) or "—"),
                 ("Mastery", (w.get("mastery") or "—").title())]
        if w.get("range"):
            stats.insert(1, ("Range", f"{w['range'][0]}/{w['range'][1]} ft"))
        if bonus:
            stats.insert(0, ("Attack", f"+{bonus} magic bonus"))
    elif kind == "armor" and base:
        a = srd.find("armor", base) or {}
        ac = f"{a.get('base', '?')}{' + Dex' if a.get('adds_dex') else ''}{' (max 2)' if a.get('dex_max') == 2 else ''}"
        if known and it.get("magic_bonus"):
            ac += f" +{it['magic_bonus']}"
        stats = [("Armor Class", ac), ("Category", (a.get("category") or "").title())]
    rules = ""
    if known and it.get("magic") and it.get("ref"):
        f = srd.RULES / "magic-items" / f"{it['ref']}.md"
        if f.exists():
            rules = _re.sub(r"^# .*\n+(\*[^\n]*\*\s*\n)?", "", f.read_text(encoding="utf-8")).strip()
    elif known and it.get("custom"):
        rules = it.get("description") or ""
    meta = (it.get("meta") or "").strip("* ") if known else ""
    subtitle = meta or " · ".join(x for x in [
        (base if base and base != it.get("alias") and base != item_display_name(it) else None),
        {"weapon": "Weapon", "armor": "Armor", "consumable": "Consumable", "gear": "Gear", "magic": "Wondrous item"}.get(kind, kind.title()),
        (it.get("rarity") if known and it.get("rarity") else None)] if x)
    return {"id": it.get("id"), "owner": owner, "name": item_display_name(it), "true_name": it["name"] if known else None,
            "subtitle": subtitle, "kind": kind, "base": base, "rarity": it.get("rarity") if known else None,
            "magic": bool(it.get("magic")), "identified": known, "attunement": bool(it.get("needs_attunement")) if known else None,
            "note": it.get("note") or "", "stats": stats, "rules_md": rules, "qty": it.get("qty", 1),
            "equipped": it.get("equipped"), "attuned": it.get("attuned"), "lit": it.get("lit"), "source": it.get("source", "")}


def pc_view(g, e):
    d = derive(e)
    slots = {str(k): {"max": v, "left": v - e.get("slots_used", {}).get(str(k), 0)} for k, v in d["slots"].items()}
    lv = d["level"]
    return {
        "id": e["id"], "kind": "pc", "name": e["name"], "player": e.get("player"), "species": e.get("species"),
        "background": e.get("background"), "classes": e["classes"], "subclasses": e.get("subclasses", {}), "level": lv,
        "hp": e["hp"], "hp_max": d["hp_max"], "temp_hp": e.get("temp_hp", 0), "ac": d["ac"], "ac_why": d["ac_why"],
        "speed": d["speed"], "init": d["init"], "pb": d["pb"], "abilities": d["abilities"], "mods": d["mods"],
        "saves": d["saves"], "skills": d["skills"], "passive_perception": d["passive_perception"],
        "save_profs": e.get("save_profs", []), "skill_profs": e.get("skills", []), "expertise": e.get("expertise", []),
        "conditions": sorted(condition_names(e)), "exhaustion": e.get("exhaustion", 0),
        "effects": [{k: f.get(k) for k in ("name", "spell", "since", "expires_at", "turn_boundary", "turn_owner")}
                    for f in effects.active(e) if f.get("managed_spell")],
        "death": e.get("death"), "dead": e.get("dead", False), "concentration": (e.get("concentration") or {}).get("spell_name"),
        "slots": slots, "pact": ({**d["pact"], "left": d["pact"]["count"] - e.get("pact_used", 0)} if d["pact"] else None),
        "spellcasting": d["spellcasting"], "resources": d["resources"],
        "attacks": [dict(a, name=item_display_name(it)) if (it := next((i for i in e.get("inventory", []) if i["id"] == a.get("item")), None)) else a
                    for a in d["attacks"]],
        "spells": e.get("spells", {}), "granted_spells": e.get("granted_spells", []),
        "xp": e.get("xp", 0), "xp_next": xp_threshold(lv + 1) if lv < 20 else None,
        "coins": e.get("coins", {}), "wealth": fmt_cp(coins_total_cp(e)), "inspiration": e.get("inspiration", False),
        "inventory": [player_item(it) for it in e.get("inventory", [])],
        "feats": [f["name"] for f in e.get("feats", [])], "languages": e.get("languages", []),
        "features": features_of(e), "tools": e.get("tools", []), "choices": e.get("choices", {}),
        "token": e.get("token"), "portrait": e.get("portrait"), "art": art.art_version(e), "hit_dice": {c: {"max": l, "left": l - e.get("hd_spent", {}).get(c, 0)} for c, l in e["classes"].items()},
    }


def npc_view(g, e):
    ally = e.get("side") == "ally"
    v = {"id": e["id"], "kind": e["kind"], "name": e["name"], "side": e.get("side", "enemy"), "type": e.get("type"),
         "size": e.get("size"), "status": status_band(e), "conditions": [c["name"] for c in e.get("conditions", [])],
         "token": e.get("token"), "dead": bool(e.get("dead")), "portrait": e.get("portrait"),
         "art": art.art_version(e)}
    if ally:
        v.update({"hp": e["hp"], "hp_max": e["hp_max"], "ac": derive(e)["ac"]})
    return v


def creature_info(g, e):
    """What the party knows about a non-PC: public facts plus what the signed log has revealed in play."""
    import re as _re
    s = g.state
    ally = e.get("side") == "ally"
    name = e["name"]
    info = {"id": e["id"], "name": name, "side": e.get("side", "enemy"), "size": e.get("size"), "type": e.get("type"), "art": art.art_version(e),
            "status": status_band(e), "dead": bool(e.get("dead")),
            "conditions": [{"name": c["name"], "source": c.get("source"), "until": c.get("until")} for c in e.get("conditions", [])],
            "lore": e.get("lore", []), "full": ally,
            "appearance": e.get("appearance") or (e.get("bio") or {}).get("appearance") or "", "alignment": e.get("alignment") or ""}
    feed = [f.get("text", "") for f in s["feed"] if f.get("kind") != "dm"]
    ac, attacks, saves, dmg, hits, misses = None, [], [], 0, 0, 0
    for t in feed:
        m = _re.search(r"attacks " + _re.escape(name) + r" with .*?= (\d+) vs AC (\d+)(?: \([^)]*?cover \+(\d+)\))? → (\w+)", t)
        if m:
            ac = int(m.group(2)) - int(m.group(3) or 0)  # the creature's own AC, without the cover it had that time
            if m.group(4).startswith("MISS"):
                misses += 1
            else:
                hits += 1
        m = _re.match(r"⚔ " + _re.escape(name) + r" attacks .*? with (.+?):", t)
        if m and m.group(1) not in attacks:
            attacks.append(m.group(1))
        m = _re.match(_re.escape(name) + r" — (\w+) save DC (\d+): .*?= (-?\d+) → (\w+)", t)
        if m:
            saves.append(f"{m.group(1)} save DC {m.group(2)}: {m.group(3)} ({m.group(4).lower()})")
        m = _re.match(r"💥 " + _re.escape(name) + r" takes (\d+) ", t)
        if m:
            dmg += int(m.group(1))
    info.update({"ac_known": ac, "attacks_seen": attacks, "saves_seen": saves[-6:], "damage_dealt_to": dmg,
                 "hits_taken": hits, "misses_against": misses})
    if ally:
        d = derive(e)
        info.update({"hp": e["hp"], "hp_max": e["hp_max"], "ac": d["ac"], "speed": e.get("speed"),
                     "actions": [{"name": a["name"], "text": a.get("text", "")} for a in e.get("actions", [])]})
    return info


# The map hierarchy, top to bottom: the region (the world map), a town or area (all its quarters on one sheet), a section
# (one quarter, a street, a village green) and an interior (a building's rooms). Each map names its `parent` one level up.
LEVELS = ("region", "area", "section", "interior")


def map_level(m):
    """A map's place in the hierarchy: set with `map set <id> --kv level=...`, else guessed from the kind of map."""
    if m.get("level") in LEVELS:
        return m["level"]
    return {"region": "region", "interior": "interior"}.get(m.get("kind"), "section")


def map_ancestors(s, mid):
    """The chain of parents above a map, nearest first (cycles are refused when set, but guarded here too)."""
    out, seen = [], {mid}
    p = s["maps"].get(mid, {}).get("parent")
    while p and p in s["maps"] and p not in seen:
        out.append(p)
        seen.add(p)
        p = s["maps"][p].get("parent")
    return out


def visible_maps(g):
    """Maps the players can look at now: the one on the table, every map a PC stands on (split party), every map above
    those in the hierarchy (the quarter, the town, the region they are in), the known places one level down, and every
    map connected through `map link` (other floors, the stair down, the rooms beyond them) that the party knows."""
    s = g.state
    here = {s["view"].get("map")} | {e["token"]["map"] for e in s["entities"].values()
                                      if e["kind"] == "pc" and e.get("token") and not e.get("dead") and not e.get("departed")}
    here.discard(None)
    vis = set(here) | {mid for mid, m in s["maps"].items() if m.get("world")}   # the world map is always open
    for mid in list(here):
        vis.update(map_ancestors(s, mid))                     # where you are sits inside these, so they're open too
    todo = list(here)
    while todo:   # the whole connected place, however many links away
        for other in s["maps"].get(todo.pop(), {}).get("links", []):
            if other not in vis and s["maps"].get(other, {}).get("shown"):
                vis.add(other)
                todo.append(other)
    above = {a for h in here for a in map_ancestors(s, h)}
    kids = {mid for mid, m in s["maps"].items() if m.get("parent") in here and m.get("shown")}
    return {mid for mid in vis | kids if s["maps"].get(mid, {}).get("shown") or mid in above}


def browsable_maps(g):
    """Maps the players can open by clicking a place on a map they can see: a known map anchored to a town, site or poi
    (`map set <child> --kv anchor=<place-id>`) inside a visible map, and so on down. These ride along without a tab."""
    s = g.state
    vis = visible_maps(g)
    out, todo = set(), list(vis)
    while todo:
        mid = todo.pop()
        for cid, c in s["maps"].items():
            if c.get("parent") == mid and c.get("anchor") and c.get("shown") and cid not in vis and cid not in out:
                out.add(cid)
                todo.append(cid)
    return out


def openable_maps(g):
    """Every map the players may open: the tabs plus the known places reached by clicking through."""
    return visible_maps(g) | browsable_maps(g)


def map_order(s, mids):
    """Tab order: the hierarchy walked top-down (region, then each town, its quarters, their interiors), so every map
    sits after its parent; maps outside the hierarchy follow in their own order."""
    mids = list(mids)
    kids = {}
    for mid in mids:
        p = s["maps"][mid].get("parent")
        kids.setdefault(p if p in mids else None, []).append(mid)
    rank = {lv: i for i, lv in enumerate(LEVELS)}
    out = []

    def walk(mid):
        out.append(mid)
        for k in kids.get(mid, []):
            walk(k)
    for root in sorted(kids.get(None, []), key=lambda m: (not s["maps"][m].get("world"), rank[map_level(s["maps"][m])])):
        walk(root)
    return out


def seen_by_players(g, e):
    """Have the players ever seen this creature? (revealed at some point, or it spoke, moved or acted in the public log.)
    A creature that has left the table keeps its face in the log and the journal; one never seen stays a secret."""
    if not e:
        return False
    if _seen(g,e) or e.get("known"):
        return True
    # only lines the players witnessed: what it said, what was narrated about it, or its appearing on the table
    # (not moves or actions logged while it was hidden)
    return any(f.get("who") == e["id"] and f.get("kind") in ("speech", "narration", "creature")
               for f in g.state.get("feed", []))


def _seen(g, e):
    """Can the players see this creature where it stands right now?"""
    if not e or e.get("hidden"):
        return False
    t = e.get("token")
    if not t or e["kind"] == "pc" or e.get("side") == "ally":
        return True
    m = g.state["maps"].get(t.get("map"))
    if not m or not m.get("fog"):
        return True
    rv = m.get("revealed") or []
    return 0 <= t["y"] < len(rv) and 0 <= t['x'] < len(rv[t['y']]) and rv[t["y"]][t["x"]] == "1"


def _cell_seen(m, x, y):
    if not m.get("fog"):
        return True
    rv = m.get("revealed") or []
    return 0 <= y < len(rv) and 0 <= x < len(rv[y]) and rv[y][x] == "1"


def animation_cues(g, feed):
    """What the live table animates: the structured side of recent public feed lines (moves, attacks, damage, turns,
    DM effects), filtered so an animation never shows a hidden creature or a position under fog."""
    s = g.state
    ent = s["entities"]
    out = []
    for f in feed[-80:]:
        k = f.get("kind")
        c = {"seq": f.get("seq"), "k": k}
        who = ent.get(f.get("who")) if f.get("who") else None
        if k == "move" and who:
            m = s["maps"].get(f.get("map"))
            path = f.get("path") or ([f["to"]] if f.get("to") else None)
            if not m or not path or not _seen(g, who):
                continue
            if who["kind"] != "pc" and who.get("side") != "ally":
                path = [p for p in path if _cell_seen(m, *p)]
                if not path:
                    continue
            c.update(who=who["id"], map=f["map"], path=path, placed=bool(f.get("placed")), forced=bool(f.get("forced")),
                     group=f.get("group"))
        elif k == "attack" and f.get("target"):
            tgt = ent.get(f["target"])
            if not _seen(g, tgt):
                continue
            c.update(who=who["id"] if _seen(g, who) else None, target=tgt["id"], hit=f.get("hit"), crit=f.get("crit"),
                     ranged=f.get("ranged"), dtype=f.get("dtype"), spell=f.get("spell"), roll=f.get("roll"), nat=f.get("nat"))
        elif k == "damage" and "amount" in f:
            if not _seen(g, who):
                continue
            c.update(who=who["id"], amount=f["amount"], dtype=f.get("dtype"), crit=f.get("crit"), down=f.get("down"), dead=f.get("dead"))
            if who["kind"] == "pc" or who.get("side") == "ally":
                c.update(hp=f.get("hp"), hp_max=f.get("hp_max"))
        elif k == "heal" and who and ("amount" in f or "temp" in f):
            if not _seen(g, who):
                continue
            c.update(who=who["id"], amount=f.get("amount"), temp=f.get("temp"))
            if who["kind"] == "pc" or who.get("side") == "ally":
                c.update(hp=f.get("hp"), hp_max=f.get("hp_max"))
        elif k == "condition" and f.get("cond"):
            if not _seen(g, who):
                continue
            c.update(who=who["id"], cond=f["cond"], on=f.get("on"))
        elif k == "spell" and f.get("spell"):
            tg = [t for t in f.get("targets", []) if _seen(g, ent.get(t))]
            if not _seen(g, who) and not tg:
                continue
            c.update(who=who["id"] if _seen(g, who) else None, spell=f["spell"], targets=tg, dtype=f.get("dtype"), fxkind=f.get("fxkind"))
        elif k == "roll" and (f.get("save") or f.get("death")):
            if not _seen(g, who):
                continue
            c.update(who=who["id"], save=f.get("save"), success=f.get("success"), death=f.get("death"), roll=f.get("roll"))
        elif k == "turn" and who:
            if not _seen(g, who):
                continue
            c.update(who=who["id"], round=f.get("round"))
        elif k == "combat" and f.get("phase"):
            c.update(phase=f["phase"], round=f.get("round"))
        elif k in ("speech", "narration"):
            # the story as it happens: a bubble over the speaker's token, a caption by the creature a line is about
            c.update(text=f.get("text", ""), speaker=f.get("speaker"), ts=f.get("ts"),
                     who=who["id"] if who and _seen(g, who) else None)
        elif k == "fx":
            pts = [f.get(p) for p in ("at", "from", "to") if isinstance(f.get(p), dict)]
            if any(not _seen(g, ent.get(p.get("id"))) for p in pts):
                continue
            coords=[f.get(p) for p in ('at','from','to') if isinstance(f.get(p),(list,tuple))]
            m=s['maps'].get(f.get('map') or s['view'].get('map'))
            if coords and (not m or any(len(p)!=2 or not _cell_seen(m,*p) for p in coords)):
                continue
            c.update({x: f[x] for x in ("fx", "at", "from", "to", "color", "radius", "label", "map", "fit") if x in f})
        else:
            continue
        out.append(c)
    return out


def player_view(g):
    s = g.state
    c = combat(g)
    visible = [e for e in s["entities"].values() if _seen(g,e)]
    order = []
    if c:
        for i, o in enumerate(c.get("order", [])):
            e = s["entities"].get(o["id"])
            if not _seen(g,e):
                continue
            order.append({"id": o["id"], "name": e["name"], "init": o["init"], "side": "pc" if e["kind"] == "pc" else e.get("side", "enemy"),
                          "current": i == c["turn"], "status": status_band(e) if e["kind"] != "pc" else f"{e['hp']}/{e['hp_max']}"})
    cur = current_id(g)
    econ = None
    if cur and cur in s["entities"] and (s["entities"][cur]["kind"] == "pc" or s["entities"][cur].get("side") == "ally"):
        ec = economy(g, cur)
        e = s["entities"][cur]
        sp = derive(e)["speed"]["walk"]
        econ = {"id": cur, "action": not ec.get("action_used"), "bonus": not ec.get("bonus_used"),
                "reaction": not ec.get("reaction_used"), "move_left": sp * (2 if ec.get("dashed") else 1) - ec.get("move_used", 0),
                "attacks_left": ec.get("attacks_left")}
    feed = [f for f in s["feed"] if f.get("kind") != "dm"][-1000:]
    rolls = [{k: r.get(k) for k in ("id", "who", "purpose", "expr", "mode", "crit", "total", "nat", "terms", "text", "seq")}
             for r in s["rolls"] if not r.get("hidden")][-60:]
    tabs = visible_maps(g)
    maps_known = {mid: {"id": mid, "name": m["name"], "kind": m["kind"], "w": m["w"], "h": m["h"], "world": bool(m.get("world")),
                        "level": map_level(m), "parent": m.get("parent"), "anchor": m.get("anchor"), "tab": mid in tabs,
                        "floor": [{"id": f["id"], "x": f["x"], "y": f["y"], "name": item_display_name(f["item"]), "qty": f["item"].get("qty", 1),
                                   "note": f.get("note", ""), "in": f.get("in"), "art": itemart.item_art_version(f["item"])}
                                  for f in m.get("floor", []) if not in_sealed(m, f)
                                  if not m.get("fog") or (m.get("revealed") and m["revealed"][f["y"]][f["x"]] == "1")],
                        # a sealed cache shows as a closed box: what's inside stays off the table until someone opens it
                        "containers": [{k: c.get(k) for k in ("id", "x", "y", "name", "text", "coins_cp", "sealed")
                                        if not (c.get("sealed") and k == "coins_cp")} for c in m.get("containers", [])
                                       if not m.get("fog") or (m.get("revealed") and m["revealed"][c["y"]][c["x"]] == "1")],
                        "pois": [{k: p.get(k) for k in ("id", "x", "y", "name", "journal")}
                                 for p in m.get("pois", []) + (m.get("settlements", []) if m.get("kind") == "region" else [])
                                 if p.get("id") and not p.get("hidden")
                                 and (not m.get("fog") or (m.get("revealed") and m["revealed"][p["y"]][p["x"]] == "1"))]}
                  for mid, m in ((mid, s["maps"][mid]) for mid in map_order(s, tabs | browsable_maps(g)))}
    return {
        "campaign": s["campaign"].get("title"), "session": s["session"], "time": fmt_time(s["time"]), "minutes": s["time"],
        "seq": s["seq"], "events": len(g.events), "head": g.events[-1]["hash"][:12] if g.events else "",
        "view": s["view"], "maps": maps_known,
        "party": [pc_view(g, e) for e in visible if e["kind"] == "pc"],
        "others": [npc_view(g, e) for e in visible if e["kind"] != "pc" and e.get("token", {}).get("map") == s["view"].get("map")],
        # creatures the players have met who have since left the table: their faces stay in the log and the journal
        "offstage": [{"id": e["id"], "name": e["name"], "side": e.get("side", "neutral"), "art": art.art_version(e)}
                     for e in s["entities"].values() if (e["kind"] != "pc" or e.get("departed")) and e.get("hidden") and seen_by_players(g, e)]
                  + [npc_view(g, e) for e in visible if e["kind"] != "pc" and e.get("side") == "ally" and e.get("token", {}).get("map") != s["view"].get("map")],
        "combat": {"round": c["round"], "order": order, "current": cur if cur and _seen(g,s['entities'].get(cur)) else None,
                   "economy": econ} if c else None,
        "requests": [{"id": r["id"], "who": r["who"], "name": s["entities"].get(r["who"], {}).get("name"), "label": r["label"]}
                     for r in s["requests"].values()],
        "feed": feed, "rolls": rolls, "roll_count": s["roll_count"], "cues": animation_cues(g, feed),
        # each entry carries its section (clue / place) and, for map objects, the name of the place it was seen
        "journal": [{**e, "cat": journal_cat(e),
                     **({"where": s["maps"].get(e["poi"]["map"], {}).get("name", e["poi"]["map"])} if e.get("poi") else {})}
                    for e in s.get("journal", [])],
        "lore": [{"id": e["id"], "name": e["name"], "facts": e.get("lore", [])} for e in s["entities"].values()
                 if e.get("lore") and not e.get("hidden")],
        "overrides": s["overrides"][-20:], "settings": {k: v for k, v in s["settings"].items() if k in ("player_rolls", "xp_mode", "difficulty", "xp_rate")},
        "assets": {k: {kk: v.get(kk) for kk in ("id", "name", "kind", "license", "credit", "source")} for k, v in s["assets"].items() if v.get("public")},
    }


def map_svg(g, map_id, mode="player", live=False):
    """live=True: for the viewer, where tokens show each creature's generated art (static snapshot files keep emblems)."""
    m = g.state["maps"][map_id]
    style = (g.state["view"].get("anim") or {}).get("tokens", "art")
    ents = []
    for e in g.state["entities"].values():
        if e.get("token", {}).get("map") != map_id:
            continue
        if mode == "player" and not _seen(g,e):
            continue
        ee = dict(e)
        if e.get("portrait") and e["portrait"] in g.state["assets"] and (mode!='player' or g.state['assets'][e['portrait']].get('public')):
            ee["portrait_href"] = f"/asset/{e['portrait']}"
        elif live and style == "art":
            ee["portrait_href"] = f"/api/art/face/{e['id']}.svg?v={art.art_version(e)}"
        ents.append(ee)
    party_pos = g.state["view"].get("party_pos") if m["kind"] == "region" else None
    return render.render_map(m, mode, ents, current_id(g), party_pos=party_pos, live=live)


# ------------------------------------------------------------ markdown snapshots

def sheet_md(g, e):
    d = derive(e)
    lines = [f"# {e['name']}", "",
             "> AUTO-GENERATED from the signed engine log — do not edit. Change things with `python -m engine ...`.", "",
             f"**Player:** {e.get('player')} · **{e['species']}** · **{' / '.join(f'{c} {l}' for c, l in e['classes'].items())}**"
             + (f" ({', '.join(e['subclasses'].values())})" if e.get("subclasses") else "") +
             f" · **Background:** {e['background']} · **XP:** {e.get('xp', 0)}", "",
             f"**HP** {e['hp']}/{d['hp_max']}" + (f" (+{e['temp_hp']} temp)" if e.get("temp_hp") else "") +
             f" · **AC** {d['ac']} ({d['ac_why']}) · **Speed** {d['speed']['walk']} ft · **Initiative** {d['init']:+d} · "
             f"**Proficiency** +{d['pb']} · **Passive Perception** {d['passive_perception']}", "",
             "| STR | DEX | CON | INT | WIS | CHA |", "|---|---|---|---|---|---|",
             "| " + " | ".join(f"{d['abilities'][a]} ({d['mods'][a]:+d})" for a in srd.ABILITIES) + " |", "",
             "**Saves:** " + ", ".join(f"{a.upper()} {d['saves'][a]:+d}{'*' if a in e['save_profs'] else ''}" for a in srd.ABILITIES),
             "", "**Skills:** " + ", ".join(f"{s.title()} {d['skills'][s]:+d}{'**' if s in e.get('expertise', []) else '*' if s in e['skills'] else ''}" for s in srd.SKILLS),
             "", f"**Conditions:** {', '.join(c['name'] for c in e.get('conditions', [])) or '—'} · **Exhaustion:** {e.get('exhaustion', 0)}"
             + (f" · **Concentrating on:** {e['concentration']['spell_name']}" if e.get("concentration") else ""), "",
             "## Attacks", "", "| Attack | To hit | Damage | Notes |", "|---|---|---|---|"]
    for a in d["attacks"]:
        lines.append(f"| {a['name']} | {a['bonus']:+d} | {a['damage']} {a['type']} | {'range ' + '/'.join(map(str, a['range'])) + ' ft' if a.get('range') else 'reach ' + str(a['reach']) + ' ft'}"
                     f"{', mastery ' + a['mastery'] if a.get('mastery') else ''} |")
    lines += ["", f"Attacks per Attack action: {d['attacks_per_action']}", ""]
    if any(f.get("managed_spell") for f in effects.active(e)):
        lines += ["**Active spell effects:** " + ", ".join(
            f["name"] + (f" (expires at minute {f['expires_at']:g})" if f.get("expires_at") is not None else "")
            for f in effects.active(e) if f.get("managed_spell")), ""]
    if d["spellcasting"]:
        lines += ["## Spellcasting", ""]
        for cls, sc in d["spellcasting"].items():
            lines.append(f"- **{cls}:** save DC {sc['dc']}, attack {sc['attack']:+d}, cantrips {sc['cantrips']}, prepared {sc['prepared']}, up to level {sc['max_level']}")
        if d["slots"]:
            lines.append("- **Slots:** " + ", ".join(f"L{k} {v - e.get('slots_used', {}).get(str(k), 0)}/{v}" for k, v in d["slots"].items()))
        if d["pact"]:
            lines.append(f"- **Pact slots:** {d['pact']['count'] - e.get('pact_used', 0)}/{d['pact']['count']} at level {d['pact']['level']}")
        sp = e.get("spells", {})
        lines.append(f"- **Cantrips:** {', '.join(sp.get('cantrips', [])) or '—'}")
        lines.append(f"- **Prepared:** {', '.join(sp.get('prepared', [])) or '—'}")
        if sp.get("spellbook"):
            lines.append(f"- **Spellbook:** {', '.join(sp['spellbook'])}")
        lines.append("")
    if e.get("granted_spells"):
        lines += ["**Granted spells:** " + ", ".join(f"{x['slug']} ({x['source']}{', free cast used' if x.get('free_used') else ''})" for x in e["granted_spells"]), ""]
    res = resources(e)
    if res:
        lines += ["## Limited features", ""] + [f"- **{n}:** {v['max'] - v['used']}/{v['max']}" for n, v in res.items()] + [""]
    lines += ["## Features & feats", "", ", ".join(f["name"] for f in e.get("feats", [])), "",
              f"Species traits: {', '.join(e.get('species_traits', []))}", "",
              "## Inventory", "", f"**Coins:** {fmt_cp(coins_total_cp(e))}", ""]
    for it in e.get("inventory", []):
        lines.append(f"- `{it['id']}` {it.get('qty', 1)}× " + (f"{it['alias']} ({it['name']})" if it.get("alias") else it["name"]) +
                     ("" if item_known(it) else f" (UNIDENTIFIED — players see \"{item_display_name(it)}\")") + (" (equipped)" if it.get("equipped") else "") +
                     (" (attuned)" if it.get("attuned") else "") + (f" — {it['rarity']}" if it.get("rarity") else "") + f" · _{it.get('source', '')}_" +
                     (f"\n  - {it['note']}" if it.get("note") else ""))
    lines += ["", f"Hit Point Dice: " + ", ".join(f"{c} d{srd.find('classes', c)['hit_die']} {l - e.get('hd_spent', {}).get(c, 0)}/{l}" for c, l in e["classes"].items()),
              f"Languages: {', '.join(e.get('languages', []))} · Tools: {', '.join(e.get('tools', []))} · Armor training: {', '.join(e.get('armor_training', [])) or 'none'}",
              "", "## HP history", ""] + [f"- Level {h['level']}: +{h['gain']} ({h['how']})" for h in e.get("hp_log", [])]
    return "\n".join(lines) + "\n"


def in_sealed(m, f):
    """True for an item inside a container nobody has opened yet (`loot cache` / `loot body`)."""
    return bool(f.get("in")) and any(c["id"] == f["in"] and c.get("sealed") for c in m.get("containers", []))


def state_md(g):
    s = g.state
    c = combat(g)
    lines = [f"# Current State — {s['campaign'].get('title', '')}", "",
             "> AUTO-GENERATED after every engine command. Narrative notes belong in npcs.md / locations.md / quests.md / log/.", "",
             f"**Session:** {s['session']} · **In-world time:** {fmt_time(s['time'])} · **Mode:** {'COMBAT round ' + str(c['round']) if c else 'exploration'}",
             f"**Current map:** {s['maps'].get(s['view'].get('map'), {}).get('name', '—')} (`{s['view'].get('map')}`) · **Events:** {len(g.events)} · **Log head:** `{g.events[-1]['hash'][:16] if g.events else ''}`",
             "**Settings:** " + ", ".join(f"{k}={v}" for k, v in s["settings"].items()) +
             (f" · **Party position (region):** {s['view'].get('party_pos')}" if s["view"].get("party_pos") else ""), "",
             "## Party", "", "| Character | Lvl | HP | AC | Conditions | Slots | Position |", "|---|---|---|---|---|---|---|"]
    for e in s["entities"].values():
        if e["kind"] != "pc":
            continue
        d = derive(e)
        slots = " ".join(f"L{k}:{v - e.get('slots_used', {}).get(str(k), 0)}/{v}" for k, v in d["slots"].items())
        pos = f"{e['token']['map']} ({e['token']['x']},{e['token']['y']})" if e.get("token") else "—"
        lines.append(f"| {e['name']} (`{e['id']}`) | {d['level']} | {e['hp']}/{d['hp_max']}{' +' + str(e['temp_hp']) if e.get('temp_hp') else ''} | {d['ac']} | "
                     f"{', '.join(c2['name'] for c2 in e.get('conditions', [])) or '—'}{' · exh ' + str(e['exhaustion']) if e.get('exhaustion') else ''}"
                     f"{' · DEAD' if e.get('dead') else ''} | {slots or '—'} | {pos} |")
    others = [e for e in s["entities"].values() if e["kind"] != "pc"]
    if others:
        lines += ["", "## Other creatures (DM view)", "", "| Creature | Side | HP | AC | Conditions | Position | Hidden |", "|---|---|---|---|---|---|---|"]
        for e in others:
            pos = f"{e['token']['map']} ({e['token']['x']},{e['token']['y']})" if e.get("token") else "—"
            lines.append(f"| {e['name']} (`{e['id']}`, {e.get('srd', 'custom')}) | {e.get('side')} | {e['hp']}/{e['hp_max']} | {derive(e)['ac']} | "
                         f"{', '.join(c2['name'] for c2 in e.get('conditions', [])) or '—'}{' · DEAD' if e.get('dead') else ''} | {pos} | {'yes' if e.get('hidden') else ''} |")
    agenda = [x for x in s.get("agenda", []) if x.get("status") in ("pending", "due")]
    if agenda:
        lines += ["", "## Agenda (scheduled by the engine; `agenda list`)", ""]
        for x in sorted(agenda, key=lambda x: x["due"]):
            pay = x.get("pay")
            lines.append(f"- `{x['id']}` {fmt_time(x['due'])} [{x['status']}{', secret' if x.get('secret') else ''}] {x['text']}"
                         + (f" ({'auto ' if x.get('auto') else ''}{pay if isinstance(pay, str) else fmt_cp(pay)} → {x['to']})" if pay else ""))
    owed = [x for x in s.get("loot", []) if x.get("status") == "owed"]
    if owed:
        lines += ["", "## ⚠ Loot owed (decide before the party searches: `loot body` / `loot none`)", ""]
        lines += [f"- `{x['foe']}` {x['name']} (CR {x.get('cr')}) at {x.get('map')} ({x.get('x')},{x.get('y')})" for x in owed]
    if c:
        lines += ["", f"## Initiative — round {c['round']}", ""]
        for i, o in enumerate(c["order"]):
            lines.append(f"{'➤' if i == c['turn'] else ' '} {o['init']:>2}  {s['entities'].get(o['id'], {}).get('name', o['id'])}")
    if s["maps"]:
        lines += ["", "## Maps (exact current contents — tokens and items stay where they were left)", ""]
        for mid in s["maps"]:
            if s["maps"][mid]["kind"] == "region":
                continue
            lines += [map_state_md(g, mid), ""]
    if s["requests"]:
        lines += ["", "## Pending player rolls", ""] + [f"- `{r['id']}` {r['who']}: {r['label']}" for r in s["requests"].values()]
    lines += ["", "## Recent events", ""] + [f"- {f['text']}" for f in s["feed"][-15:]]
    return "\n".join(lines) + "\n"


def map_state_md(g, mid):
    """Everything on a map right now: creatures (with position/status), items on the floor, doors, labels."""
    s = g.state
    m = s["maps"][mid]
    lines = [f"### {m['name']} (`{mid}`, {m['kind']} {m['w']}×{m['h']}, lighting {m.get('lighting', 'bright')})"]
    ents = [e for e in s["entities"].values() if e.get("token", {}).get("map") == mid]
    for e in sorted(ents, key=lambda e: (e["kind"] != "pc", e["name"])):
        t = e["token"]
        state = "DEAD" if e.get("dead") else f"{e['hp']}/{e['hp_max']} HP"
        conds = ", ".join(c["name"] for c in e.get("conditions", []))
        lines.append(f"- {e['name']} (`{e['id']}`, {e['kind'] if e['kind'] == 'pc' else e.get('side', 'enemy')}) at ({t['x']},{t['y']}) — {state}"
                     + (f" · {conds}" if conds else "") + (" · hidden" if e.get("hidden") else ""))
    boxes = {c["id"]: c for c in m.get("containers", [])}
    for c in m.get("containers", []):
        lines.append(f"- container `{c['id']}`: {c['name']} at ({c['x']},{c['y']})"
                     + (" · SEALED (contents hidden from players)" if c.get("sealed") else "")
                     + (f" · lock DC {c['lock_dc']}" if c.get("lock_dc") else "")
                     + (f" — coins: {fmt_cp(c['coins_cp'])}" if c.get("coins_cp") else ""))
    for f in m.get("floor", []):
        where = f"in {boxes[f['in']]['name']} (`{f['in']}`)" if f.get("in") in boxes else "item on floor"
        lines.append(f"- {where} `{f['id']}`: {f['item'].get('qty', 1)}× {f['item']['name']} at ({f['x']},{f['y']}) — {f.get('note', '')}")
    for p in m.get("pois", []):
        lines.append(f"- point of interest `{p['id']}`: {p['name']} at ({p['x']},{p['y']}) → journal {p['journal']}")
    doors = []
    for y, row in enumerate(m["grid"]):
        for x, ch in enumerate(row):
            if ch in "Dd":
                doors.append(f"({x},{y}) {'open' if ch == 'd' else 'closed'}")
    if doors:
        lines.append("- doors: " + ", ".join(doors))
    if m.get("labels"):
        lines.append("- labels: " + ", ".join(f"{lb['text']} ({lb['x']},{lb['y']})" for lb in m["labels"]))
    return "\n".join(lines)


def snapshot_map(g, mid, why="left"):
    """Freeze a map exactly as the party left it: player + DM SVG and a text summary under views/maps/."""
    d = Path(g.dir) / "views" / "maps"
    d.mkdir(parents=True, exist_ok=True)
    tag = f"{mid}-e{len(g.events):05d}"
    (d / f"{tag}-player.svg").write_text(map_svg(g, mid, "player"), encoding="utf-8")
    (d / f"{tag}-dm.svg").write_text(map_svg(g, mid, "dm"), encoding="utf-8")
    (d / f"{tag}.md").write_text(f"# Snapshot — {why} at {fmt_time(g.state['time'])} (event {len(g.events)})\n\n"
                                 + map_state_md(g, mid) + "\n", encoding="utf-8")
    return d / f"{tag}.md"


def write_view_file(path, text, tries=5):
    """Write a regenerated view atomically (temp file, then replace). On Windows a reader such as the live table can
    hold the file for a moment; retry briefly, and if it stays locked skip it: views are rebuilt after every command,
    so a missed one must never fail the command that already went through."""
    import os
    import sys
    import time
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    for attempt in range(tries):
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
            return True
        except OSError:
            time.sleep(0.05 * (attempt + 1))
    try:
        tmp.unlink()
    except OSError:
        pass
    print(f"(note: {path.name} was busy and wasn't refreshed this time; the next command rebuilds it)", file=sys.stderr)
    return False


def write_snapshots(g):
    d = Path(g.dir)
    (d / "party").mkdir(exist_ok=True)
    write_view_file(d / "state.md", state_md(g))
    for e in g.state["entities"].values():
        if e["kind"] == "pc":
            write_view_file(d / "party" / f"{e['id']}.md", sheet_md(g, e))
    views = d / "views"
    views.mkdir(exist_ok=True)
    mid = g.state["view"].get("map")
    if mid and mid in g.state["maps"]:
        write_view_file(views / "current-map.svg", map_svg(g, mid, "player"))
