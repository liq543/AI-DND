"""Reusable spell effects. All mutations use Game events; old logs need no migration.

Effects carry their source, lifetime and mechanical contributions. Multiple castings
of the same spell remain recorded, but only the strongest contribution applies.
Narrative capabilities are tracked without pretending to simulate a three-dimensional world.
"""
import re


def active(e):
    """Apply the strongest simultaneous version of a named spell, not additive copies."""
    selected, ordinary = {}, []
    for fx in e.get("effects", []):
        if not fx.get("managed_spell"):
            ordinary.append(fx)
            continue
        key = fx["spell"]
        if key not in selected or fx.get("potency", 0) >= selected[key].get("potency", 0):
            selected[key] = fx
    return ordinary + list(selected.values())


def has(e, flag):
    return any(f.get(flag) for f in active(e))


def clock(g):
    c = g.state.get("combat") or {}
    # Combat historically stores its elapsed minutes only when it ends.
    return g.state["time"] + (max(0, c.get("round", 1) - 1) / 10 if c.get("active") else 0)


def duration(text):
    m = re.search(r"\b(\d+)\s*(round|minute|hour|day)s?\b", text or "", re.I)
    return int(m[1]) * {"round": .1, "minute": 1, "hour": 60, "day": 1440}[m[2].lower()] if m else None


def template(g, caster, spell, slot, **fields):
    fx = {"id": f"fx{g.state['seq'] + 1}", "managed_spell": True, "name": spell["name"],
          "spell": spell["slug"], "caster": caster["id"], "concentration": bool(spell["concentration"]),
          "potency": slot, "since": clock(g), **fields}
    if fx["concentration"]:
        fx["concentration_instance"] = (caster.get("concentration") or {}).get("instance")
    minutes = duration(spell["duration"])
    if minutes is not None and not fields.get("turn_boundary"):
        fx["expires_at"] = clock(g) + minutes
    if fields.get("turn_boundary"):
        owner = g.get(fields.get("turn_owner") or caster["id"])
        fx.update(turn_owner=owner["id"], turn_number=owner.get("turns_started", 0) + 1)
        # A turn-relative rider also expires outside combat after a round.
        fx["expires_at"] = clock(g) + .1
    return fx


def add(g, e, fx):
    from .core import hp_max
    before_max = hp_max(e)
    previous = [f for f in e.get("effects", []) if f.get("spell") == fx["spell"] and
                (f.get("caster") == fx["caster"] or not f.get("managed_spell"))]
    # Refresh a same-source effect without stacking or triggering its end penalty.
    for old in previous:
        if old.get("id"):
            g.set(e, conditions=[c for c in e.get("conditions", []) if c.get("effect_id") != old["id"]])
    g.set(e, effects=[f for f in e.get("effects", []) if f not in previous] + [fx])
    difference = hp_max(e) - before_max
    if difference:
        g.set(e, hp=min(hp_max(e), max(0, e["hp"] + max(0, difference))))
    if fx.get("condition"):
        from .mechanics import add_condition
        add_condition(g, e, fx["condition"], source=fx["name"], caster=fx["caster"],
                      spell=fx["spell"], effect_id=fx["id"])
    g.say(f"   {e['name']}: {fx['name']} takes effect.", kind="spell-effect", who=e["id"], spell=fx["spell"])


def remove(g, e, fx, reason="ends"):
    from .core import hp_max
    g.set(e, effects=[f for f in e.get("effects", []) if f.get("id") != fx["id"]],
          conditions=[c for c in e.get("conditions", []) if c.get("effect_id") != fx["id"]])
    if e["hp"] > hp_max(e):
        g.set(e, hp=hp_max(e))
    g.say(f"   {e['name']}: {fx['name']} {reason}.", kind="spell-effect", who=e["id"], spell=fx["spell"])
    if fx.get("haste") and not has(e, "haste") and not e.get("dead"):
        lethargy = {"id": f"fx{g.state['seq'] + 1}", "name": "Haste lethargy", "spell": "haste-lethargy",
                    "caster": fx["caster"], "managed_spell": True, "condition": "incapacitated", "speed_zero": True,
                    "turn_owner": e["id"], "turn_number": e.get("turns_started", 0) + 1,
                    "turn_boundary": "end", "expires_at": clock(g) + .1}
        add(g, e, lethargy)


def expire(g):
    now = clock(g)
    c = g.state.get("combat") or {}
    for e in list(g.entities.values()):
        conc = e.get("concentration")
        if conc:
            minutes = duration(conc.get("duration"))
            if minutes is not None and now + 1e-9 >= conc.get("since", now) + minutes:
                from .mechanics import end_concentration
                end_concentration(g, e, "its duration ran out")
        for fx in list(e.get("effects", [])):
            if not fx.get("managed_spell") or fx.get("expires_at") is None:
                continue
            if c.get("active") and fx.get("turn_boundary"):
                continue  # exact creature turn boundaries take precedence over wall time
            if now + 1e-9 >= fx["expires_at"] and fx in e.get("effects", []):
                remove(g, e, fx, "expires")


