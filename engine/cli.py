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

from . import art, assets, chargen, dice, forces as F, itemart, loot as L, maps, mechanics as M, render, srd, views, walls as W
from .core import (Game, RuleError, derive, fmt_time, level, parse_duration, parse_when, replay, tier, TIER_MAX_GP_AWARD,
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

CHRONICLE_TEMPLATE = """# Chronicle: {saga}

> The saga's history so far, read at the start of every session of chapter {chapter} ({title}).
> Earlier chapters keep their full notes in their own folders: search them (grep) for an exact callback,
> never load them wholesale. Chapter {chapter} continues from `campaigns/{previous}/` ({previous_title}).

## The chapters so far

## The crew: who they are now, and what they will never forget

## What they carry (the important things; the sheets have the rest)

## Who wants them, and why

## Promises, debts and grudges

## Threads left hanging (and where the full story lives)
"""


def chapter_source(slug):
    """An earlier chapter of a saga, loaded read-only. Its signed log must verify (a TamperError stops everything)."""
    src = CAMPAIGNS / (slug or "")
    if not slug or slug.startswith(("_", ".")) or not src.is_dir() or not (src / "engine").is_dir():
        raise RuleError(f"No campaign '{slug}' to continue from. An archived campaign has to be brought back "
                        "with `campaign switch` first.")
    return Game(src, verify=True)


# a carried-over sheet keeps everything the character owns and knows; these belong to the scene they left behind
CARRY_DROP = ("token", "temp_hp", "concentration", "last_long_rest_end", "masteries_changed_at", "wake_at", "departed",
              "offstage", "hidden", "dead")
ITEM_CARRY_DROP = ("lit", "venom", "venom_until", "venom_used_at")


def import_entity(g, a):
    """`char import <id> [--from <earlier-campaign>]`: bring a character or companion over from an earlier chapter of
    the saga with the sheet exactly as the signed log has it (classes, features, spells, inventory, coins, XP, look),
    fresh from the journey between chapters (rested: full HP, spell slots and Hit Dice; no conditions)."""
    if not a.args:
        raise RuleError("char import <id> [--from <earlier-campaign>]")
    slug = getattr(a, "from_slug", None) or g.state["campaign"].get("previous")
    if not slug:
        raise RuleError('This campaign doesn\'t continue an earlier one (`campaign new "Title" --from <slug>`); '
                        "pass --from <slug>.")
    src = chapter_source(slug)
    found = src.get(a.args[0])
    if found.get("dead"):
        raise RuleError(f"{found['name']} died in '{slug}'; the dead don't carry over.")
    e = json.loads(json.dumps(found))
    if e["id"] in g.entities:
        raise RuleError(f"{e['name']} ({e['id']}) is already in this campaign.")
    for k in CARRY_DROP:
        e.pop(k, None)
    # `appearance` is what anyone sees at a glance. For a character with a lasting description (`bio.appearance`) it is
    # the look of the old chapter's last scene (a disguise, that night's clothes), so it stays behind; a companion's
    # only description comes along, to be checked against the time skip.
    has_bio_look = bool((e.get("bio") or {}).get("appearance"))
    scene_look = e.pop("appearance", None) if has_bio_look else None
    e["conditions"], e["effects"] = [], []
    e["hp"] = e.get("hp_max", e.get("hp"))
    if e["kind"] == "pc":
        # the time between chapters counts as a Long Rest, with everything one restores (mechanics.long_rest)
        e.update(hd_spent={}, slots_used={}, resources_used={}, pact_used=0, exhaustion=0,
                 death={"success": 0, "fail": 0, "stable": False})
        if e.get("granted_spells"):
            e["granted_spells"] = [dict(x, free_used=False) for x in e["granted_spells"]]
        if "Resourceful" in e.get("species_traits", []):
            e["inspiration"] = True  # Human: Resourceful
    e["inventory"] = [{k: v for k, v in i.items() if k not in ITEM_CARRY_DROP} for i in e.get("inventory", [])]
    e["chronicle"] = {"from": slug, "title": src.state["campaign"].get("title"), "seq": src.state["seq"]}
    # pictures the sheet points at (a pinned portrait, an item's own art) come along with it
    for aid in sorted({e.get("portrait")} | {i.get("art") for i in e["inventory"]} - {None}):
        asset = src.state["assets"].get(aid)
        if not asset or aid in g.state["assets"]:
            continue
        f = Path(src.dir) / "assets" / asset["file"]
        if f.exists():
            assets.assets_dir(g.dir).joinpath(asset["file"]).write_bytes(f.read_bytes())
            g.emit("asset.add", asset=asset)
    g.emit("entity.add", entity=e)
    e = g.get(e["id"])
    extra = ""
    start = g.state["settings"].get("start_level", 1)
    if e["kind"] == "pc" and level(e) < start and e.get("xp", 0) < M.xp_threshold(start):
        g.set(e, xp=M.xp_threshold(start))
        extra = (f" This chapter starts at level {start}: XP set to {M.xp_threshold(start)}; "
                 f"`char levelup {e['id']}` until level {start}.")
    items = sum(i.get("qty", 1) for i in e.get("inventory", []))
    g.say(f"📜 {e['name']} carries over from {e['chronicle']['title']}: the full sheet, {items} items, "
          f"{M.fmt_cp(M.coins_total_cp(e))}." + extra, kind="party", who=e["id"])
    if scene_look:
        g.note(f"  ✎ {e['name']}'s look from the last scene stayed behind (their lasting description came along). "
               f'Describe them as they are now: npc describe {e["id"]} --text "..."')
    elif e.get("appearance"):
        g.note(f"  ✎ Check that {e['name']}'s look still fits after the time skip: \"{e['appearance']}\" "
               f'(npc describe {e["id"]} --text "..." to change it)')


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
        chapter = None
        if getattr(a, "from_slug", None):
            # the next chapter of a saga: the earlier campaign's signed log must verify before anything carries over
            prev = chapter_source(a.from_slug)
            pc = prev.state["campaign"]
            chapter = {"saga": getattr(a, "saga", None) or pc.get("saga") or pc.get("title"), "chapter": (pc.get("chapter") or 1) + 1,
                       "previous": a.from_slug, "previous_title": pc.get("title"), "previous_seq": prev.state["seq"]}
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
        g.emit("campaign.init", title=title, slug=slug, ruleset="SRD 5.2", **(chapter or {}))
        for kv in a.set or []:
            k, _, v = kv.partition("=")
            set_setting(g, k, v)
        g.say(f"📜 New campaign: {title}", kind="scene")
        if chapter:
            g.say(f"📜 Chapter {chapter['chapter']} of {chapter['saga']}, continuing from {chapter['previous_title']}.",
                  kind="scene")
            chron = dest / "chronicle.md"
            if not chron.exists():
                chron.write_text(CHRONICLE_TEMPLATE.format(saga=chapter["saga"], chapter=chapter["chapter"], title=title,
                                                           previous=chapter["previous"],
                                                           previous_title=chapter["previous_title"]), encoding="utf-8")
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
            "start_level": None, "hp_mode": ("avg", "roll"),
            # house rule: "narrated" = no forced-march saves on ordinary journeys; `travel --push` still rolls them
            "forced_march": ("srd", "narrated"),
            # house rule: a table's pacing choice; every XP award is multiplied by it (public, in the log)
            "xp_rate": ("1", "1.5", "2", "3")}


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
    if a.action == "import":
        import_entity(g, a)
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
        raise RuleError("char roll-stats|create|import|levelup|catch-up|masteries|leave|rejoin|bio|show|inspire|use-inspiration|remove")


def cmd_spells(g, a):
    if not a.who:
        raise RuleError("This spells command needs a creature id.")
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
    elif a.action == "refund":
        # rules/spells/counterspell: a countered spell "cast with a spell slot" doesn't expend it; also a public repair for
        # a slot the DM spent by mistake. Needs the level and a public reason.
        if getattr(a, "spell", None) and not a.level:
            # a once-per-Long-Rest free cast (Magic Initiate and the like) given back, publicly
            if not a.source:
                raise RuleError('spells refund <who> --spell "<name>" --source "why the free cast comes back" (shown publicly)')
            slug = srd.slug(a.spell)
            spent = [x for x in e.get("granted_spells", []) if x["slug"] == slug and x.get("free_used")]
            day_key = f"{slug}-day"   # a stat block's "N/Day Each" spell (rules/spells/counterspell: a voided cast comes back)
            # or a stat-block action that casts it ("Misty Step (3/Day)", "Protective Magic (3/Day)")
            act = next((x for x in e.get("actions", []) if x.get("per_day") and slug.replace("-", " ") in x["text"].lower()
                        and e.get("per_day_used", {}).get(x["name"], 0) > 0), None)
            if not spent and act and not e.get("per_day_used", {}).get(day_key, 0):
                day_key = act["name"]
            if not spent and e.get("per_day_used", {}).get(day_key, 0) > 0:
                g.set(e, **{f"per_day_used__{day_key}": e["per_day_used"][day_key] - 1})
                g.override(a.source, f"one daily cast of {a.spell} refunded to {e['name']}")
                g.say(f"⚖ {e['name']}: one daily cast of {a.spell} is back — {a.source}.", kind="info")
                return
            if not spent:
                raise RuleError(f"{e['name']} has no spent free cast of {a.spell} to refund.")
            g.set(e, granted_spells=[dict(x, free_used=False) if x is spent[0] else x for x in e["granted_spells"]])
            g.override(a.source, f"the free cast of {a.spell} ({spent[0]['source']}) refunded to {e['name']}")
            g.say(f"⚖ {e['name']}: the free cast of {a.spell} ({spent[0]['source']}) is back — {a.source}.", kind="info")
            return
        if not a.level or not a.source:
            raise RuleError('spells refund <who> --level N --source "why the slot comes back" (shown publicly) | '
                            'spells refund <who> --spell "<name>" --source "..." (a free cast)')
        used = e.get("slots_used", {}).get(str(a.level), 0)
        if used < 1:
            raise RuleError(f"{e['name']} has no spent level {a.level} slot to refund.")
        g.set(e, **{f"slots_used__{a.level}": used - 1})
        g.override(a.source, f"one level {a.level} spell slot refunded to {e['name']}")
        g.say(f"⚖ {e['name']}: one level {a.level} spell slot refunded — {a.source}.", kind="info")
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
        align = None
        if getattr(a, "align", None):
            align = " ".join(w.capitalize() for w in a.align.replace("-", " ").split())
            if align not in ALIGNMENTS:
                raise RuleError(f"--align \"{'|'.join(ALIGNMENTS)}\"")
        for e in made:
            # one line can do the whole new-creature checklist: add, place, describe, align
            if getattr(a, "desc", None):
                g.set(e, appearance=a.desc)
            if align:
                g.set(e, alignment=align)
            if not e["hidden"]:
                g.say(f"👁 {e['name']} appears{' (' + e['side'] + ')' if e['side'] != 'enemy' else ''}.", kind="creature", who=e["id"])
            g.note(f"  added {e['id']}: {e['srd_name']} AC {e['ac']} HP {e['hp']} CR {e['cr']}"
                   + (" · described" if getattr(a, "desc", None) else "") + (f" · {align}" if align else ""))
    elif a.action in ("leave", "return"):
        # a creature walks out of the scene (not hiding in it): off the table, out of any fight here. `return` brings it back.
        for i in ids(a.what):
            e = g.get(i)
            if a.action == "leave":
                was_hidden = e.get("hidden")   # read before g.set, which updates e in place
                g.set(e, hidden=True, offstage=True, **({"known": True} if not was_hidden or e.get("known") else {}))
                g.say(f"👋 {e['name']} leaves the scene.", kind="creature") if not was_hidden else None
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
    if e.get("hidden"):
        g.note(f"{e['name']} (hidden) is at ({x},{y}) on {m['name']}.")   # the players mustn't learn where an unseen creature is
    else:
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
             and not e.get("departed") and not e.get("offstage")    # those who have left the scene stay out of it
             and "petrified" not in M.condition_names(e)]          # stone is out of the fight: no initiative
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
            _announce_turn(g, first, 1)
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
            # the dead, the downed foes and the petrified (stone: out of the fight) get no turns
            if ne and not ne.get("dead") and not (ne["kind"] != "pc" and ne["hp"] <= 0)                     and "petrified" not in M.condition_names(ne):
                break
        c["economy"] = {**c.get("economy", {}), nid: {}}
        g.emit("combat.set", combat=c)
        ne = g.get(nid)
        _announce_turn(g, ne, c["round"])
        M.start_of_turn(g, ne)
        return
    if a.action == "add":
        e = g.get(a.ids)
        if getattr(a, "init", None) is not None:
            # repair: a creature removed by mistake rejoins at the initiative it already rolled (logged publicly)
            if not a.reason:
                raise RuleError('combat add <id> --init N --reason "..." (restoring an initiative already rolled)')
            r = {"total": int(a.init)}
            g.override(a.reason, f"{e['name']} rejoins at initiative {a.init}")
        else:
            r = M.roll_initiative(g, e, now=True)
        c = dict(c)
        c["order"] = sorted([o for o in c["order"] if o["id"] != e["id"]] + [{"id": e["id"], "init": r["total"], "tie": derive(e)["init"]}],
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
        _announce_turn(g, e, c["round"], " — returned after a skip")
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
        if a.ids and g.get(a.ids)["id"] != cur:
            # replay an earlier creature's turn this round (its turn was played wrong): the order rewinds to it,
            # and everyone after it acts again from there
            who = g.get(a.ids)["id"]
            idx = next((i for i, o in enumerate(c["order"]) if o["id"] == who), None)
            if idx is None or idx > c["turn"]:
                raise RuleError(f"{g.get(who)['name']} hasn't had its turn yet this round; nothing to replay.")
            later = [o["id"] for o in c["order"][idx:c["turn"] + 1]]
            c["turn"] = idx
            c["economy"] = {**c.get("economy", {}), **{i: {} for i in later}}
            cur = who
        else:
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
            _announce_turn(g, ne, c["round"])
            M.start_of_turn(g, ne)
        return
    if a.action == "end":
        defeated = c.get("defeated", [])
        xp = sum(g.entities[i]["xp"] for i in defeated if i in g.entities)
        g.emit("encounter.log", defeated=defeated, xp=xp, awarded=False, time=g.state["time"],
               rounds=c["round"], ammo=c.get("ammo_total") or {k: v.get("ammo_spent", 0) for k, v in c.get("economy", {}).items() if v.get("ammo_spent")},
               ammo_magic=c.get("ammo_magic", {}), ammo_magic_hits=c.get("ammo_magic_hits", {}))
        # the fight took its rounds (6 s each), not a whole minute: short spells cast in it keep the time they have left
        g.emit("time.set", minutes=g.state["time"] + c["round"] / 10)
        for e in g.entities.values():
            conds = [x for x in e.get("conditions", []) if x["name"] in ("dodging", "helped", "raging", "disengaged")]
            if conds:
                g.set(e, conditions=[x for x in e["conditions"] if x not in conds])
            if e.get("displacement_off"):
                g.set(e, displacement_off=False)   # Cloak of Displacement: the fight's turns are over
        g.emit("combat.set", combat=None)
        M.after_time(g)
        g.say(f"🏁 Combat ends after {c['round']} round(s). Defeated: {', '.join(g.entities[i]['name'] for i in defeated if i in g.entities) or 'none'}"
              f" ({xp} XP available — `xp award --encounter`).", kind="combat", phase="end")
        L.owe(g, defeated)
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
    _announce_turn(g, first, 1)
    M.start_of_turn(g, first)


def _announce_turn(g, e, rnd, suffix=""):
    """Public turn marker. A hidden creature's turn is announced without its name (the DM's note keeps it)."""
    if e.get("hidden"):
        g.say(f"▶ A hidden creature's turn (round {rnd}){suffix}.", kind="turn", round=rnd)
        g.note(f"[secret] {e['name']}'s turn (round {rnd}){suffix}.")
    else:
        g.say(f"▶ {e['name']}'s turn (round {rnd}){suffix}.", kind="turn", who=e["id"], round=rnd)


ACTIONS = {"dash", "disengage", "dodge", "help", "hide", "ready", "search", "study", "utilize", "influence", "magic", "attack", "grapple", "shove", "escape"}


def cmd_action(g, a):
    e = g.get(a.who)
    name = a.name.lower()
    kind = "bonus" if a.bonus else "reaction" if a.reaction else "action"
    if name in ("end-concentration", "drop-concentration"):
        # SRD: you can end Concentration at any time (no action required), even off your turn
        if not e.get("concentration"):
            raise RuleError(f"{e['name']} isn't concentrating on anything.")
        M.end_concentration(g, e, "ended by choice")
        return
    if name not in ACTIONS:
        raise RuleError(f"'{name}' is not an SRD action. Actions: {', '.join(sorted(ACTIONS))}. Class features: `feature`.")
    if kind == "bonus" and not a.via:
        raise RuleError("Taking an action as a Bonus Action needs a feature that allows it (--via \"Cunning Action\").")
    spell_dash = bool(a.via and a.via.lower() == "expeditious retreat" and M.E.has(e, "bonus_dash") and name == "dash")
    if a.via and not spell_dash and not __import__("engine.core", fromlist=["has_feature"]).has_feature(e, a.via) and \
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
    if name == "hide":
        M.check_can_hide(g, e)
    M.use_action(g, e, kind, name)
    if name == "dash":
        ec = M.economy(g, e["id"])
        g and M.combat(g) and M.set_economy(g, e["id"], **({"dashed2": True} if ec.get("dashed") else {"dashed": True}))
        g.say(f"{e['name']} takes the Dash action (extra movement equal to Speed).", kind="action")
    elif name == "utilize":
        # the Utilize action covers an object interaction beyond the free one (picking up a second item, etc.)
        if M.combat(g):
            ec = M.economy(g, e["id"])
            M.set_economy(g, e["id"], utilize_credit=ec.get("utilize_credit", 0) + 1)
        g.say(f"{e['name']} takes the Utilize action" + (f" ({a.note})" if a.note else "") + ".", kind="action")
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
        skill = a.skill or "perception"
        # --target: the creature searched for; a Cloak of Elvenkind it wears gives Perception checks to find it Disadvantage
        hid = g.get(a.target) if a.target else None
        M.ability_check(g, e, skill, dc=a.dc, dis=M.perceive_dis(hid) if hid and skill == "perception" else ())
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
                     offhand=a.offhand, versatile=a.versatile, sneak=a.sneak, smite=a.smite, now=a.now, knockout=a.knockout,
                     ammo=a.ammo)
        if "request" in (r or {}):
            break


