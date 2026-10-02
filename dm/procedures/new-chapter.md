# Procedure: New Chapter (a saga continues)

A **saga** is a run of campaigns played by the same crew: each campaign is one **chapter**. The crew keeps their sheets,
their loot, their scars and their memories from one chapter to the next. Each chapter still gets its own folder, its own
signed log and a clean, focused set of notes, so the DM's context stays small.

## 0. Close the old chapter
1. Follow `save-game.md` for the last session: session log, a `log/summary.md` paragraph, outstanding XP, `session end`, `verify`.
2. In the old `campaign.md`, set **Status** to `Complete: chapter N of <saga>` and add a two-line "how it ended".
3. **Don't archive it.** An archived campaign can't be continued or searched for callbacks.

## 1. Chapter zero: ask before you plan
One message of questions, no spoilers, each with a suggested default. Cover:
- **The land:** where they go next, and how the chapter's acts are laid out across it.
- **The objective's shape:** heist, conquest, hunt, founding something, a war to exploit.
- **Old threads:** for each one, carry, background or drop.
- **The crew:** keep, grow or lose members; companions' futures.
- **Length and level range, and the mix:** combat, travel and exploration, scheming.
- **Tone, lines and veils.**
- **The time skip** between chapters, and what may happen offscreen.

Record the answers in the new `campaign.md`.

## 2. Create the chapter
```
python -m engine campaign new "<Title>" --from <previous-slug> --set start_level=<N> --set player_rolls=... --set xp_mode=...
```
This links the chapters (`campaign.init` records the saga, the chapter number and the previous chapter) and writes a
`chronicle.md` skeleton. The previous chapter's signed log must verify, or nothing carries over.

## 3. Carry the crew
```
python -m engine char import <pc-id>          # each player character and DM-run party member
python -m engine char import <companion-id>   # each companion NPC who travels with them (a ward, a pet, a hireling)
python -m engine char levelup <pc-id> ...     # up to start_level, with every choice (character-creation.md)
```
`char import` copies the sheet exactly as the old log has it: classes, features, spells, every item with its notes and
provenance, coins, XP, bio and look. It drops only what belonged to the old scene: the token, conditions, temporary HP
and spent resources. The time skip counts as rest, so HP, slots and Hit Dice are full. If the chapter starts above the
character's level, XP comes up to that level's floor. Show each portrait and confirm the look still fits after the
time skip (`asset look`).

## 4. Write the chronicle (what everyone carries forward)
`chronicle.md` is read at the start of **every** session of the new chapter (`resume-game.md`). Keep it under about 6 KB
and write it so the DM could play from it alone:
- **The chapters so far:** a tight paragraph per chapter. Name the big beats and the turning points.
- **The crew now:** each member's state of mind, their loyalties, what they'll never forget or forgive, and their
  relationships with each other.
- **What they carry:** the items that matter to the story (the sheets have the rest) and how they got them.
- **Who wants them, and why:** pursuers, rivals and creditors, with what each knows and could do.
- **Promises, debts and grudges:** owed in both directions.
- **Threads left hanging:** one line each, with a pointer to where the full story lives
  (`campaigns/<previous>/log/session-003.md`, `campaigns/<previous>/npcs.md → <name>`).

## 5. Carry the notes forward selectively
The new chapter starts clean. Copy forward only what will matter here:
- **npcs.md:** recurring people only, each marked `(from chapter N)`.
- **secrets.md:** the saga's long arc (DM-only, kept up to date chapter after chapter) and any villain clock that is
  still running.
- **quests.md:** the threads the player chose to carry.

Everything else stays in the old folder for callbacks.

## 6. Callbacks
When play needs an exact detail from an earlier chapter, search the old folder for it:
`grep -n "<name or phrase>" campaigns/<previous>/log/*.md campaigns/<previous>/npcs.md`. Read only the lines you
need. Never open a whole old chapter, and never `_archive/`.

## 7. Prep the chapter deeply, before the first scene
A chapter runs for many sessions. Prep it like a campaign, and write it all into the notes **before** play:
- **secrets.md: the chapter bible.**
  - The truth behind the hook, and how it ties into the saga's long arc.
  - Three to five factions, each with a want, a leader and resources.
  - The main opposition, with a 6 to 8 step clock.
  - Every act's places, set pieces and climax.
  - Five or six secrets with three clues each.
  - How every crew member's history hooks in.
  - A list of complications for when the crew goes off-script. A crew that derails is normal: the world should have
    somewhere to go when they do.
- **locations.md:** each region of the chapter, with its towns, lairs, roads and travel times.
- **npcs.md:** a roster of 10 to 15 people, each with a want, a quirk, a secret and a stat block.
- **quests.md:** the hook, the chapter's grand objective, and 4 to 6 side threads.
- **The region map** (`map gen region`) and the starting location's map, to the detail standard in `visuals.md`.

## 8. The briefing, then begin
Follow `new-game.md` §5, written as "Previously, in the saga…":
- What happened.
- What the time skip held.
- Where they are now.
- Who is with them.
- What each of them wants.

Then `session start` and an establishing beat.