def turn_boundary(g, owner, boundary):
    for e in list(g.entities.values()):
        for fx in list(e.get("effects", [])):
            if fx.get("managed_spell") and fx.get("turn_owner") == owner["id"] and \
                    fx.get("turn_boundary") == boundary and owner.get("turns_started", 0) >= fx["turn_number"]:
                remove(g, e, fx)


def roll_modifiers(g, e, kind, ability=None, skill=None):
    """Return flat bonus, signed dice expression, Advantage reasons, Disadvantage reasons."""
    bonus, dice, adv, dis = 0, "", [], []
    for fx in active(e):
        if kind in fx.get("adv_tests", []) or kind == "check" and ability in fx.get("adv_checks", []) or \
                kind == "save" and ability in fx.get("adv_saves", []):
            adv.append(fx["name"])
        if kind == "check" and ability in fx.get("dis_checks", []):
            dis.append(fx["name"])
        if kind == "save" and ability in fx.get("dis_saves", []):
            dis.append(fx["name"])
        if kind == "save":
            bonus += fx.get("save_bonus", 0) + fx.get("save_bonuses", {}).get(ability, 0)
        if kind == "check":
            bonus += fx.get("skill_bonuses", {}).get(skill, 0)
        spec = fx.get("roll_dice", {})
        if kind in spec and (not fx.get("skill") or fx["skill"] == skill):
            dice += spec[kind]
    # A selected Pass without Trace target benefits only while actually in its caster's aura.
    if kind == "check" and skill == "stealth":
        from .mechanics import dist_ft
        for caster in g.entities.values():
            fx = next((f for f in active(caster) if f.get("stealth_aura") and e["id"] in f.get("targets", [])), None)
            if fx and (caster["id"] == e["id"] or (dist_ft(caster, e) is not None and dist_ft(caster, e) <= 30)):
                bonus += 10
                break
    return bonus, dice, adv, dis


def attack_modes(att, tgt, distance=None):
    adv, dis = [], []
    for fx in active(att):
        if "attack" in fx.get("adv_tests", []):
            adv.append(fx["name"])
    from .core import item_sense
    senses = str(att.get("senses", "")).lower() + (" truesight" if item_sense(att, "truesight") else "")
    for fx in active(tgt):
        if fx.get("attacks_against_adv") and not any(c["name"] == "blinded" for c in att.get("conditions", [])):
            adv.append(fx["name"])
        if fx.get("attacks_against_dis") and not (fx.get("blur") and any(s in senses for s in ("blindsight", "truesight"))):
            dis.append(fx["name"])
        if fx.get("protected_types") and any(t in str(att.get("type", "")).lower() for t in fx["protected_types"]):
            dis.append(fx["name"])
    return adv, dis


def consume_attack_advantage(g, target):
    for fx in list(active(target)):
        if fx.get("next_attack_adv"):
            remove(g, target, fx, "is used by the attack")


def hit_riders(g, attacker, target, crit=False):
    """Damage shared by weapon and spell attacks (e.g. Hex)."""
    parts = []
    for fx in active(target):
        if fx.get("hit_damage") and fx.get("caster") == attacker["id"]:
            expr, dtype = fx["hit_damage"]
            r = g.roll(expr, fx["name"], attacker["id"], crit=crit)
            parts.append([r["total"], dtype])
            g.say(f"   {fx['name']}: {r['text']} {dtype}.", kind="spell-effect")
    return parts


def reduce_damage(g, e, parts):
    """Resistance cantrip reduces the chosen damage before Resistance/Immunity (SRD damage order)."""
    c = g.state.get("combat") or {}
    turn = (c.get("started"), c.get("round"), c.get("turn")) if c.get("active") else ("time", clock(g))
    out = [list(p) for p in parts]
    for fx in active(e):
        if not fx.get("damage_reduce") or tuple(fx.get("used_turn", [])) == turn:
            continue
        dtype = fx["damage_reduce"]
        if not any(t == dtype and amount > 0 for amount, t in out):
            continue
        r = g.roll("1d4", fx["name"], e["id"])
        left = r["total"]
        for part in out:
            if part[1] == dtype:
                take = min(max(0, part[0]), left)
                part[0] -= take
                left -= take
        g.set(e, effects=[dict(f, used_turn=list(turn)) if f.get("id") == fx["id"] else f for f in e["effects"]])
        g.say(f"   {fx['name']} reduces {dtype} damage: {r['text']}.", kind="spell-effect", who=e["id"])
    return out
