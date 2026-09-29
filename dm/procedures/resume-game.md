# Procedure: Resume Game

1. `python -m engine status` — confirms the active campaign, verifies the signed log, and prints the full state.
   If it reports tampering, stop (AGENTS.md §1.7). If the player wants a different campaign: `campaign list`,
   `campaign switch <slug>`, and recommend a fresh chat.
2. Start the live table and give the player the link (AGENTS.md §2).
3. Read (nothing else yet): `dm/engine-reference.md`, `dm/dm-guide.md`, `dm/visuals.md` (once per chat),
   `campaign.md`, `log/summary.md`, `secrets.md`, `quests.md` (Active), the last ~40 lines of the newest
   `log/session-*.md`, and the party sheets in `party/*.md`. Grep `npcs.md` / `locations.md` on demand.
4. If the previous session was saved, `python -m engine session start`. If play was cut off mid-session, continue it.
5. Make sure the table shows the right thing: `map show <id>` for where they are, `scene "..."`.
6. "Previously on…" — 3–5 dramatic, player-facing sentences (no secrets).
7. Re-set the scene: where they are, what's in front of them, combat state if any (whose turn — `combat status`).
8. *"What do you do?"*
