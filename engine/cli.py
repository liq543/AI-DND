"""`python -m engine <command>` — the ONLY way game mechanics change.

Every command validates against the SRD, rolls with the secure RNG, and appends signed events.
If a command would break a rule it prints `✖ RULE:` and changes nothing.
Run `python -m engine help` for the command list, `python -m engine <command> -h` for options.
"""
import argparse
import json
import re
import shlex
import shutil
import sys
from pathlib import Path

from . import art, assets, chargen, dice, itemart, maps, mechanics as M, render, srd, views
from .core import (Game, RuleError, derive, fmt_time, level, parse_duration, replay, tier, TIER_MAX_GP_AWARD,
                   SIZE_CELLS)
from .store import ACTIVE_FILE, CAMPAIGNS, Store, TamperError, active_dir

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"


def xy(text):
    m = re.match(r"^\s*(\d+)\s*[, ]\s*(\d+)\s*$", str(text))
    if not m:
        raise RuleError(f"Coordinates must look like 12,7 (got '{text}').")
    return int(m.group(1)), int(m.group(2))


def ids(text):
    return [t.strip() for t in (text or "").split(",") if t.strip()]


# ====================================================================== campaign management

def cmd_campaign(a):
    CAMPAIGNS.mkdir(exist_ok=True)
    if a.action == "new":
        title = " ".join(a.args)
        if not title:
            raise RuleError('Usage: campaign new "Title"')
        slug = srd.slug(title)
        dest = CAMPAIGNS / slug
        if dest.exists() or (CAMPAIGNS / "_archive" / slug).exists():
            raise RuleError(f"Campaign '{slug}' already exists.")
        for src in (TEMPLATES / "campaign").rglob("*"):
            target = dest / src.relative_to(TEMPLATES / "campaign")
            if src.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                import datetime
                target.write_text(src.read_text(encoding="utf-8").replace("{{TITLE}}", title)
                                  .replace("{{DATE}}", datetime.date.today().isoformat()), encoding="utf-8")
        (dest / "party").mkdir(exist_ok=True)
        (dest / "assets").mkdir(exist_ok=True)
        Store(dest).init()
        ACTIVE_FILE.write_text(slug + "\n", encoding="utf-8")
        g = Game(dest)
        g.cmdline = f"campaign new {title}"
        g.emit("campaign.init", title=title, slug=slug, ruleset="SRD 5.2")
        for kv in a.set or []:
            k, _, v = kv.partition("=")
            set_setting(g, k, v)
        g.say(f"📜 New campaign: {title}", kind="scene")
        g.commit()
        views.write_snapshots(g)
        print(f"Created and activated campaigns/{slug}/ (signed engine log initialised).")
        return
    if a.action == "list":
        cur = ACTIVE_FILE.read_text(encoding="utf-8").strip() if ACTIVE_FILE.exists() else ""
        for p in sorted(CAMPAIGNS.iterdir()):
            if p.is_dir() and p.name != "_archive":
                print(("* " if p.name == cur else "  ") + p.name)
        arch = CAMPAIGNS / "_archive"
        if arch.exists():
            for p in sorted(arch.iterdir()):
                print(f"  {p.name} (archived)")
        return
    if a.action == "switch":
        slug = a.args[0]
        arch = CAMPAIGNS / "_archive" / slug
        if arch.exists():
            shutil.move(str(arch), str(CAMPAIGNS / slug))
        if not (CAMPAIGNS / slug).is_dir():
            raise RuleError(f"No campaign '{slug}'.")
        ACTIVE_FILE.write_text(slug + "\n", encoding="utf-8")
        print(f"Active campaign: {slug}. Start a fresh chat before playing it so no other story is in context.")
        return
    if a.action == "archive":
        slug = a.args[0]
        if not (CAMPAIGNS / slug).is_dir():
            raise RuleError(f"No campaign '{slug}'.")
        (CAMPAIGNS / "_archive").mkdir(exist_ok=True)
        shutil.move(str(CAMPAIGNS / slug), str(CAMPAIGNS / "_archive" / slug))
        if ACTIVE_FILE.exists() and ACTIVE_FILE.read_text(encoding="utf-8").strip() == slug:
            ACTIVE_FILE.unlink()
        print(f"Archived {slug}.")
        return
    raise RuleError("campaign new|list|switch|archive")


SETTINGS = {"player_rolls": ("auto", "viewer"), "xp_mode": ("xp", "milestone"), "difficulty": ("forgiving", "standard", "deadly"),
            "start_level": None, "hp_mode": ("avg", "roll")}


def set_setting(g, key, value):
    if key not in SETTINGS:
        raise RuleError(f"Unknown setting '{key}'. Settings: {', '.join(SETTINGS)}")
    allowed = SETTINGS[key]
    if key == "start_level":
        v = int(value)
        if not 1 <= v <= 20:
            raise RuleError("start_level must be 1–20.")
        if g.pcs() and v != g.state["settings"].get("start_level", 1):
            raise RuleError("start_level is fixed once characters exist.")
        value = v
    elif value not in allowed:
        raise RuleError(f"{key} must be one of {allowed}")
    g.emit("setting", key=key, value=value)
    g.say(f"⚙ Setting: {key} = {value}", kind="info")


def cmd_set(g, a):
    k, _, v = a.kv.partition("=")
    set_setting(g, k.strip(), v.strip())


def cmd_session(g, a):
    n = g.state["session"] + (1 if a.action == "start" else 0)
    if a.action == "start":
        g.emit("session.set", n=n)
        log = Path(g.dir) / "log" / f"session-{n:03d}.md"
        log.parent.mkdir(exist_ok=True)
        if not log.exists():
            import datetime
            log.write_text(f"# Session {n} — {datetime.date.today().isoformat()}\n\n> Play-by-play. Append a bullet per scene.\n\n", encoding="utf-8")
        g.say(f"— Session {n} begins — {fmt_time(g.state['time'])}", kind="scene")
    else:
        g.say(f"— Session {n} ends —", kind="scene")


# ====================================================================== characters

def cmd_char(g, a):
    if a.action == "roll-stats":
        name = " ".join(a.args)
        if not name:
            raise RuleError('Usage: char roll-stats "Character Name"')
        existing = [r for r in g.state["rolls"] if r.get("purpose", "").startswith("ability scores") and r.get("who") == name]
        if existing:
            raise RuleError(f"Ability scores for {name} were already rolled ({existing[0].get('group')}). No rerolls.")
        gid = f"stats-{g.state['roll_count'] + 1}"
        totals = []
        for i in range(6):
            r = dice.roll("4d6kh3")
            rid = f"r{g.state['roll_count'] + 1}"
            g.emit("roll", id=rid, who=name, purpose=f"ability scores #{i + 1}", group=gid, expr="4d6kh3", total=r["total"],
                   nat=None, terms=r["terms"], text=r["text"], hidden=False, mode=None, crit=False)
            totals.append(r["total"])
            g.say(f"🎲 {name} ability score #{i + 1}: {r['text']}", kind="roll", roll=rid)
        g.say(f"   {name}'s scores to assign: {sorted(totals, reverse=True)} (roll group {gid})", kind="roll")
        return
    if a.action == "create":
        chargen.create(g, a)
        return
    e = g.get(a.args[0]) if a.args else None
    if a.action == "levelup":
        chargen.levelup(g, e, a)
    elif a.action == "catch-up":
        chargen.catch_up(g, e, a)
    elif a.action == "masteries":
        chargen.set_masteries(g, e, a.masteries)
    elif a.action == "bio":
        field, text = a.args[1], " ".join(a.args[2:])
        if field not in ("appearance", "personality", "ideals", "bonds", "flaws", "backstory", "goals", "alignment", "notes"):
            raise RuleError("bio fields: appearance personality ideals bonds flaws backstory goals alignment notes")
        g.set(e, **{f"bio__{field}": text})
        g.note(f"Updated {e['name']} {field}.")
    elif a.action == "show":
        print(views.sheet_md(g, e))
    elif a.action == "inspire":
        if e.get("inspiration"):
            raise RuleError(f"{e['name']} already has Heroic Inspiration (it doesn't stack).")
        reason = " ".join(a.args[1:])
        if len(reason) < 5:
            raise RuleError("Give the reason Heroic Inspiration is awarded (shown to the player).")
        g.set(e, inspiration=True)
        g.say(f"🌟 {e['name']} gains Heroic Inspiration — {reason}", kind="xp")
    elif a.action == "use-inspiration":
        if not e.get("inspiration"):
            raise RuleError(f"{e['name']} has no Heroic Inspiration.")
        g.set(e, inspiration=False)
        g.say(f"🌟 {e['name']} spends Heroic Inspiration to reroll — use the new roll.", kind="xp")
    elif a.action in ("leave", "rejoin"):
        # a character parts ways with the party (alive, sheet kept): off the table, out of XP, rests and the party panel.
        # `rejoin` brings them back if the story does.
        reason = " ".join(a.args[1:])
        if len(reason) < 4:
            raise RuleError(f'char {a.action} <id> "why" (shown to the player)')
        if a.action == "leave":
            g.set(e, departed=True, hidden=True, known=True, offstage=True)
            g.say(f"👋 {e['name']} leaves the party — {reason}.", kind="party", who=e["id"])
        else:
            g.set(e, departed=False, hidden=False, offstage=False)
            g.say(f"🤝 {e['name']} rejoins the party — {reason}.", kind="party", who=e["id"])
    elif a.action == "remove":
        g.emit("entity.remove", id=e["id"])
        g.say(f"{e['name']} leaves the party.")
    else:
        raise RuleError("char roll-stats|create|levelup|catch-up|masteries|leave|rejoin|bio|show|inspire|use-inspiration|remove")


def cmd_spells(g, a):
    e = g.get(a.who)
    if a.action == "set":
        cls = a.cls or next(iter(derive(e)["spellcasting"]), None)
        if not cls:
            raise RuleError(f"{e['name']} has no Spellcasting feature.")
        book = [g.require("spells", s, "Spell") for s in ids(a.spellbook)] if a.spellbook else None
        if g.state.get("combat") and g.state["combat"].get("active"):
            raise RuleError("Spells are prepared on a Long Rest or level-up, not mid-combat.")
        chargen.set_spells(g, e, cls, ids(a.cantrips) or e.get("spells", {}).get("cantrips", []),
                           ids(a.prepared), book)
    elif a.action == "scribe":
        if "Wizard" not in e["classes"]:
            raise RuleError("Only Wizards keep spellbooks.")
        sp = g.require("spells", a.spell, "Spell")
        if "Wizard" not in sp["classes"] or sp["level"] == 0:
            raise RuleError(f"{sp['name']} isn't a levelled Wizard spell.")
        if sp["level"] > derive(e)["spellcasting"]["Wizard"]["max_level"]:
            raise RuleError(f"{e['name']} can't yet scribe level {sp['level']} spells.")
        source = a.source or ""
        if not re.search(r"scroll|spellbook|level up|found|copied", source, re.I):
            raise RuleError("--source must say where the spell comes from (spell scroll item, another spellbook, or 'level up').")
        book = list(e.get("spells", {}).get("spellbook", []))
        if sp["slug"] in book:
            raise RuleError(f"{sp['name']} is already in the spellbook.")
        if "level up" not in source.lower():
            M.change_coins(g, e, -50 * 100 * sp["level"], "scribing ink")
            g.emit("time.set", minutes=g.state["time"] + 120 * sp["level"])
        book.append(sp["slug"])
        g.set(e, spells={**e.get("spells", {}), "spellbook": book})
        g.say(f"📖 {e['name']} scribes {sp['name']} into their spellbook ({source}).", kind="spell")
    elif a.action == "list":
        cls = a.cls or next(iter(e["classes"]))
        sc = derive(e)["spellcasting"].get(cls)
        rows = [s for s in srd.data()["spells"].values() if cls in s["classes"] and s["level"] <= (sc or {}).get("max_level", 0)]
        for s in sorted(rows, key=lambda s: (s["level"], s["name"])):
            print(f"L{s['level']} {s['name']} ({s['slug']}){' [C]' if s['concentration'] else ''}{' [R]' if s['ritual'] else ''}")


# ====================================================================== creatures

def instantiate_monster(g, mon, name=None, side="enemy", hidden=False, hp_mode="avg"):
    eid = g.new_id(name or mon["name"])
    hp = mon["hp"]
    how = "average"
    if hp_mode == "roll" and mon.get("hp_dice"):
        r = g.roll(mon["hp_dice"], f"{mon['name']} hit points", eid, hidden=True)
        hp, how = max(1, r["total"]), "rolled"
    lr = next((a for a in mon["actions"] if a["name"] == "Legendary Resistance"), None)
    e = {"id": eid, "kind": "monster", "name": name or mon["name"], "srd": mon.get("slug"), "srd_name": mon["name"],
         "side": side, "hidden": hidden, "size": ("Medium" if mon["size"] == "Small" and str(mon["type"]).lower().startswith("humanoid") else mon["size"]), "type": mon["type"], "alignment": mon["alignment"],
         "ac": mon["ac"], "hp": hp, "hp_max": hp, "hp_how": how, "temp_hp": 0, "speed": mon["speed"], "init": mon["init"],
         "abilities": mon["abilities"], "skills": mon["skills"], "resist": mon["resist"], "immune": mon["immune"],
         "vulnerable": mon["vulnerable"], "condition_immune": mon["condition_immune"], "darkvision": mon["darkvision"],
         "passive_perception": mon["passive_perception"], "cr": mon["cr"], "xp": mon["xp"], "pb": mon["pb"],
         "multiattack": mon["multiattack"], "actions": mon["actions"], "conditions": [], "effects": [],
         "cells": SIZE_CELLS.get(mon["size"], 1), "legendary_resistance": (lr or {}).get("per_day", 0),
         "recharge_ready": {a["name"]: True for a in mon["actions"] if a.get("recharge")}}
    g.emit("entity.add", entity=e)
    return g.get(eid)


ALIGNMENTS = ("Lawful Good", "Neutral Good", "Chaotic Good", "Lawful Neutral", "Neutral", "Chaotic Neutral",
              "Lawful Evil", "Neutral Evil", "Chaotic Evil", "Unaligned")


def cmd_npc(g, a):
    if a.action == "resize":
        # SRD generic NPCs are "Medium or Small" humanoids; pick the one that fits the person
        e = g.get(a.what)
        size = (a.size or "").title()
        if size not in ("Tiny", "Small", "Medium", "Large", "Huge", "Gargantuan"):
            raise RuleError("npc resize <id> --size Tiny|Small|Medium|Large|Huge|Gargantuan")
        g.set(e, size=size)
        g.note(f"  {e['name']} is {size}.")
        return
    if a.action == "describe":
        # what anyone looking at them can see (shown on their info panel); replaces the previous description
        e = g.get(a.what)
        if not a.text or len(a.text) < 4:
            raise RuleError('npc describe <id> --text "what the characters can see"')
        g.set(e, appearance=a.text)
        g.note(f"  Described {e['name']}.")
        return
    if a.action == "alignment":
        # the character's own alignment (their outlook), which replaces the stat block's generic one; shown on their info card
        e = g.get(a.what)
        if e["kind"] == "pc":
            raise RuleError(f"{e['name']} is a player character: their alignment is the player's to play, not the table's to show.")
        text = " ".join(w.capitalize() for w in (a.text or "").replace("-", " ").split())
        if text not in ALIGNMENTS:
            raise RuleError(f"npc alignment {a.what} --text \"{'|'.join(ALIGNMENTS)}\"")
        g.set(e, alignment=text)
        g.note(f"  {e['name']} is {text}.")
        return
    if a.action in ("unarmored", "armored"):
        # a stat block's AC includes the armour it wears; a creature caught without it (asleep, bathing, stripped)
        # has the SRD unarmoured AC, 10 + its Dexterity modifier. `armored` puts the stat block's AC back.
        e = g.get(a.what)
        if e["kind"] == "pc":
            raise RuleError("PCs' AC follows their equipped armour: use `item unequip` instead.")
        mon = g.lookup("monsters", e.get("srd") or "") or {}
        if a.action == "unarmored":
            dex = (e.get("abilities") or mon.get("abilities") or {}).get("dex", 10)
            if isinstance(dex, dict):     # stat blocks store {"score": n, "mod": m, ...}
                dex = dex.get("score", 10 + 2 * dex.get("mod", 0))
            ac = 10 + (dex - 10) // 2
            g.set(e, ac=ac, armored_ac=e.get("armored_ac", e["ac"]))
            g.say(f"🛡 {e['name']} has no armour on: AC {ac} (10 + Dex).", kind="info", who=e["id"])
        else:
            ac = e.get("armored_ac") or mon.get("ac") or e["ac"]
            g.set(e, ac=ac, armored_ac=None)
            g.say(f"🛡 {e['name']} is armoured again: AC {ac}.", kind="info", who=e["id"])
        return
    if a.action == "lore":
        # public knowledge the party has earned (a knowledge check, a clue, an NPC's word) — shown on the creature's info panel
        e = g.get(a.what)
        if not a.text or len(a.text) < 4:
            raise RuleError('npc lore <id> --text "what the party now knows"')
        g.set(e, lore=e.get("lore", []) + [a.text])
        g.say(f"📚 Known about {e['name']}: {a.text}", kind="info")
        return
    if a.action == "add":
        mon = g.lookup("monsters", a.what)
        if not mon:
            sug = srd.suggest("monsters", a.what)
            raise RuleError(f"No stat block '{a.what}' in the SRD" + (f" (did you mean {', '.join(sug)}?)" if sug else "") +
                            ". Use a close SRD stat block with --name, or register one with `homebrew add monsters`.")
        made = []
        for i in range(a.count):
            nm = a.name if a.name and a.count == 1 else (f"{a.name or mon['name']} {chr(65 + i)}" if a.count > 1 else None)
            made.append(instantiate_monster(g, mon, nm, a.side, a.hidden, a.hp or g.state["settings"].get("hp_mode", "avg")))
        if a.at:
            mid = a.map or g.state["view"].get("map")
            if not mid:
                raise RuleError("No active map to place on (--map).")
            m = g.state["maps"][mid]
            x, y = xy(a.at)
            occupied = {(e["token"]["x"], e["token"]["y"]) for e in g.entities.values() if e.get("token", {}).get("map") == mid}
            spots = maps.free_cells(m, len(made), __import__("random").Random(g.state["seq"]), near=(x, y), avoid=frozenset(occupied))
            for e, (sx, sy) in zip(made, spots):
                g.set(e, token={"map": mid, "x": sx, "y": sy})
        for e in made:
            if not e["hidden"]:
                g.say(f"👁 {e['name']} appears{' (' + e['side'] + ')' if e['side'] != 'enemy' else ''}.", kind="creature", who=e["id"])
            g.note(f"  added {e['id']}: {e['srd_name']} AC {e['ac']} HP {e['hp']} CR {e['cr']}")
    elif a.action in ("leave", "return"):
        # a creature walks out of the scene (not hiding in it): off the table, out of any fight here. `return` brings it back.
        for i in ids(a.what):
            e = g.get(i)
            if a.action == "leave":
                g.set(e, hidden=True, offstage=True, **({"known": True} if not e.get("hidden") or e.get("known") else {}))
                g.say(f"👋 {e['name']} leaves the scene.", kind="creature") if not e.get("hidden") else None
            else:
                g.set(e, hidden=False, offstage=False, known=True)
                g.say(f"👁 {e['name']} is back.", kind="creature")
    elif a.action in ("reveal", "hide"):
        for i in ids(a.what):
            e = g.get(i)
            g.set(e, hidden=(a.action == "hide"), **({"known": True} if a.action == "reveal" or not e.get("hidden") else {}))
            if a.action == "reveal":
                g.say(f"👁 {e['name']} is revealed!", kind="creature")
    elif a.action == "remove":
        for i in ids(a.what):
            e = g.get(i)
            g.emit("entity.remove", id=e["id"])
            g.note(f"removed {e['id']}")
    elif a.action == "rename":
        e = g.get(a.what)
        old = e["name"]
        g.set(e, name=a.name)
        # a creature the players can't see yet keeps its real name secret (the DM is often giving it a cover name)
        g.say(f"{old} is now known as {a.name}.", **({"kind": "dm"} if e.get("hidden") else {}))
    elif a.action == "side":
        e = g.get(a.what)
        if a.side not in ("enemy", "ally", "neutral"):
            raise RuleError("side must be enemy|ally|neutral")
        g.set(e, side=a.side)
        g.say(f"{e['name']} is now {a.side}.")
    elif a.action == "show":
        e = g.get(a.what)
        print(json.dumps({k: e.get(k) for k in ("id", "name", "srd", "hp", "hp_max", "ac", "speed", "cr", "xp", "conditions", "token")}, indent=1))
        for act in e.get("actions", []):
            print(f"- [{act['section']}] {act['full_name']}: {act['text'][:160]}")


