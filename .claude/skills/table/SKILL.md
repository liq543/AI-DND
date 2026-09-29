---
name: table
description: Open (or re-open) the live D&D table — the real-time map, tokens, initiative, dice and handouts view at http://localhost:8765. Use when the player asks to see the map, the board, the table, or the visual game state.
---

Start the live table and show it to the player:

1. In the Claude desktop app, open the browser preview for the `live-table` launch configuration (`.claude/launch.json`). Otherwise run `python -m engine serve` in the background.
2. Tell the player the address: **http://localhost:8765** — it updates live as the game changes; their Roll buttons appear there.
3. Make sure it shows the right thing: `python -m engine map show <id>` for where the party is, and a `scene` banner if useful.

Player's extra instructions, if any: $ARGUMENTS
