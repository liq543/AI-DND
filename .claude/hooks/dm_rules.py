"""Claude Code hook: keeps the DM rules in the model's context without flooding it.

  UserPromptSubmit  before every reply: dm/turn-rules.md (the core digest, ~5 KB)
  SessionStart      startup, resume, clear and after every compaction: dm/standing-orders.md (the player's lessons)
  PreToolUse        only for engine commands that build or change an area (map gen/import-grid/show, scene) or add
                    a creature (npc add): the matching checklist, a few lines. Silent for everything else.
  Stop              only on turns that ran engine play commands: a short checklist, once per turn.

Why not everything everywhere: each injection is re-sent with every later message, and a payload over ~10 KB is cut to
a preview (so the rules stop reaching the model at all). The old setup (full digest on every tool call and stop) is
tagged `hooks-v1-per-tool-call`; see .claude/hooks/REVERT.md.

Reads the hook payload as JSON on stdin; prints nothing it can't read (never breaks a session).
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
DIGEST = ROOT / "dm" / "turn-rules.md"
ORDERS = ROOT / "dm" / "standing-orders.md"   # the player's standing orders: in the repo, so they travel to every machine

ENGINE_CMD = re.compile(r"-m\s+engine\s+([a-z-]+)(?:\s+([a-z-]+))?")
READ_ONLY = {"status", "verify", "log", "rules", "help", "audit", "serve", "request"}
AREA = re.compile(r"-m\s+engine\s+(map\s+(gen|import-grid|show)\b|scene\b)")
NEW_NPC = re.compile(r"-m\s+engine\s+(npc\s+add|encounter\s+spawn)\b")

STOP_CHECK = (
    "Rules check before ending this turn (dm/turn-rules.md). Did this turn: (1) log every spoken line (`say --as`) and "
    "event (`say`, `say --at <id>`); (2) advance companions and NPCs present, moving their tokens; (3) keep hidden rolls, "
    "offscreen events and unperceived NPCs out of chat, with no hints after failed checks; (4) update `scene`, lighting and "
    "`fx ambient` if time passed or the place changed; (5) give any new or changed area the full checklist (map shown, "
    "pois, creatures described and aligned, locations.md); (6) award XP for any resolved challenge; (7) update the "
    "campaign notes and session log; (8) stop at the player's decision, with no montage? Fix any miss now with engine "
    "commands and say so in one line. If all is satisfied, reply with exactly: \"✔ Rules check passed.\""
)
NPC_CHECK = ("New creature: place it, `npc describe` what anyone can see, give a named NPC an `npc alignment`, and add "
             "a named NPC to npcs.md. Hidden ones stay unnamed in chat until perceived.")


def area_checklist(rules):
    """Rule 8 of the digest (the new-or-changed area checklist), cut out of turn-rules.md so the two never drift."""
    m = re.search(r"^8\. .*?(?=^9\. )", rules, re.S | re.M)
    return m.group(0).strip() if m else "Area checklist: dm/turn-rules.md rule 8."


def engine_commands(text):
    return [m.group(1) for m in ENGINE_CMD.finditer(text or "")]


def turn_played(payload):
    """Did this turn run an engine command that changes the game? Reads the transcript back to the last user prompt.
    If the transcript can't be read, assume yes (the check is cheap; skipping a real play turn is not)."""
    path = payload.get("transcript_path")
    if not path:
        return True
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return True
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        msg = rec.get("message") or {}
        content = msg.get("content")
        if rec.get("type") == "user":
            if isinstance(content, str) or (isinstance(content, list) and not any(
                    isinstance(c, dict) and c.get("type") == "tool_result" for c in content)):
                return False   # reached the player's prompt: nothing in this turn changed the game
            continue
        if rec.get("type") == "assistant" and isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    cmd = (c.get("input") or {}).get("command", "")
                    if any(k not in READ_ONLY for k in engine_commands(cmd)):
                        return True
    return True


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace") or "{}")   # tolerate a BOM
    except (ValueError, OSError):
        payload = {}
    event = payload.get("hook_event_name") or (sys.argv[1] if len(sys.argv) > 1 else "UserPromptSubmit")
    try:
        rules = DIGEST.read_text(encoding="utf-8")
    except OSError:
        return
    if event == "UserPromptSubmit":
        print(rules)
    elif event == "SessionStart":
        orders = ORDERS.read_text(encoding="utf-8") if ORDERS.exists() else ""
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": orders}}))
    elif event == "PreToolUse":
        cmd = (payload.get("tool_input") or {}).get("command", "")
        notes = []
        if AREA.search(cmd):
            notes.append(area_checklist(rules))
        if NEW_NPC.search(cmd):
            notes.append(NPC_CHECK)
        if notes:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "\n\n".join(notes)}}))
    elif event == "Stop":
        if payload.get("stop_hook_active") or not turn_played(payload):
            return  # already checked this turn, or an out-of-game turn (no engine play commands)
        print(json.dumps({"decision": "block", "reason": STOP_CHECK}))


if __name__ == "__main__":
    main()