def cmd_place(g, a):
    e = g.get(a.who)
    mid = a.map or g.state["view"].get("map")
    if not mid or mid not in g.state["maps"]:
        raise RuleError("No such map. `map list`")
    m = g.state["maps"][mid]
    x, y = xy(a.at)
    if maps.move_cost(m, x, y) is None:
        raise RuleError(f"({x},{y}) is {maps.TERRAIN.get(maps.cell(m, x, y), ('?',))[0]} — can't stand there.")
    for o in g.entities.values():
        if (o["id"] != e["id"] and not o.get("offstage") and o.get("token", {}).get("map") == mid
                and (o["token"]["x"], o["token"]["y"]) == (x, y)):
            raise RuleError(f"({x},{y}) is occupied by {o['name']}.")
    if M.combat(g) and e.get("token") and not a.force:
        raise RuleError("In combat, creatures move with `move` (movement is validated). Use --force \"reason\" for teleport/forced moves.")
    if a.force and M.combat(g):
        g.override(a.force, f"placed {e['name']} at ({x},{y})")
    g.set(e, token={"map": mid, "x": x, "y": y}, cells=SIZE_CELLS.get(e.get("size", "Medium"), 1))
    g.say(f"{e['name']} is at ({x},{y}) on {m['name']}.", kind="move", who=e["id"], map=mid, to=[x, y], placed=True)
    M.reveal_for(g, g.get(e["id"]))


def cmd_move(g, a):
    path = [xy(p) for p in a.path.split()] if a.path else None
    dest = xy(a.to) if a.to else (path[-1] if path else None)
    if a.force:
        e = g.get(a.who)
        g.say(f"{e['name']} is moved by force: {a.force}", kind="move")
    M.move(g, a.who, dest, path, force=a.force, crawl=a.crawl)


def cmd_party_move(g, a):
    """Move every PC (and allies) on the current map together, e.g. exploring out of combat."""
    if M.combat(g):
        raise RuleError("In combat, each creature moves on its own turn.")
    x, y = xy(a.to)
    for e in [e for e in g.entities.values() if (e["kind"] == "pc" or e.get("side") == "ally") and e.get("token") and alive_e(e)]:
        mid = e["token"]["map"]
        m = g.state["maps"][mid]
        occupied = {(o["token"]["x"], o["token"]["y"]) for o in g.entities.values() if o.get("token", {}).get("map") == mid and o["id"] != e["id"]}
        spot = maps.free_cells(m, 1, __import__("random").Random(len(g.pending)), near=(x, y), avoid=frozenset(occupied), radius=3)
        if spot:
            M.move(g, e["id"], spot[0], group="party")


def alive_e(e):
    return not e.get("dead")


# ====================================================================== combat

