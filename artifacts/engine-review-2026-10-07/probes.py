"""Review diagnostics, not regression tests: assertions confirm CURRENT faulty behavior.

Run from the repository root: python artifacts/engine-review-2026-10-07/probes.py
All campaigns are disposable temporary fixtures. Production campaigns are never loaded.
No engine source, signing keys, or event files are edited by this script.
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import builtins

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))
import _cli
from engine import core, maps, srd, views

results = []
commands = []


def run(env, *args, code=0):
    actual, output = _cli.run(env, *args)
    commands.append({"argv": list(args), "exit_code": actual, "output": output})
    assert actual == code, (args, actual, output)
    return output


def fixture(base, name):
    (base / name).mkdir()
    env = {**os.environ, "DND_CAMPAIGNS": str(base / name / "campaigns"),
           "DND_ENGINE_HOME": str(base / name / "home"), "PYTHONIOENCODING": "utf-8"}
    run(env, "campaign", "new", "Review Fixture")
    return env


def wizard(env):
    run(env, "char", "create", "--name", "Mira Vale", "--class", "Wizard", "--species", "Elf",
        "--background", "Sage", "--method", "pointbuy",
        "--scores", "str=8,dex=14,con=14,int=15,wis=12,cha=8", "--bonus", "int+2,con+1",
        "--skills", "investigation,medicine", "--languages", "Elvish,Draconic",
        "--species-skill", "perception", "--mi-cantrips", "light,mage hand", "--mi-spell", "shield")
    run(env, "spells", "set", "mira", "--cantrips", "fire bolt,ray of frost,minor illusion",
        "--prepared", "magic missile,identify,mage armor,detect magic",
        "--spellbook", "magic missile,identify,mage armor,detect magic,shield,sleep")


def bard(env):
    run(env, "char", "create", "--name", "Lia Song", "--class", "Bard", "--species", "Human",
        "--background", "Acolyte", "--method", "standard",
        "--scores", "str=8,dex=14,con=13,int=10,wis=12,cha=15", "--bonus", "cha+2,wis+1",
        "--skills", "deception,persuasion,performance", "--species-skill", "stealth",
        "--species-feat", "Alert", "--mi-cantrips", "guidance,thaumaturgy", "--mi-spell", "bless",
        "--languages", "Elvish,Dwarvish", "--instrument", "viol")
    run(env, "spells", "set", "lia", "--cantrips", "light,mage hand",
        "--prepared", "cure wounds,healing word,identify,detect magic")


def report(id_, evidence):
    results.append({"id": id_, "status": "reproduced", "evidence": evidence})
    print(f"{id_}: {evidence}")


def main():
    with tempfile.TemporaryDirectory(prefix="dnd-engine-review-") as tmp:
        base = Path(tmp)
        # Common spell silently succeeds but supplies no mechanical bonus.
        env = fixture(base, "bless")
        bard(env)
        g = _cli.game(env)
        symbol = next(i for i in g.get("lia")["inventory"] if "symbol" in i["name"].lower())
        output = run(env, "cast", "lia", "bless", "--targets", "lia", "--component", symbol["id"])
        g = _cli.game(env)
        assert g.get("lia").get("concentration", {}).get("spell") == "bless"
        assert not g.get("lia")["effects"] and not g.get("lia")["conditions"]
        assert "effect is narrative" in output
        run(env, "save", "lia", "wis", "--dc", "10", "--source", "review fixture")
        assert all("d4" not in r["expr"] for r in _cli.game(env).state["rolls"])
        report("F01", "Bless consumes a slot and starts concentration, but the target has no effect and its save has no bonus die.")

        # An explicit component is accepted without identity/value checks; time ignores normal casting time.
        env = fixture(base, "components")
        wizard(env)
        run(env, "item", "add", "mira", "Dagger", "--purchase")
        dagger = next(i for i in _cli.game(env).get("mira")["inventory"] if i["name"] == "Dagger")
        before = _cli.game(env).state["time"]
        run(env, "cast", "mira", "identify", "--ritual", "--component", dagger["id"])
        after = _cli.game(env).state["time"]
        assert after - before == 10
        report("F02", "Identify accepts a Dagger as its explicitly supplied costly component.")
        report("F03", "Identify ritual advances time by 10 minutes; its normal one-minute casting time is omitted.")

        env = fixture(base, "expiry")
        wizard(env)
        run(env, "cast", "mira", "mage armor", "--targets", "mira")
        run(env, "time", "9h", "--reason", "review fixture")
        assert any(f["name"] == "mage armor" for f in _cli.game(env).get("mira")["effects"])
        report("F04", "Mage Armor remains attached and applied after nine hours pass.")

        env = fixture(base, "healing")
        bard(env)
        run(env, "npc", "add", "skeleton", "--name", "Fixture Skeleton", "--side", "ally")
        run(env, "damage", "fixture", "1", "force", "--source", "review fixture")
        hp_before = _cli.game(env).get("fixture")["hp"]
        output = run(env, "cast", "lia", "cure wounds", "--targets", "fixture")
        assert "has no effect" in output and _cli.game(env).get("fixture")["hp"] == hp_before
        report("F05", "Cure Wounds is accepted and consumes its slot but refuses healing solely because the target is Undead.")

        env = fixture(base, "fog")
        run(env, "map", "gen", "arena", "--preset", "crypt", "--seed", "3", "--id", "arena", "--show")
        run(env, "map", "set", "arena", "--kv", "fog=true")
        run(env, "map", "hide", "arena", "--all")
        g = _cli.game(env)
        m = g.state["maps"]["arena"]
        x, y = next((x, y) for y in range(m["h"]) for x in range(m["w"]) if maps.move_cost(m, x, y) is not None)
        run(env, "npc", "add", "goblin-warrior", "--name", "Fixture Goblin", "--at", f"{x},{y}", "--map", "arena")
        g = _cli.game(env)
        assert not views._seen(g, g.get("fixture"))
        public = views.player_view(g)
        assert any(e["id"] == g.get("fixture")["id"] and e["token"]["x"] == x for e in public["others"])
        report("F06", "Player JSON includes the exact token coordinates of an enemy for which the engine visibility predicate returns false.")

        env = fixture(base, "viewer")
        wizard(env)
        run(env, "npc", "add", "goblin-warrior", "--name", "Fixture Goblin")
        run(env, "combat", "start", "mira,fixture")
        if _cli.game(env).state["combat"]["order"][0]["id"] != "mira":
            run(env, "combat", "next")
        run(env, "set", "player_rolls=viewer")
        before = _cli.game(env).state["roll_count"]
        run(env, "cast", "mira", "ray of frost", "--targets", "fixture")
        g = _cli.game(env)
        assert g.state["roll_count"] > before and not g.state["requests"]
        report("F07", "A PC spell attack rolls immediately in viewer mode without creating a Roll request.")

        env = fixture(base, "save")
        camp = Path(_cli.game(env).dir)
        (camp / "player-notes.md").write_text("before", encoding="utf-8")
        (camp / "player-pins.json").write_text('["before"]', encoding="utf-8")
        run(env, "quicksave", "review-save")
        (camp / "player-notes.md").write_text("after", encoding="utf-8")
        (camp / "player-pins.json").write_text('["after"]', encoding="utf-8")
        run(env, "quickload", "review-save")
        assert (camp / "player-notes.md").read_text() == "after"
        assert (camp / "player-pins.json").read_text() == '["after"]'
        report("F08", "Quickload leaves player notes and pins from after the save point.")
        run(env, "rekey")
        run(env, "quickload", "review-save", code=2)
        report("F09", "A previously valid quicksave becomes unloadable after the supported rekey command.")

        env = fixture(base, "branch")
        run(env, "quicksave", "origin")
        run(env, "say", "Fixture branch A")
        stale = _cli.game(env)
        old_head = stale.events[-1]["hash"]
        run(env, "quickload", "origin")
        run(env, "say", "Fixture branch B")
        fresh = _cli.game(env)
        assert len(fresh.events) == len(stale.events) and fresh.events[-1]["hash"] != old_head
        stale.say("Command based on the discarded fixture branch")
        assert stale.commit()
        report("F10", "A stale Game commits after quickload and divergent replay because the guard compares event count, not chain head.")

        # Inject an I/O interruption into the engine's own append operation. No manual log edits.
        env = fixture(base, "interruption")
        pending = _cli.game(env)
        before_count = len(pending.events)
        pending.say("First beat of one fixture command")
        pending.say("Second beat of the same fixture command")
        real_open = builtins.open

        class InterruptedAppend:
            def __init__(self, fh):
                self.fh, self.writes = fh, 0

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return self.fh.__exit__(*args)

            def __getattr__(self, name):
                return getattr(self.fh, name)

            def write(self, data):
                self.writes += 1
                if self.writes == 2:
                    raise OSError("fixture: interrupted command append")
                return self.fh.write(data)

        def interrupted_open(file, mode="r", *args, **kwargs):
            fh = real_open(file, mode, *args, **kwargs)
            if Path(file) == pending.store.events_path and mode == "a":
                return InterruptedAppend(fh)
            return fh

        with patch("builtins.open", side_effect=interrupted_open):
            try:
                pending.commit()
            except OSError as error:
                assert "fixture:" in str(error)
            else:
                raise AssertionError("append interruption was not exercised")
        assert len(_cli.game(env).events) == before_count + 1
        report("F11", "An interrupted two-event commit leaves its first event on disk; ordinary verified replay accepts that partial command.")
    output = Path(__file__).with_name("probe-results.json")
    output.write_text(json.dumps({"findings": results, "commands": commands}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Confirmed {len(results)} findings. Evidence: {output}")


if __name__ == "__main__":
    main()
