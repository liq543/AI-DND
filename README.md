# D&D Live Table

Play Dungeons & Dragons (SRD 5.2 / 2024 rules) with Claude (or Codex) as your Dungeon Master, a rules engine
as the referee, and a live, Roll20-style table in your browser.

## Play

| You want to | Do |
|---|---|
| Start a new campaign | Open a **new chat** in this folder → `/new-game` (or "new game") |
| Continue | Open a **new chat** → `/resume-game` (or "continue") |
| See the table | `/table`, or open **http://localhost:8765** (start it with `python -m engine serve`) |
| Stop for now | `/save-game` |
| Make / level up a character | `/new-character` |
| Roll your dice | Click **Roll** on the table when asked (or say "roll for me") |
| Ask out of character | Start with `OOC:` |

One chat per session keeps things sharp; everything important lives in the files.

## The live table

Real-time (Server-Sent Events) view of the game: world, town, dungeon and battle maps with fog of war and
line-of-sight reveal; tokens with class/creature emblems, health bars and condition badges; initiative and
remaining action/bonus/reaction/movement; every die rolled with its individual faces; the narration log;
full character sheets; item/creature/text handouts; scene banners; and **Roll** buttons for your checks.
It shows only what your characters could know: hidden monsters, secret rolls, trap locations, unexplored
rooms and enemy HP never reach the browser.

## Fair play by design

- **The engine is the referee.** Every roll, hit point, spell slot, item, coin, XP point and step on the grid goes
  through `python -m engine`, which validates it against the SRD: ability-score methods, background bonuses, class
  skill lists, action economy, reach and range, cover, conditions, concentration, spell preparation, slots and
  costly components, rest timing, ammunition, encounter XP budgets, treasure rarity by tier,
  shop prices… A move outside the rules is refused and nothing changes.
- **Real dice.** Rolls use the operating system's cryptographic RNG, are stored with every die face, and can't be
  re-rolled. Player rolls happen in the engine when you click Roll; typed numbers are never used.
- **Tamper-evident.** State is rebuilt from an append-only event log where each event is HMAC-signed and
  chained to the previous one; the key lives with the campaign (`campaigns/<name>/engine/signing.key`) so a
  campaign moves between machines with git. Editing, deleting or reordering anything is detected, and the game
  stops until it's restored from a signed backup. Lost a key from an older campaign? `python -m engine rekey`
  re-signs an intact log with a new one.
- **No quiet favours.** Anything beyond the rules (a deadly encounter, a legendary item early, a big hoard) needs a
  DM override with a reason, and every override is shown on the table for everyone to see.
- **Locked in Claude Code.** `.claude/settings.json` pre-approves engine commands and denies hand-editing engine
  data (signed logs, snapshots) or the signing keys. During the beta the DM may fix engine code and rules
  data mid-play to match the SRD (AGENTS.md §1.8).

Honest caveat: it's your computer, so *you* could always change the code or delete a campaign. The system makes
cheating visible and makes the AI unable (Claude Code) or instructed not to (Codex) bend the rules — not
physically impossible for the machine's owner.

## What's inside

```
AGENTS.md / CLAUDE.md     DM operating manual (integrity rules, session flow)
dm/                       engine-reference.md, dm-guide.md, visuals.md, procedures/
engine/                   rules engine, map generators, renderer, assets, live-table server  (python -m engine help)
viewer/                   the live table web app
rules/                    full SRD 5.2 (12 classes, 339 spells, 329 monsters, 243 magic items, core chapters)
assets/vendor/            game-icons.net icon set (4,100+ icons, CC BY 3.0) — tokens, item cards, conditions
templates/                narrative files for a new campaign
campaigns/<name>/         campaign.md, npcs/locations/quests/secrets.md, log/  (yours & the DM's notes)
campaigns/<name>/engine/  the signed event log + backups  (never edit)
campaigns/<name>/state.md, party/*.md, views/   auto-generated snapshots
tests/                    python -m unittest discover -s tests
```

Requires only Python 3.10+ (standard library). No installs, works offline.

## Handy commands

```bash
python -m engine campaign list
```

```bash
python -m engine serve
```

```bash
python -m engine verify
```

```bash
python -m unittest discover -s tests
```

## Credits & licenses

- Rules: System Reference Document 5.2 by Wizards of the Coast LLC, CC BY 4.0 (`rules/LEGAL.md`); markdown by
  [springbov/dndsrd5.2_markdown](https://github.com/springbov/dndsrd5.2_markdown).
- Icons: [game-icons.net](https://game-icons.net) by Lorc, Delapouite and contributors, CC BY 3.0
  (`assets/vendor/game-icons/`).
- Imported images keep their own license and credit, recorded with the asset (`python -m engine asset list`).