def cmd_cast(g, a):
    wall = None
    if getattr(a, "wall", None) or getattr(a, "ring", None):
        wall = wall_plan(g, a.caster, a.spell, a.wall, a.ring, a.hot)
        if a.targets:
            raise RuleError("A wall finds its own targets: everyone standing on its squares. Leave out --targets.")
        a.targets = ",".join(t["id"] for t in W.creatures_on(g, wall["map"], wall["cells"])) or "none"
    M.cast(g, a.caster, a.spell, a.level, ids(a.targets), ritual=a.ritual, free=a.free, adv=ids(a.adv), dis=ids(a.dis), readied=getattr(a, 'readied', False),
           condition=a.condition, component=a.component, now=a.now, scroll=a.scroll, choice=a.choice,
           item=getattr(a, "item", None))
    if wall:
        W.add(g, g.get(a.caster), wall["spell"], wall["map"], wall["cells"], wall["hot"], wall["side"],
              a.level or wall["spell"]["level"])


def wall_plan(g, caster_ref, spell_name, ends, center, side):
    """Where a spell wall stands: its squares and the squares its burning side reaches."""
    e = g.get(caster_ref)
    spell = g.require("spells", spell_name, "Spell")
    p = W.profile(spell["slug"])
    if not e.get("token"):
        raise RuleError(f"{e['name']} isn't on a map.")
    mid = e["token"]["map"]
    m = g.state["maps"][mid]
    if not side:
        raise RuleError("--hot <side>: which side burns (north|south|east|west..., or inside|outside for a ring)")
    if center:
        cells, c = W.ring(m, center, p)
    else:
        cells, c = W.line(m, ends, p), None
    return {"spell": spell, "map": mid, "cells": cells, "hot": W.hot_cells(cells, side, p, c), "side": side}


def cmd_check(g, a):
    for who in ids(a.who):
        M.ability_check(g, g.get(who), a.what, dc=a.dc, adv=ids(a.adv), dis=ids(a.dis), hidden=a.hidden, now=a.now,
                        purpose=a.purpose)


def cmd_forces(g, a):
    """Standing forces: units with a count, a stat block, a captain, kit, pay and an attitude (engine/forces.py)."""
    if a.action == "list":
        fs = F.units(g)
        print("Forces:" if fs else "No units yet (`forces add`).")
        for uid, u in fs.items():
            print("  " + F.describe(g, uid, u))
        return
    if a.action == "add":
        if not (a.target and a.name and a.stat and a.count):
            raise RuleError('forces add <id> --name "Hanged Men of Thornbury" --stat bandit --count 10 [--where ...] [--captain ...] [--pay "2sp/day"] [--attitude indifferent]')
        F.add(g, a.target, a.name, a.stat, a.count, a.where, a.captain, a.attitude or "indifferent", a.pay)
        return
    u = F.get(g, a.target)
    if a.action == "set":
        if not a.reason:
            raise RuleError("forces set <id> [--count N] [--where ...] [--captain ...] [--attitude ...] [--pay ...] --reason \"...\"")
        before = dict(u)
        for k in ("count", "where", "captain", "pay", "name"):
            v = getattr(a, k, None)
            if v is not None:
                u[k] = v
        if a.attitude:
            if a.attitude not in F.ATTITUDES:
                raise RuleError(f"--attitude {'|'.join(F.ATTITUDES)}")
            u["attitude"] = a.attitude
        if u["count"] < 1:
            F.save(g, a.target, None)
            g.say(f"⚔ {before['name']} is gone — {a.reason}.", kind="info")
            return
        F.save(g, a.target, u)
        g.say(f"⚔ {F.describe(g, a.target, u)} — {a.reason}.", kind="info")
    elif a.action == "equip":
        if not a.source:
            raise RuleError("forces equip <id> --from <container> [--armor ...] [--shield] [--weapon ...]")
        F.equip(g, a.target, a.source, a.armor, a.shield, a.weapon)
    elif a.action == "share":
        if not (a.coins and a.source and a.reason):
            raise RuleError('forces share <id> --coins 20gp --from <who|container> --reason "spoils of the ..."')
        F.share(g, a.target, M.parse_coins(a.coins), a.source, a.reason)
    elif a.action == "split":
        if not (a.count and a.into and a.name):
            raise RuleError('forces split <id> --count N --into <new-id> --name "..."')
        if a.count >= u["count"]:
            raise RuleError(f"{u['name']} has only {u['count']} men; split off fewer.")
        F.save(g, a.target, dict(u, count=u["count"] - a.count))
        F.add(g, a.into, a.name, u["stat"], a.count, a.where or u.get("where"), a.captain, u.get("attitude", "indifferent"), u.get("pay"))
        F.save(g, a.into, dict(F.get(g, a.into), gear=dict(u.get("gear", {}))))
    elif a.action == "enlist":
        if not a.ids:
            raise RuleError("forces enlist <unit> --ids a,b,c")
        F.enlist(g, a.target, ids(a.ids))
    elif a.action == "muster":
        if not (a.count and a.at and a.map):
            raise RuleError("forces muster <id> --count N --at x,y --map <map>")
        F.muster(g, a.target, a.count, a.map, xy(a.at), lambda g2, mon, nm, side, hidden: instantiate_monster(g2, mon, nm, side, hidden))
    else:
        raise RuleError("forces list|add|set|equip|share|split|muster|enlist")