def cmd_combat(g, a):
    c = M.combat(g)
    if a.action == "start":
        if c:
            raise RuleError("Combat is already running (`combat end` first).")
        mid = g.state["view"].get("map")
        members = [g.get(i) for i in ids(a.ids)] if a.ids else \
            [e for e in g.entities.values() if e.get("token", {}).get("map") == mid and not e.get("dead")
             and not e.get("departed") and not e.get("offstage")]   # those who have left the scene stay out of it
        if not members:
            raise RuleError("No combatants. Place tokens on the current map or pass --ids.")
        if a.ids:
            left_out = [e for e in g.entities.values() if e.get("token", {}).get("map") == mid and not e.get("dead")
                        and e["id"] not in {m["id"] for m in members} and not e.get("hidden")]
            if left_out:
                g.note("  ⚠ Not in initiative: " + ", ".join(e["name"] for e in left_out) +
                       " — bystanders still act each round (flee, hide, beg, grab loot); add them with `combat add <id>`.")
        surprised = set(ids(a.surprised))
        order, pending = [], {}
        for e in members:
            r = M.roll_initiative(g, e, e["id"] in surprised)
            if "request" in r:
                pending[e["id"]] = r["request"]
            else:
                order.append({"id": e["id"], "init": r["total"], "tie": derive(e)["init"]})
                g.say(f"   Initiative — {e['name']}: {r['text']}" + (" (surprised)" if e["id"] in surprised else ""), kind="roll")
        state = {"active": True, "round": 1, "turn": 0, "order": [], "economy": {}, "defeated": [],
                 "started": g.state["time"], "pending_init": pending, "unsorted": order}
        g.emit("combat.set", combat=state)
        g.say("⚔ Roll for initiative! Combat begins.", kind="combat", phase="start")
        if not pending:
            finalize_initiative(g)
        else:
            g.say(f"   Waiting on initiative from: {', '.join(g.get(i)['name'] for i in pending)}.", kind="combat")
        return
    if not c:
        raise RuleError("No combat running.")
    if c.get("pending_init") and a.action not in ("end", "status"):
        raise RuleError("Initiative rolls are still pending: " + ", ".join(c["pending_init"]))
    if a.action == "swap":
        # Alert (SRD feat): "Immediately after you roll Initiative, you can swap your Initiative with the Initiative of one
        # willing ally in the same combat. You can't make this swap if you or the ally has the Incapacitated condition."
        who = ids(a.ids)
        if len(who) != 2:
            raise RuleError("combat swap <alert-pc>,<ally>")
        e, ally = g.get(who[0]), g.get(who[1])
        if not M.has_feat(e, "Alert"):
            raise RuleError(f"{e['name']} doesn't have the Alert feat (Initiative Swap).")
        if c["round"] != 1 or c["turn"] != 0 or c["economy"].get(c["order"][0]["id"]) or c.get("swapped"):
            raise RuleError("Initiative Swap happens immediately after Initiative is rolled, before anyone acts.")
        if ally.get("side") not in ("pc", "ally") and ally["kind"] != "pc":
            raise RuleError(f"{ally['name']} isn't an ally.")
        for x in (e, ally):
            if "incapacitated" in M.condition_names(x):
                raise RuleError(f"{x['name']} is Incapacitated and can't swap Initiative.")
        order = [dict(o) for o in c["order"]]
        oe = next((o for o in order if o["id"] == e["id"]), None)
        oa = next((o for o in order if o["id"] == ally["id"]), None)
        if not oe or not oa:
            raise RuleError("Both must be in this combat.")
        oe["init"], oa["init"], oe["tie"], oa["tie"] = oa["init"], oe["init"], oa["tie"], oe["tie"]
        order.sort(key=lambda o: (-o["init"], -o["tie"], o["id"]))
        first_changed = order[0]["id"] != c["order"][0]["id"]
        c = dict(c, order=order, swapped=True)
        if first_changed:
            c["economy"] = {order[0]["id"]: {}}
        g.emit("combat.set", combat=c)
        g.say(f"⚡ Alert: {e['name']} swaps Initiative with {ally['name']} ({oe['init']} ↔ {oa['init']}).", kind="combat")
        g.say("Initiative order: " + " → ".join(f"{g.get(o['id'])['name']} ({o['init']})" for o in order
                                               if not g.get(o['id']).get('hidden')), kind="combat")
        if first_changed:
            first = g.get(order[0]["id"])
            g.say(f"▶ {first['name']}'s turn (round 1).", kind="turn", who=first["id"], round=1)
            M.start_of_turn(g, first)
        return
    if a.action == "next":
        cur = g.get(M.current_id(g)) if M.current_id(g) in g.entities else None
        if cur:
            M.end_of_turn(g, cur)
        c = dict(M.combat(g))
        n = len(c["order"])
        for _ in range(n):
            c["turn"] += 1
            if c["turn"] >= n:
                c["turn"] = 0
                c["round"] += 1
                g.say(f"— Round {c['round']} —", kind="combat", phase="round", round=c["round"])
                # reactions refresh at the start of each creature's turn; reset per-turn economy
            nid = c["order"][c["turn"]]["id"]
            ne = g.entities.get(nid)
            if ne and not ne.get("dead") and not (ne["kind"] != "pc" and ne["hp"] <= 0):
                break
        c["economy"] = {**c.get("economy", {}), nid: {}}
        g.emit("combat.set", combat=c)
        ne = g.get(nid)
        g.say(f"▶ {ne['name']}'s turn (round {c['round']}).", kind="turn", who=nid, round=c["round"])
        M.start_of_turn(g, ne)
        return
    if a.action == "add":
        e = g.get(a.ids)
        r = M.roll_initiative(g, e, now=True)
        c = dict(c)
        c["order"] = sorted(c["order"] + [{"id": e["id"], "init": r["total"], "tie": derive(e)["init"]}],
                            key=lambda o: (-o["init"], -o["tie"]))
        cur = M.current_id(g)
        c["turn"] = next(i for i, o in enumerate(c["order"]) if o["id"] == cur)
        g.emit("combat.set", combat=c)
        g.say(f"{e['name']} joins the fight (initiative {r['total']}).", kind="combat")
        return
    if a.action == "give-turn":
        # repair: a creature's turn was skipped by mistake; return the turn to it (logged publicly)
        if not a.ids or not a.reason:
            raise RuleError('combat give-turn <id> --reason "..."')
        e = g.get(a.ids)
        c = dict(c)
        idx = next((i for i, o in enumerate(c["order"]) if o["id"] == e["id"]), None)
        if idx is None:
            raise RuleError(f"{e['name']} isn't in the initiative order.")
        c["turn"] = idx
        c["economy"] = {**c.get("economy", {}), e["id"]: {}}
        g.emit("combat.set", combat=c)
        g.override(a.reason, f"turn returned to {e['name']}")
        g.say(f"▶ {e['name']}'s turn (round {c['round']}) — returned after a skip.", kind="turn", who=e["id"], round=c["round"])
        return
    if a.action == "oa-window":
        # beta repair: open the opportunity-attack window a move warning should have opened (logged publicly)
        att_id, _, tgt_id = (a.ids or "").partition(",")
        if not tgt_id or not a.reason:
            raise RuleError('combat oa-window <attacker>,<target> --reason "..."')
        M.set_economy(g, g.get(att_id)["id"], oa_window=g.get(tgt_id)["id"])
        g.override(a.reason, f"opportunity-attack window for {g.get(att_id)['name']} vs {g.get(tgt_id)['name']}")
        return
    if a.action == "reset-turn":
        # beta repair: the current creature's action economy was left stale by an engine bug; logged publicly
        if not a.reason or len(a.reason) < 8:
            raise RuleError('combat reset-turn --reason "what went wrong" (shown to the player)')
        cur = M.current_id(g)
        c = dict(c)
        c["economy"] = {**c.get("economy", {}), cur: {}}
        g.emit("combat.set", combat=c)
        g.override(a.reason, f"reset {g.get(cur)['name']}'s turn economy")
        g.say(f"🔧 {g.get(cur)['name']}'s turn economy reset — {a.reason}", kind="combat")
        return
    if a.action == "remove":
        e = g.get(a.ids)
        c = dict(c)
        cur = M.current_id(g)
        c["order"] = [o for o in c["order"] if o["id"] != e["id"]]
        was_current = cur == e["id"]
        if was_current:
            if c["turn"] >= len(c["order"]):
                c["turn"] = 0
                c["round"] += 1
            c["economy"] = {**c.get("economy", {}), c["order"][c["turn"]]["id"]: {}}  # the next creature starts a fresh turn
        else:
            c["turn"] = next(i for i, o in enumerate(c["order"]) if o["id"] == cur)
        g.emit("combat.set", combat=c)
        g.say(f"{e['name']} leaves combat.", kind="combat")
        if was_current:
            ne = g.get(c["order"][c["turn"]]["id"])
            g.say(f"▶ {ne['name']}'s turn (round {c['round']}).", kind="turn", who=ne["id"], round=c["round"])
            M.start_of_turn(g, ne)
        return
    if a.action == "end":
        defeated = c.get("defeated", [])
        xp = sum(g.entities[i]["xp"] for i in defeated if i in g.entities)
        g.emit("encounter.log", defeated=defeated, xp=xp, awarded=False, time=g.state["time"],
               rounds=c["round"], ammo={k: v.get("ammo_spent", 0) for k, v in c.get("economy", {}).items() if v.get("ammo_spent")})
        g.emit("time.set", minutes=g.state["time"] + max(1, c["round"] // 10))
        for e in g.entities.values():
            conds = [x for x in e.get("conditions", []) if x["name"] in ("dodging", "helped", "raging", "disengaged")]
            if conds:
                g.set(e, conditions=[x for x in e["conditions"] if x not in conds])
        g.emit("combat.set", combat=None)
        g.say(f"🏁 Combat ends after {c['round']} round(s). Defeated: {', '.join(g.entities[i]['name'] for i in defeated if i in g.entities) or 'none'}"
              f" ({xp} XP available — `xp award --encounter`).", kind="combat", phase="end")
        return
    if a.action == "status":
        for i, o in enumerate(c["order"]):
            e = g.entities.get(o["id"], {})
            print(f"{'➤' if i == c['turn'] else ' '} {o['init']:>2} {e.get('name')} HP {e.get('hp')}/{e.get('hp_max')} {M.economy(g, o['id'])}")


def finalize_initiative(g):
    c = dict(M.combat(g))
    order = sorted(c["unsorted"], key=lambda o: (-o["init"], -o["tie"], o["id"]))
    c.update({"order": order, "turn": 0, "pending_init": {}, "unsorted": []})
    c["economy"] = {order[0]["id"]: {}}
    g.emit("combat.set", combat=c)
    g.say("Initiative order: " + " → ".join(f"{g.get(o['id'])['name']} ({o['init']})" for o in order if not g.get(o['id']).get('hidden')), kind="combat")
    first = g.get(order[0]["id"])
    g.say(f"▶ {first['name']}'s turn (round 1).", kind="turn", who=first["id"], round=1)
    M.start_of_turn(g, first)


ACTIONS = {"dash", "disengage", "dodge", "help", "hide", "ready", "search", "study", "utilize", "influence", "magic", "attack", "grapple", "shove", "escape"}


def cmd_action(g, a):
    e = g.get(a.who)
    name = a.name.lower()
    kind = "bonus" if a.bonus else "reaction" if a.reaction else "action"
    if name not in ACTIONS:
        raise RuleError(f"'{name}' is not an SRD action. Actions: {', '.join(sorted(ACTIONS))}. Class features: `feature`.")
    if kind == "bonus" and not a.via:
        raise RuleError("Taking an action as a Bonus Action needs a feature that allows it (--via \"Cunning Action\").")
    if a.via and not __import__("engine.core", fromlist=["has_feature"]).has_feature(e, a.via) and \
            not any(x["name"].lower() == a.via.lower() for x in e.get("actions", [])):
        raise RuleError(f"{e['name']} doesn't have '{a.via}'.")
    if name in ("grapple", "shove"):
        M.grapple_or_shove(g, e, g.get(a.target) if a.target else None, name, prone=bool(getattr(a, "prone", False)),
                           reaction=kind == "reaction")
        return
    if name == "escape":
        # Ending a Grapple: an action, Strength (Athletics) or Dexterity (Acrobatics) vs the grapple's escape DC
        gr = next((c for c in e.get("conditions", []) if c["name"] == "grappled"), None)
        if not gr:
            raise RuleError(f"{e['name']} isn't Grappled.")
        M.use_action(g, e, kind, "escape a grapple")
        skill = a.skill or ("athletics" if M.skill_mod(M.g_ent(g, e), "athletics") >= M.skill_mod(M.g_ent(g, e), "acrobatics") else "acrobatics")
        r = M.ability_check(g, e, skill, dc=gr.get("escape_dc", 10), now=True, purpose="escape the grapple")
        if r.get("success"):
            M.remove_condition(g, g.get(e["id"]), "grappled")
        return
    M.use_action(g, e, kind, name)
    if name == "dash":
        ec = M.economy(g, e["id"])
        g and M.combat(g) and M.set_economy(g, e["id"], **({"dashed2": True} if ec.get("dashed") else {"dashed": True}))
        g.say(f"{e['name']} takes the Dash action (extra movement equal to Speed).", kind="action")
    elif name == "disengage":
        M.combat(g) and M.set_economy(g, e["id"], disengaged=True)
        g.say(f"{e['name']} Disengages — no Opportunity Attacks this turn.", kind="action")
    elif name == "dodge":
        M.add_condition(g, e, "dodging", source="Dodge action", until="start of its next turn", quiet=True)
        g.say(f"{e['name']} takes the Dodge action — attacks against it have Disadvantage; Advantage on Dex saves.", kind="action")
    elif name == "help":
        if not a.target:
            raise RuleError("Help needs --target (the ally you help).")
        t = g.get(a.target)
        M.add_condition(g, t, "helped", source=f"Help from {e['name']}", until="start of its next turn", quiet=True)
        g.say(f"{e['name']} Helps {t['name']} — Advantage on their next ability check or attack roll.", kind="action")
    elif name == "hide":
        r = M.ability_check(g, e, "stealth", dc=15, now=True)
        if r.get("success"):
            M.add_condition(g, e, "invisible", source="Hide (Stealth " + str(r["total"]) + ")", quiet=True)
            g.say(f"{e['name']} is Hidden (Invisible until found; enemies need Perception ≥ {r['total']}).", kind="action")
    elif name == "search":
        M.ability_check(g, e, a.skill or "perception", dc=a.dc)
    elif name == "study":
        M.ability_check(g, e, a.skill or "investigation", dc=a.dc)
    elif name == "influence":
        M.ability_check(g, e, a.skill or "persuasion", dc=a.dc)
    else:
        g.say(f"{e['name']} takes the {name.title()} action" + (f": {a.note}" if a.note else "") + ".", kind="action")


def cmd_attack(g, a):
    for _ in range(a.times):
        adv = ids(a.adv)
        if M.combat(g) and not a.reaction and M.economy(g, a.attacker).get("steady_aim"):
            adv = [x for x in adv if x.lower() != "steady aim"] + ["Steady Aim"]
            M.set_economy(g, a.attacker, steady_aim=False)
        r = M.attack(g, a.attacker, a.target, a.weapon, adv=adv, dis=ids(a.dis), reaction=a.reaction,
                     offhand=a.offhand, versatile=a.versatile, sneak=a.sneak, smite=a.smite, now=a.now, knockout=a.knockout)
        if "request" in (r or {}):
            break


def cmd_cast(g, a):
    M.cast(g, a.caster, a.spell, a.level, ids(a.targets), ritual=a.ritual, free=a.free, adv=ids(a.adv), dis=ids(a.dis),
           condition=a.condition, component=a.component, now=a.now, scroll=a.scroll)


def cmd_check(g, a):
    for who in ids(a.who):
        M.ability_check(g, g.get(who), a.what, dc=a.dc, adv=ids(a.adv), dis=ids(a.dis), hidden=a.hidden, now=a.now,
                        purpose=a.purpose)


def cmd_ruling(g, a):
    """A public DM ruling or correction (shown in the viewer's DM-override list): mistakes, retcons, judgement calls."""
    if not a.what or not a.reason or len(a.reason) < 10:
        raise RuleError('ruling --what "what was decided" --reason "why" (shown to the players)')
    g.override(a.reason, a.what)
    g.say(f"⚖ DM ruling: {a.what} — {a.reason}", kind="info")


def cmd_contest(g, a):
    """Opposed check (rules/core/01-playing-the-game.md → Contests): e.g. an NPC's Deception vs a PC's Insight.
    The initiator must beat the opponent; a tie leaves things as they were (the opponent wins).
    --passive: the opponent uses its passive score (10 + modifier) instead of rolling (they aren't actively trying).
    --hidden: the rolls are secret (a lie the characters can't know about); players only see that a secret check happened."""
    from .core import skill_mod
    A, B = g.get(a.who), g.get(a.vs)
    skill_a, skill_b = a.what.lower(), a.vs_skill.lower()
    ra = M.ability_check(g, A, skill_a, adv=ids(a.adv), dis=ids(a.dis), hidden=a.hidden, now=True,
                         purpose=a.purpose or f"contest: {skill_a} vs {B['name']}'s {skill_b}")
    if a.passive:
        if skill_b not in srd.SKILLS:
            raise RuleError(f"--passive needs a skill for the opponent, got '{skill_b}'.")
        tb = 10 + skill_mod(B, skill_b) + (5 if a.passive_adv else 0) - (5 if a.passive_dis else 0)
        desc_b = f"passive {skill_b.title()} {tb}"
    else:
        rb = M.ability_check(g, B, skill_b, hidden=a.hidden, now=True, purpose=f"contest: {skill_b} vs {A['name']}'s {skill_a}")
        tb = rb["total"]
        desc_b = f"{skill_b.title()} {tb}"
    winner = A if ra["total"] > tb else B
    line = (f"⚖ Contest — {A['name']} {skill_a.title()} {ra['total']} vs {B['name']} {desc_b} → "
            f"{winner['name']} wins" + (" (tie: things stay as they were)" if ra["total"] == tb else "") + ".")
    if a.hidden:
        g.note("[secret] " + line)
    else:
        g.say(line, kind="roll")


def cmd_save(g, a):
    parts = []
    if a.damage:
        m = re.match(r"^\s*([\dd+\- ]+)\s+(\w+)\s*$", a.damage)
        if not m or m.group(2).lower() not in srd.DAMAGE_TYPES:
            raise RuleError('--damage must look like "8d6 fire"')
        r = g.roll(m.group(1).replace(" ", ""), f"{a.source or 'effect'} damage", None)
        parts = [[r["total"], m.group(2).lower()]]
        g.say(f"   {a.source or 'Effect'} damage: {r['text']} {m.group(2).lower()}", kind="roll")
    for who in ids(a.who):
        M.saving_throw(g, g.get(who), a.ability, a.dc, adv=ids(a.adv), dis=ids(a.dis), source=a.source, spell=a.spell, now=a.now,
                       effect={"damage": parts, "half": a.half, "condition": a.condition, "source": a.source,
                               "repeat_save": f"{a.ability}:{a.dc}" if a.repeat else None} if (parts or a.condition) else None)


def cmd_damage(g, a):
    e = g.get(a.who)
    if not a.source:
        raise RuleError("Damage needs --source (trap, fall, hazard, spell name...). It's shown to the player.")
    amt = a.amount
    if not re.fullmatch(r"\d+", amt):
        r = g.roll(amt, f"{a.source} damage", None)
        amt = r["total"]
        g.say(f"   {a.source}: {r['text']}", kind="roll")
    if a.type.lower() not in srd.DAMAGE_TYPES:
        raise RuleError(f"Damage type must be one of {', '.join(srd.DAMAGE_TYPES)}")
    M.apply_damage(g, e, [[int(amt), a.type.lower()]], source=a.source, crit=a.crit)


def cmd_heal(g, a):
    e = g.get(a.who)
    if e["kind"] == "pc" or e.get("side") == "ally":
        if not a.override:
            raise RuleError("Healing a party member must come from a mechanic: `cast` (healing spell), `item use` (potion), "
                            "`feature` (Second Wind, Lay On Hands), `rest`, or Hit Point Dice. Anything else needs "
                            "--override \"reason\" (e.g. a temple priest NPC casting Cure Wounds for 10 GP — shown to the player).")
        g.override(a.override, f"heal {e['name']} {a.amount}")
    amt = a.amount
    if not re.fullmatch(r"\d+", amt):
        amt = g.roll(amt, f"{a.source} healing", None)["total"]
    M.heal(g, e, int(amt), a.source or "healing")


def cmd_temphp(g, a):
    e = g.get(a.who)
    if (e["kind"] == "pc" or e.get("side") == "ally") and not a.override:
        raise RuleError("Temporary HP for the party must come from a spell/feature (`cast`, `feature`) or --override \"reason\".")
    if a.override:
        g.override(a.override, f"{a.amount} temp HP to {e['name']}")
    M.temp_hp(g, e, int(a.amount), a.source or "effect")


def cmd_condition(g, a):
    for who in ids(a.who):
        e = g.get(who)
        if a.action == "add":
            M.add_condition(g, e, a.name, source=a.source, until=a.until, save=a.save, rounds=a.rounds,
                            caster=getattr(a, "caster", None), spell=getattr(a, "spell", None))
        elif a.name.lower() in ("concentration", "concentrating"):
            if not e.get("concentration"):
                raise RuleError(f"{e['name']} isn't concentrating on anything.")
            M.end_concentration(g, e, a.source or "ended")
        else:
            cond = next((c for c in e.get("conditions", []) if c["name"] == a.name.lower()), None)
            M.remove_condition(g, e, a.name)
            if cond:
                M.release_spell_if_unused(g, cond)


def cmd_exhaustion(g, a):
    e = g.get(a.who)
    n = int(a.delta)
    new = max(0, min(6, e.get("exhaustion", 0) + n))
    if not a.source:
        raise RuleError("Exhaustion changes need --source.")
    if n < 0 and e["kind"] == "pc" and not re.search(r"long rest|greater restoration|spell|potion", a.source, re.I) and not a.override:
        raise RuleError("Exhaustion is removed by Long Rests (1 level) or specific magic. Other sources need --override.")
    if a.override:
        g.override(a.override, f"exhaustion {n:+d} for {e['name']}")
    g.set(e, exhaustion=new)
    msg = f"{e['name']}'s Exhaustion is now {new} ({a.source})" + (" — −2×level to d20 tests and −5 ft Speed per level." if new else ".")
    if new >= 6:
        g.set(e, dead=True)
        msg += f" {e['name']} DIES from exhaustion."
    g.say(msg, kind="condition")


FEATURE_ACTIONS = {"Second Wind": "bonus", "Rage": "bonus", "Lay On Hands": "bonus", "Bardic Inspiration": "bonus",
                   "Channel Divinity": "action", "Wild Shape": "bonus", "Action Surge": None, "Innate Sorcery": "bonus",
                   "Indomitable": None, "Arcane Recovery": None, "Magical Cunning": None, "Favored Enemy": None,
                   "Focus Points": None, "Sorcery Points": None, "Divine Intervention": "action",
                   "Steady Aim": "bonus", "Fast Hands": "bonus", "Cutting Words": "reaction"}


def cmd_feature(g, a):
    from .core import has_feature, resources as res_of
    e = g.get(a.who)
    name = a.name
    res = res_of(e)
    key = next((k for k in res if k.lower() == name.lower()), None)
    if not key and not has_feature(e, name):
        raise RuleError(f"{e['name']} doesn't have the feature '{name}' (check the class table in rules/classes/).")
    amount = a.amount or 1
    if key:
        info = res[key]
        if key == "Lay On Hands":
            if info["max"] - info["used"] < amount:
                raise RuleError(f"Lay On Hands pool has {info['max'] - info['used']} HP left.")
        elif info["max"] - info["used"] < amount:
            raise RuleError(f"{e['name']} has no uses of {key} left ({info['used']}/{info['max']} used). They recharge on a "
                            f"{'Short or ' if info['short'] else ''}Long Rest.")
    act = FEATURE_ACTIONS.get(key or name.title())
    if (key or name).lower() == "steady aim" and M.combat(g) and M.economy(g, e["id"]).get("move_used", 0):
        raise RuleError("Steady Aim works only if you haven't moved this turn.")
    if M.combat(g) and act:
        M.use_action(g, e, act, key or name)
    if key:
        g.set(e, **{f"resources_used__{key}": info["used"] + amount})
    k = (key or name).lower()
    if k == "second wind":
        r = g.roll(f"1d10+{e['classes']['Fighter']}", "Second Wind", e["id"])
        M.heal(g, e, r["total"], "Second Wind")
    elif k == "rage":
        if any(x["name"] == "heavy" for x in []) or any(i.get("category") == "heavy" and i.get("equipped") for i in e.get("inventory", [])):
            raise RuleError("You can't Rage while wearing Heavy armor.")
        M.add_condition(g, e, "raging", source="Rage", rounds=100)
        g.say("   Rage: resistance to B/P/S damage, bonus Rage Damage on Strength attacks, Advantage on Strength checks/saves; no spellcasting or Concentration.")
        if e.get("concentration"):
            M.end_concentration(g, e, "entered a Rage")
    elif k == "lay on hands":
        t = g.get(a.target) if a.target else e
        M.heal(g, t, amount, "Lay On Hands")
    elif k == "action surge":
        if not M.combat(g) or M.current_id(g) != e["id"]:
            raise RuleError("Action Surge is used on your turn in combat.")
        M.set_economy(g, e["id"], action_surge=True)
        g.say(f"⚡ {e['name']} uses Action Surge — one additional action this turn.", kind="action")
    elif k == "steady aim":
        if M.combat(g):
            M.set_economy(g, e["id"], move_used=10 ** 4, steady_aim=True)  # Speed 0 for the rest of the turn
        g.say(f"🎯 {e['name']} takes Steady Aim — Advantage on the next attack this turn; Speed 0 until the turn ends.", kind="action")
    elif k == "bardic inspiration":
        t = g.get(a.target) if a.target else None
        if not t or t["id"] == e["id"]:
            raise RuleError("Bardic Inspiration targets another creature (--target).")
        die = srd.find("classes", "Bard")["levels"][e["classes"]["Bard"]].get("Bardic Die", "d6")
        g.set(t, effects=t.get("effects", []) + [{"name": f"Bardic Inspiration {die}", "from": e["id"]}])
        g.say(f"🎵 {e['name']} gives {t['name']} Bardic Inspiration ({die}) — add it to one failed d20 test within the hour.", kind="action")
    else:
        g.say(f"✦ {e['name']} uses {key or name}" + (f" ({amount})" if amount > 1 else "") + (f": {a.note}" if a.note else "") + ".", kind="action")
        g.note(f"  Resolve per rules/classes/*.md → {name}.")


def cmd_bardic(g, a):
    e = g.get(a.who)
    fx = next((f for f in e.get("effects", []) if f["name"].startswith("Bardic Inspiration")), None)
    if not fx:
        raise RuleError(f"{e['name']} has no Bardic Inspiration die.")
    die = fx["name"].split()[-1]
    r = g.roll(f"1{die}", "Bardic Inspiration", e["id"])
    g.set(e, effects=[f for f in e["effects"] if f is not fx and f != fx])
    g.say(f"🎵 {e['name']} adds Bardic Inspiration: +{r['total']} ({r['text']}) to the roll.", kind="roll")


def cmd_deathsave(g, a):
    M.death_save(g, g.get(a.who), now=a.now)


def cmd_stabilize(g, a):
    helper, dying = g.get(a.helper), g.get(a.who)
    if dying["hp"] > 0 or dying.get("dead"):
        raise RuleError(f"{dying['name']} isn't dying.")
    M.use_action(g, helper, "action", "stabilize")
    r = M.ability_check(g, helper, "medicine", dc=10, now=True)
    if r.get("success"):
        hrs = g.roll("1d4", f"{dying['name']} hours until regaining 1 HP", dying["id"])["total"]
        g.set(dying, death={"success": 0, "fail": 0, "stable": True, "wake_at": g.state["time"] + hrs * 60})
        g.say(f"{helper['name']} stabilizes {dying['name']} (they regain 1 HP in {hrs} hour(s) if left to rest).", kind="heal")


def cmd_legendary(g, a):
    e = g.get(a.who)
    left = e.get("legendary_resistance", 0) - e.get("legendary_resistance_used", 0)
    if left <= 0:
        raise RuleError(f"{e['name']} has no Legendary Resistance left.")
    g.set(e, legendary_resistance_used=e.get("legendary_resistance_used", 0) + 1)
    g.say(f"👑 {e['name']} uses Legendary Resistance — the failed save becomes a success! ({left - 1} left)", kind="roll")


def cmd_rest(g, a):
    members = [g.get(i) for i in ids(a.who)] if a.who else [e for e in g.pcs() if not e.get("dead")]
    if a.kind == "short":
        hd = {}
        for part in ids(a.hd):
            k, _, n = part.partition(":")
            hd[g.get(k)["id"]] = int(n or 1)
        focus = {}
        for part in ids(a.focus):
            k, _, item = part.partition(":")
            if not item:
                raise RuleError("--focus who:item-id (one magic item per creature)")
            if g.get(k)["id"] in focus:
                raise RuleError("A creature can focus on only one magic item per Short Rest.")
            M.find_item(g.get(k), item)
            focus[g.get(k)["id"]] = item
        M.short_rest(g, members, hd, focus)
    else:
        M.long_rest(g, members)


def cmd_time(g, a):
    mins = parse_duration(a.amount)
    if mins <= 0:
        raise RuleError("Time only moves forward.")
    if M.combat(g):
        raise RuleError("Time passes in rounds during combat (`combat next`).")
    M.require_no_dying(g, "letting time pass")
    g.emit("time.set", minutes=g.state["time"] + mins)
    M.after_time(g)
    g.say(f"⏳ {a.amount} pass{'es' if not a.amount.endswith('s') else ''}{' — ' + a.reason if a.reason else ''}. Now {fmt_time(g.state['time'])}.", kind="time")


def cmd_travel(g, a):
    pace = {"fast": 4, "normal": 3, "slow": 2}[a.pace]
    if M.combat(g):
        raise RuleError("You can't travel in the middle of combat.")
    M.require_no_dying(g, "travelling")
    miles = a.miles
    region = None
    if a.to:
        mid = a.map or next((k for k, m in g.state["maps"].items() if m["kind"] == "region"), None)
        if not mid:
            raise RuleError("No region map. `map gen region`")
        region = g.state["maps"][mid]
        start = g.state["view"].get("party_pos")
        if not start:
            raise RuleError("Set the party's region position first: `map party x,y`")
        tx, ty = xy(a.to)
        cost = {"p": 1, "g": 1, "s": 1, "d": 2, "f": 2, "F": 2, "h": 2, "w": 2, "M": 3, "K": 3}
        dist, parent = {tuple(start): 0}, {}
        import heapq
        pq = [(0, tuple(start))]
        roads = {tuple(p) for r in region.get("roads", []) for p in r}
        while pq:
            cst, cur = heapq.heappop(pq)
            if cur == (tx, ty):
                break
            for nx, ny in maps.neighbors({"grid": region["grid"], "w": region["w"], "h": region["h"]}, *cur):
                if not (0 <= nx < region["w"] and 0 <= ny < region["h"]):
                    continue
                t = region["grid"][ny][nx]
                if t in "OCL":
                    continue
                step = (1 if (nx, ny) in roads else cost.get(t, 1)) * (1.414 if nx != cur[0] and ny != cur[1] else 1)
                if cst + step < dist.get((nx, ny), 1e9):
                    dist[(nx, ny)] = cst + step
                    parent[(nx, ny)] = cur
                    heapq.heappush(pq, (cst + step, (nx, ny)))
        if (tx, ty) not in dist:
            raise RuleError("No overland route there (water without a boat?).")
        miles = round(dist[(tx, ty)] * region.get("miles_per_cell", 2), 1)
    if not miles:
        raise RuleError("travel <miles> or travel --to x,y")
    hours = miles / pace
    days, rem = divmod(hours, 8)
    total_min = int(days * 1440 + rem * 60)
    g.emit("time.set", minutes=g.state["time"] + total_min)
    if region:
        g.emit("view.set", party_pos=[tx, ty])
    M.after_time(g)
    g.say(f"🧭 The party travels {miles} miles at a {a.pace} pace ({pace} mph, 8 hours a day"
          f"{', difficult terrain counted' if region else ''}) — {int(days)} day(s) {rem:.1f} h. Now {fmt_time(g.state['time'])}.", kind="time")
    if a.pace == "fast":
        g.say("   Fast pace: Disadvantage on Wisdom (Perception/Survival) and Dexterity (Stealth) checks while travelling.")
    if a.pace == "slow":
        g.say("   Slow pace: Advantage on Wisdom (Perception/Survival) checks; the party can travel stealthily.")


def _reveal_pcs_on(g, mid):
    """Fog of war follows the party: recompute what every PC/ally on this map can see (after layout or light changes)."""
    for e in list(g.entities.values()):
        if e.get("token", {}).get("map") == mid:
            M.reveal_for(g, g.get(e["id"]))


# ====================================================================== items, coins, xp

def cmd_item(g, a):
    e = g.get(a.who)
    if a.action == "add":
        src = a.source or ""
        if not src and not a.purchase:
            raise RuleError("Items need --source (loot: <from where>, reward: <from whom>, found: <where>, starting, crafted).")
        if a.purchase:
            src = "purchase"
        elif not re.match(r"^(loot|reward|found|starting|crafted|gift|stolen|quest)\b", src, re.I):
            raise RuleError("--source must start with loot / reward / found / starting / crafted / gift / stolen / quest, "
                            "e.g. --source \"loot: bandit captain's chest\"")
        price = M.parse_coins(a.price) if a.price else None
        M.add_item(g, e, a.item, qty=a.qty, source=src, price=price, purchase=a.purchase, override=a.override, custom=a.custom,
                   identified=True if a.identified else None)
    elif a.action in ("remove", "drop", "sell", "give"):
        to = g.get(a.to) if a.to else None
        if a.action == "give" and not to:
            raise RuleError("give needs --to")
        M.remove_item(g, e, a.item, a.qty, "dropped" if a.action == "drop" else a.source or "removed", sell=a.action == "sell", to=to)
    elif a.action == "pickup":
        M.pick_up(g, e, a.item)
    elif a.action == "stash":
        if not a.to:
            raise RuleError("item stash <who> <item-id> --to <container-id> [--qty N]  (see `map container`)")
        M.stash_item(g, e, a.item, a.to, a.qty)
    elif a.action == "floor-record":
        # beta fix: put an item that was dropped before floor tracking existed onto the map — only if the log shows that drop
        line = f"{e['name']}: {a.qty}× {a.item} dropped."
        drops = sum(1 for f in g.state["feed"] if f.get("text") == line)
        recorded = sum(1 for m in g.state["maps"].values() for fl in m.get("floor", [])
                       if fl["item"]["name"] == a.item and fl.get("note", "").startswith(f"dropped by {e['name']}"))
        if drops <= recorded:
            raise RuleError(f"The log has no unrecorded drop \"{line}\" to put on the floor.")
        if not a.to:
            raise RuleError("floor-record needs --to x,y (where it was dropped)")
        x, y = xy(a.to)
        item = M.resolve_item(g, a.item) or {"name": a.item, "kind": "gear"}
        M.put_on_floor(g, e["token"]["map"], x, y, {**item, "qty": a.qty, "equipped": False, "source": "starting equipment"},
                       f"dropped by {e['name']} (recorded after a beta fix)")
    elif a.action == "equip":
        M.equip(g, e, a.item, True)
    elif a.action == "unequip":
        M.equip(g, e, a.item, False)
    elif a.action == "attune":
        M.attune(g, e, a.item, True)
    elif a.action == "unattune":
        M.attune(g, e, a.item, False)
    elif a.action == "use":
        M.use_item(g, e, a.item, a.to)
    elif a.action == "identify":
        # the Identify spell (cast it first), or the DM confirming another in-world way (a sage, a clear clue, a potion taste)
        if not a.how:
            raise RuleError('item identify <who> <item> --how "Identify spell (cast by wren)" | "tasted it" | ... (a Short Rest: `rest short --focus who:item`)')
        M.identify_item(g, e, a.item, a.how)
    elif a.action == "obscure":
        # beta repair / DM: mark a magic item the characters don't actually understand yet as unidentified
        it = M.find_item(e, a.item)
        if not it.get("magic"):
            raise RuleError(f"{it['name']} isn't magical.")
        if not a.how:
            raise RuleError('item obscure <who> <item> --how "why the characters don\'t know it yet"')
        g.set(e, inventory=[dict(i, identified=False) if i["id"] == it["id"] else i for i in e["inventory"]])
        g.say(f"❔ {e['name']}'s {it['name']} is marked unidentified — {a.how}.", kind="item")
    elif a.action == "refresh":
        # beta repair: re-read an inventory item's rules from the SRD (after an engine fix), keeping id, qty, source, notes
        it = M.find_item(e, a.item)
        fresh = M.resolve_item(g, it["name"])
        if not fresh:
            raise RuleError(f"{it['name']} isn't an SRD item.")
        keep = {k: it[k] for k in ("id", "qty", "equipped", "attuned", "source", "alias", "note", "identified", "lit") if k in it}
        g.set(e, inventory=[{**fresh, **keep} if i["id"] == it["id"] else i for i in e["inventory"]])
        g.say(f"🔧 {e['name']}'s {it['name']} re-read from the SRD (beta fix): now {fresh['kind']}" +
              (f", based on {fresh['base_name']}" if fresh.get("base_name") else "") + ".", kind="item")
    elif a.action == "unpack":
        M.unpack(g, e, a.item)
    elif a.action == "note":
        # flavour only: what a notable item really is (e.g. a disguised or heirloom weapon the engine treats as its SRD base). No mechanics change.
        if not a.text and not a.alias:
            raise RuleError('item note <who> <item> --text "what it is / looks like" [--alias "Display name"]')
        it = M.find_item(e, a.item)
        upd = {}
        if a.text:
            upd["note"] = a.text
        if a.alias:
            upd["alias"] = a.alias
        inv = [dict(i, **upd) if i["id"] == it["id"] else i for i in e["inventory"]]
        g.set(e, inventory=inv)
        g.say(f"🏷 {e['name']}'s {it['name']}" + (f" is now known as \"{a.alias}\"" if a.alias else "") + " — note added.", kind="item")
    elif a.action == "light":
        it = M.find_item(e, a.item)
        if not re.search(r"torch|lantern|candle", it["name"], re.I):
            raise RuleError("Only torches, lanterns and candles can be lit.")
        inv = [dict(i, lit=not i.get("lit")) if i["id"] == it["id"] else i for i in e["inventory"]]
        g.set(e, inventory=inv)
        g.say(f"🔥 {e['name']} {'lights' if not it.get('lit') else 'puts out'} the {it['name']}.")
        M.reveal_for(g, g.get(e["id"]))
    elif a.action == "recover-ammo":
        # SRD: after a fight you can recover half the ammunition you spent (item arg = ammo name, e.g. Arrows)
        encs = [x for x in g.state["encounters"] if "defeated" in x]
        if not encs or not encs[-1].get("ammo", {}).get(e["id"]):
            raise RuleError("No ammunition was spent in the last combat.")
        idx = len(encs)
        if any(x.get("recovered_for") == e["id"] and x.get("encounter") == idx for x in g.state["encounters"]):
            raise RuleError("Ammunition from that fight was already recovered.")
        n = encs[-1]["ammo"][e["id"]] // 2
        if n < 1:
            raise RuleError("Too little ammunition was spent to recover any (half, rounded down).")
        M.add_item(g, e, a.item, qty=n, source="found: recovered after combat")
        g.emit("encounter.log", recovered_for=e["id"], encounter=idx, qty=n)
    elif a.action == "card":
        it = M.find_item(e, a.item)
        out = Path(g.dir) / "views" / f"item-{it['id']}.svg"
        out.parent.mkdir(exist_ok=True)
        out.write_text(assets.item_card(it), encoding="utf-8")
        print(out)
    else:
        raise RuleError("item add|remove|drop|sell|give|equip|unequip|attune|unattune|use|light|recover-ammo|card")


def cmd_coins(g, a):
    e = g.get(a.who)
    delta = M.parse_coins(a.amount)
    if not a.source:
        raise RuleError("Coins need --source (loot: ..., reward: ..., spent: ..., sold: ...).")
    if delta > 0:
        cap = TIER_MAX_GP_AWARD[tier(g.party_level())] * 100
        if delta > cap and not a.override:
            raise RuleError(f"{M.fmt_cp(delta)} in one award exceeds the tier {tier(g.party_level())} guideline ({M.fmt_cp(cap)}). "
                            "Use --override \"reason\" (shown to the player) for a genuine hoard.")
        if a.override:
            g.override(a.override, f"award {M.fmt_cp(delta)} to {e['name']}")
    M.change_coins(g, e, delta, a.source)
    g.say(f"💰 {e['name']} {'gains' if delta > 0 else 'spends'} {M.fmt_cp(abs(delta))} ({a.source}). Purse: {M.fmt_cp(M.coins_total_cp(g.get(e['id'])))}.", kind="item")


def cmd_xp(g, a):
    members = [e for e in g.pcs() if not e.get("dead")]
    if a.action == "award":
        if a.encounter:
            encs = [x for x in g.state["encounters"] if "defeated" in x]
            if not encs:
                raise RuleError("No finished combat to award XP for.")
            last = encs[-1]
            if last.get("awarded") or any(x.get("awarded_encounter") == len(encs) for x in g.state["encounters"]):
                raise RuleError("XP for the last encounter was already awarded.")
            if not last["xp"]:
                raise RuleError("No enemies were defeated in the last combat (defeat = killed, knocked out, captured or routed "
                                "— for routed/captured foes use `npc` damage/conditions first, or --amount with a reason).")
            M.award_xp(g, members, last["xp"], "combat encounter")
            g.emit("encounter.log", awarded_encounter=len(encs))
        else:
            if not a.amount or not a.reason:
                raise RuleError("xp award --encounter, or --amount N --reason \"quest/trap/social encounter overcome\"")
            budget = srd.data()["xp_budget"][g.party_level()]["high"] * len(members)
            if a.amount > budget and not a.override:
                raise RuleError(f"{a.amount} XP exceeds a High-difficulty encounter's budget for this party ({budget}). "
                                "Larger story awards need --override.")
            if a.override:
                g.override(a.override, f"{a.amount} XP award")
            M.award_xp(g, members, a.amount, a.reason)
    elif a.action == "sync":
        # bring a character who joined late (or was made before this rule) up to the party's XP, never down
        if not a.who:
            raise RuleError("xp sync <character-id>")
        e = g.get(a.who)
        if e["kind"] != "pc":
            raise RuleError(f"{e['name']} isn't a party character.")
        xp, ms = M.party_xp(g, exclude=e["id"])
        if xp <= e.get("xp", 0) and ms <= e.get("milestones", 0):
            raise RuleError(f"{e['name']} already has the party's XP ({e.get('xp', 0)}).")
        g.set(e, xp=max(xp, e.get("xp", 0)), milestones=max(ms, e.get("milestones", 0)))
        g.say(f"⭐ {e['name']} is brought up to the party's XP ({max(xp, e.get('xp', 0))}), so the whole party levels together.", kind="xp")
    elif a.action == "milestone":
        if g.state["settings"].get("xp_mode") != "milestone":
            raise RuleError("Campaign uses XP, not milestones (`set xp_mode=milestone` before characters are made).")
        if not a.reason or len(a.reason) < 8:
            raise RuleError("A milestone needs the story reason (--reason).")
        for e in members:
            g.set(e, milestones=e.get("milestones", 0) + 1)
        g.say(f"⭐ Milestone reached: {a.reason} — every character may level up.", kind="xp")


# ====================================================================== maps

def cmd_map(g, a):
    s = g.state
    if a.action == "gen":
        seed = a.seed if a.seed is not None else (g.state["roll_count"] * 7919 + len(g.events) * 104729) % 10 ** 6
        kind = a.target or a.kind
        kw = {}
        if a.w:
            kw["w"] = a.w
        if a.h:
            kw["h"] = a.h
        if a.name:
            kw["name"] = a.name
        if kind == "wilderness" and a.biome:
            kw["biome"] = a.biome
        if kind == "arena":
            kw["preset"] = a.preset or "forest-clearing"
        if kind == "interior" and a.building:
            kw["kind"] = a.building
        if kind not in maps.GENERATORS:
            raise RuleError(f"map kinds: {', '.join(maps.GENERATORS)}")
        if kind == "interior" and (kw.get("w", 24) < 16 or kw.get("h", 18) < 14):
            raise RuleError("interior maps need at least --w 16 --h 14 (back rooms need the space); "
                            "for a narrow place, generate at that size and `map paint` it into shape")
        m = maps.GENERATORS[kind](seed, **kw)
        mid = a.id or srd.slug(m["name"])[:40]
        while mid in s["maps"]:
            mid += "-2"
        m["id"] = mid
        m["generator"] = {"kind": kind, "seed": seed, **{k: v for k, v in kw.items()}}
        g.emit("map.add", map=m)
        g.note(f"Generated {kind} map '{m['name']}' id={mid} ({m['w']}×{m['h']}, seed {seed}).")
        if a.show:
            show_map(g, mid)
    elif a.action == "list":
        for mid, m in s["maps"].items():
            print(f"{'*' if s['view'].get('map') == mid else ' '} {mid}: {m['name']} [{m['kind']}] {m['w']}x{m['h']}{' shown' if m.get('shown') else ''}")
    elif a.action == "show":
        show_map(g, a.target)
    elif a.action == "reveal" or a.action == "hide":
        m = s["maps"][a.target]
        cells = []
        if a.all:
            cells = [[x, y] for y in range(m["h"]) for x in range(m["w"])]
        elif a.room:
            r = next((r for r in m["rooms"] if r["n"] == a.room), None)
            if not r:
                raise RuleError(f"No room {a.room}.")
            cells = [[x, y] for y in range(r["y"] - 1, r["y"] + r["h"] + 1) for x in range(r["x"] - 1, r["x"] + r["w"] + 1)]
        elif a.rect:
            x1, y1, x2, y2 = [int(v) for v in a.rect.split(",")]
            cells = [[x, y] for y in range(min(y1, y2), max(y1, y2) + 1) for x in range(min(x1, x2), max(x1, x2) + 1)]
        else:
            raise RuleError("--all, --room N or --rect x1,y1,x2,y2")
        g.emit("map.reveal", id=m["id"], cells=cells, hide=a.action == "hide")
        g.note(f"{a.action}: {len(cells)} cells")
    elif a.action == "door":
        m = s["maps"][a.target]
        x, y = xy(a.at)
        c = maps.cell(m, x, y)
        new = {"open": "d", "close": "D", "reveal": "D", "break": "d"}.get(a.state)
        if c not in "DdS":
            raise RuleError(f"({x},{y}) isn't a door.")
        if c == "S" and a.state != "reveal":
            raise RuleError("That secret door hasn't been found yet (`map door ... reveal` after a successful check).")
        grid = [list(r) for r in m["grid"]]
        grid[y][x] = new
        feats = [dict(f, hidden=False) if f["type"] == "secret_door" and (f["x"], f["y"]) == (x, y) else f for f in m["features"]]
        g.emit("map.set", id=m["id"], set={"grid": ["".join(r) for r in grid], "features": feats})
        g.say(f"🚪 The door at ({x},{y}) is {({'reveal': 'discovered', 'open': 'opened', 'close': 'closed', 'break': 'broken'}).get(a.state, a.state)}.", kind="map")
        for e in g.pcs():
            if e.get("token", {}).get("map") == m["id"]:
                M.reveal_for(g, g.get(e["id"]))
    elif a.action == "feature":
        m = s["maps"][a.target]
        feats = [dict(f) for f in m["features"]]
        x, y = xy(a.at)
        f = next((f for f in feats if (f["x"], f["y"]) == (x, y)), None)
        if a.state == "reveal":
            if not f:
                raise RuleError("No feature there.")
            f["hidden"] = False
            g.say(f"⚠ Discovered: {f['name']} at ({x},{y}).", kind="map")
        elif a.state == "add":
            feats.append({"type": a.ftype or "poi", "x": x, "y": y, "name": a.name or "Point of interest", "hidden": a.hidden})
        elif a.state == "remove":
            feats = [ff for ff in feats if (ff["x"], ff["y"]) != (x, y)]
        g.emit("map.set", id=m["id"], set={"features": feats})
    elif a.action == "crop":
        m = s["maps"][a.target]
        if a.room:
            r = next(r for r in m["rooms"] if r["n"] == a.room)
            pad = a.pad
            sub = maps.crop(m, r["x"] - pad, r["y"] - pad, r["w"] + 2 * pad, r["h"] + 2 * pad, name=f"{m['name']} — {r['label']}")
        else:
            x1, y1, x2, y2 = [int(v) for v in a.rect.split(",")]
            sub = maps.crop(m, x1, y1, x2 - x1 + 1, y2 - y1 + 1)
        mid = a.id or srd.slug(sub["name"])[:40]
        while mid in s["maps"]:
            mid += "-2"
        sub["id"] = mid
        g.emit("map.add", map=sub)
        g.note(f"Cropped battle map {mid}")
        if a.show:
            show_map(g, mid)
    elif a.action == "paint":
        m = s["maps"][a.target]
        if a.char not in maps.TERRAIN:
            raise RuleError(f"Terrain codes: {', '.join(f'{k!r}={v[0]}' for k, v in maps.TERRAIN.items())}")
        grid = [list(r) for r in m["grid"]]
        for spec in a.at.split():
            if "-" in spec:
                (x1, y1), (x2, y2) = [xy(p) for p in spec.split("-")]
                for yy in range(min(y1, y2), max(y1, y2) + 1):
                    for xx in range(min(x1, x2), max(x1, x2) + 1):
                        grid[yy][xx] = a.char
            else:
                x, y = xy(spec)
                grid[y][x] = a.char
        g.emit("map.set", id=m["id"], set={"grid": ["".join(r) for r in grid]})
    elif a.action == "set":
        m = s["maps"][a.target]
        k, _, v = a.kv.partition("=")
        styles = {"walls": render.WALL_STYLES, "floor": render.FINE_STYLES, "wood": render.WOOD_STYLES, "stone": render.STONE_STYLES}
        if k not in ("name", "lighting", "fog", "theme", "accent", *styles):
            raise RuleError("map set name=...|lighting=bright|dim|dark|fog=true|false|theme=" + "|".join(render.THEMES) +
                            "|" + "|".join(f"{s}={'/'.join(o)}" for s, o in styles.items()) + "|accent=#rrggbb")
        if k in styles and v not in styles[k]:
            raise RuleError(f"{k}: " + "|".join(styles[k]))
        if k == "accent" and not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            raise RuleError("accent: a colour like #c9a14a")
        val = v if k != "fog" else v.lower() == "true"
        if k == "lighting" and v not in ("bright", "dim", "dark"):
            raise RuleError("lighting: bright|dim|dark")
        if k == "theme" and v not in render.THEMES:
            raise RuleError("theme: " + "|".join(render.THEMES))
        g.emit("map.set", id=m["id"], set={(f"style_{k}" if k in styles else k): val})
        if k in ("lighting", "fog"):
            _reveal_pcs_on(g, m["id"])
    elif a.action == "party":
        x, y = xy(a.target)
        g.emit("view.set", party_pos=[x, y])
        g.say(f"🧭 The party is at ({x},{y}) on the region map.", kind="map")
    elif a.action in ("poi", "poi-move", "poi-remove"):
        # points of interest: a notable object the characters have perceived, pinned to the tile it physically occupies,
        # clickable on the table and linked to its journal entry. Permanent until the room changes (move / remove it).
        if a.target not in s["maps"]:
            raise RuleError(f"No map '{a.target}'.")
        m = s["maps"][a.target]
        pois = [dict(p) for p in m.get("pois", [])]
        if a.action == "poi":
            if not a.at or not a.name:
                raise RuleError('map poi <map> x,y --name "Title" (--text "what they perceive" | --id <journal-id>)')
            x, y = xy(a.at)
            if not (0 <= x < m["w"] and 0 <= y < m["h"]):
                raise RuleError(f"({x},{y}) is outside {m['name']} ({m['w']}×{m['h']}).")
            if any((p["x"], p["y"]) == (x, y) for p in pois):
                raise RuleError(f"({x},{y}) already has a point of interest; move that one or pick the neighbouring tile.")
            jid = a.id
            if jid:
                if not any(j["id"] == jid for j in s.get("journal", [])):
                    raise RuleError(f"No journal entry '{jid}'.")
            else:
                if not a.text:
                    raise RuleError('map poi needs --text "what the characters perceive" (creates the journal entry) or --id <journal-id>')
                jid = f"j{len(s.get('journal', [])) + 1}"
                journal_add(g, {"kind": "text", "title": a.name, "text": a.text, "ref": a.text, "poi": {"map": m["id"], "x": x, "y": y}})
            pid = f"poi-{max([int(p['id'].split('-')[1]) for p in pois] + [0]) + 1}"
            pois.append({"id": pid, "x": x, "y": y, "name": a.name, "journal": jid})
            g.emit("map.set", id=m["id"], set={"pois": pois})
            g.say(f"📍 Noted on {m['name']}: {a.name} ({x},{y}) — click it on the map for its journal entry.", kind="map")
        else:
            p = next((p for p in pois if p["id"] == a.id), None)
            if not p:
                raise RuleError(f"No point of interest '{a.id}' on {m['name']} ({', '.join(q['id'] for q in pois) or 'none'}).")
            if not a.reason:
                raise RuleError("--reason \"what changed in the room\" (shown in the log)")
            if a.action == "poi-move":
                x, y = xy(a.at)
                pois = [dict(q, x=x, y=y) if q["id"] == p["id"] else q for q in pois]
                g.say(f"📍 {p['name']} moved to ({x},{y}) on {m['name']} — {a.reason}.", kind="map")
            else:
                pois = [q for q in pois if q["id"] != p["id"]]
                g.say(f"📍 {p['name']} is no longer on {m['name']} — {a.reason}. (Its journal entry remains.)", kind="map")
            g.emit("map.set", id=m["id"], set={"pois": pois})
    elif a.action == "icons":
        # search the vendored icon library for props: `map icons globe` / `map icons "cooking pot"`
        words = " ".join(w for w in (a.target, a.at, a.state) if w)
        if not words:
            raise RuleError("map icons <words> — e.g. `map icons cauldron`, `map icons book pile`")
        hits = assets.search_icons(words, 30)
        print(", ".join(hits) if hits else "No icons match; try a simpler word.")
    elif a.action in ("prop", "prop-move", "prop-remove"):
        # decoration drawn from an icon on a tile: a globe on a desk, a skull on a shelf, a harp in a corner.
        # With --blocks the square is filled (impassable, half cover); without it the piece is set dressing.
        m = s["maps"].get(a.target)
        if not m:
            raise RuleError(f"No map '{a.target}'.")
        props = [dict(p) for p in m.get("props", [])]
        grid = [list(r) for r in m["grid"]]
        if a.action == "prop":
            if not a.at or not a.icon:
                raise RuleError('map prop <map> x,y --icon <name> [--name "Brass globe"] [--blocks] [--size small|large] [--color #hex] [--rotate 30]')
            if not assets.has_icon(a.icon):
                near = assets.search_icons(a.icon.replace("-", " "), 8)
                raise RuleError(f"No icon '{a.icon}'." + (f" Close matches: {', '.join(near)}" if near else " Search with `map icons <words>`."))
            if a.color and not re.fullmatch(r"#[0-9a-fA-F]{6}", a.color):
                raise RuleError("--color: a colour like #6a4a2a")
            x, y = xy(a.at)
            if not (0 <= x < m["w"] and 0 <= y < m["h"]):
                raise RuleError(f"({x},{y}) is outside {m['name']} ({m['w']}×{m['h']}).")
            if any((p["x"], p["y"]) == (x, y) for p in props):
                raise RuleError(f"({x},{y}) already has a prop; remove it first or use the next tile.")
            n = 1
            while any(p["id"] == f"prop-{n}" for p in props):
                n += 1
            pr = {"id": f"prop-{n}", "x": x, "y": y, "icon": a.icon, "name": a.name or a.icon.replace("-", " ")}
            for k in ("size", "color", "rotate"):
                if getattr(a, k):
                    pr[k] = getattr(a, k)
            change = {"props": props + [pr]}
            if a.blocks:
                if maps.move_cost(m, x, y) is None:
                    pr["on"] = grid[y][x]          # sits on a piece that already fills the square
                else:
                    pr["floor"] = grid[y][x]
                    grid[y][x] = "`"
                    change["grid"] = ["".join(r) for r in grid]
            g.emit("map.set", id=m["id"], set=change)
            g.say(f"🪑 {pr['name']} placed at ({x},{y}) on {m['name']}" + (" (fills the square)" if a.blocks else "") + ".", kind="map")
        else:
            p = next((p for p in props if p["id"] == a.id), None)
            if not p:
                raise RuleError(f"No prop '{a.id}' on {m['name']} ({', '.join(q['id'] for q in props) or 'none'}).")
            if not a.reason:
                raise RuleError('--reason "what happened to it" (shown in the log)')
            change = {}
            if p.get("floor") and grid[p["y"]][p["x"]] == "`":
                grid[p["y"]][p["x"]] = p["floor"]
            if a.action == "prop-move":
                x, y = xy(a.at)
                q = dict(p, x=x, y=y)
                q.pop("floor", None)
                if p.get("floor"):
                    q["floor"] = grid[y][x]
                    grid[y][x] = "`"
                props = [q if r["id"] == p["id"] else r for r in props]
                g.say(f"🪑 {p['name']} moved to ({x},{y}) on {m['name']} — {a.reason}.", kind="map")
            else:
                props = [r for r in props if r["id"] != p["id"]]
                g.say(f"🪑 {p['name']} is gone from {m['name']} — {a.reason}.", kind="map")
            change["props"] = props
            change["grid"] = ["".join(r) for r in grid]
            g.emit("map.set", id=m["id"], set=change)
    elif a.action in ("container", "container-remove"):
        # a tile that holds things: a chest, a strongbox, a hidden cache. Items stashed there are listed inside it.
        m = s["maps"].get(a.target)
        if not m:
            raise RuleError(f"No map '{a.target}'.")
        boxes = [dict(c) for c in m.get("containers", [])]
        if a.action == "container":
            if not a.at or not a.name:
                raise RuleError('map container <map> x,y --name "Miller\'s chest" [--text "what it looks like"] [--id chest-1]')
            x, y = xy(a.at)
            if any((c["x"], c["y"]) == (x, y) for c in boxes):
                raise RuleError(f"There's already a container at ({x},{y}).")
            n = 1
            while any(c["id"] == f"box-{n}" for c in boxes):
                n += 1
            box = {"id": a.id or f"box-{n}", "x": x, "y": y, "name": a.name, "text": a.text or ""}
            # anything already lying on that tile goes into it
            floor = [dict(f, **({"in": box["id"]} if (f["x"], f["y"]) == (x, y) and not f.get("in") else {})) for f in m.get("floor", [])]
            g.emit("map.set", id=m["id"], set={"containers": boxes + [box], "floor": floor})
            inside = sum(1 for f in floor if f.get("in") == box["id"])
            g.say(f"🧰 {box['name']} at ({x},{y}) on {m['name']}" + (f", holding {inside} item(s) already there" if inside else "") + ".",
                  kind="map")
        else:
            box = next((c for c in boxes if c["id"] == a.id), None)
            if not box or not a.reason:
                raise RuleError("map container-remove <map> --id box-1 --reason \"...\"  (its items stay on the floor)")
            floor = [{k: v for k, v in f.items() if not (k == "in" and v == box["id"])} for f in m.get("floor", [])]
            g.emit("map.set", id=m["id"], set={"containers": [c for c in boxes if c["id"] != box["id"]], "floor": floor})
            g.say(f"🧰 {box['name']} is gone from {m['name']} — {a.reason}. Its contents are left on the floor.", kind="map")
    elif a.action == "label":
        m = s["maps"][a.target]
        x, y = xy(a.at)
        g.emit("map.set", id=m["id"], set={"labels": m["labels"] + [{"x": x, "y": y, "text": a.name, "hidden": a.hidden}]})
    elif a.action == "from-image":
        asset = s["assets"].get(a.target)
        if not asset:
            raise RuleError("No such asset. `asset fetch <url>` or `asset import <file>` first.")
        w, h = a.w or 30, a.h or 20
        m = maps.new_map("battle", a.name or asset["name"], w, h, fill=".", seed=0)
        m["fog"] = False
        m["revealed"] = ["1" * w for _ in range(h)]
        m["background"] = asset["id"]
        mid = a.id or srd.slug(m["name"])[:40]
        m["id"] = mid
        g.emit("map.add", map=m)
        g.note(f"Image battle map {mid} ({w}x{h} squares). Paint walls with `map paint {mid} # x1,y1-x2,y2`.")
    elif a.action == "render":
        m = s["maps"][a.target]
        out = Path(a.out) if a.out else Path(g.dir) / "views" / f"map-{m['id']}{'-dm' if a.dm else ''}.svg"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(views.map_svg(g, m["id"], "dm" if a.dm else "player"), encoding="utf-8")
        print(out)
    elif a.action == "ascii":
        m = s["maps"][a.target]
        pos = {(e["token"]["x"], e["token"]["y"]): e for e in g.entities.values() if e.get("token", {}).get("map") == m["id"]}
        print("    " + "".join(str(x % 10) for x in range(m["w"])))
        for y, row in enumerate(m["grid"]):
            line = "".join((pos[(x, y)]["name"][0].upper() if pos[(x, y)]["kind"] == "pc" else pos[(x, y)]["name"][0].lower()) if (x, y) in pos else c for x, c in enumerate(row))
            print(f"{y:>3} {line}")
        for r in m.get("rooms", []):
            print(f"  room {r['n']}: {r['label']} at ({r['x']},{r['y']}) {r['w']}x{r['h']}")
        for f in m.get("features", []):
            print(f"  feature: {f['type']} {f.get('name')} ({f['x']},{f['y']}){' HIDDEN' if f.get('hidden') else ''}")
    elif a.action == "import-grid":
        # hand-drawn layout: a text file, one row per line, using the terrain codes in dm/visuals.md
        mid = a.target
        if mid not in s["maps"]:
            raise RuleError(f"No map '{mid}'. Create one first (map gen ...), then import a grid into it.")
        if not a.out:
            raise RuleError("map import-grid <id> --out <grid.txt>")
        rows = [r.rstrip("\n") for r in Path(a.out).read_text(encoding="utf-8").splitlines() if r.strip() and not r.startswith(";")]
        width = max(len(r) for r in rows)
        rows = [r.ljust(width, "#") for r in rows]
        bad = sorted({ch for r in rows for ch in r if ch not in maps.TERRAIN})
        if bad:
            raise RuleError(f"Unknown terrain codes in grid: {' '.join(repr(b) for b in bad)}")
        m = s["maps"][mid]
        g.emit("map.set", id=mid, set={"grid": rows, "w": width, "h": len(rows), "rooms": [], "features": [], "labels": [], "floor": [],
                                        "revealed": ["1" * width] * len(rows) if not m.get("fog") else ["0" * width] * len(rows)})
        print(f"Imported a {width}×{len(rows)} grid into '{m['name']}'.")
        _reveal_pcs_on(g, mid)
    elif a.action in ("link", "unlink"):
        # physically connected areas (floors of a building, a stair to a cellar): shown together in the map tabs
        other = a.at
        if a.target not in s["maps"] or other not in s["maps"]:
            raise RuleError("map link <map-a> <map-b>  (both must exist)")
        for x, y in ((a.target, other), (other, a.target)):
            links = [l for l in s["maps"][x].get("links", []) if l != y] + ([y] if a.action == "link" else [])
            g.emit("map.set", id=x, set={"links": links})
        g.note(f"  {'Linked' if a.action == 'link' else 'Unlinked'} {s['maps'][a.target]['name']} ↔ {s['maps'][other]['name']}.")
    elif a.action == "snapshot":
        mid = a.target or s["view"].get("map")
        if mid not in s["maps"]:
            raise RuleError(f"No map '{mid}'.")
        print(f"📸 Snapshot of '{s['maps'][mid]['name']}' → {views.snapshot_map(g, mid, why='manual snapshot')}")
    else:
        raise RuleError("map gen|list|show|reveal|hide|door|feature|crop|paint|set|party|label|from-image|render|ascii|snapshot")


def show_map(g, mid):
    if mid not in g.state["maps"]:
        raise RuleError(f"No map '{mid}'.")
    prev = g.state["view"].get("map")
    if prev and prev != mid and prev in g.state["maps"] and g.state["maps"][prev]["kind"] != "region":
        path = views.snapshot_map(g, prev, why=f"party moved to {g.state['maps'][mid]['name']}")
        g.note(f"  📸 Saved the exact state of '{g.state['maps'][prev]['name']}' → {path}")
    g.emit("map.set", id=mid, set={"shown": True})
    g.emit("view.set", map=mid)
    m = g.state["maps"][mid]
    g.say(f"🗺 Map: {m['name']}", kind="map")
    for e in g.pcs():
        if e.get("token", {}).get("map") == mid:
            M.reveal_for(g, g.get(e["id"]))


# ====================================================================== assets & presentation

def cmd_asset(g, a):
    s = g.state
    if a.action == "icon":
        for n in assets.search_icons(" ".join(a.args), 25):
            print(n)
        return
    if a.action in ("fetch", "import"):
        src = a.args[0]
        if not a.license:
            raise RuleError("--license is required (e.g. CC0, CC-BY-4.0, public domain, 'own work'). Only use images you may use.")
        aid = srd.slug(a.name or Path(src).stem)[:32] or "asset"
        while aid in s["assets"]:
            aid += "-2"
        if a.action == "fetch":
            try:
                data, ctype = assets.fetch(src, g.dir)
            except Exception as err:
                raise RuleError(f"Couldn't fetch image: {err}")
        else:
            p = Path(src)
            if not p.exists():
                raise RuleError(f"No file {src}")
            import mimetypes
            data, ctype = p.read_bytes(), (mimetypes.guess_type(str(p))[0] or "")
            if p.suffix.lower() == ".svg":
                ctype = "image/svg+xml"
            if ctype not in assets.ALLOWED_TYPES:
                raise RuleError(f"Unsupported file type {ctype}")
        path, sha = assets.save_file(g.dir, data, ctype, aid)
        meta = {"id": aid, "name": a.name or aid, "kind": a.kind or "image", "file": path.name, "sha256": sha,
                "license": a.license, "credit": a.credit or "", "source": src, "public": not a.private}
        g.emit("asset.add", asset=meta)
        g.note(f"Asset {aid} saved ({len(data) // 1024} KB, sha256 {sha[:12]}).")
        if a.item:
            set_item_art(g, a.item, aid)
        if a.portrait:
            e = g.get(a.portrait)
            g.set(e, portrait=aid)
            g.say(f"🖼 New portrait for {e['name']}.", kind="asset")
        return
    if a.action == "draw":
        # Claude-authored SVG art (portraits, handouts, scenes). Scripts are rejected.
        src = Path(a.args[0])
        text = src.read_text(encoding="utf-8")
        if not text.lstrip().startswith("<svg"):
            raise RuleError("draw expects an SVG file.")
        aid = srd.slug(a.name or src.stem)[:32]
        while aid in s["assets"]:
            aid += "-2"
        path, sha = assets.save_file(g.dir, text.encode(), "image/svg+xml", aid)
        g.emit("asset.add", asset={"id": aid, "name": a.name or aid, "kind": a.kind or "art", "file": path.name, "sha256": sha,
                                   "license": "original (generated for this campaign)", "credit": "DM", "source": "generated", "public": not a.private})
        if a.portrait:
            g.set(g.get(a.portrait), portrait=aid)
        if a.item:
            set_item_art(g, a.item, aid)
        g.note(f"Asset {aid} registered.")
        return
    if a.action == "portrait":
        # Pin a portrait. Without this, every creature is drawn live from its look and description (and updates with them).
        e = g.get(a.args[0])
        if a.clear:
            g.set(e, portrait=None)
            g.note(f"{e['name']} is drawn live from their look again.")
            return
        svg = assets.portrait_svg(e) if a.style == "heraldic" else art.portrait_svg(e)
        aid = srd.slug(f"portrait-{e['id']}")
        while aid in s["assets"]:
            aid += "-2"
        path, sha = assets.save_file(g.dir, svg.encode(), "image/svg+xml", aid)
        g.emit("asset.add", asset={"id": aid, "name": f"{e['name']} portrait", "kind": "portrait", "file": path.name, "sha256": sha,
                                   "license": "generated; icons CC BY 3.0 game-icons.net", "credit": "game-icons.net", "source": "generated", "public": True})
        g.set(e, portrait=aid)
        g.note(f"Portrait {aid} pinned (it no longer follows `asset look` changes; `asset portrait {e['id']} --clear` to go back to live art).")
        return
    if a.action == "look":
        # What a creature looks like, feature by feature. The live table redraws its portrait and token from this.
        e = g.get(a.args[0])
        if getattr(a, "like", None):
            # keep another creature's face: an NPC who joins the party as a character, a double, a twin
            other = g.get(a.like)
            kept = other.get("art_of") or {"seed": other["id"], "name": other.get("name", ""),
                                             "style": art._style_for(other), "species": art.species_of(other)}
            g.set(e, art_of=kept)
            desc = other.get("appearance") or (other.get("bio") or {}).get("appearance")
            if desc and not (e.get("appearance") or (e.get("bio") or {}).get("appearance")):
                g.set(e, appearance=desc)
            g.note(f"🎨 {e['name']} now looks like {other['name']} did.")
        fields = {f: getattr(a, f"look_{f}") for f in art.LOOK_FIELDS if getattr(a, f"look_{f}", None)}
        if a.clear:
            drop = art.LOOK_FIELDS if a.clear == "all" else [x.strip() for x in a.clear.split(",")]
            bad = [x for x in drop if x not in art.LOOK_FIELDS]
            if bad:
                raise RuleError(f"Unknown look field(s): {', '.join(bad)}. Fields: {', '.join(art.LOOK_FIELDS)}")
            g.set(e, **{f"look__{f}": None for f in drop if f in (e.get("look") or {})})
        if fields:
            g.set(e, **{f"look__{k}": v for k, v in fields.items()})
        if fields or a.clear:
            if e.get("portrait"):
                g.note(f"  Note: {e['name']} has a pinned portrait ({e['portrait']}); `asset portrait {e['id']} --clear` to show the live art.")
            g.note("🎨 Look updated.")
        g.note(art.describe_look(g.get(e["id"])))
        return
    if a.action == "art":
        # Write the generated picture to a file so the DM can look at it (or hand-edit it and `asset draw` it back).
        ref = a.args[0] if a.args else ""
        if ":" in ref:
            owner, _, iid = ref.partition(":")
            if owner == "srd":
                it = M.resolve_item(g, iid)
                if not it:
                    raise RuleError(f"No SRD item {iid}")
                svg, name = itemart.item_svg({**it, "identified": True}), srd.slug(it["name"])
            else:
                it = M.find_item(g.get(owner), iid)
                svg, name = itemart.item_svg(it), f"{owner}-{it['id']}"
        else:
            e = g.get(ref)
            svg = art.face_svg(e) if a.crop == "face" else art.portrait_svg(e)
            name = f"{e['id']}-{a.crop or 'portrait'}"
        out = Path(a.out) if a.out else Path(g.dir) / "views" / "art" / f"{name}.svg"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(svg, encoding="utf-8")
        g.note(f"Wrote {out}")
        return
    if a.action == "list":
        for k, v in s["assets"].items():
            print(f"{k}: {v['name']} [{v['kind']}] {v['license']} — {v.get('credit', '')} ({v['source'][:60]})")
        return
    raise RuleError("asset icon|fetch|import|draw|portrait|look|art|list")


def set_item_art(g, ref, aid):
    """Give one inventory item its own picture (drawn or fetched) instead of the generated illustration."""
    owner, _, iid = ref.partition(":")
    e = g.get(owner)
    it = M.find_item(e, iid)
    g.set(e, inventory=[dict(i, art=aid) if i["id"] == it["id"] else i for i in e["inventory"]])
    g.note(f"  {e['name']}'s {it['name']} now shows {aid}.")


# ====================================================================== table animation (DM-controlled)

ANIM_DEFAULTS = {"speed": 1.0, "moves": "on", "attacks": "on", "numbers": "on", "turns": "on", "camera": "follow", "dice": "on",
                 "shake": "on", "sync": "on", "tokens": "art", "ambient": "none", "intensity": 0.6}
ANIM_PRESETS = {
    "cinematic": {"speed": 0.8, "moves": "on", "attacks": "on", "numbers": "on", "turns": "on", "camera": "follow", "dice": "on", "shake": "on", "sync": "on"},
    "standard": {"speed": 1.0, "moves": "on", "attacks": "on", "numbers": "on", "turns": "on", "camera": "follow", "dice": "on", "shake": "on", "sync": "on"},
    "quick": {"speed": 2.0, "moves": "on", "attacks": "on", "numbers": "on", "turns": "off", "camera": "follow", "dice": "off", "shake": "off", "sync": "off"},
    "off": {"moves": "off", "attacks": "off", "numbers": "off", "turns": "off", "camera": "off", "dice": "off", "shake": "off", "sync": "off"},
}
ANIM_CHOICES = {"moves": ("on", "off"), "attacks": ("on", "off"), "numbers": ("on", "off"), "turns": ("on", "off"),
                "camera": ("follow", "off"), "dice": ("on", "off"), "shake": ("on", "off"), "sync": ("on", "off"),
                "tokens": ("art", "icon"), "ambient": ("none", "rain", "snow", "fog", "embers", "ash", "motes", "storm")}
FX_EFFECTS = ("burst", "ring", "beam", "bolt", "projectile", "flash", "shake", "banner", "focus", "ping", "float", "sparkle", "smoke")
FX_COLORS = {"fire": "#ff6a1a", "cold": "#6ad8ff", "ice": "#6ad8ff", "lightning": "#bfe4ff", "acid": "#9ae02a", "poison": "#6ac04a",
             "necrotic": "#8a4ac0", "radiant": "#ffe28a", "holy": "#ffe28a", "force": "#b89aff", "psychic": "#ff6ad8",
             "thunder": "#9ab0ff", "blood": "#c8102a", "shadow": "#3a2a5a", "arcane": "#9a6af0", "nature": "#5ac84a",
             "gold": "#e0b448", "white": "#ffffff", "black": "#111111", "red": "#e0302a", "green": "#3ac85a", "blue": "#3a8af0",
             "purple": "#9a4ae0", "orange": "#ff8a2a", "yellow": "#ffe04a"}


def anim_settings(g):
    return {**ANIM_DEFAULTS, **(g.state["view"].get("anim") or {})}


def _fx_point(g, ref, mid):
    """A creature id or x,y → [x, y] on map mid (creatures must be on that map)."""
    if not ref:
        return None
    if re.match(r"^\s*\d+\s*,\s*\d+\s*$", ref):
        return list(xy(ref))
    e = g.get(ref)
    t = e.get("token")
    if not t or t.get("map") != mid:
        raise RuleError(f"{e['name']} isn't on map {mid}.")
    return {"id": e["id"]}


def cmd_fx(g, a):
    """How the live table animates (the DM's call), plus one-off visual effects. Visual only: nothing here changes the game."""
    cur = anim_settings(g)
    if a.action in ("status", "show"):
        g.note("Table animation: " + ", ".join(f"{k}={v}" for k, v in cur.items()))
        return
    if a.action == "preset":
        name = (a.args or [""])[0]
        if name not in ANIM_PRESETS:
            raise RuleError(f"fx preset {'|'.join(ANIM_PRESETS)}")
        g.emit("view.set", anim={**cur, **ANIM_PRESETS[name], "preset": name})
        g.note(f"🎞 Table animation preset: {name}.")
        return
    if a.action == "set":
        new = dict(cur)
        for kv in a.args:
            if "=" not in kv:
                raise RuleError(f"fx set key=value ... (got '{kv}'). Keys: speed, {', '.join(ANIM_CHOICES)}, intensity")
            k, v = [x.strip().lower() for x in kv.split("=", 1)]
            if k in ("speed", "intensity"):
                try:
                    f = float(v.rstrip("x"))
                except ValueError:
                    raise RuleError(f"{k} must be a number")
                lo, hi = (0.25, 4.0) if k == "speed" else (0.1, 1.0)
                if not lo <= f <= hi:
                    raise RuleError(f"{k} must be between {lo} and {hi}")
                new[k] = f
            elif k in ANIM_CHOICES:
                v = {"true": "on", "yes": "on", "false": "off", "no": "off", "none": "none"}.get(v, v)
                if k == "camera" and v == "on":
                    v = "follow"
                if v not in ANIM_CHOICES[k]:
                    raise RuleError(f"{k}: {'|'.join(ANIM_CHOICES[k])}")
                new[k] = v
            else:
                raise RuleError(f"Unknown fx setting '{k}'. Keys: speed, {', '.join(ANIM_CHOICES)}, intensity")
        new["preset"] = "custom"
        g.emit("view.set", anim=new)
        g.note("🎞 Table animation: " + ", ".join(f"{k}={v}" for k, v in new.items()))
        return
    if a.action == "ambient":
        kind = (a.args or ["none"])[0].lower()
        if kind not in ANIM_CHOICES["ambient"]:
            raise RuleError(f"fx ambient {'|'.join(ANIM_CHOICES['ambient'])} [--intensity 0.1-1]")
        new = {**cur, "ambient": kind}
        if a.intensity is not None:
            if not 0.1 <= a.intensity <= 1:
                raise RuleError("--intensity must be between 0.1 and 1")
            new["intensity"] = a.intensity
        g.emit("view.set", anim=new)
        g.note(f"🌦 Ambient: {kind}.")
        return
    if a.action in ("camera", "focus"):
        a.action, a.args = "play", ["focus"] + list(a.args)
    if a.action != "play":
        raise RuleError("fx status | preset cinematic|standard|quick|off | set key=value ... | ambient <kind> | play <effect> ... | camera <id|x,y|fit>")
    if not a.args or a.args[0] not in FX_EFFECTS:
        raise RuleError(f"fx play {'|'.join(FX_EFFECTS)} [--at x,y|--on id] [--from id|x,y --to id|x,y] [--color fire|#hex] [--radius ft] [--text ...]")
    eff = a.args[0]
    rest = a.args[1:]
    mid = a.map or g.state["view"].get("map")
    cue = {"fx": eff}
    if eff in ("banner", "float") and (a.text or rest):
        cue["label"] = (a.text or " ".join(rest))[:120]
    elif eff == "focus" and rest:
        if rest[0] == "fit":
            cue["fit"] = True
        else:
            cue["at"] = _fx_point(g, rest[0], mid)
    at = a.on or a.at
    if at:
        cue["at"] = _fx_point(g, at, mid)
    if a.src or a.dst:
        if not (a.src and a.dst):
            raise RuleError("--from and --to go together.")
        cue["from"], cue["to"] = _fx_point(g, a.src, mid), _fx_point(g, a.dst, mid)
    if eff in ("burst", "ring", "ping", "sparkle", "smoke", "float") and "at" not in cue:
        raise RuleError(f"fx play {eff} needs --at x,y or --on <creature>.")
    if eff in ("beam", "bolt", "projectile") and "from" not in cue:
        raise RuleError(f"fx play {eff} needs --from and --to.")
    if eff == "focus" and "at" not in cue and not cue.get("fit"):
        raise RuleError("fx camera <creature|x,y|fit>")
    if eff == "float" and not cue.get("label"):
        raise RuleError('fx play float --on <creature> --text "..."')
    if a.color:
        c = a.color.lower()
        if c not in FX_COLORS and not re.match(r"^#[0-9a-f]{6}$", c):
            raise RuleError(f"--color: {', '.join(FX_COLORS)} or #rrggbb")
        cue["color"] = FX_COLORS.get(c, c)
    if a.radius:
        cue["radius"] = max(5, min(120, a.radius))
    cue["map"] = mid
    what = {"focus": "camera", "banner": f"banner “{cue.get('label', '')}”"}.get(eff, eff)
    g.say(f"🎞 {what}", kind="fx", **cue)


def _anchor(g, ref):
    """The creature a line belongs to (id, full name or first name; the current map's creatures first), if the players
    can see it: its token gets the speech bubble or caption on the live table."""
    if not ref:
        return None
    ents = list(g.entities.values())
    here = (g.state.get("view") or {}).get("map")
    ents.sort(key=lambda e: 0 if (e.get("token") or {}).get("map") == here else 1)
    norm = lambda s: re.sub(r"[\s\-_']+", " ", s.strip().lower())  # noqa: E731  ('jory-brannock' == 'Jory Brannock')
    r = norm(ref)
    e = (g.entities.get(ref) or next((e for e in ents if norm(e["name"]) == r), None)
         or next((e for e in ents if norm(e["name"]).split()[0] == r.split()[0]), None))
    return e["id"] if e and not e.get("hidden") and e.get("token") else None


def cmd_say(g, a):
    text = " ".join(a.text)
    if a.speaker:
        who = _anchor(g, a.speaker)
        g.say(f"“{text}”", kind="speech", speaker=a.speaker, **({"who": who} if who else {}))
    else:
        who = _anchor(g, a.at)
        if a.at and not who:
            g.note(f"  (no visible token for '{a.at}': the line shows in the story strip only)")
        g.say(text, kind="narration", **({"who": who} if who else {}))


def cmd_scene(g, a):
    scene = {"title": a.title, "text": a.desc or "", "image": a.image, "time": fmt_time(g.state["time"])}
    if a.image and a.image not in g.state["assets"]:
        raise RuleError(f"No asset '{a.image}'.")
    g.emit("view.set", scene=scene)
    g.say(f"🎬 {a.title}" + (f" — {a.desc}" if a.desc else ""), kind="scene")
    if a.map:
        show_map(g, a.map)


def cmd_show(g, a):
    kind, ref = a.kind, a.ref
    handout = {"kind": kind, "ref": ref, "title": a.title or ""}
    if kind == "item":
        owner, _, iid = ref.partition(":")
        e = g.get(owner)
        it = M.find_item(e, iid)
        handout.update({"title": it["name"], "owner": e["id"], "item": it["id"]})
    elif kind == "creature":
        e = g.get(ref)
        if e.get("hidden"):
            raise RuleError(f"{e['name']} is hidden from the players.")
        handout["title"] = e["name"]
    elif kind == "asset":
        if ref not in g.state["assets"]:
            raise RuleError(f"No asset {ref}")
        handout["title"] = a.title or g.state["assets"][ref]["name"]
    elif kind == "text":
        handout.update({"title": a.title or "Handout", "text": ref})
    elif kind == "srd-item":
        mi = srd.find("magic_items", ref) or srd.find("weapons", ref) or srd.find("armor", ref) or srd.find("gear", ref)
        if not mi:
            raise RuleError(f"No SRD item {ref}")
        handout["title"] = mi["name"]
    elif kind == "clear":
        g.emit("view.set", handout=None)
        return
    else:
        raise RuleError("show item <owner:item-id> | creature <id> | asset <id> | text \"...\" --title | srd-item <name> | clear")
    g.emit("view.set", handout=handout)
    g.say(f"📜 Shown to the players: {handout['title']}", kind="handout")
    journal_add(g, handout)


def journal_add(g, handout, note=None):
    """The players' journal: every handout, card and clue they've been shown, kept for later."""
    j = g.state.get("journal", [])
    entry = {**handout, "id": f"j{len(j) + 1}", "time": fmt_time(g.state["time"]), "session": g.state["session"]}
    if note:
        entry["note"] = note
    g.emit("journal.add", entry=entry)


def cmd_journal(g, a):
    if a.action != "add":
        raise RuleError('journal add "text" --title "..." (adds a note to the players\' journal)')
    if not a.text or not a.title:
        raise RuleError('journal add "text" --title "..."')
    journal_add(g, {"kind": "text", "title": a.title, "text": a.text, "ref": a.text})
    g.say(f"📓 Added to the journal: {a.title}", kind="handout")


def cmd_homebrew(g, a):
    if not a.reason or len(a.reason) < 10:
        raise RuleError("Homebrew needs a --reason (why the SRD doesn't cover it). It's shown to the player.")
    entry = json.loads(Path(a.file).read_text(encoding="utf-8"))
    kind = a.kind
    need = {"monsters": ["name", "ac", "hp", "speed", "abilities", "cr", "xp", "actions"],
            "items": ["name", "kind", "rarity", "description"],
            "subclasses": ["class", "name", "features"],
            "species": ["name", "size", "speed", "traits"], "backgrounds": ["name", "abilities", "feat", "skills", "tool", "equipment"]}
    if kind not in need:
        raise RuleError(f"homebrew kinds: {', '.join(need)}")
    missing = [k for k in need[kind] if k not in entry]
    if missing:
        raise RuleError(f"Homebrew {kind[:-1]} is missing fields: {', '.join(missing)}")
    if kind == "monsters":
        cr_xp = {"0": 10, "1/8": 25, "1/4": 50, "1/2": 100, "1": 200, "2": 450, "3": 700, "4": 1100, "5": 1800, "6": 2300,
                 "7": 2900, "8": 3900, "9": 5000, "10": 5900, "11": 7200, "12": 8400, "13": 10000, "14": 11500, "15": 13000}
        if str(entry["cr"]) in cr_xp and entry["xp"] != cr_xp[str(entry["cr"])]:
            raise RuleError(f"XP for CR {entry['cr']} is {cr_xp[str(entry['cr'])]} (rules/core/11-reading-stat-blocks.md).")
        entry.setdefault("slug", srd.slug(entry["name"]))
        for k, v in (("size", "Medium"), ("type", "Humanoid"), ("alignment", "Neutral"), ("init", 0), ("skills", {}),
                     ("resist", []), ("immune", []), ("vulnerable", []), ("condition_immune", []), ("darkvision", 0),
                     ("passive_perception", 10), ("pb", 2), ("languages", ""), ("multiattack", 1), ("hp_dice", None)):
            entry.setdefault(k, v)
    if kind == "items":
        if entry["rarity"] not in ("Common", "Uncommon", "Rare", "Very Rare", "Legendary", "Artifact", "Mundane"):
            raise RuleError("rarity must be Common/Uncommon/Rare/Very Rare/Legendary/Artifact/Mundane")
        entry["magic"] = entry["rarity"] != "Mundane"
        entry["homebrew"] = True
        entry.setdefault("value_cp", 0)
    key = srd.slug(entry["name"])
    if kind == "subclasses":
        hb = dict(g.state["homebrew"].get("subclasses", {}).get(srd.slug(entry["class"]), {}))
        hb[entry["name"]] = entry
        g.emit("homebrew.add", kind="subclasses", slug=srd.slug(entry["class"]), entry=hb)
    else:
        g.emit("homebrew.add", kind=kind, slug=key, entry=entry)
    g.say(f"🛠 Homebrew {kind[:-1]} registered: {entry['name']} — {a.reason}", kind="override")


def cmd_encounter(g, a):
    members = [e for e in g.pcs() if not e.get("dead")]
    lvl = g.party_level()
    budget = srd.data()["xp_budget"][lvl]
    creatures = []
    for spec in a.monsters:
        name, _, n = spec.partition(":")
        mon = g.lookup("monsters", name)
        if not mon:
            raise RuleError(f"No stat block '{name}'.")
        creatures.append((mon, int(n or 1)))
    total = sum(m["xp"] * n for m, n in creatures)
    n = max(1, len(members))
    rating = "trivial"
    for k in ("low", "moderate", "high"):
        if total >= budget[k] * n * (0.5 if k == "low" else 1):
            rating = k
    over = total > budget["high"] * n
    print(f"Party: {n} PCs, level {lvl}. Budgets — Low {budget['low'] * n}, Moderate {budget['moderate'] * n}, High {budget['high'] * n} XP.")
    print(f"Encounter: {', '.join(f'{c}× {m['name']} (CR {m['cr']}, {m['xp']} XP)' for m, c in creatures)} = {total} XP → "
          f"{'ABOVE HIGH' if over else rating.upper()}")
    if a.action == "spawn":
        diff = g.state["settings"].get("difficulty", "standard")
        if over and not a.override:
            raise RuleError(f"This encounter ({total} XP) exceeds the High budget ({budget['high'] * n}) — too deadly by the "
                            f"encounter-building rules. Reduce it or pass --override \"story reason\" (shown to the player).")
        if a.override:
            g.override(a.override, f"encounter above High budget ({total} XP)")
        mid = a.map or g.state["view"].get("map")
        m = g.state["maps"].get(mid)
        import random
        rng = random.Random(g.state["seq"])
        occupied = {(e["token"]["x"], e["token"]["y"]) for e in g.entities.values() if e.get("token", {}).get("map") == mid}
        near = xy(a.near) if a.near else None
        made = []
        for mon, cnt in creatures:
            for i in range(cnt):
                nm = f"{mon['name']} {chr(65 + i)}" if cnt > 1 else mon["name"]
                e = instantiate_monster(g, mon, nm, "enemy", a.hidden, g.state["settings"].get("hp_mode", "avg"))
                made.append(e)
        if m:
            spots = maps.free_cells(m, len(made), rng, near=near, avoid=frozenset(occupied), radius=6)
            for e, (x, y) in zip(made, spots):
                g.set(e, token={"map": mid, "x": x, "y": y})
        if not a.hidden:
            g.say(f"⚠ Enemies appear: {', '.join(e['name'] for e in made)}!", kind="creature")
        g.note("Spawned: " + ", ".join(f"{e['id']}@{g.get(e['id']).get('token', {}).get('x')},{g.get(e['id']).get('token', {}).get('y')}" for e in made))


def cmd_request(g, a):
    reqs = g.state["requests"]
    if a.action == "list":
        for r in reqs.values():
            print(f"{r['id']}: {r['who']} — {r['label']}")
        if not reqs:
            print("No pending player rolls.")
        return
    rid = a.id
    if rid not in reqs:
        raise RuleError(f"No pending request {rid}.")
    if a.action == "cancel":
        g.emit("request.close", id=rid, status="cancelled")
        g.say(f"Roll request {rid} cancelled.", kind="request")
        return
    fulfill(g, rid, "chat")


def fulfill(g, rid, via):
    req = g.state["requests"][rid]
    spec = req["spec"]
    op = spec["op"]
    g.emit("request.close", id=rid, status="rolled", via=via)
    e = g.get(spec.get("who") or spec.get("att"))
    if op == "check":
        M.ability_check(g, e, spec["what"], dc=spec["dc"], adv=spec["adv"], dis=spec["dis"], hidden=spec.get("hidden"),
                        purpose=spec.get("purpose"), now=True, request=rid)
    elif op == "save":
        M.saving_throw(g, e, spec["ability"], spec["dc"], adv=spec["adv"], dis=spec["dis"], source=spec.get("source"),
                       spell=spec.get("spell"), now=True, request=rid, effect=spec.get("effect"))
    elif op == "attack":
        M.attack(g, spec["att"], spec["tgt"], spec["weapon"], adv=spec["adv"], dis=spec["dis"], reaction=spec["reaction"],
                 offhand=spec["offhand"], versatile=spec["versatile"], sneak=spec["sneak"], smite=spec["smite"], now=True, request=rid)
    elif op == "death":
        M.death_save(g, e, now=True, request=rid)
    elif op == "initiative":
        r = M.roll_initiative(g, e, spec.get("surprised"), now=True, request=rid)
        c = dict(M.combat(g))
        c["pending_init"] = {k: v for k, v in c["pending_init"].items() if k != e["id"]}
        c["unsorted"] = c["unsorted"] + [{"id": e["id"], "init": r["total"], "tie": derive(e)["init"]}]
        g.emit("combat.set", combat=c)
        g.say(f"   Initiative — {e['name']}: {r['text']}", kind="roll")
        if not c["pending_init"]:
            finalize_initiative(g)


def cmd_roll(g, a):
    r = g.roll(a.expr, a.purpose or "DM roll", a.who, "adv" if a.adv else "dis" if a.dis else None, hidden=a.hidden)
    if a.hidden:
        g.say("🎲 The DM rolls secretly.", kind="roll-hidden")
        g.note(f"[secret] {a.purpose or ''}: {r['text']}")
    else:
        g.say(f"🎲 {a.purpose or 'Roll'}: {r['text']}", kind="roll", roll=r["id"])


# ====================================================================== info

def cmd_status(g, a):
    print(views.state_md(g))


def cmd_audit(g, a):
    s = g.state
    print(f"Events: {len(g.events)} · Rolls: {s['roll_count']} · Log head {g.events[-1]['hash'][:16] if g.events else ''} (signature chain verified)")
    print("\nOverrides (all shown publicly):")
    for o in s["overrides"]:
        print(f"  #{o['seq']}: {o['what']} — {o['reason']}")
    print("\nHomebrew:")
    for k, v in s["homebrew"].items():
        print(f"  {k}: {', '.join(v)}")
    if a.hidden:
        print("\nHidden rolls:")
        for r in s["rolls"]:
            if r.get("hidden"):
                print(f"  {r['id']} {r['purpose']}: {r['text']}")


def cmd_quick(a):
    """Quicksave / quickload: named restore points. A quickload resets the whole game (log, notes, views) exactly."""
    from . import quicksave as Q
    d = active_dir()
    try:
        if a.cmd == "quicksave" and a.name == "list":
            saves = Q.list_saves(d)
            for m in saves:
                print(f"  {m['slot']}: event {m['seq']} ({m.get('event_ts') or '?'}){' - ' + m['label'] if m.get('label') else ''}")
            print(f"{len(saves)} quicksave(s).")
            return 0
        if a.cmd == "quicksave" and a.name == "delete":
            Q.delete(d, a.target)
            print(f"Deleted quicksave '{a.target}'.")
            return 0
        if a.cmd == "quicksave":
            m = Q.save(d, a.name, a.at_seq, a.label)
            print(f"💾 Quicksaved '{m['slot']}' at event {m['seq']}.")
            return 0
        m = Q.load(d, a.name)
    except Q.QuicksaveError as err:
        print(f"✖ RULE: {err}")
        return 2
    g = Game()
    views.write_snapshots(g)
    print(f"⏪ Quickloaded '{m['slot']}': the game is exactly as it was at event {m['seq']} ({fmt_time(g.state['time'])}).")
    return 0


def cmd_verify(a):
    d = active_dir()
    st = Store(d)
    try:
        ev = st.load()
        print(f"✔ {len(ev)} events, signature chain intact. Head {ev[-1]['hash'][:16] if ev else '-'}")
        # snapshots vs replay
        g = Game(d)
        views.write_snapshots(g)
    except TamperError as err:
        print(f"✖ TAMPERING DETECTED: {err}")
        print("The game refuses to continue on a modified log. Restore events.jsonl from backup "
              "(campaigns/<name>/engine/backups/) or accept the last valid event with `engine repair --truncate`.")
        sys.exit(3)


def cmd_rekey(a):
    d = active_dir()
    st = Store(d)
    n = st.rekey()
    print(f"✔ Re-signed {n} events (and backups) with a new key at {st.key_path.relative_to(d.parent.parent)}.")
    if st.legacy_key_path.exists():
        print(f"  The old key in {st.legacy_key_path} is no longer used and can be deleted.")


def cmd_repair(a):
    d = active_dir()
    st = Store(d)
    lines = [l for l in st.events_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    good = st.valid_prefix()
    if good == len(lines):
        print("Log is intact — nothing to repair.")
        return
    best, n = st.restore_best_backup()
    if a.restore:
        if not best:
            print("No fully valid backup found.")
            return
        bk = st.engine_dir / "backups"
        import time
        shutil.copy(st.events_path, bk / f"events-tampered-{int(time.time())}.jsonl")
        shutil.copyfile(best, st.events_path)
        print(f"Restored {n} signed events from {best.name}. Tampered copy kept in backups/.")
        return
    if best:
        print(f"A valid signed backup with {n} events exists ({best.name}). Restore it with `repair --restore`.")
    if not a.truncate:
        print(f"The first {good} of {len(lines)} events are valid. Re-run with --truncate to discard the rest (a backup is kept).")
        return
    bk = st.engine_dir / "backups"
    bk.mkdir(exist_ok=True)
    import time
    shutil.copy(st.events_path, bk / f"events-tampered-{int(time.time())}.jsonl")
    st.events_path.write_text("\n".join(lines[:good]) + ("\n" if good else ""), encoding="utf-8")
    print(f"Log truncated to {good} valid events. Tampered copy saved in {bk}.")


def cmd_log(g, a):
    for f in g.state["feed"][-a.n:]:
        print(f"[{f.get('seq')}] {f['text']}")


def cmd_rules(a):
    """Quick SRD lookup for the DM."""
    kind, name = a.kind, " ".join(a.name)
    folder = {"spell": "spells", "monster": "monsters", "item": "magic-items"}.get(kind)
    if folder:
        p = ROOT / "rules" / folder / f"{srd.slug(name)}.md"
        if not p.exists():
            sug = srd.suggest({"spell": "spells", "monster": "monsters", "item": "magic_items"}[kind], name)
            raise RuleError(f"Not found. Did you mean: {', '.join(sug)}")
        print(p.read_text(encoding="utf-8"))
    elif kind == "condition":
        text = (ROOT / "rules" / "core" / "08-rules-glossary.md").read_text(encoding="utf-8")
        m = re.search(r"^#### " + re.escape(name.title()) + r".*?(?=^#### |\Z)", text, re.M | re.S)
        print(m.group(0) if m else "Not found")
    else:
        raise RuleError("rules spell|monster|item|condition <name>")


def cmd_serve(a):
    from . import server
    server.serve(a.port, a.host)


# ====================================================================== parser

def build_parser():
    p = argparse.ArgumentParser(prog="python -m engine", description="D&D 5.2 SRD game engine — the only way mechanics change.")
    sp = p.add_subparsers(dest="cmd")

    c = sp.add_parser("campaign", help="new|list|switch|archive")
    c.add_argument("action")
    c.add_argument("args", nargs="*")
    c.add_argument("--set", action="append", help="setting=value at creation (player_rolls, xp_mode, difficulty, start_level)")
    c = sp.add_parser("set", help="change a campaign setting: key=value")
    c.add_argument("kv")
    c = sp.add_parser("session", help="start|end")
    c.add_argument("action", choices=["start", "end"])

    c = sp.add_parser("char", help="roll-stats|create|levelup|catch-up|masteries|leave|rejoin|bio|show|inspire|use-inspiration|remove")
    c.add_argument("action")
    c.add_argument("args", nargs="*")
    for opt in ("name", "player", "species", "background", "method", "scores", "bonus", "skills", "languages", "equipment",
                "bg-equipment", "species-skill", "species-feat", "expertise", "fighting-style", "masteries", "mi-cantrips",
                "mi-spell", "mi-list", "size", "ancestry", "hp", "subclass", "asi", "feat", "instrument", "skilled", "bonus-skills", "scholar"):
        c.add_argument(f"--{opt}", dest=opt.replace("-", "_"))
    c.add_argument("--class", dest="cls")

    c = sp.add_parser("spells", help="set|scribe|list")
    c.add_argument("action", choices=["set", "scribe", "list"])
    c.add_argument("who")
    c.add_argument("--class", dest="cls")
    c.add_argument("--cantrips")
    c.add_argument("--prepared", default="")
    c.add_argument("--spellbook")
    c.add_argument("--spell")
    c.add_argument("--source")

    c = sp.add_parser("journal", help="add \"text\" --title — a note in the players' journal (handouts are added automatically)")
    c.add_argument("action")
    c.add_argument("text", nargs="?")
    c.add_argument("--title")

    c = sp.add_parser("npc", help="add <srd-monster>|reveal|hide|leave|return|remove|rename|side|show|describe|lore|alignment")
    c.add_argument("action")
    c.add_argument("what")
    c.add_argument("--text", help="npc lore: public knowledge about the creature")
    c.add_argument("--size", help="npc resize: Small/Medium/...")
    c.add_argument("--name")
    c.add_argument("--count", type=int, default=1)
    c.add_argument("--side", default="enemy")
    c.add_argument("--hidden", action="store_true")
    c.add_argument("--hp", choices=["avg", "roll"])
    c.add_argument("--at")
    c.add_argument("--map")

    c = sp.add_parser("place", help="put a creature's token on a map")
    c.add_argument("who")
    c.add_argument("at")
    c.add_argument("--map")
    c.add_argument("--force")
    c = sp.add_parser("move", help="move a token (validated path & movement)")
    c.add_argument("who")
    c.add_argument("to", nargs="?")
    c.add_argument("--path", help='"x,y x,y ..." explicit squares')
    c.add_argument("--crawl", action="store_true")
    c.add_argument("--force", help="forced movement reason (shove, spell)")
    c = sp.add_parser("party-move", help="move the whole party out of combat")
    c.add_argument("to")
    c = sp.add_parser("stand")
    c.add_argument("who")

    c = sp.add_parser("combat", help="start|next|end|add|remove|status|swap (Alert: combat swap kit,wren)")
    c.add_argument("action")
    c.add_argument("ids", nargs="?")
    c.add_argument("--surprised")
    c.add_argument("--reason")
    c = sp.add_parser("action", help="take an SRD action (dash, dodge, help, hide, ...)")
    c.add_argument("who")
    c.add_argument("name")
    c.add_argument("--bonus", action="store_true")
    c.add_argument("--reaction", action="store_true")
    c.add_argument("--via")
    c.add_argument("--target")
    c.add_argument("--skill")
    c.add_argument("--dc", type=int)
    c.add_argument("--note")
    c.add_argument("--prone", action="store_true", help="shove: knock Prone instead of pushing 5 ft")

    c = sp.add_parser("attack", help="weapon / monster attack, fully resolved")
    c.add_argument("attacker")
    c.add_argument("target")
    c.add_argument("weapon", nargs="?")
    c.add_argument("--adv", help="extra Advantage reasons, comma separated")
    c.add_argument("--dis", help="extra Disadvantage reasons")
    c.add_argument("--reaction", action="store_true")
    c.add_argument("--offhand", action="store_true")
    c.add_argument("--versatile", action="store_true")
    c.add_argument("--sneak", action="store_true")
    c.add_argument("--smite", type=int, help="Divine Smite slot level")
    c.add_argument("--knockout", action="store_true")
    c.add_argument("--times", type=int, default=1)
    c.add_argument("--now", action="store_true", help="roll now even in viewer-roll mode")

    c = sp.add_parser("cast", help="cast a spell: slots, components, concentration, effects")
    c.add_argument("caster")
    c.add_argument("spell")
    c.add_argument("--level", type=int)
    c.add_argument("--targets")
    c.add_argument("--ritual", action="store_true")
    c.add_argument("--free", help="free casting source, e.g. 'Magic Initiate'")
    c.add_argument("--scroll", help="inventory id of a spell scroll")
    c.add_argument("--condition", help="condition applied on a failed save (e.g. paralyzed)")
    c.add_argument("--component", help="inventory id of the costly component")
    c.add_argument("--adv")
    c.add_argument("--dis")
    c.add_argument("--now", action="store_true")

    c = sp.add_parser("check", help="ability check / skill check")
    c.add_argument("who")
    c.add_argument("what")
    c.add_argument("--dc", type=int)
    c.add_argument("--adv")
    c.add_argument("--dis")
    c.add_argument("--hidden", action="store_true")
    c.add_argument("--purpose")
    c.add_argument("--now", action="store_true")
    c = sp.add_parser("ruling", help="public DM ruling/correction: ruling --what ... --reason ...")
    c.add_argument("--what")
    c.add_argument("--reason")

    c = sp.add_parser("contest", help="opposed check: contest <who> <skill> --vs <id> --vs-skill <skill> [--passive]")
    c.add_argument("who")
    c.add_argument("what")
    c.add_argument("--vs", required=True)
    c.add_argument("--vs-skill", dest="vs_skill", required=True)
    c.add_argument("--passive", action="store_true", help="opponent uses 10 + modifier")
    c.add_argument("--passive-adv", dest="passive_adv", action="store_true")
    c.add_argument("--passive-dis", dest="passive_dis", action="store_true")
    c.add_argument("--adv")
    c.add_argument("--dis")
    c.add_argument("--hidden", action="store_true")
    c.add_argument("--purpose")

    c = sp.add_parser("save", help="saving throw(s), optional damage/condition")
    c.add_argument("who")
    c.add_argument("ability")
    c.add_argument("--dc", type=int, required=True)
    c.add_argument("--damage")
    c.add_argument("--half", action="store_true")
    c.add_argument("--condition")
    c.add_argument("--repeat", action="store_true", help="target repeats the save at end of each turn")
    c.add_argument("--source")
    c.add_argument("--spell", action="store_true")
    c.add_argument("--adv")
    c.add_argument("--dis")
    c.add_argument("--now", action="store_true")

    c = sp.add_parser("damage", help="environmental / trap / other damage")
    c.add_argument("who")
    c.add_argument("amount")
    c.add_argument("type")
    c.add_argument("--source")
    c.add_argument("--crit", action="store_true")
    c = sp.add_parser("heal", help="generic healing (party needs --override)")
    c.add_argument("who")
    c.add_argument("amount")
    c.add_argument("--source")
    c.add_argument("--override")
    c = sp.add_parser("temphp")
    c.add_argument("who")
    c.add_argument("amount")
    c.add_argument("--source")
    c.add_argument("--override")
    c = sp.add_parser("condition", help="add|remove")
    c.add_argument("action", choices=["add", "remove"])
    c.add_argument("who")
    c.add_argument("name")
    c.add_argument("--source")
    c.add_argument("--until")
    c.add_argument("--rounds", type=int)
    c.add_argument("--save", help="ability:DC repeat save at end of turns")
    c.add_argument("--caster", help="id of the creature whose spell/concentration causes this condition")
    c.add_argument("--spell", help="spell slug the condition belongs to (ends with that concentration)")
    c = sp.add_parser("exhaustion")
    c.add_argument("who")
    c.add_argument("delta")
    c.add_argument("--source")
    c.add_argument("--override")
    c = sp.add_parser("feature", help="use a class feature / limited resource")
    c.add_argument("who")
    c.add_argument("name")
    c.add_argument("--amount", type=int)
    c.add_argument("--target")
    c.add_argument("--note")
    c = sp.add_parser("bardic", help="spend a Bardic Inspiration die")
    c.add_argument("who")
    c = sp.add_parser("deathsave")
    c.add_argument("who")
    c.add_argument("--now", action="store_true")
    c = sp.add_parser("stabilize")
    c.add_argument("helper")
    c.add_argument("who")
    c = sp.add_parser("legendary-resist")
    c.add_argument("who")
    c = sp.add_parser("rest", help="short|long")
    c.add_argument("kind", choices=["short", "long"])
    c.add_argument("--who")
    c.add_argument("--hd", help="hit dice to spend: kira:2,bob:1")
    c.add_argument("--focus", help="short rest: identify a magic item by focusing on it, kira:item-id (one per creature)")
    c = sp.add_parser("time", help="advance in-world time")
    c.add_argument("amount")
    c.add_argument("--reason")
    c = sp.add_parser("travel")
    c.add_argument("miles", nargs="?", type=float)
    c.add_argument("--pace", default="normal", choices=["fast", "normal", "slow"])
    c.add_argument("--to")
    c.add_argument("--map")

    c = sp.add_parser("item", help="add|remove|drop|stash|pickup|sell|give|equip|unequip|attune|unattune|use|light|note|unpack|identify|obscure|refresh|recover-ammo|card")
    c.add_argument("action")
    c.add_argument("who")
    c.add_argument("item")
    c.add_argument("--qty", type=int, default=1)
    c.add_argument("--source")
    c.add_argument("--purchase", action="store_true")
    c.add_argument("--price")
    c.add_argument("--override")
    c.add_argument("--custom")
    c.add_argument("--to")
    c.add_argument("--text", help="item note: what the item really is / looks like (flavour)")
    c.add_argument("--alias", help="item note: display name (e.g. 'Oathkeeper' for a Longsword)")
    c.add_argument("--how", help="item identify/obscure: how the characters learned (or why they don't know) its properties")
    c.add_argument("--identified", action="store_true", help="item add: the characters already know what this magic item does")
    c = sp.add_parser("coins")
    c.add_argument("who")
    c.add_argument("amount")
    c.add_argument("--source")
    c.add_argument("--override")
    c = sp.add_parser("xp", help="award|milestone|sync <id>")
    c.add_argument("action", choices=["award", "milestone", "sync"])
    c.add_argument("who", nargs="?", help="sync: the character to bring up to the party's XP")
    c.add_argument("--encounter", action="store_true")
    c.add_argument("--amount", type=int)
    c.add_argument("--reason")
    c.add_argument("--override")
    c = sp.add_parser("encounter", help="plan|spawn <monster:count ...>")
    c.add_argument("action", choices=["plan", "spawn"])
    c.add_argument("monsters", nargs="+")
    c.add_argument("--map")
    c.add_argument("--near")
    c.add_argument("--hidden", action="store_true")
    c.add_argument("--override")

    c = sp.add_parser("map", help="gen|list|show|reveal|hide|door|feature|crop|paint|set|party|label|poi|poi-move|poi-remove|container|container-remove|from-image|render|ascii")
    c.add_argument("action")
    c.add_argument("target", nargs="?")
    c.add_argument("at", nargs="?")
    c.add_argument("state", nargs="?")
    c.add_argument("--kind", default="dungeon")
    c.add_argument("--name")
    c.add_argument("--id")
    c.add_argument("--seed", type=int)
    c.add_argument("--w", type=int)
    c.add_argument("--h", type=int)
    c.add_argument("--biome")
    c.add_argument("--preset")
    c.add_argument("--building")
    c.add_argument("--show", action="store_true")
    c.add_argument("--all", action="store_true")
    c.add_argument("--room", type=int)
    c.add_argument("--rect")
    c.add_argument("--pad", type=int, default=2)
    c.add_argument("--char")
    c.add_argument("--kv")
    c.add_argument("--ftype")
    c.add_argument("--hidden", action="store_true")
    c.add_argument("--dm", action="store_true")
    c.add_argument("--out")
    c.add_argument("--text", help="map poi: what the characters perceive (becomes the journal entry)")
    c.add_argument("--reason", help="map poi-move/poi-remove: what changed")
    c.add_argument("--icon", help="map prop: a game-icons name (find one with `map icons <words>`)")
    c.add_argument("--blocks", action="store_true", help="map prop: the piece fills its square (impassable, half cover)")
    c.add_argument("--size", choices=("small", "medium", "large"), help="map prop: how much of the tile it fills")
    c.add_argument("--color", help="map prop: silhouette colour, #rrggbb")
    c.add_argument("--rotate", type=int, help="map prop: degrees")

    c = sp.add_parser("asset", help="icon|fetch|import|draw|portrait|look|art|list")
    c.add_argument("action")
    c.add_argument("args", nargs="*")
    c.add_argument("--name")
    c.add_argument("--kind")
    c.add_argument("--license")
    c.add_argument("--credit")
    c.add_argument("--portrait", help="set as this creature's portrait")
    c.add_argument("--like", help="look: keep another creature's face (an NPC who joins the party as a character)")
    c.add_argument("--item", help="draw/fetch/import: use as this item's picture (owner:item-id)")
    c.add_argument("--private", action="store_true")
    c.add_argument("--style", choices=["art", "heraldic"], default="art", help="portrait: generated bust (default) or the old heraldic card")
    c.add_argument("--clear", nargs="?", const="all", help="portrait: unpin; look: clear fields (comma list or all)")
    c.add_argument("--out", help="art: write the SVG here")
    c.add_argument("--crop", choices=["portrait", "face"], help="art: framed portrait (default) or the token face")
    for f in ("hair", "beard", "eyes", "skin", "marks", "headwear", "outfit", "cloak", "build", "age", "expression", "horns",
              "accent", "background", "presentation"):
        c.add_argument(f"--{f}", dest=f"look_{f}", help=f"look: {f} (free text, e.g. --hair \"long silver braid\")")
    c = sp.add_parser("fx", help="table animation: status|preset|set|ambient|play <effect>|camera <target>")
    c.add_argument("action")
    c.add_argument("args", nargs="*")
    c.add_argument("--at")
    c.add_argument("--on")
    c.add_argument("--from", dest="src")
    c.add_argument("--to", dest="dst")
    c.add_argument("--color")
    c.add_argument("--radius", type=int, help="feet")
    c.add_argument("--text")
    c.add_argument("--map")
    c.add_argument("--intensity", type=float)
    c = sp.add_parser("say", help="narration or NPC speech to the viewer feed")
    c.add_argument("text", nargs="+")
    c.add_argument("--as", dest="speaker")
    c.add_argument("--at", dest="at", help="narration about a creature (id or name): shown by its token on the table")
    c = sp.add_parser("scene", help="set the scene banner in the viewer")
    c.add_argument("title")
    c.add_argument("--desc")
    c.add_argument("--image")
    c.add_argument("--map")
    c = sp.add_parser("show", help="show a handout: item|creature|asset|text|srd-item|clear")
    c.add_argument("kind")
    c.add_argument("ref", nargs="?", default="")
    c.add_argument("--title")
    c = sp.add_parser("homebrew", help="register homebrew (public)")
    c.add_argument("kind")
    c.add_argument("--file", required=True)
    c.add_argument("--reason")
    c = sp.add_parser("request", help="list|roll <id>|cancel <id> — pending player rolls")
    c.add_argument("action", choices=["list", "roll", "cancel"])
    c.add_argument("id", nargs="?")
    c = sp.add_parser("roll", help="free DM roll (random tables etc.)")
    c.add_argument("expr")
    c.add_argument("--purpose")
    c.add_argument("--who")
    c.add_argument("--hidden", action="store_true")
    c.add_argument("--adv", action="store_true")
    c.add_argument("--dis", action="store_true")

    sp.add_parser("status")
    c = sp.add_parser("audit")
    c.add_argument("--hidden", action="store_true")
    sp.add_parser("verify")
    c = sp.add_parser("quicksave", help="save a named restore point: quicksave [name] [--at-seq N] | quicksave list | quicksave delete <name>")
    c.add_argument("name", nargs="?")
    c.add_argument("target", nargs="?")
    c.add_argument("--at-seq", type=int, help="save the game as it was after event N (a point already passed)")
    c.add_argument("--label", default="")
    c = sp.add_parser("quickload", help="restore a quicksave exactly (default: the most recent)")
    c.add_argument("name", nargs="?")
    c = sp.add_parser("repair")
    c.add_argument("--truncate", action="store_true")
    c.add_argument("--restore", action="store_true", help="restore the newest fully-signed backup")
    sp.add_parser("rekey", help="re-sign the log with a fresh key stored in the campaign folder")
    c = sp.add_parser("log")
    c.add_argument("-n", type=int, default=30)
    c = sp.add_parser("rules", help="spell|monster|item|condition <name>")
    c.add_argument("kind")
    c.add_argument("name", nargs="+")
    c = sp.add_parser("serve", help="run the live viewer")
    c.add_argument("--port", type=int, default=8765)
    c.add_argument("--host", default="127.0.0.1")
    sp.add_parser("help")
    return p


HANDLERS = {
    "set": cmd_set, "session": cmd_session, "char": cmd_char, "spells": cmd_spells, "npc": cmd_npc, "place": cmd_place,
    "journal": cmd_journal, "contest": cmd_contest, "ruling": cmd_ruling,
    "move": cmd_move, "party-move": cmd_party_move, "stand": lambda g, a: M.stand(g, a.who), "combat": cmd_combat,
    "action": cmd_action, "attack": cmd_attack, "cast": cmd_cast, "check": cmd_check, "save": cmd_save,
    "damage": cmd_damage, "heal": cmd_heal, "temphp": cmd_temphp, "condition": cmd_condition, "exhaustion": cmd_exhaustion,
    "feature": cmd_feature, "bardic": cmd_bardic, "deathsave": cmd_deathsave, "stabilize": cmd_stabilize,
    "legendary-resist": cmd_legendary, "rest": cmd_rest, "time": cmd_time, "travel": cmd_travel, "item": cmd_item,
    "coins": cmd_coins, "xp": cmd_xp, "encounter": cmd_encounter, "map": cmd_map, "asset": cmd_asset, "say": cmd_say, "fx": cmd_fx,
    "scene": cmd_scene, "show": cmd_show, "homebrew": cmd_homebrew, "request": cmd_request, "roll": cmd_roll,
    "status": cmd_status, "audit": cmd_audit, "log": cmd_log,
}
READ_ONLY = {"status", "audit", "log"}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):  # (not when a test runs the CLI in-process with captured output)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:] if argv is None else argv
    # `coins kira -5sp`: a negative amount looks like an option to argparse; pass it as a value instead
    argv = [f"={x}" if i and argv[0] == "coins" and re.match(r"^-\d", x) else x for i, x in enumerate(argv)]
    p = build_parser()
    a = p.parse_args(argv)
    if not a.cmd or a.cmd == "help":
        p.print_help()
        return 0
    try:
        if a.cmd == "campaign":
            cmd_campaign(a)
            return 0
        if a.cmd == "verify":
            cmd_verify(a)
            return 0
        if a.cmd in ("quicksave", "quickload"):
            return cmd_quick(a)
        if a.cmd == "repair":
            cmd_repair(a)
            return 0
        if a.cmd == "rekey":
            cmd_rekey(a)
            return 0
        if a.cmd == "rules":
            cmd_rules(a)
            return 0
        if a.cmd == "serve":
            cmd_serve(a)
            return 0
        g = Game()
        g.cmdline = " ".join(shlex.quote(x) for x in argv)
        HANDLERS[a.cmd](g, a)
        if a.cmd not in READ_ONLY:
            g.commit()
            views.write_snapshots(g)
        for line in g.out:
            print(line)
        return 0
    except RuleError as err:
        print(f"✖ RULE: {err}")
        print("  (nothing was changed)")
        return 2
    except TamperError as err:
        print(f"✖ TAMPERING DETECTED: {err}")
        print("  The engine refuses to run on a modified log. See `python -m engine verify` / `repair`.")
        return 3
    except (KeyError, IndexError) as err:
        print(f"✖ ERROR: {type(err).__name__}: {err}  (nothing was changed)")
        return 1
