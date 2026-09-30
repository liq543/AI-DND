"""Claude Code hook: puts the DM rule digest (dm/turn-rules.md) into the model's context at every point it acts.

  UserPromptSubmit  before every reply          (plain stdout is added as context)
  SessionStart      on startup, resume, clear and after every compaction (plus the saved memories)
  PreToolUse        before every tool call
  PostToolUse       after every tool call
  Stop              once per turn: blocks ending until the reply has been checked against the digest

Reads the hook payload as JSON on stdin; prints nothing it can't read (never breaks a session).
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
DIGEST = ROOT / "dm" / "turn-rules.md"
ORDERS = ROOT / "dm" / "standing-orders.md"   # the player's standing orders: in the repo, so they travel to every machine


def memories():
    """The saved feedback memories for this project, if the memory folder exists."""
    slug = "".join(c if c.isalnum() else "-" for c in str(ROOT))
    d = Path.home() / ".claude" / "projects" / slug / "memory"
    if not d.is_dir():
        return ""
    parts = [p.read_text(encoding="utf-8", errors="replace") for p in sorted(d.glob("*.md")) if p.name != "MEMORY.md"]
    return "\n\n# Saved memories (standing instructions from the player)\n\n" + "\n\n---\n\n".join(parts) if parts else ""


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    event = payload.get("hook_event_name") or (sys.argv[1] if len(sys.argv) > 1 else "UserPromptSubmit")
    try:
        rules = DIGEST.read_text(encoding="utf-8")
    except OSError:
        return
    if ORDERS.exists():
        rules += "\n\n" + ORDERS.read_text(encoding="utf-8")
    if event == "UserPromptSubmit":
        print(rules)
    elif event == "SessionStart":
        out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": rules + memories()}}
        print(json.dumps(out))
    elif event in ("PreToolUse", "PostToolUse"):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": rules}}))
    elif event == "Stop":
        if payload.get("stop_hook_active"):
            return  # already checked once this turn
        reason = ("Before ending this turn, check what you just did and said against the DM rule digest below. "
                  "If anything was missed (a poi, a scene banner, a description, an alignment, a log line, notes, a leaked "
                  "hidden roll, a montage, a frozen world), fix it now with engine commands and tell the player in one line. "
                  "If everything is satisfied, reply with exactly one short line: \"✔ Rules check passed.\"\n\n" + rules)
        print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
