# Procedure: Save / End Session

Mechanics are saved automatically by the engine after every command. Saving is about the **story** notes.

1. If mid-combat, either finish it or leave it running (the engine keeps the initiative, turn and HP exactly).
2. **Session log** — `log/session-NNN.md` has a bullet for every scene played.
3. **log/summary.md** — append one paragraph (5–8 sentences): what happened, choices made, who they met, what was
   gained or lost, how it ended.
4. **npcs.md / locations.md / quests.md** — new names, attitudes, places, quest progress.
5. **XP** — award anything outstanding: `xp award --encounter` after fights; `xp award --amount N --reason "..."`
   for overcome non-combat challenges (engine caps it at the party's High budget).
6. **secrets.md** — advance the villain's clock for what the party did or didn't do; tick off discovered clues;
   jot ideas for next time.
7. `python -m engine session end` and `python -m engine verify`.
8. Tell the player: a one-line cliffhanger, what they gained, and
   *"Saved. Next time, open a fresh chat here and say 'continue'."*