def cmd_loot(g, a):
    """Treasure decided before anyone searches: loot owed by notable foes, sealed caches, tier-fit suggestions."""
    s = g.state
    if a.action == "list":
        left = L.owed(g)
        print("Loot owed (decide before the party searches):" if left else "No loot owed.")
        for x in left:
            print(f"  {x['foe']}: {x['name']} (CR {x.get('cr')}) at {x.get('map')} ({x.get('x')},{x.get('y')}), {fmt_time(x['time'])}")
        sealed = [(mid, c) for mid, m in s["maps"].items() for c in m.get("containers", []) if c.get("sealed")]
        print("Sealed caches:" if sealed else "No sealed caches.")
        for mid, c in sealed:
            inside = [f"{f['item'].get('qty', 1)}× {f['item']['name']}" for f in s["maps"][mid].get("floor", []) if f.get("in") == c["id"]]
            print(f"  {mid}:{c['id']} {c['name']} at ({c['x']},{c['y']})" + (f" lock DC {c['lock_dc']}" if c.get("lock_dc") else "")
                  + ": " + (", ".join(inside) or "no items") + (f", {M.fmt_cp(c['coins_cp'])}" if c.get("coins_cp") else ""))
        return
    if a.action == "suggest":
        cap, rows, total = L.suggest(g, rarity=a.rarity, kind=a.kind)
        print(f"Party level {g.party_level()} (tier {tier(g.party_level())}): magic up to {cap}. {total} SRD items fit"
              + (f"; first {len(rows)}" if total > len(rows) else "") + ":")
        for r in rows:
            print("  " + r)
        return
    if a.action in ("body", "none"):
        x = next((x for x in s.get("loot", []) if x["foe"] == a.target), None)
        e = g.entities.get(a.target)
        if not x and not e:
            raise RuleError(f"No creature '{a.target}'.")
        if x and x["status"] != "owed":
            raise RuleError(f"{x['name']}'s loot is already decided ({x['status']}).")
        if not x:
            t = e.get("token") or {}
            x = {"foe": e["id"], "name": e["name"], "cr": e.get("cr"), "map": t.get("map"), "x": t.get("x"), "y": t.get("y"),
                 "time": s["time"], "status": "owed"}
            g.emit("loot.add", item=x)
        if a.action == "none":
            if not a.reason or len(a.reason.strip()) < 8:
                raise RuleError(f"loot none {a.target} --reason \"why nothing of value (8+ characters)\"")
            g.emit("loot.set", foe=x["foe"], set={"status": "none", "reason": a.reason.strip()})
            g.note(f"💰 {x['name']}: nothing of value ({a.reason.strip()}).")
            return
        if not (a.items or a.coins):
            raise RuleError(f'loot body {a.target} --items "Longsword +1; 2x Potion of Healing" [--coins 30gp] [--at map:x,y] [--name ...]')
        items = L.build_items(g, a.items, a.override)
        coins = M.parse_coins(a.coins) if a.coins else 0
        if coins > TIER_MAX_GP_AWARD[tier(g.party_level())] * 100 and not a.override:
            raise RuleError(f"{M.fmt_cp(coins)} on one body is more than the tier guideline; use --override \"reason\" (public).")
        if a.at:
            mid, _, pos = a.at.rpartition(":")
            px, py = xy(pos)
        else:
            mid, px, py = x.get("map"), x.get("x"), x.get("y")
            if not mid or px is None:
                raise RuleError(f"{x['name']} isn't on a map; give --at <map>:x,y for where the gear lies.")
        box = L.make_cache(g, mid, px, py, a.name or f"{x['name']}'s gear", items, coins, text=a.text, source="loot")
        g.emit("loot.set", foe=x["foe"], set={"status": "decided", "box": box["id"], "box_map": mid})
        g.note(f"💰 {x['name']}'s gear sealed in `{mid}:{box['id']}` at ({px},{py}): {len(items)} item line(s)"
               + (f", {M.fmt_cp(coins)}" if coins else "") + f". Players see it when someone runs `loot open <who> {box['id']}`.")
        return
    if a.action == "cache":
        if not a.target or not a.pos or not a.name:
            raise RuleError('loot cache <map> x,y --name "Iron strongbox" --items "..." [--coins 140gp] [--lock 15] [--text ...]')
        x0, y0 = xy(a.pos)
        items = L.build_items(g, a.items, a.override)
        coins = M.parse_coins(a.coins) if a.coins else 0
        if coins > TIER_MAX_GP_AWARD[tier(g.party_level())] * 100 and not a.override:
            raise RuleError(f"{M.fmt_cp(coins)} in one cache is more than the tier guideline; use --override \"reason\" (public).")
        if a.override and coins > TIER_MAX_GP_AWARD[tier(g.party_level())] * 100:
            g.override(a.override, f"{M.fmt_cp(coins)} in {a.name}")
        box = L.make_cache(g, a.target, x0, y0, a.name, items, coins, lock_dc=a.lock, text=a.text, box_id=a.id, source="loot")
        g.say(f"🧰 {box['name']} at ({x0},{y0}) on {s['maps'][a.target]['name']}" + (" (locked)" if box.get("lock_dc") else "") + ".",
              kind="map")
        g.note(f"  sealed `{box['id']}`: {len(items)} item line(s)" + (f", {M.fmt_cp(coins)}" if coins else "") + " — hidden until opened.")
        return
    if a.action == "open":
        L.open_cache(g, g.get(a.target), a.pos, a.unlocked)
        return
    raise RuleError("loot list|suggest|body|none|cache|open")


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
    # Cloak of Elvenkind: Wisdom (Perception) checks made to perceive its wearer have Disadvantage
    dis_a = ids(a.dis) + (M.perceive_dis(B) if skill_a == "perception" else [])
    dis_b = M.perceive_dis(A) if skill_b == "perception" else []
    ra = M.ability_check(g, A, skill_a, adv=ids(a.adv), dis=dis_a, hidden=a.hidden, now=True,
                         purpose=a.purpose or f"contest: {skill_a} vs {B['name']}'s {skill_b}")
    if a.passive:
        if skill_b not in srd.SKILLS:
            raise RuleError(f"--passive needs a skill for the opponent, got '{skill_b}'.")
        # rules glossary, Passive Perception: +5 with Advantage (a Robe of Eyes), -5 with Disadvantage (a Cloak of Elvenkind)
        p_adv = a.passive_adv or (skill_b == "perception" and bool(M.item_bonus(B, "adv_perception")))
        p_dis = a.passive_dis or bool(dis_b)
        tb = 10 + skill_mod(B, skill_b) + (5 if p_adv else 0) - (5 if p_dis else 0)
        desc_b = f"passive {skill_b.title()} {tb}"
    else:
        rb = M.ability_check(g, B, skill_b, dis=dis_b, hidden=a.hidden, now=True,
                             purpose=f"contest: {skill_b} vs {A['name']}'s {skill_a}")
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
    attacker = g.get(a.attacker) if getattr(a, "attacker", None) else None   # a hand-rolled attack that hit: reactions can answer it
    M.apply_damage(g, e, [[int(amt), a.type.lower()]], source=a.source, crit=a.crit, attacker=attacker)


def cmd_heal(g, a):
    e = g.get(a.who)
    if getattr(a, "undo_death", False):
        # repair: a death that came from a voided DM error is undone (public; never a substitute for a resurrection)
        if not a.override:
            raise RuleError('heal <id> <hp> --undo-death --override "the DM error being corrected"')
        if not e.get("dead"):
            raise RuleError(f"{e['name']} isn't dead.")
        g.override(a.override, f"death of {e['name']} undone")
        hp = int(a.amount) if re.fullmatch(r"\d+", a.amount) else 0
        g.set(e, dead=False, hp=hp, death={"success": 0, "fail": 0, "stable": False})
        c = M.combat(g)
        if c and e["id"] in c.get("defeated", []):
            cc = dict(c)
            cc["defeated"] = [x for x in c["defeated"] if x != e["id"]]
            g.emit("combat.set", combat=cc)
        if hp == 0 and e["kind"] == "pc":
            M.add_condition(g, g.get(e["id"]), "unconscious", source="0 HP", quiet=True)
        g.say(f"⚖ {e['name']} is not dead after all: {hp} HP" + (", Unconscious and dying" if hp == 0 and e["kind"] == "pc" else "") + ".", kind="info")
        return
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


FEATURE_ACTIONS = {"Second Wind": "bonus", "Adrenaline Rush": "bonus", "Rage": "bonus", "Lay On Hands": "bonus", "Bardic Inspiration": "bonus",
                   "Channel Divinity": "action", "Wild Shape": "bonus", "Action Surge": None, "Innate Sorcery": "bonus",
                   "Indomitable": None, "Arcane Recovery": None, "Magical Cunning": None, "Favored Enemy": None,
                   "Focus Points": None, "Sorcery Points": None, "Divine Intervention": "action",
                   "Steady Aim": "bonus", "Fast Hands": "bonus", "Cutting Words": "reaction", "Uncanny Dodge": "reaction"}


