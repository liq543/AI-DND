# Rules Library — Where to Look

Rules are the **D&D System Reference Document 5.2 (2024 rules)**, CC-BY-4.0 (see [LEGAL.md](LEGAL.md)).
Never load a whole big file "just in case". Grep for the term, then read only the matching section.

## Lookup recipes

| Need | Do this |
|---|---|
| A specific spell | `rules/spells/<spell-name>.md` (kebab-case, e.g. `cure-wounds.md`). Unsure of name → grep `rules/spells/_index.md` |
| Spells by class/level | grep `rules/spells/_index.md` for e.g. `\| 1 \|.*Cleric` |
| A monster / NPC stat block | `rules/monsters/<name>.md` (e.g. `goblin-warrior.md`, `bandit-captain.md`) |
| Monsters by CR | grep `rules/monsters/_index.md` for e.g. `\| 1/2 \|` |
| A magic item | `rules/magic-items/<name>.md`; browse by rarity in `rules/magic-items/_index.md` |
| A condition (Prone, Grappled, …) or any keyword | grep `rules/core/08-rules-glossary.md` for `^#### <Term>` and read ~20 lines |
| Class features / level table | `rules/classes/<class>.md` |
| Species, backgrounds | `rules/core/04-character-origins.md` |
| Feats | `rules/core/05-feats.md` |
| Weapons, armor, gear, prices | `rules/core/06-equipment.md` |
| Encounter XP budget | `rules/core/09-gameplay-toolbox.md` → "Combat Encounters" |
| Traps, poisons, environment, travel pace | `rules/core/09-gameplay-toolbox.md` |

## Core chapters (`rules/core/`)

| File | Contents |
|---|---|
| 01-playing-the-game.md | Rhythm of play, abilities, d20 tests, proficiency, actions, social interaction, exploration, **combat**, damage & healing |
| 02-character-creation.md | Step-by-step creation, level advancement (XP table), higher-level starts, multiclassing, trinkets |
| 04-character-origins.md | Backgrounds (Acolyte, Criminal, Sage, Soldier) and Species (Dragonborn, Dwarf, Elf, Gnome, Goliath, Halfling, Human, Orc, Tiefling) |
| 05-feats.md | Origin, General, Fighting Style and Epic Boon feats |
| 06-equipment.md | Coins, weapons (and Mastery properties), armor, tools, gear, mounts, lifestyle, hirelings, crafting |
| 07-spellcasting-rules.md | Preparing and casting spells, slots, components, concentration, areas |
| 08-rules-glossary.md | Alphabetical definitions: every **condition**, action, area of effect, hazard, rest |
| 09-gameplay-toolbox.md | Travel, curses, environment, fear, poison, traps, **encounter building** |
| 10-magic-item-rules.md | Rarity, value, attunement, activation, cursed/sentient items, crafting |
| 11-reading-stat-blocks.md | How monster stat blocks work, CR → XP/proficiency table |

## Entry folders

- `rules/classes/` — barbarian, bard, cleric, druid, fighter, monk, paladin, ranger, rogue, sorcerer, warlock, wizard
- `rules/spells/` — 339 spells + `_index.md` (level, school, classes)
- `rules/monsters/` — 329 monsters and animals + `_index.md` (CR, type)
- `rules/magic-items/` — 243 items + `_index.md` (type, rarity, attunement)

The SRD does not include every published subclass, species, or monster. If a player wants something outside it,
the DM may allow a reasonable homebrew version — write it into the campaign's `campaign.md` under House Rules so it stays consistent.

Rebuild from source with `tools/build_rules.py` (instructions in its header).
