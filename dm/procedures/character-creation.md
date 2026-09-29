# Procedure: Character Creation & Level Up

The engine enforces the rules of `rules/core/02-character-creation.md`; your job is to make it a fun
conversation. Summarise options briefly (don't dump chapters) and recommend fits for their concept.

## Build a character
1. **Concept** in one sentence → suggest class / species / background.
2. **Class** — read `rules/classes/<class>.md` (core traits, level 1 features, skill list, equipment options A/B/C).
3. **Background** (`rules/core/04-character-origins.md`: Acolyte, Criminal, Sage, Soldier) → its three abilities,
   Origin feat, skills, tool, equipment A (items) or B (50 GP).
4. **Species** (Dragonborn, Dwarf, Elf, Gnome, Goliath, Halfling, Human, Orc, Tiefling). Note the choice each needs:
   Human → `--species-skill` + `--species-feat` (Origin feat); Elf → `--species-skill insight|perception|survival`;
   Dragonborn → `--ancestry <colour>`; Tiefling → `--ancestry abyssal|chthonic|infernal`; Small-or-Medium species → `--size`.
5. **Ability scores** — the campaign's method:
   - standard: 15, 14, 13, 12, 10, 8 assigned as they like;
   - pointbuy: 8–15, 27 points;
   - roll: `python -m engine char roll-stats "<Name>"` — show the six results, the player assigns them. One set per character, ever.
   Then background bonus: +2/+1 or +1/+1/+1 among the background's three abilities.
6. **Class choices**: skills (exact number from the class list, not duplicating background skills), Fighter
   `--fighting-style`, Weapon Mastery `--masteries` (Barbarian, Fighter, Paladin, Ranger, Rogue), Rogue `--expertise`,
   Magic Initiate choices if the background/feat grants it, two languages besides Common.
7. **Create** it (engine computes HP, AC, saves, skills, attacks; grants and equips starting gear):
   `python -m engine char create --name ... (see dm/engine-reference.md)`
8. **Spellcasters**: `spells set <id> --cantrips ... --prepared ...` (Wizards also `--spellbook` six level-1 spells).
9. **Personality**: `char bio <id> appearance|personality|ideals|bonds|flaws|backstory|goals "..."`.
10. **Portrait**: `asset portrait <id>`. Place the token when play begins.
11. Read back a short summary (the Sheet tab in the live table shows everything) and confirm.

Starting above level 1: the campaign's `start_level` lets `char levelup` run without XP until that level;
level up one level at a time with the required choices.

## Level up
When the engine announces "LEVEL UP available" (XP) or after `xp milestone`:
```
python -m engine char levelup <id> [--class <new class for multiclass>] [--hp avg|roll] [--subclass <name>]
    [--feat "Ability Score Improvement" --asi str+2 | --feat "<general feat>"] [--fighting-style ...] [--expertise a,b]
```
The engine tells you which choices a level requires (subclass at 3, feats at 4/8/12/16, Epic Boon at 19...).
Then update prepared spells (`spells set`) if the character casts. SRD subclasses: one per class (e.g. Champion,
Evoker, Life Domain, Thief); others must be registered as public homebrew first.
