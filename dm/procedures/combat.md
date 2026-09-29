# Procedure: Combat

The engine runs the bookkeeping (initiative, turns, action economy, movement, reach and range, cover,
advantage/disadvantage from conditions, damage types, concentration, death saves, recharge, XP). You run the
drama and the monsters' tactics.

## Set up
1. The battlefield: current map, or `map crop <id> --room N --show`, or `map gen arena --preset ... --show`.
   Make sure every PC has a token (`place`).
2. Foes: `encounter plan <monster:count ...>` to check difficulty, then `encounter spawn ... --near x,y`
   (or `npc add ... --at x,y`). Hidden ambushers: `--hidden`, then `npc reveal` when they strike.
   Budgets come from `rules/core/09-gameplay-toolbox.md`; above High needs a public `--override` — don't.
3. `combat start [--surprised ids]` with **no id list**, so everyone on the map rolls initiative, **bystanders
   included**. If you pass ids, the engine warns about who's left out; add them with `combat add <id>`.
   **Civilians and neutrals act every round** like anyone else. They are frightened people, not furniture:
   they flee for exits, hide under things, beg, bargain, shout for the Watch, grab a valuable and run, or
   (if brave) help a side. Decide and run their turn with `move` / `action hide|dash|dodge` / `say`, and give
   each at least one line of narration per round when they do something visible. In player-roll mode, the player clicks **Roll** for their initiative;
   the order is set once everyone has rolled.
4. Describe the battlefield in one paragraph: distances, cover, light, terrain.

## Each turn
- The engine announces whose turn it is. **PC turn**: the player declares; you translate into commands:
  `move`, `attack`, `cast`, `action`, `feature`, `item use`… Each is validated — if it says ✖ RULE, explain and
  offer legal options. **Monster turn**: choose smart tactics for the creature (read its stat block with
  `npc show <id>`), then `move` / `attack` / `action` for it.
- Opportunity attacks: when the engine warns someone left a reach, decide if the monster uses its reaction
  (`attack <id> <target> --reaction`); for a PC, ask the player.
- Riders the engine flags as "possible extra damage … DM applies": check the condition and apply with `damage`
  if it's met. Weapon Mastery notes: apply the property (e.g. `condition add ... prone` for Topple after a failed save).
- `combat next` to end the turn. Keep narration per turn to 1–3 sentences; the table shows the numbers.

## Ending
- `combat end` when one side is defeated, flees, or surrenders. Then `xp award --encounter`, loot with
  `item add ... --source "loot: ..."` / `coins ... --source "loot: ..."`, `item recover-ammo` for archers.
- Note consequences (survivors who fled, noise, prisoners) in the session log.

## Dropping to 0 HP
The engine handles it: PCs fall Unconscious and roll death saves at the start of their turns (Roll button in
player-roll mode); damage at 0 HP adds failures (crits add two); massive damage kills outright. Allies can
`stabilize` (Medicine DC 10) or heal them. Monsters at 0 HP are defeated (`--knockout` on a melee attack to
capture instead).
