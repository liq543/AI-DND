"""Quicksave / quickload: named restore points for the whole game, like a video game's save slots.

A quicksave stores the signed event log up to a point (a prefix of a valid hash chain is itself a valid chain),
together with the DM's narrative notes and the table views. A quickload puts all of it back exactly: the log is
truncated to the save point, the notes and views are restored, and the rotating backups are reset so nothing from
the discarded timeline can come back through `repair`. The game is then exactly as it was when the save was made.

Saves live in campaigns/<name>/quicksaves/<slot>/ and survive a quickload (you can load the same slot again and again).
"""
import datetime
import json
import os
import re
import shutil
from pathlib import Path

from .store import Store

NOTE_FILES = ("campaign.md", "npcs.md", "locations.md", "quests.md", "secrets.md")
NOTE_DIRS = ("log", "views")


class QuicksaveError(Exception):
    pass


def _slot(name):
    slot = re.sub(r"[^a-z0-9-]+", "-", (name or "").lower()).strip("-")
    return slot or datetime.datetime.now().strftime("quick-%Y%m%d-%H%M%S")


def saves_dir(campaign_dir):
    return Path(campaign_dir) / "quicksaves"


def list_saves(campaign_dir):
    out = []
    for p in sorted(saves_dir(campaign_dir).glob("*/meta.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return sorted(out, key=lambda m: m.get("created", ""))


def save(campaign_dir, name=None, at_seq=None, label=""):
    """Store the log (up to at_seq, default: all of it) plus notes and views under a named slot."""
    campaign_dir = Path(campaign_dir)
    store = Store(campaign_dir)
    with store.lock():
        events = store.load()
        n = len(events) if at_seq is None else int(at_seq)
        if not 0 < n <= len(events):
            raise QuicksaveError(f"--at-seq must be between 1 and {len(events)}")
        slot = _slot(name)
        dst = saves_dir(campaign_dir) / slot
        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True)
        with open(store.events_path, encoding="utf-8") as fh:
            lines = [l for l in fh if l.strip()][:n]
        (dst / "events.jsonl").write_text("".join(lines), encoding="utf-8", newline="\n")
        for f in NOTE_FILES:
            if (campaign_dir / f).exists():
                shutil.copy2(campaign_dir / f, dst / f)
        for d in NOTE_DIRS:
            if (campaign_dir / d).is_dir():
                shutil.copytree(campaign_dir / d, dst / d)
        meta = {"slot": slot, "seq": n, "label": label or "", "created": datetime.datetime.now().isoformat(timespec="seconds"),
                "event_ts": events[n - 1].get("ts")}
        (dst / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        return meta


def load(campaign_dir, name=None):
    """Restore a slot (default: the most recent one) exactly: log, notes, views, and fresh backups."""
    campaign_dir = Path(campaign_dir)
    saves = list_saves(campaign_dir)
    if not saves:
        raise QuicksaveError("No quicksaves yet. Make one with `quicksave [name]`.")
    meta = next((m for m in saves if m["slot"] == _slot(name)), None) if name else saves[-1]
    if not meta:
        raise QuicksaveError(f"No quicksave '{name}'. Saves: " + ", ".join(m["slot"] for m in saves))
    src = saves_dir(campaign_dir) / meta["slot"]
    store = Store(campaign_dir)
    probe = Store(campaign_dir)
    probe.events_path = src / "events.jsonl"
    if probe.valid_prefix() != meta["seq"]:
        raise QuicksaveError(f"Quicksave '{meta['slot']}' doesn't verify under this campaign's key; it can't be loaded.")
    with store.lock():
        tmp = store.events_path.with_suffix(".jsonl.tmp")
        shutil.copyfile(src / "events.jsonl", tmp)
        os.replace(tmp, store.events_path)
        bdir = store.engine_dir / "backups"
        if bdir.is_dir():  # the discarded future must not come back through `repair --restore`
            for p in bdir.glob("*.jsonl"):
                p.unlink()
        bdir.mkdir(exist_ok=True)
        shutil.copyfile(store.events_path, bdir / "latest.jsonl")
        for f in NOTE_FILES:
            target = campaign_dir / f
            if (src / f).exists():
                shutil.copy2(src / f, target)
            elif target.exists():
                target.unlink()
        for d in NOTE_DIRS:
            target = campaign_dir / d
            if target.is_dir():
                shutil.rmtree(target)
            if (src / d).is_dir():
                shutil.copytree(src / d, target)
    return meta


def delete(campaign_dir, name):
    dst = saves_dir(campaign_dir) / _slot(name)
    if not dst.is_dir():
        raise QuicksaveError(f"No quicksave '{name}'.")
    shutil.rmtree(dst)