def cmd_feature(g, a):
    from .core import has_feature, resources as res_of
    e = g.get(a.who)
    name = a.name
    res = res_of(e)
    key = next((k for k in res if k.lower() == name.lower()), None)
    if not key and not has_feature(e, name):
        raise RuleError(f"{e['name']} doesn't have the feature '{name}' (check the class table in rules/classes/).")
    amount = a.amount or 1
    if getattr(a, "refund", None):
        if not key or not res[key]["used"]:
            raise RuleError(f"{e['name']} has no spent use of '{name}' to refund.")
        g.set(e, **{f"resources_used__{key}": res[key]["used"] - 1})
        g.override(a.refund, f"one use of {key} refunded to {e['name']}")
        g.say(f"⚖ {e['name']}: one use of {key} refunded.", kind="info")
        return
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
    if (key or name).lower() == "uncanny dodge":
        # rules/classes/rogue.md: when an attacker you can see hits you with an attack roll, your Reaction halves the damage
        hit, c = e.get("last_hit"), M.combat(g)
        if not c or not hit or hit.get("round") != c.get("round") or hit.get("time") != g.state["time"] or hit.get("dodged"):
            raise RuleError("Uncanny Dodge answers an attack that just hit you (this round); there's no such hit to halve.")
        # the reaction comes before the damage: judge it on the state before this hit (the hit's own fall to 0 HP
        # doesn't stop it), and if half the damage leaves the rogue standing, that fall never happened
        if e["hp"] == 0 and hit.get("hp_before") and not e.get("dead"):
            half_lost = max(0, hit["hp_lost"] - (hit["amount"] - hit["amount"] // 2))
            if hit["hp_before"] - half_lost > 0:
                M.undo_fall(g, e)
                e = g.get(e["id"])
    if M.combat(g) and act:
        M.use_action(g, e, act, key or name)
    if key:
        g.set(e, **{f"resources_used__{key}": info["used"] + amount})
    k = (key or name).lower()
    if k == "uncanny dodge":
        hit = e["last_hit"]
        back = min(hit["hp_lost"], hit["amount"] - hit["amount"] // 2)
        if hit.get("hp_before") is not None:
            # HP the hit took beyond what was left don't come back: the rogue ends on (HP before) − (half the damage)
            new_hp = max(0, hit["hp_before"] - max(0, hit["hp_lost"] - back))
        else:
            new_hp = e["hp"] + back
        g.set(e, hp=min(M.hp_max(e), new_hp), last_hit=dict(hit, dodged=True))
        back = g.get(e["id"])["hp"] - e["hp"]
        g.say(f"🌀 {e['name']} uses Uncanny Dodge: the hit's {hit['amount']} damage is halved to {hit['amount'] // 2} "
              f"({back} HP back; {g.get(e['id'])['hp']}/{M.hp_max(e)}).", kind="heal", who=e["id"])
        return
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
    elif k == "adrenaline rush":
        # rules/core/04-character-origins.md (Orc): Dash as a Bonus Action, gaining Temporary HP equal to Proficiency Bonus
        if M.combat(g):
            ec = M.economy(g, e["id"])
            M.set_economy(g, e["id"], **({"dashed2": True} if ec.get("dashed") else {"dashed": True}))
        from .core import pb_for_level, level as level_of
        pb = pb_for_level(level_of(e))
        g.say(f"✦ {e['name']} uses Adrenaline Rush: Dash as a Bonus Action.", kind="action")
        M.temp_hp(g, e, pb, "Adrenaline Rush")
    elif k == "arcane recovery":
        # rules/classes/wizard.md: on a Short Rest, recover expended slots whose levels total up to half the wizard level
        # (rounded up), none of level 6+. --note lists the slot levels, e.g. "1,1" or "2".
        wiz = e["classes"].get("Wizard", 0)
        levels = [int(x) for x in re.findall(r"\d+", a.note or "")]
        if not levels:
            raise RuleError('Arcane Recovery: say which slots, e.g. --note "1,1" or --note "2"')
        if sum(levels) > (wiz + 1) // 2 or any(l >= 6 for l in levels):
            raise RuleError(f"Arcane Recovery recovers slots totalling at most {(wiz + 1) // 2} levels, none of level 6+.")
        used = dict(e.get("slots_used", {}))
        for l in levels:
            if used.get(str(l), 0) <= 0:
                raise RuleError(f"{e['name']} has no expended level {l} slot to recover.")
            used[str(l)] -= 1
        g.set(e, slots_used=used)
        g.say(f"📖 {e['name']} uses Arcane Recovery: regains level {', '.join(map(str, levels))} slot(s).", kind="action")
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
    e = g.get(a.who)
    if a.void_fails is not None:
        if a.void_fails < 1:
            raise RuleError("--void-fails needs a number of failures (1-3).")
        # repair: strike death save failures that came from a voided roll (logged publicly)
        if not a.reason:
            raise RuleError('deathsave <who> --void-fails N --reason "..." (after voiding the roll with `ruling`)')
        d = dict(e.get("death") or {})
        if e.get("dead"):
            raise RuleError(f"{e['name']} is dead; use quickload if the player asks, or a ruling first.")
        d["fail"] = max(0, d.get("fail", 0) - a.void_fails)
        g.set(e, death=d)
        g.override(a.reason, f"{a.void_fails} death save failure(s) struck from {e['name']}")
        g.say(f"⚖ {e['name']}: {a.void_fails} death save failure(s) struck ({d['fail']} remain).", kind="info")
        return
    M.death_save(g, e, now=a.now)


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
    if getattr(a, "refund_hd", None):
        # repair: give back Hit Point Dice spent by mistake (logged publicly); no rest is taken
        if not a.reason:
            raise RuleError('rest short --refund-hd kira:1 --reason "..."')
        for part in ids(a.refund_hd):
            k, _, n = part.partition(":")
            e = g.get(k)
            spent = dict(e.get("hd_spent", {}))
            left = int(n or 1)
            for cls in sorted(spent, key=lambda c: -spent[c]):
                take = min(left, spent[cls])
                spent[cls] -= take
                left -= take
            if left:
                raise RuleError(f"{e['name']} hasn't spent that many Hit Point Dice.")
            g.set(e, hd_spent=spent)
            g.override(a.reason, f"{n or 1} Hit Point Die refunded to {e['name']}")
            g.say(f"⚖ {e['name']}: {n or 1} Hit Point Die refunded.", kind="info")
        return
    members = [g.get(i) for i in ids(a.who)] if a.who else [e for e in g.pcs() if not e.get("dead")]
    focus, attune_to = rest_focus(g, a)
    if a.kind == "short":
        hd = {}
        for part in ids(a.hd):
            k, _, n = part.partition(":")
            hd[g.get(k)["id"]] = int(n or 1)
        M.short_rest(g, members, hd, focus, attune_to)
    elif getattr(a, "ended_at", None):
        # repair: the time already passed (a journey's nights) held a Long Rest the engine didn't credit; logged publicly
        when = parse_when(a.ended_at)
        if when is None or not a.reason:
            raise RuleError('rest long --ended-at "Day N, HH:MM" --reason "..."')
        if when > g.state["time"]:
            raise RuleError("--ended-at must be in the past (use `rest long` for a rest taken now).")
        for e in members:
            last = e.get("last_long_rest_end")
            if last is not None and when - 8 * 60 - last < 16 * 60:
                raise RuleError(f"{e['name']} had finished a Long Rest {M.fmt_duration(when - 8 * 60 - last)} before that one began — "
                                f"Long Rests need 16 hours between them (rules/core/08-rules-glossary.md → Long Rest).")
        if focus or attune_to:
            raise RuleError("--focus / --attune need a rest taken now (`rest short` or `rest long`), not a repair.")
        g.override(a.reason, f"a Long Rest ending {fmt_time(when)} credited to {', '.join(e['name'] for e in members)}")
        M.long_rest(g, members, ended_at=when)
    else:
        M.long_rest(g, members)
        # rules/core/06-equipment.md: identifying or attuning takes a Short Rest focused on the item; a Long Rest's
        # 8 hours include that time (one item per creature, as for a Short Rest)
        for eid, ref in focus.items():
            M.identify_item(g, g.get(eid), ref, "focused on it through the Long Rest")
        for eid, ref in attune_to.items():
            M.attune(g, g.get(eid), ref, during_rest="Long Rest")


def rest_focus(g, a):
    """--focus / --attune who:item-id pairs: one magic item per creature per rest, to identify it or to attune to it."""
    focus, attune_to = {}, {}
    for part in ids(getattr(a, "focus", None)):
        k, _, item = part.partition(":")
        if not item:
            raise RuleError("--focus who:item-id (one magic item per creature)")
        if g.get(k)["id"] in focus:
            raise RuleError("A creature can focus on only one magic item per rest.")
        M.find_item(g.get(k), item)
        focus[g.get(k)["id"]] = item
    for part in ids(getattr(a, "attune", None)):
        k, _, item = part.partition(":")
        if not item:
            raise RuleError("--attune who:item-id (one magic item per creature)")
        eid = g.get(k)["id"]
        if eid in attune_to or eid in focus:
            raise RuleError("A creature can focus on only one magic item per rest (to identify it or to attune to it).")
        M.find_item(g.get(eid), item)
        attune_to[eid] = item
    return focus, attune_to


def cmd_time(g, a):
    if a.rewind_to:
        # repair only: a command run by mistake (a journey nobody declared) moved the clock; put it back, publicly.
        # Nothing that fired in the voided span is undone here: check the log and repair those separately.
        when = parse_when(a.rewind_to)
        if when is None:
            raise RuleError('--rewind-to "Day N, HH:MM"')
        if not a.override:
            raise RuleError('time --rewind-to "Day N, HH:MM" --override "the DM error being corrected"')
        if when >= g.state["time"]:
            raise RuleError("--rewind-to must be earlier than now (time moves forward with `time <amount>`).")
        g.override(a.override, f"the clock put back from {fmt_time(g.state['time'])} to {fmt_time(when)}")
        g.emit("time.set", minutes=when)
        td = g.state["view"].get("travel_day")
        if td and td.get("start", 0) > when:
            g.emit("view.set", travel_day=None)
        g.say(f"⏪ The clock is put back to {fmt_time(when)} — {a.override}.", kind="time")
        return
    if not a.amount:
        raise RuleError("time <amount> (e.g. 2h, 30m)")
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
        mid = a.map or next((k for k, m in g.state["maps"].items() if m.get("world")), None) or             next((k for k, m in g.state["maps"].items() if m["kind"] == "region"), None)
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
    # rules/core/09-gameplay-toolbox.md: past 8 hours of travel in a day, a Constitution save at the end of each extra
    # hour (DC 10 + hours past 8) or 1 Exhaustion level. The day's hours count until a Long Rest or 24 hours pass.
    now = g.state["time"]
    walkers = [e for e in g.pcs() if not e.get("dead")]
    day = dict(g.state["view"].get("travel_day") or {})
    rested = max([e.get("last_long_rest_end") or -1 for e in walkers] or [-1])
    if not day or now - day["start"] >= 1440 or rested >= day["start"]:
        day = {"start": now, "hours": 0.0}
    done, push = day["hours"], False
    narrated = g.state["settings"].get("forced_march", "srd") == "narrated"
    if narrated and not getattr(a, "push", False):
        total_min = int(hours * 60) if hours <= 16 else total_min
    elif hours <= 8 and done + hours > 8:
        if not getattr(a, "push", False):
            from engine.core import save_mod
            dcs = [10 + (h - 8) for h in range(max(9, int(done) + 1), int(done + hours) + 1)]
            odds = []
            for e in walkers:
                ok = 1.0
                for dc in dcs:   # chance of passing every save (a natural 20 isn't an automatic success on a save)
                    ok *= min(1.0, max(0.0, (21 - (dc - save_mod(e, "con"))) / 20))
                odds.append(f"{e['name']} {round((1 - ok) * 100)}%")
            raise RuleError(f"The party has travelled {done:.1f} h today; this leg takes {hours:.1f} h and runs "
                            f"{done + hours - 8:.1f} h past 8 hours. That's a forced march: at the end of each extra hour "
                            f"everyone makes a Constitution save ({', '.join(f'DC {d}' for d in dcs) or 'none completed'}) or "
                            f"gains 1 Exhaustion level (each level: -2 to every d20 test and -5 ft Speed; 6 levels kill; a Long "
                            f"Rest removes one). Chance of tiring at least once: {', '.join(odds)}. Add --push to march on, "
                            f"travel {max(0.0, 8 - done) * pace:.0f} miles or less, or rest first.")
        total_min, push = int(hours * 60), True
    g.emit("time.set", minutes=g.state["time"] + total_min)
    if region:
        g.emit("view.set", party_pos=[tx, ty])
    M.after_time(g)
    # A journey of more than one travel day spends its nights off the road: 8 hours on the move and 16 off each day,
    # time enough for a Long Rest every night (rules/core/09-gameplay-toolbox.md, Travel Pace; 08-rules-glossary.md, Long Rest).
    nights = int(total_min // 1440)
    if nights >= 1 and not push:
        rest_end = g.state["time"] - int(round(rem * 60))
        able = [e for e in walkers if e["hp"] >= 1 and (e.get("last_long_rest_end") is None
                                                         or rest_end - 8 * 60 - e["last_long_rest_end"] >= 16 * 60)]
        if able:
            M.long_rest(g, able, ended_at=rest_end, nights=nights)
    g.say(f"🧭 The party travels {miles} miles at a {a.pace} pace ({pace} mph, 8 hours a day"
          f"{', difficult terrain counted' if region else ''}) — "
          f"{f'{hours:.1f} h' if narrated and not push and hours <= 16 else f'{int(days)} day(s) {rem:.1f} h'}. Now {fmt_time(g.state['time'])}.", kind="time")
    if a.pace == "fast":
        g.say("   Fast pace: Disadvantage on Wisdom (Perception/Survival) and Dexterity (Stealth) checks while travelling.")
    if a.pace == "slow":
        g.say("   Slow pace: Advantage on Wisdom (Perception/Survival) checks; the party can travel stealthily.")
    if narrated and not push and done + hours > 8:
        g.say("   House rule (travel is narrated): no forced-march saves for an ordinary journey.")
    if narrated and getattr(a, "push", False) and done + hours > 8:
        push = True   # a deliberate, punishing push: the SRD saves apply
    if push:
        for hour in range(max(9, int(done) + 1), int(done + hours) + 1):
            dc = 10 + (hour - 8)
            for e in walkers:
                res = M.saving_throw(g, g.get(e["id"]), "con", dc, source=f"forced march, hour {hour}", now=True)
                if res and res.get("success") is False:
                    cur = g.get(e["id"])
                    new = min(6, cur.get("exhaustion", 0) + 1)
                    g.set(cur, exhaustion=new)
                    g.say(f"   {cur['name']}'s Exhaustion is now {new} (forced march).", kind="condition")
                    if new >= 6:
                        g.set(cur, dead=True)
                        g.say(f"   {cur['name']} DIES from exhaustion.", kind="condition")
        day["hours"] = done + hours
    else:
        day["hours"] = rem if days else done + hours
    if days:
        day["start"] = g.state["time"] - int(rem * 60)
    g.emit("view.set", travel_day=day)


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
        appraised = M.parse_coins(a.price) if (a.action == "sell" and a.price) else None
        M.remove_item(g, e, a.item, a.qty, "dropped" if a.action == "drop" else a.source or "removed", sell=a.action == "sell", to=to,
                      appraised_cp=appraised)
    elif a.action == "pickup":
        M.pick_up(g, e, a.item, with_attack=getattr(a, 'with_attack', False))
    elif a.action == "stash":
        if not a.to:
            raise RuleError("item stash <who> <item-id> --to <container-id> [--qty N]  (see `map container`)")
        if any(i["id"] == a.to for i in e.get("inventory", [])):
            M.bag_item(g, e, a.item, a.to, a.qty if a.qty != 1 else None)   # a carried bag (Bag of Holding)
        else:
            M.stash_item(g, e, a.item, a.to, a.qty)
    elif a.action == "unbag":
        M.unbag_item(g, e, a.item)
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
        M.use_item(g, e, a.item, a.to, level=a.level)
    elif a.action == "recover-thrown":
        M.recover_thrown(g, e, a.item, a.how)
    elif a.action == "venom-hit":
        if not a.to:
            raise RuleError('item venom-hit <who> <item> --to <target> --how "..."')
        M.venom_hit(g, e, a.item, a.to, a.how)
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
        if re.search(r"flame tongue", it["name"], re.I):
            # rules/magic-items/flame-tongue.md: a Bonus Action and a command word, while holding it (on or off)
            if not it.get("equipped"):
                raise RuleError(f"{e['name']} must be holding the {it['name']} to ignite it (`item equip`).")
            if not it.get("attuned"):
                raise RuleError(f"The {it['name']} requires attunement before its command word works.")
            M.use_action(g, e, "bonus", "Flame Tongue command word")
            inv = [dict(i, lit=not i.get("lit")) if i["id"] == it["id"] else i for i in e["inventory"]]
            g.set(e, inventory=inv)
            g.say(f"🔥 {e['name']}'s {it['name']} " + ("bursts into flame (+2d6 Fire on a hit; Bright Light 40 ft, Dim 40 ft more)."
                                                        if not it.get("lit") else "gutters out."))
            M.reveal_for(g, g.get(e["id"]))
            return
        if not re.search(r"torch|lantern|candle", it["name"], re.I):
            raise RuleError("Only torches, lanterns and candles (and a Flame Tongue) can be lit.")
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
        last = encs[-1]
        # magic ammunition (Arrows +1) stops being magical once it hits: only its misses come back magic, the rest as plain
        fired_magic = last.get("ammo_magic", {}).get(e["id"], {})
        hits_magic = last.get("ammo_magic_hits", {}).get(e["id"], {})
        want = M.resolve_item(g, a.item) or {}
        kind = "magic" if want.get("magic_bonus") else "plain"
        if any(x.get("recovered_for") == e["id"] and x.get("encounter") == idx and x.get("kind", "plain") == kind
               for x in g.state["encounters"]):
            raise RuleError(f"{'Magic' if kind == 'magic' else 'Plain'} ammunition from that fight was already recovered.")
        if kind == "magic":
            name = next((k for k in fired_magic if k.lower() == want["name"].lower()), None)
            if not name:
                raise RuleError(f"{e['name']} fired no {want['name']} in the last combat.")
            n = (fired_magic[name] - hits_magic.get(name, 0)) // 2
        else:
            n = (last["ammo"][e["id"]] - sum(fired_magic.values()) + sum(hits_magic.values())) // 2
        if n < 1:
            raise RuleError("Too little ammunition was spent to recover any (half, rounded down).")
        M.add_item(g, e, a.item, qty=n, source="found: recovered after combat", override=a.override,
                   identified=True if kind == "magic" else None)
        g.emit("encounter.log", recovered_for=e["id"], encounter=idx, qty=n, kind=kind)
    elif a.action == "card":
        it = M.find_item(e, a.item)
        out = Path(g.dir) / "views" / f"item-{it['id']}.svg"
        out.parent.mkdir(exist_ok=True)
        out.write_text(assets.item_card(it), encoding="utf-8")
        print(out)
    else:
        raise RuleError("item add|remove|drop|sell|give|equip|unequip|attune|unattune|use|light|recover-ammo|card")


def _find_box(g, ref, near=None):
    """A container (chest, strongbox, vault) by id on any map, or None. Ids are unique per map, so when two maps share
    one, the box on the map where `near` (a creature id) stands wins."""
    found = [(m, c) for m in g.state["maps"].values() for c in m.get("containers", []) if c["id"] == ref]
    here = ((g.entities.get(near) or {}).get("token") or {}).get("map") if near else None
    return next(((m, c) for m, c in found if m["id"] == here), found[0] if found else None)


def _box_coins(g, m, box, delta):
    if delta < 0 and box.get("sealed"):
        raise RuleError(f"Nobody has opened the {box['name']} yet: `loot open <who> {box['id']}` first.")
    have = box.get("coins_cp", 0)
    if have + delta < 0:
        raise RuleError(f"{box['name']} holds only {M.fmt_cp(have)}.")
    boxes = [dict(c, coins_cp=have + delta) if c["id"] == box["id"] else c for c in m.get("containers", [])]
    g.emit("map.set", id=m["id"], set={"containers": boxes})
    return have + delta


def cmd_coins(g, a):
    # coins kept in a container (a vault, a strongbox): `coins <box-id> 500gp --from kit` deposits,
    # `coins kit 200gp --from <box-id>` withdraws. The character must be on the container's map.
    box_to = _find_box(g, a.who, near=getattr(a, "from_who", None))
    box_from = _find_box(g, a.from_who, near=a.who) if getattr(a, "from_who", None) else None
    if box_to and not getattr(a, "from_who", None):
        # money arriving in (or spent straight out of) the vault: a tribute, a sale, wages paid from it
        m, box = box_to
        delta = M.parse_coins(a.amount)
        if not a.source:
            raise RuleError("Vault coins need --source (tribute: ..., sold: ..., spent: ...), or --from <who> to move a purse.")
        if delta > 0:
            cap = TIER_MAX_GP_AWARD[tier(g.party_level())] * 100
            if delta > cap and not a.override:
                raise RuleError(f"{M.fmt_cp(delta)} at once exceeds the tier {tier(g.party_level())} guideline ({M.fmt_cp(cap)}). "
                                "Use --override \"reason\" (shown to the player) for a genuine hoard.")
            if a.override:
                g.override(a.override, f"{M.fmt_cp(delta)} into {box['name']}")
        total = _box_coins(g, m, box, delta)
        g.say(f"💰 {box['name']} {'receives' if delta > 0 else 'pays out'} {M.fmt_cp(abs(delta))} ({a.source}). "
              f"{box['name']}: {M.fmt_cp(total)}.", kind="item")
        return
    if box_to or box_from:
        delta = M.parse_coins(a.amount)
        if delta <= 0:
            raise RuleError("Vault coins move with --from: `coins <box> 500gp --from kit` or `coins kit 200gp --from <box>`.")
        (m, box), who = (box_to, a.from_who) if box_to else (box_from, a.who)
        e = g.get(who)
        if (e.get("token") or {}).get("map") != m["id"]:
            raise RuleError(f"{e['name']} must be at {m['name']} to use {box['name']}.")
        if box_to:
            M.change_coins(g, e, -delta, a.source or f"put in {box['name']}")
            total = _box_coins(g, m, box, delta)
            g.say(f"💰 {e['name']} puts {M.fmt_cp(delta)} into {box['name']}. {box['name']}: {M.fmt_cp(total)}; purse "
                  f"{M.fmt_cp(M.coins_total_cp(g.get(e['id'])))}.", kind="item")
        else:
            total = _box_coins(g, m, box, -delta)
            M.change_coins(g, e, delta, a.source or f"taken from {box['name']}")
            g.say(f"💰 {e['name']} takes {M.fmt_cp(delta)} from {box['name']}. {box['name']}: {M.fmt_cp(total)}; purse "
                  f"{M.fmt_cp(M.coins_total_cp(g.get(e['id'])))}.", kind="item")
        return
    e = g.get(a.who)
    delta = M.parse_coins(a.amount)
    if getattr(a, "from_who", None):
        # a hand-over between characters moves existing money, so the loot cap doesn't apply
        giver = g.get(a.from_who)
        if delta <= 0:
            raise RuleError("coins <to> <amount> --from <giver>: the amount must be positive.")
        if giver["id"] == e["id"]:
            raise RuleError("A character can't hand coins to themselves.")
        M.change_coins(g, giver, -delta, a.source or f"given to {e['name']}")
        M.change_coins(g, e, delta, a.source or f"from {giver['name']}")
        g.say(f"💰 {giver['name']} hands {M.fmt_cp(delta)} to {e['name']}. Purses: {giver['name']} "
              f"{M.fmt_cp(M.coins_total_cp(g.get(giver['id'])))}, {e['name']} {M.fmt_cp(M.coins_total_cp(g.get(e['id'])))}.", kind="item")
        return
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


def cmd_agenda(g, a):
    """Scheduled events the engine remembers: deliveries, debts, visits, deadlines. They're announced when their
    time comes (`time`, `travel`, `rest`), and a payment marked --auto is made into or out of its target then."""
    from .core import parse_when, parse_duration, fmt_time
    items = g.state.get("agenda", [])
    if a.action == "add":
        if not a.text:
            raise RuleError("agenda add needs --text \"what happens\".")
        due = parse_when(a.at) if a.at else (g.state["time"] + parse_duration(a.inn) if a.inn else None)
        if due is None:
            raise RuleError("agenda add needs --at \"Day 7 08:00\" or --in 2d.")
        item = {"id": f"a{len(items) + 1}", "due": due, "text": a.text, "status": "pending", "secret": bool(a.secret)}
        if a.pay:
            if not a.to:
                raise RuleError("A payment needs --to <container or character> (e.g. --to treasury).")
            pay = a.pay.strip()
            if "d" in pay.lower().replace("gp", ""):
                item["pay"] = pay.lower().replace("gp", "")   # dice, in crowns, rolled when it falls due
            else:
                item["pay"] = M.parse_coins(pay)
            item.update(to=a.to, auto=bool(a.auto))
        if due <= g.state["time"]:
            raise RuleError(f"{fmt_time(due)} has already passed (it's {fmt_time(g.state['time'])}).")
        g.emit("agenda.add", item=item)
        (g.note if a.secret else lambda m: g.say(m, kind="info"))(
            f"📅 Scheduled for {fmt_time(due)}: {a.text}" + (f" ({'auto-paid' if a.auto else 'payment'} "
            f"{item['pay'] if isinstance(item['pay'], str) else ('-' if item['pay'] < 0 else '') + M.fmt_cp(abs(item['pay']))} {'out of' if not isinstance(item['pay'], str) and item['pay'] < 0 else 'to'} {a.to})" if a.pay else "") + f" [{item['id']}]")
    elif a.action in ("done", "cancel"):
        it = next((x for x in items if x["id"] == a.target), None)
        if not it:
            raise RuleError(f"No agenda item '{a.target}'. `agenda list` shows them.")
        g.emit("agenda.set", id=it["id"], set={"status": "done" if a.action == "done" else "cancelled", "note": a.note or a.reason})
        g.note(f"📅 {it['id']} {a.action}: {it['text']}" + (f" — {a.note or a.reason}" if (a.note or a.reason) else ""))
    else:
        open_ = [x for x in items if x["status"] in ("pending", "due")]
        if not open_:
            g.note("Agenda: nothing scheduled.")
        for x in sorted(open_, key=lambda x: x["due"]):
            g.note(f"  {x['id']}  {fmt_time(x['due'])}  [{x['status']}{', secret' if x.get('secret') else ''}]  {x['text']}"
                   + (f"  ({'auto ' if x.get('auto') else ''}{x['pay'] if isinstance(x['pay'], str) else M.fmt_cp(x['pay'])} → {x['to']})" if x.get('pay') else ""))


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
        elif a.overcome:
            # stat-block XP for foes overcome without being killed (captured, charmed and taken, routed, surrendered).
            # This is the creatures' own XP, so it isn't capped by the story-award budget: a dragon is worth a dragon.
            if not a.reason:
                raise RuleError('xp award --overcome <ids> --reason "how they were overcome (captured, routed...)"')
            done = {d for x in g.state["encounters"] for d in x.get("defeated", [])}
            total, names = 0, []
            for cid in ids(a.overcome):
                e = g.get(cid)
                if e["kind"] == "pc":
                    raise RuleError(f"{e['name']} is a party character.")
                if e.get("xp_awarded") or (e.get("dead") and e["id"] in done):
                    raise RuleError(f"XP for {e['name']} was already awarded.")
                xp = e.get("xp") or (srd.find("monsters", e["srd"]) or {}).get("xp", 0) if e.get("srd") else e.get("xp")
                if not xp:
                    raise RuleError(f"{e['name']} has no XP value in its stat block.")
                total += xp
                names.append(f"{e['name']} ({xp})")
                g.set(e, xp_awarded=True)
            M.award_xp(g, members, total, f"{a.reason}: " + ", ".join(names))
        else:
            if not a.amount or not a.reason:
                raise RuleError("xp award --encounter, --overcome <ids>, or --amount N --reason \"quest/trap/social encounter overcome\"")
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

def _map_set_one(g, s, m, kv):
    k, _, v = kv.partition("=")
    styles = {"walls": render.WALL_STYLES, "floor": render.FINE_STYLES, "wood": render.WOOD_STYLES, "stone": render.STONE_STYLES}
    if k == "world":
        # the region map of record: always one click away on the table, whatever map the scene is on
        if m["kind"] != "region":
            raise RuleError("Only a region map can be the world map (`map gen region`).")
        on = v.lower() in ("on", "true", "yes", "1")
        g.emit("map.set", id=m["id"], set={"world": on, **({"shown": True} if on else {})})
        g.say(f"🗺 {m['name']} is {'now the world map: always open on the table' if on else 'no longer the world map'}.", kind="map")
        return
    if k == "known":
        # a place the party already knows (explored before play, or on an earlier visit): its tab stays on the table
        # whenever they're anywhere connected to it (`map link`), without the table switching to it now
        on = v.lower() in ("on", "true", "yes", "1")
        g.emit("map.set", id=m["id"], set={"shown": on})
        g.say(f"🗺 {m['name']} is {'known to the party' if on else 'no longer on the table'}.", kind="map")
        return
    if k == "parent":
        # the hierarchy: region > area (a town and all its quarters) > section (one quarter) > interior (a building)
        if v in ("", "none"):
            g.emit("map.set", id=m["id"], set={"parent": None})
            g.note(f"  {m['name']} no longer sits inside another map.")
            return
        if v not in s["maps"]:
            raise RuleError(f"parent: no map '{v}' (`map list`)")
        if v == m["id"] or m["id"] in views.map_ancestors(s, v):
            raise RuleError("parent: a map can't sit inside itself or inside one of its own children")
        g.emit("map.set", id=m["id"], set={"parent": v})
        g.note(f"  {m['name']} sits inside {s['maps'][v]['name']}.")
        return
    if k == "anchor":
        # the place on the parent map (a town, a site, a poi) that opens this map when the players click it
        par = s["maps"].get(m.get("parent") or "")
        if not par:
            raise RuleError("anchor: set the map's parent first (`--kv parent=<map>`)")
        places = {p.get("id") for p in par.get("pois", []) + par.get("settlements", [])}
        if v not in places:
            raise RuleError(f"anchor: no town, site or poi '{v}' on {par['name']}")
        g.emit("map.set", id=m["id"], set={"anchor": v})
        g.note(f"  Clicking {v} on {par['name']} opens {m['name']} (once the party knows it).")
        return
    if k == "level":
        if v not in views.LEVELS:
            raise RuleError("level: " + "|".join(views.LEVELS))
        g.emit("map.set", id=m["id"], set={"level": v})
        g.note(f"  {m['name']} is a{'n' if v[0] in 'aei' else ''} {v} map.")
        return
    if k not in ("name", "lighting", "fog", "theme", "accent", *styles):
        raise RuleError("map set name=...|parent=<map>|anchor=<place on the parent>|level=region|area|section|interior|lighting=bright|dim|dark|fog=true|false|theme=" + "|".join(render.THEMES) +
                        "|" + "|".join(f"{s}={'/'.join(o)}" for s, o in styles.items()) + "|accent=#rrggbb|world=on|off|known=on|off")
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


# smallest open area (in 5 ft squares) a hand-drawn map may have without --small: room for a fight
MIN_PLAY_W, MIN_PLAY_H = 20, 14


REGION_SETTLEMENTS = ("hamlet", "village", "town", "city", "capital", "castle", "abbey")
REGION_SITES = ("ruins", "dungeon", "tower", "cave", "shrine", "camp", "lair", "battlefield", "grove", "barrow", "mine",
                "bridge", "inn", "mill", "stones")


def _line_cells(x0, y0, x1, y1):
    """Every square on the straight line between two waypoints (Bresenham), so roads and rivers stay connected."""
    cells, dx, dy = [], abs(x1 - x0), -abs(y1 - y0)
    sx, sy, err = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1), abs(x1 - x0) - abs(y1 - y0)
    while True:
        cells.append([x0, y0])
        if (x0, y0) == (x1, y1):
            return cells
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def region_edit(g, a):
    """Author a region map by hand: the world map of record. Towns and sites can be clicked on the table for what the
    party knows of them (their journal entry); hidden ones stay off the players' map until `map discover`."""
    s = g.state
    if a.target not in s["maps"] or s["maps"][a.target]["kind"] != "region":
        raise RuleError(f"map {a.action} works on a region map (`map gen region`); '{a.target}' isn't one.")
    m = s["maps"][a.target]
    settlements = [dict(x) for x in m.get("settlements", [])]
    sites = [dict(x) for x in m.get("pois", [])]
    if a.action in ("settlement", "site"):
        kinds = REGION_SETTLEMENTS if a.action == "settlement" else REGION_SITES
        a.ftype = getattr(a, "stype", None) or a.ftype
        if not a.at or not a.name or (a.ftype or "") not in kinds:
            raise RuleError(f'map {a.action} <region> x,y --name "Name" --type {"|".join(kinds)} [--text "what is known"] [--hidden]')
        x, y = xy(a.at)
        if not (0 <= x < m["w"] and 0 <= y < m["h"]):
            raise RuleError(f"({x},{y}) is outside {m['name']} ({m['w']}×{m['h']}).")
        if any((o["x"], o["y"]) == (x, y) for o in settlements + sites):
            raise RuleError(f"({x},{y}) already holds a town or site on {m['name']}.")
        pid = srd.slug(a.name)[:40] or f"{a.action}-{len(settlements) + len(sites) + 1}"
        while any(o.get("id") == pid for o in settlements + sites):
            pid += "-2"
        entry = {"id": pid, "x": x, "y": y, "kind": a.ftype, "name": a.name, "hidden": bool(a.hidden)}
        if a.text and not a.hidden:
            entry["journal"] = f"j{len(s.get('journal', [])) + 1}"
            journal_add(g, {"kind": "text", "title": a.name, "text": a.text, "ref": a.text,
                            "poi": {"map": m["id"], "x": x, "y": y}, "cat": "place"})
        elif a.text:
            entry["text"] = a.text   # kept for when it's discovered
        (settlements if a.action == "settlement" else sites).append(entry)
        g.emit("map.set", id=m["id"], set={"settlements": settlements, "pois": sites})
        if a.hidden:   # a place the party hasn't heard of must not appear in the table's log either
            g.note(f"🗺 {a.name} ({a.ftype}) marked at ({x},{y}) on {m['name']} (hidden from the players).")
        else:
            g.say(f"🗺 {a.name} ({a.ftype}) marked at ({x},{y}) on {m['name']}.", kind="map")
    elif a.action == "route":
        # map route <region> road|river --path "x,y x,y ..." : straight runs between the waypoints
        kind, way = a.at, getattr(a, "route_path", None) or a.rect
        if kind not in ("road", "river") or not way:
            raise RuleError('map route <region> road|river --path "x,y x,y x,y ..." (waypoints, in order)')
        pts = [xy(t) for t in way.replace(";", " ").split() if t.strip()]
        if len(pts) < 2:
            raise RuleError("A road or river needs at least two waypoints.")
        cells = []
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            seg = _line_cells(x0, y0, x1, y1)
            cells += seg if not cells else seg[1:]
        key = "roads" if kind == "road" else "rivers"
        g.emit("map.set", id=m["id"], set={key: m.get(key, []) + [cells]})
        g.say(f"🗺 A {kind} drawn on {m['name']} through {len(pts)} waypoints ({len(cells)} squares)" +
              (f": {a.name}." if a.name else "."), kind="map")
    elif a.action == "discover":
        # the party learns of a hidden town or site: it appears on their map, with what they now know
        ref = a.at
        hit = next((o for o in settlements + sites if o.get("id") == ref), None)
        if not hit:
            raise RuleError(f"No town or site '{ref}' on {m['name']}.")
        hit["hidden"] = False
        text = a.text or hit.pop("text", None)
        if text and not hit.get("journal"):
            hit["journal"] = f"j{len(s.get('journal', [])) + 1}"
            journal_add(g, {"kind": "text", "title": hit["name"], "text": text, "ref": text,
                            "poi": {"map": m["id"], "x": hit["x"], "y": hit["y"]}, "cat": "place"})
        g.emit("map.set", id=m["id"], set={"settlements": settlements, "pois": sites})
        g.say(f"🗺 {hit['name']} is now on the party's map.", kind="map")
    else:  # region-remove
        if not a.id or not a.reason:
            raise RuleError('map region-remove <region> --id <town|site|road-N|river-N> --reason "what happened"')
        if a.id.startswith(("road-", "river-")) and a.id.split("-")[1].isdigit():
            key, n = ("roads" if a.id.startswith("road-") else "rivers"), int(a.id.split("-")[1])
            lst = list(m.get(key, []))
            if not 1 <= n <= len(lst):
                raise RuleError(f"No {a.id} on {m['name']} ({len(lst)} {key}).")
            lst.pop(n - 1)
            g.emit("map.set", id=m["id"], set={key: lst})
        else:
            keep_s = [o for o in settlements if o.get("id") != a.id]
            keep_p = [o for o in sites if o.get("id") != a.id]
            if len(keep_s) + len(keep_p) == len(settlements) + len(sites):
                raise RuleError(f"No town or site '{a.id}' on {m['name']}.")
            g.emit("map.set", id=m["id"], set={"settlements": keep_s, "pois": keep_p})
        g.say(f"🗺 {a.id} removed from {m['name']}: {a.reason}.", kind="map")


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
        if not a.kv:
            raise RuleError("map set <id> --kv key=value [--kv key=value ...]")
        for kv in a.kv:
            _map_set_one(g, s, m, kv)
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
                # a map object is filed under the journal's "Places & objects", not "Handouts & clues",
                # unless the DM marks it as a story clue (--clue) or files it there later (`journal file`)
                journal_add(g, {"kind": "text", "title": a.name, "text": a.text, "ref": a.text,
                                "poi": {"map": m["id"], "x": x, "y": y}, "cat": "clue" if a.clue else "place"})
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
    elif a.action == "spell-wall":
        # draw a wall for a spell its caster is already concentrating on (cast before the engine drew walls, or
        # redrawn after a fix): no new save, it only stands from now on and burns as the spell says
        if not (a.caster and a.spell and (a.line or a.ring) and a.hot):
            raise RuleError('map spell-wall --caster <id> --spell "wall of fire" (--line "x,y x,y" | --ring x,y) --hot <side>')
        ce = g.get(a.caster)
        spell = g.require("spells", a.spell, "Spell")
        if (ce.get("concentration") or {}).get("spell") != spell["slug"]:
            raise RuleError(f"{ce['name']} isn't concentrating on {spell['name']}.")
        plan = wall_plan(g, a.caster, a.spell, a.line, a.ring, a.hot)
        m = g.state["maps"][plan["map"]]
        keep = [w for w in m.get("spell_walls", []) if not (w["caster"] == ce["id"] and w["spell"] == spell["slug"])]
        if len(keep) != len(m.get("spell_walls", [])):
            g.emit("map.set", id=plan["map"], set={"spell_walls": keep})   # redrawn: the old outline is replaced
        W.add(g, ce, spell, plan["map"], plan["cells"], plan["hot"], plan["side"],
              (ce.get("concentration") or {}).get("level") or spell["level"])
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
    elif a.action in ("settlement", "site", "route", "discover", "region-remove"):
        region_edit(g, a)
    elif a.action == "label":
        m = s["maps"][a.target]
        x, y = xy(a.at)
        g.emit("map.set", id=m["id"], set={"labels": m["labels"] + [{"x": x, "y": y, "text": a.name, "hidden": a.hidden}]})
    elif a.action == "unlabel":
        m = s["maps"][a.target]
        x, y = xy(a.at)
        keep = [l for l in m["labels"] if (l["x"], l["y"]) != (x, y)]
        if len(keep) == len(m["labels"]):
            raise RuleError(f"No label at ({x},{y}) on {m['id']}.")
        g.emit("map.set", id=m["id"], set={"labels": keep})
        print(f"🏷 Label removed at ({x},{y}) on {m['name']}.")
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
        region = s["maps"][mid]["kind"] == "region"
        bad = sorted({ch for r in rows for ch in r if ch not in (maps.BIOMES if region else maps.TERRAIN)})
        if bad:
            raise RuleError(f"Unknown terrain codes in grid: {' '.join(repr(b) for b in bad)}" +
                            (f" (region codes: {' '.join(maps.BIOMES)})" if region else ""))
        if region:
            # a hand-drawn region replaces the generator's land: its random towns, roads, rivers and labels go with it;
            # towns and sites placed by hand (`map settlement` / `map site`) stay
            m = s["maps"][mid]
            g.emit("map.set", id=mid, set={"grid": rows, "w": width, "h": len(rows), "revealed": ["1" * width] * len(rows),
                                           "roads": [], "rivers": [], "labels": [],
                                           "settlements": [x for x in m.get("settlements", []) if x.get("id")],
                                           "pois": [x for x in m.get("pois", []) if x.get("id")]})
            print(f"Imported a {width}×{len(rows)} region grid into '{m['name']}' "
                  f"({m.get('miles_per_cell', 2)} miles a square). The generator's towns, roads and rivers were cleared; "
                  "draw your own with `map settlement`, `map site` and `map route`.")
            return
        # a playable map needs room to fight in: measure the open area (everything that isn't solid wall), so a tiny
        # room padded out with wall rows doesn't pass. Genuinely small places (a skiff, a cell) say so with --small.
        open_cells = [(x, y) for y, r in enumerate(rows) for x, ch in enumerate(r) if ch != "#"]
        if open_cells and not a.small:
            ow = max(x for x, _ in open_cells) - min(x for x, _ in open_cells) + 1
            oh = max(y for _, y in open_cells) - min(y for _, y in open_cells) + 1
            if ow < MIN_PLAY_W or oh < MIN_PLAY_H:
                raise RuleError(f"the open area of this grid is only {ow}×{oh} squares; a playable map needs at least "
                                f"{MIN_PLAY_W}×{MIN_PLAY_H} (5 ft squares) so a fight has room. Draw it bigger, or pass "
                                f"--small \"why\" for a place that truly is that small (a skiff, a cell)")
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
    from . import art,painted,portrait_profiles
    s = g.state
    if a.action=='faces':
        from . import art,painted,portrait_profiles
        if len(a.args)!=1:raise RuleError('asset faces <id> [--choose collection/number]')
        e=g.get(a.args[0]);identity=art.visual_identity(e)
        choices=[(pair,r) for pair,r in painted.portrait_records().items() if r['species']==identity['species'] and r['presentation']==identity['presentation']]
        if a.choose:
            try:
                col,num=a.choose.rsplit('/',1);pair=(col,int(num))
            except (ValueError,TypeError):raise RuleError('--choose must be collection/number, as listed by asset faces.')
            if pair not in dict(choices) or not painted.uri(*pair):raise RuleError('Chosen face must match the resolved species and presentation and exist locally.')
            profile=dict(e.get('portrait_profile') or portrait_profiles.capture(e));profile['choice']=pair;profile['mode']='painted'
            g.set(e,portrait_profile=profile)
            g.note(f'Face selected and retained for {e["name"]}: {col}/{pair[1]:02d}.')
        else:
            current=art.portrait_choice(e);L=art.look_of(e)
            choices.sort(key=lambda entry:(entry[1].get('age')!=L['age'],entry[1].get('outfit')!=L['outfit'],entry[0]))
            g.note(f'{e["name"]}: {identity["species"]} / {identity["presentation"]}; {len(choices)} compatible faces. Current: {current}.')
            for pair,r in choices:
                g.note(f'  {pair[0]}/{pair[1]:02d}: {r.get("age","adult")}, {r.get("skin")}, {r.get("hair_color")} hair, {r.get("outfit")}.')
        return
    if a.action=='stabilize':
        from . import portrait_profiles,art
        if a.all:targets=list(g.entities.values())
        elif a.args:targets=[g.get(ident) for ident in a.args]
        else:raise RuleError('asset stabilize <ids...> or --all; --refresh intentionally chooses again.')
        originals=portrait_profiles.original_descriptions(g.events)
        changed=0
        for e in targets:
            if e.get('portrait_profile') and not a.refresh:continue
            source=(e.get('portrait_profile') or {}).get('source_description') if a.refresh else originals.get(e['id'])
            g.set(e,portrait_profile=portrait_profiles.capture(e,source))
            changed+=1
        g.note(f'Stabilized {changed} portrait identities. Scene descriptions now leave these faces unchanged.')
        return
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
    if a.action == 'identity':
        # Inspection only: no events, guesses, automatic pins or changes to mechanics.
        current=s.get('view',{}).get('map')
        es=[g.get(ref) for ref in a.args] if a.args else [e for e in s['entities'].values() if a.all or e.get('kind')=='pc' or (e.get('token') or {}).get('map')==current]
        count=0
        for e in es:
            report=art.identity_report(e)
            if a.issues_only and not report['warnings']:continue
            g.note(report['summary'])
            for warning in report['warnings']:g.note('  ⚠ '+warning)
            count+=1
        g.note(f'Checked {len(es)} creature(s); displayed {count}. No identity changed.')
        return
    if a.action == "look":
        # What a creature looks like, feature by feature. The live table redraws its portrait and token from this.
        e = g.get(a.args[0])
        fields = {f: getattr(a, f"look_{f}") for f in art.LOOK_FIELDS if getattr(a, f"look_{f}", None)}
        if 'presentation' in fields:
            value=art.presentation_from(fields['presentation'])
            if not value:raise RuleError('Presentation: feminine/female, masculine/male, or androgynous/neutral/nonbinary.')
            fields['presentation']=value
        if 'species' in fields:fields['species']=art.canonical_species(fields['species'])
        if a.clear_like:
            g.set(e,art_of=None)
            g.note('Appearance source cleared; live art follows this creature again.')
        if getattr(a, "like", None):
            # keep another creature's face: an NPC who joins the party as a character, a double, a twin
            other = g.get(a.like)
            kept = other.get("art_of") or {"seed": other["id"], "name": other.get("name", ""),
                                             "style": art._style_for(other), "species": art.species_of(other),
                                             "presentation": art.visual_identity(other)['presentation'],"traits":art.look_of(other),
                                             "portrait_asset":art.portrait_choice(other),"recipient_look":dict(e.get('look') or {})}
            kept=dict(kept,recipient_look=dict(e.get('look') or {}))
            g.set(e, art_of=kept)
            desc = other.get("appearance") or (other.get("bio") or {}).get("appearance")
            if desc and not (e.get("appearance") or (e.get("bio") or {}).get("appearance")):
                g.set(e, appearance=desc)
            g.note(f"🎨 {e['name']} now looks like {other['name']} did.")
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
            g.note("🎨 Look updated. Visual pins do not change species traits or other mechanics.")
        g.note(art.describe_look(g.get(e["id"])))
        report=art.identity_report(g.get(e['id']))
        for warning in report['warnings']:g.note('  ⚠ '+warning)
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
    raise RuleError("asset icon|fetch|import|draw|portrait|look|identity|art|list")


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


def _name_words(s):
    """Name words for matching speech to a token. Punctuation is not part of the word, so a spoken 'Marta' finds
    'Marta, the smith', and a hyphenated id still matches the two-word name."""
    raw = re.sub(r"[\s\-_']+", " ", str(s).strip().lower())
    return [w for w in (re.sub(r"[^a-z0-9]", "", p) for p in raw.split()) if w]


def _anchor(g, ref):
    """The creature a line belongs to (id, full name or first name; the current map's creatures first), if the players
    can see it: its token gets the speech bubble or caption on the live table."""
    if not ref:
        return None
    ents = list(g.entities.values())
    here = (g.state.get("view") or {}).get("map")
    ents.sort(key=lambda e: 0 if (e.get("token") or {}).get("map") == here else 1)
    r = _name_words(ref)
    if not r:
        return None
    words = lambda e: _name_words(e.get("name", ""))  # noqa: E731
    e = (g.entities.get(ref) or next((e for e in ents if words(e) == r), None)
         or next((e for e in ents if words(e)[:1] == r[:1]), None))
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
    # the usual bookkeeping when time passes or the place changes, in the same command: lighting, weather, the map
    mid = a.map or g.state["view"].get("map")
    if getattr(a, "lighting", None):
        if not mid or mid not in g.state["maps"]:
            raise RuleError("scene --lighting needs a map (--map, or one already showing).")
        sub_run(g, ["map", "set", mid, "--kv", f"lighting={a.lighting}"])
    if getattr(a, "ambient", None):
        sub_run(g, ["fx", "ambient", a.ambient])
    if a.map:
        show_map(g, a.map)


def sub_run(g, argv):
    """Run another engine command inside this one (same rules, same Game, same save)."""
    sa = build_parser().parse_args(fix_negative_coins(argv))
    HANDLERS[sa.cmd](g, sa)


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
    if a.action == "file":
        # move entries between the journal's sections: `journal file j36,j40 --as clue`
        if not a.text or a.file_as not in ("clue", "place"):
            raise RuleError("journal file <ids,...> --as clue|place")
        known = {e["id"]: e for e in g.state.get("journal", [])}
        ids = [i.strip() for i in a.text.split(",") if i.strip()]
        missing = [i for i in ids if i not in known]
        if missing:
            raise RuleError(f"No journal entry {', '.join(missing)}.")
        g.emit("journal.set", ids=ids, set={"cat": a.file_as})
        where = "Handouts & clues" if a.file_as == "clue" else "Places & objects"
        g.say(f"📓 Filed under {where}: {', '.join(known[i]['title'] for i in ids)}", kind="handout")
        return
    if a.action == "edit":
        # correct a handout's wording in place: `journal edit j12 --text "..." [--title "..."]`.
        # The revision is announced in the feed, so the players see that the entry changed.
        new_text = a.new_text
        if not a.text or not (new_text or a.title):
            raise RuleError('journal edit <id> --text "new text" [--title "new title"]')
        entry = next((e for e in g.state.get("journal", []) if e["id"] == a.text), None)
        if not entry:
            raise RuleError(f"No journal entry {a.text}.")
        if entry.get("kind", "text") != "text" and new_text:
            raise RuleError(f"{a.text} is a {entry.get('kind')} handout; only text entries can be reworded.")
        changes = {}
        if new_text:
            changes.update(text=new_text, ref=new_text)
        if a.title:
            changes["title"] = a.title
        g.emit("journal.set", ids=[a.text], set=changes)
        g.say(f"📓 Journal entry revised: {a.title or entry['title']}", kind="handout")
        return
    if a.action != "add":
        raise RuleError('journal add "text" --title "..." | journal file <ids,...> --as clue|place | journal edit <id> --text "..."')
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
                 offhand=spec["offhand"], versatile=spec["versatile"], sneak=spec["sneak"], smite=spec["smite"], now=True, request=rid,
                 ammo_used=spec.get("ammo_used"))
    elif op == "spell_attack":
        M.spell_attack(g, e, g.get(spec["target"]), g.require("spells", spec["spell"], "Spell"),
                       spec["sc"], spec["expr"], spec["fx"], spec["adv"], spec["dis"], True,
                       slot=spec["slot"], request=rid)
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
        ev = st.load(full=True)   # an explicit verify re-checks every signature
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
    c.add_argument("--from", dest="from_slug", help="campaign new: the next chapter of a saga, continuing this earlier campaign")
    c.add_argument("--saga", help="campaign new --from: the saga's name (default: the earlier chapter's saga, or its title)")
    c = sp.add_parser("set", help="change a campaign setting: key=value")
    c.add_argument("kv")
    c = sp.add_parser("session", help="start|end")
    c.add_argument("action", choices=["start", "end"])

    c = sp.add_parser("char", help="roll-stats|create|import|levelup|catch-up|masteries|leave|rejoin|bio|show|inspire|use-inspiration|remove")
    c.add_argument("action")
    c.add_argument("args", nargs="*")
    c.add_argument("--from", dest="from_slug", help="char import: the earlier chapter to bring the character over from")
    for opt in ("name", "player", "species", "background", "method", "scores", "bonus", "skills", "languages", "equipment",
                "bg-equipment", "species-skill", "species-feat", "expertise", "fighting-style", "masteries", "mi-cantrips",
                "mi-spell", "mi-list", "size", "ancestry", "hp", "subclass", "asi", "feat", "instrument", "skilled", "bonus-skills", "scholar",
                "discoveries"):
        c.add_argument(f"--{opt}", dest=opt.replace("-", "_"))
    c.add_argument("--class", dest="cls")

    c = sp.add_parser("spells", help="set|scribe|list|refund|support")
    c.add_argument("action", choices=["set", "scribe", "list", "refund", "support"])
    c.add_argument("--level", type=int, help="refund: the slot level to give back")
    c.add_argument("who", nargs="?")
    c.add_argument("--class", dest="cls")
    c.add_argument("--cantrips")
    c.add_argument("--prepared", default="")
    c.add_argument("--spellbook")
    c.add_argument("--spell")
    c.add_argument("--source")

    c = sp.add_parser("journal", help="add \"text\" --title — a note in the players' journal (handouts are added automatically); "
                                      "file <ids> --as clue|place — move entries between Handouts & clues and Places & objects; "
                                      "edit <id> --text \"...\" [--title] — correct an entry's wording (announced)")
    c.add_argument("action")
    c.add_argument("text", nargs="?")
    c.add_argument("--title")
    c.add_argument("--as", dest="file_as", choices=("clue", "place"))
    c.add_argument("--text", dest="new_text", help="journal edit: the corrected text")

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
    c.add_argument("--desc", help="npc add: what anyone can see (same as a following `npc describe`)")
    c.add_argument("--align", help="npc add: the creature's alignment (same as a following `npc alignment`)")

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
    c.add_argument("--init", type=int, help="repair: rejoin at an initiative already rolled (needs --reason)")
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
    c.add_argument("--ammo", help="inventory id of the ammunition to fire (e.g. arrows-1-1 for Arrows +1); default: plain ammunition first")
    c.add_argument("--times", type=int, default=1)
    c.add_argument("--now", action="store_true", help="roll now even in viewer-roll mode")

    c = sp.add_parser("cast", help="cast a spell: slots, components, concentration, effects")
    c.add_argument("caster")
    c.add_argument("spell")
    c.add_argument("--level", type=int)
    c.add_argument("--targets")
    c.add_argument("--readied", action="store_true", help="release a spell readied with the Ready action (uses the Reaction)")
    c.add_argument("--ritual", action="store_true")
    c.add_argument("--free", help="free casting source, e.g. 'Magic Initiate'")
    c.add_argument("--scroll", help="inventory id of a spell scroll")
    c.add_argument("--item", help="inventory id of a charged item that casts the spell (e.g. a Wand of Magic Missiles); --level sets charges")
    c.add_argument("--condition", help="condition applied on a failed save (e.g. paralyzed)")
    c.add_argument("--component", help="inventory id of the costly component")
    c.add_argument("--choice", help="spell option: skill, ability, damage type, condition, or Mass Heal allocations")
    c.add_argument("--adv")
    c.add_argument("--dis")
    c.add_argument("--now", action="store_true")
    c.add_argument("--wall", help='Wall of Fire as a line: "x,y x,y" (its two ends, up to 60 ft); targets are found on its squares')
    c.add_argument("--ring", help="Wall of Fire as a ring: its centre x,y (20 ft across)")
    c.add_argument("--hot", help="the burning side: north|south|east|west|northeast|... or inside|outside for a ring")

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
    c.add_argument("--attacker", help="the creature whose hand-rolled attack hit (lets Uncanny Dodge answer it)")
    c = sp.add_parser("heal", help="generic healing (party needs --override)")
    c.add_argument("who")
    c.add_argument("amount")
    c.add_argument("--source")
    c.add_argument("--override")
    c.add_argument("--undo-death", action="store_true", help="repair: undo a death caused by a voided DM error (needs --override)")
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
    c.add_argument("--refund", help='repair: give back one use spent by mistake (the reason, shown publicly)')
    c = sp.add_parser("bardic", help="spend a Bardic Inspiration die")
    c.add_argument("who")
    c = sp.add_parser("deathsave")
    c.add_argument("who")
    c.add_argument("--now", action="store_true")
    c.add_argument("--void-fails", type=int, help="repair: strike failures from a voided roll (needs --reason)")
    c.add_argument("--reason")
    c = sp.add_parser("stabilize")
    c.add_argument("helper")
    c.add_argument("who")
    c = sp.add_parser("legendary-resist")
    c.add_argument("who")
    c = sp.add_parser("rest", help="short|long")
    c.add_argument("kind", choices=["short", "long"])
    c.add_argument("--who")
    c.add_argument("--hd", help="hit dice to spend: kira:2,bob:1")
    c.add_argument("--focus", help="short or long rest: identify a magic item by focusing on it, kira:item-id (one per creature)")
    c.add_argument("--attune", help="short or long rest: attune to a magic item through the rest, kira:item-id (one per creature)")
    c.add_argument("--refund-hd", help="repair: refund Hit Point Dice spent by mistake, kira:1 (needs --reason; takes no rest)")
    c.add_argument("--ended-at", help='repair: a Long Rest already taken inside time that has passed, ending "Day N, HH:MM" '
                                      '(needs --reason; no time passes)')
    c.add_argument("--reason")
    c = sp.add_parser("forces", help="list|add|set|equip|share|split|muster: the units you command (numbers, kit, pay, attitude)")
    c.add_argument("action", choices=["list", "add", "set", "equip", "share", "split", "muster", "enlist"])
    c.add_argument("--ids", help="enlist: creatures already on the map who join the unit")
    c.add_argument("target", nargs="?", help="the unit id")
    c.add_argument("--name")
    c.add_argument("--stat", help="SRD stat block of one man (bandit, guard, commoner, warrior-infantry...)")
    c.add_argument("--count", type=int)
    c.add_argument("--where")
    c.add_argument("--captain")
    c.add_argument("--pay", help='e.g. "2sp/day"')
    c.add_argument("--attitude", choices=["hostile", "indifferent", "friendly", "helpful"])
    c.add_argument("--from", dest="source", help="equip: the container the kit comes out of · share: who or which container pays")
    c.add_argument("--armor")
    c.add_argument("--shield", action="store_true")
    c.add_argument("--weapon")
    c.add_argument("--coins")
    c.add_argument("--into")
    c.add_argument("--at")
    c.add_argument("--map")
    c.add_argument("--reason")
    c = sp.add_parser("loot", help="list|suggest|body|none|cache|open: treasure decided before anyone searches")
    c.add_argument("action", choices=["list", "suggest", "body", "none", "cache", "open"])
    c.add_argument("target", nargs="?", help="body/none: the foe · cache: the map · open: who opens it")
    c.add_argument("pos", nargs="?", help="cache: x,y · open: the container id")
    c.add_argument("--items", help='"Longsword +1; 2x Potion of Healing; Ledger=a merchant ledger"')
    c.add_argument("--coins", help="30gp 5sp")
    c.add_argument("--name")
    c.add_argument("--text")
    c.add_argument("--id")
    c.add_argument("--at", help="body: map:x,y where the gear lies (default: the body's tile)")
    c.add_argument("--lock", type=int, help="cache: lock DC")
    c.add_argument("--unlocked", help="open: how the lock was beaten (a check passed, the key)")
    c.add_argument("--rarity", choices=["Common", "Uncommon", "Rare", "Very Rare", "Legendary"])
    c.add_argument("--kind", help="suggest: weapon, armor, wondrous, ring, potion...")
    c.add_argument("--reason")
    c.add_argument("--override")
    c = sp.add_parser("agenda", help="add|list|done|cancel scheduled events (deliveries, debts, visits)")
    c.add_argument("action", choices=["add", "list", "done", "cancel"])
    c.add_argument("target", nargs="?")
    c.add_argument("--at", help='"Day 7 08:00"')
    c.add_argument("--in", dest="inn", help="from now: 2d, 6h")
    c.add_argument("--text")
    c.add_argument("--pay", help="coins (650gp, -430gp) or crowns as dice (600+2d40)")
    c.add_argument("--to", help="who or which container is paid (treasury)")
    c.add_argument("--auto", action="store_true", help="make the payment automatically when it falls due")
    c.add_argument("--secret", action="store_true", help="DM only: not announced on the table")
    c.add_argument("--note")
    c.add_argument("--reason")
    c = sp.add_parser("time", help="advance in-world time")
    c.add_argument("amount", nargs="?")
    c.add_argument("--reason")
    c.add_argument("--rewind-to", help='repair: put the clock back to "Day N, HH:MM" after a voided DM error (public)')
    c.add_argument("--override", help="the DM error being corrected (required with --rewind-to)")
    c = sp.add_parser("travel")
    c.add_argument("miles", nargs="?", type=float)
    c.add_argument("--pace", default="normal", choices=["fast", "normal", "slow"])
    c.add_argument("--to")
    c.add_argument("--map")
    c.add_argument("--push", action="store_true", help="march past 8 hours in a day (Con saves or Exhaustion)")

    c = sp.add_parser("item", help="add|remove|drop|stash|pickup|sell|give|equip|unequip|attune|unattune|use|venom-hit|recover-thrown|light|note|unpack|identify|obscure|refresh|recover-ammo|card")
    c.add_argument("--with-attack", action="store_true", help="pickup: pick up a weapon as part of an attack (one per attack)")
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
    c.add_argument("--level", type=int, help="item use: the expended spell slot level a Pearl of Power restores (default: highest, 3 max)")
    c = sp.add_parser("coins")
    c.add_argument("who")
    c.add_argument("amount")
    c.add_argument("--source")
    c.add_argument("--override")
    c.add_argument("--from", dest="from_who", help="hand coins over from another character (no loot cap: nothing new enters the game)")
    c = sp.add_parser("xp", help="award|milestone|sync <id>")
    c.add_argument("action", choices=["award", "milestone", "sync"])
    c.add_argument("who", nargs="?", help="sync: the character to bring up to the party's XP")
    c.add_argument("--encounter", action="store_true")
    c.add_argument("--overcome", help="ids of foes overcome without being killed (captured, routed): their stat-block XP, uncapped")
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

    c = sp.add_parser("map", help="gen|list|show|reveal|hide|door|feature|crop|paint|set|party|label|unlabel|poi|poi-move|poi-remove|container|container-remove|from-image|render|ascii|settlement|site|route|discover|region-remove")
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
    c.add_argument("--kv", action="append", help="map set: key=value; repeat --kv for several settings")
    c.add_argument("--ftype")
    c.add_argument("--hidden", action="store_true")
    c.add_argument("--dm", action="store_true")
    c.add_argument("--out")
    c.add_argument("--text", help="map poi: what the characters perceive (becomes the journal entry)")
    c.add_argument("--clue", action="store_true", help="map poi: a story clue, filed under Handouts & clues (default: Places & objects)")
    c.add_argument("--reason", help="map poi-move/poi-remove: what changed")
    c.add_argument("--icon", help="map prop: a game-icons name (find one with `map icons <words>`)")
    c.add_argument("--blocks", action="store_true", help="map prop: the piece fills its square (impassable, half cover)")
    c.add_argument("--size", choices=("small", "medium", "large"), help="map prop: how much of the tile it fills")
    c.add_argument("--color", help="map prop: silhouette colour, #rrggbb")
    c.add_argument("--rotate", type=int, help="map prop: degrees")
    c.add_argument("--type", dest="stype", help="map settlement/site: hamlet|village|town|city|capital|castle|abbey, or ruins|lair|grove|...")
    c.add_argument("--path", dest="route_path", help='map route <region> road|river --path "x,y x,y ..." (waypoints)')
    c.add_argument("--small", help="map import-grid: why this place is genuinely smaller than a playable map (a skiff, a cell)")
    c.add_argument("--caster", help="map spell-wall: who is concentrating on the wall spell")
    c.add_argument("--spell", help="map spell-wall: the spell (wall of fire)")
    c.add_argument("--line", help='map spell-wall: the two ends "x,y x,y"')
    c.add_argument("--ring", help="map spell-wall: a ring's centre x,y")
    c.add_argument("--hot", help="map spell-wall: the burning side (north|south|... or inside|outside)")

    c = sp.add_parser("asset", help="icon|fetch|import|draw|portrait|look|identity|stabilize|faces|art|list")
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
    c.add_argument('--all',action='store_true',help='identity: audit every creature; default is party and current map')
    c.add_argument('--issues-only',action='store_true',help='identity: show only missing/conflicting identity or pinned art')
    c.add_argument('--clear-like',action='store_true',help='look: stop preserving another creature\'s appearance')
    c.add_argument('--refresh',action='store_true',help='stabilize: intentionally select a face again from saved appearance and current pins')
    c.add_argument('--choose',help='faces: retain an exact compatible collection/number from the face catalogue')
    for f in ("hair", "beard", "eyes", "skin", "marks", "headwear", "outfit", "cloak", "build", "age", "expression", "horns",
              "accent", "background", "presentation", "species"):
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
    c.add_argument("--lighting", choices=["bright", "dim", "dark"], help="also set the map's lighting")
    c.add_argument("--ambient", help="also set the table's weather (fx ambient: none|rain|snow|fog|embers|ash|motes|storm)")
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
    c = sp.add_parser("batch", help="run many commands in one go: one load, one save, one table update")
    c.add_argument("file", nargs="?", default="-", help="a file of commands, one per line (default: read stdin)")
    c.add_argument("--atomic", action="store_true", help="all or nothing: if any step is refused, keep none of them")
    c.add_argument("--dry-run", action="store_true",
                   help="check every step against the rules and save nothing (stops at the first step that rolls dice)")
    c.add_argument("-q", "--quiet", action="store_true", help="don't echo each step, only its output")
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
    "coins": cmd_coins, "agenda": cmd_agenda, "loot": cmd_loot, "forces": cmd_forces, "xp": cmd_xp, "encounter": cmd_encounter, "map": cmd_map, "asset": cmd_asset, "say": cmd_say, "fx": cmd_fx,
    "scene": cmd_scene, "show": cmd_show, "homebrew": cmd_homebrew, "request": cmd_request, "roll": cmd_roll,
    "status": cmd_status, "audit": cmd_audit, "log": cmd_log,
}
READ_ONLY = {"status", "audit", "log"}
# commands that manage the campaign itself rather than play it: run them on their own, never inside a batch
NOT_IN_BATCH = {"campaign", "verify", "quicksave", "quickload", "repair", "rekey", "serve", "batch", "help", "rules"}
ENGINE_PREFIX = re.compile(r"^\s*(?:py|python3?|python)\s+-m\s+engine\s+")


def fix_negative_coins(argv):
    # `coins kira -5sp`: a negative amount looks like an option to argparse; pass it as a value instead
    return [f"={x}" if i and argv[0] == "coins" and re.match(r"^-\d", x) else x for i, x in enumerate(argv)]


def batch_steps(text):
    """One command per line. Blank lines and lines starting with # are skipped; a line ending in a backslash
    continues on the next. A leading `py -m engine` / `python -m engine` is optional."""
    steps, buf, first = [], "", 0
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not buf:
            first = n
            if not line.strip() or line.lstrip().startswith("#"):
                continue
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        buf += line
        steps.append((first, ENGINE_PREFIX.sub("", buf).strip()))
        buf = ""
    if buf.strip():
        steps.append((first, ENGINE_PREFIX.sub("", buf).strip()))
    return steps


def rollback_to(g, mark):
    """Drop a refused step's pending events and rebuild the state from the log plus the steps that stood."""
    from .core import apply
    g.pending = g.pending[:mark]
    g.state = replay(g.events)
    for ev in g.pending:
        apply(g.state, {**ev, "seq": g.state["seq"] + 1})


def cmd_batch(a, parser):
    """Run many engine commands as one: the log is loaded and verified once, each step is checked by the same
    rules as on its own, the events are signed and saved together, and the live table updates once.

    A refused step stops the batch there: the steps before it stand (or none, with --atomic) and the rest are
    listed, not run. Nothing is ever chained past a refusal."""
    import contextlib
    import io
    if a.file == "-":
        if hasattr(sys.stdin, "reconfigure"):
            try:
                sys.stdin.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
        text = sys.stdin.read()
    else:
        text = Path(a.file).read_text(encoding="utf-8-sig")  # files saved by Windows tools often start with a BOM
    steps = batch_steps(text.lstrip("﻿"))
    if not steps:
        raise RuleError("the batch is empty: give one engine command per line")
    parsed = []
    for line_no, cmd in steps:
        try:
            argv = fix_negative_coins(shlex.split(cmd))
        except ValueError as err:
            raise RuleError(f"line {line_no}: can't read `{cmd}` ({err}); nothing was run")
        err_buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(err_buf):
                sa = parser.parse_args(argv)
        except SystemExit:
            msg = (err_buf.getvalue().strip().splitlines() or ["not a valid engine command"])[-1]
            raise RuleError(f"line {line_no}: `{cmd}` → {msg}; nothing was run")
        if not sa.cmd or sa.cmd in NOT_IN_BATCH or sa.cmd not in HANDLERS or (sa.cmd == "spells" and sa.action == "support"):
            raise RuleError(f"line {line_no}: `{sa.cmd or cmd}` can't run inside a batch (run it on its own); nothing was run")
        parsed.append((line_no, cmd, argv, sa))

    g = Game()
    if a.dry_run:
        def no_dice(*args, **kw):
            raise RuleError("dry run stops before any dice are rolled (a roll is final, so it can't be previewed)")
        g.roll = no_dice
    done, failed = 0, None
    for i, (line_no, cmd, argv, sa) in enumerate(parsed, 1):
        mark, out_mark = len(g.pending), len(g.out)
        g.cmdline = " ".join(shlex.quote(x) for x in argv)
        if not a.quiet:
            print(f"▸ {i}. {cmd}")
        try:
            HANDLERS[sa.cmd](g, sa)
        except (RuleError, KeyError, IndexError) as err:
            for line in g.out[out_mark:]:
                print("  " + line)
            rollback_to(g, mark)
            g.out = g.out[:out_mark]
            kind = "✖ RULE" if isinstance(err, RuleError) else f"✖ ERROR: {type(err).__name__}"
            print(f"{kind}: {err}")
            failed = (i, line_no, cmd)
            break
        for line in g.out[out_mark:]:
            print(line)
        done += 1
    rest = parsed[failed[0]:] if failed else []
    if a.dry_run:
        print(f"── dry run: {done} of {len(parsed)} step(s) pass the rules; nothing was saved.")
    elif failed and a.atomic:
        print(f"── --atomic: step {failed[0]} was refused, so none of the {len(parsed)} steps were saved.")
    else:
        written = g.commit()
        if written:
            views.write_snapshots(g)
        print(f"── batch: {done} of {len(parsed)} step(s) done, {len(written)} event(s) saved in one go.")
    if failed:
        print(f"   Stopped at step {failed[0]} (line {failed[1]}): {failed[2]}")
        for j, (line_no, cmd, _, _) in enumerate(rest, failed[0] + 1):
            print(f"   not run {j}: {cmd}")
        return 2
    return 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):  # (not when a test runs the CLI in-process with captured output)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:] if argv is None else argv
    argv = fix_negative_coins(argv)
    p = build_parser()
    a = p.parse_args(argv)
    if not a.cmd or a.cmd == "help":
        p.print_help()
        return 0
    try:
        if a.cmd == "spells" and a.action == "support":
            from .spells import PROFILES, support
            rows = [srd.find("spells", a.who)] if a.who else sorted(srd.data()["spells"].values(), key=lambda s: (s["level"], s["name"]))
            if not rows or rows[0] is None:
                raise RuleError(f"Unknown spell: {a.who}")
            if not a.who:
                print(f"{len(PROFILES)} explicit spell profiles; other spells use parsed resolution or DM narration.")
            for spell in rows:
                entry = support(spell)
                print(f"{spell['name']} (level {spell['level']}) [{entry['status']}] — {entry['mechanics']}")
                if entry["choice"]:
                    print(f"  --choice: {entry['choice']}")
                if entry["remaining"]:
                    print(f"  DM: {entry['remaining']}")
            return 0
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
        if a.cmd == "batch":
            return cmd_batch(a, p)
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
