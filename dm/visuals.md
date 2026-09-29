# Visuals — Maps, Scenes, Tokens, Handouts, Art

The player watches the **live table** (http://localhost:8765). Anything you do through the engine appears
there within a fraction of a second. Keep it current: whenever the characters' situation changes visually,
change the table.

## When to update the table

**Hard rule: the moment the characters enter a new area (a room, a stair, a street, a tunnel, a boat), show a map
of it before narrating what they see.** Generate one (`map gen ...`, then `map paint` it to match the fiction),
`map show` it, `place` every PC, companion, NPC and important object on it, and set a `scene` banner. Never
narrate a new location while the table still shows the old one. Tokens left behind stay on the old map.
**The players only see connected, known areas.** Map tabs show the map on the table, every map a PC stands on
(a split party sees all their maps), and maps linked as physically connected (`map link cellar tavern`, for a stair
or another floor) that the party has already seen. Old, far-away places drop out of the tabs, and the server won't
serve them. What the characters can glimpse of an unexplored connected area (the top of a cellar stair, a room seen
through a doorway) is your call: reveal just those cells (`map reveal <id> --rect ...`) instead of showing the whole
floor.
**Time changes places too.** Every time the party enters, re-enters, passes by or even glimpses a known area (such as the street outside a building), ask whether it needs updating for the hour and for what has happened since: opening hours, crowds gone home, doors locked, night guards posted, lamps lit or dark, weather. Apply it with `npc remove`/`npc add --hidden`/`move`/`map door`/`map set lighting=` *before* showing the map.
**Returning somewhere means updating it first.** Before you `map show` a place the party left earlier, apply
everything that happened there meanwhile: villain-clock moves, NPCs who left or arrived, bodies carried off, doors
barred, loot taken. Use `move`/`place`/`npc remove`/`map door`/`map paint`, and compare with its last
`views/maps/` snapshot. Then show it and narrate the differences.
**Maps are never overwritten.** Each map keeps its exact state in the signed log: tokens, bodies, doors, paint,
floor items and labels. When the party returns, `map show <id>` brings it back as they left it. Every switch also
writes a frozen snapshot of the map they left to `views/maps/<id>-e<event>.md` plus player/DM SVGs
(`map snapshot <id>` makes one on demand), and `state.md` → "Maps" lists what is on every map right now.
Check it before describing a place the party revisits.

| Moment | Do |
|---|---|
| Campaign start | `map gen region --show` (the world), then `map party x,y` on the starting town |
| Arriving in a settlement | `map gen town --name "Quinvale" --show`; place the party with `party-move` or `place` |
| Entering a building | `map gen interior --building tavern|shop|temple --show` |
| Entering a dungeon / cave | `map gen dungeon|cave --show` — fog of war is automatic; PCs reveal what they can see as they move |
| Fight breaks out | Use the current map, or `map crop <id> --room N --show` / `map gen arena --preset ... --show` |
| New scene or location | `scene "Title" --desc "one evocative line"` |
| Anyone speaks (PCs too) | `say --as "Name" "..."`: always log the player's PC lines and the key lines of companions and NPCs (keep the full dialogue in chat) |
| Loot / letter / clue | `show item owner:item-id`, `show text "..." --title "..."`, `show srd-item "..."` |
| Meeting a notable creature | `show creature <id>` (players see a card — never its stats) |
| Door opened / secret found | `map door <id> x,y open|reveal`, `map feature <id> x,y reveal` |
| Room entered from afar / scouted | `map reveal <id> --room N` |

Prefer one well-chosen update per beat over constant churn.

## Maps

- **Seeded & reproducible.** Every map records its generator + seed. `map ascii <id>` prints the grid, rooms, and
  hidden features for you; the player sees the rendered map without hidden traps, secret doors, or unexplored rooms.
- **Kinds:** `region` (overland: coasts, biomes, rivers, roads, settlements, points of interest; 2 miles per cell),
  `town`, `dungeon` (numbered rooms, doors, secret door, traps, stairs), `cave`, `wilderness`
  (`--biome forest|plains|swamp|hills|desert|snow`), `interior` (`--building tavern|temple|shop`),
  `arena` (`--preset road-ambush|forest-clearing|bridge|ruins|crypt|cave-chamber|tavern-brawl`).
- **Record what's on it.** After generating, write the important rooms/places into `locations.md` (and the
  secrets of hidden rooms into `secrets.md`), keyed by map id and room number, so descriptions stay consistent.
- **Custom touches:** `map paint` terrain codes: `#` wall, `.` floor, `,` grass, `:` road, `t` undergrowth (difficult),
  `^` rubble (difficult), `w` shallow water, `~` deep water, `T` tree, `P` pillar, `o` boulder (half cover),
  `h` furniture, `c` counter, `D` door, `d` open door, `S` secret door, `<` `>` stairs, `x` chasm, `b` bridge.
- **More terrain codes:** `k` carpet, `q` marble floor, `a` gaming table (half cover), `g` railing (half cover),
  `v` crates/barrels (half cover), `l` lamp/candelabrum (a pool of light, walkable), `u` statue or display plinth
  (¾ cover), `n` mast/column (¾ cover).
- **Every place must look like itself.** Never reuse a generator layout for a different kind of place with the
  furniture shuffled. Set a **theme** (`map set <id> --kv theme=stone|ship|sewer|marble`: palette, textures, trim,
  backdrop) and give the map a shape that matches the fiction: a ship has a bow and a hold, a library has stacks and
  reading nooks, a sewer has channels and ledges. For bespoke layouts, write the grid as a text file (one row per line)
  and `map import-grid <id> --out grid.txt`. Add set dressing: lamps, crates, carpets, statues.
- **Lighting drives fog of war**: `map set <id> --kv lighting=bright|dim|dark`. In the dark, characters see only
  with Darkvision or a lit torch/lantern (`item light kira torch-1`).

## Tokens & portraits

**Every creature you describe gets its description on the table.** The moment you narrate what an NPC or
monster looks like, run `npc describe <id> --text "what anyone can see"` (looks, clothing, gear in view,
voice, what they're doing). The players click the token and read it on the info panel. Update it when their
look changes (wounded, disguised, chained). Hidden facts go in `npc lore` only once the party learns them.

- Every creature placed on a map gets a token: ring colour = side (blue party, teal ally, red enemy, gold neutral),
  emblem = class or creature type (from game-icons.net), health bar for the party, "bloodied" slash for enemies.
- `asset portrait <id>` generates a heraldic portrait card (used in the party panel and on the token).
- For a bespoke look you can **draw** one: write an SVG file (no scripts — they are rejected) and register it with
  `asset draw file.svg --name "Sister Maren" --portrait maren`. Keep it simple and evocative: silhouette, palette,
  one telling detail.
- **Public images:** `asset fetch <url> --name "..." --license CC0|CC-BY-4.0|public domain --credit "Author, source"`.
  Only use images whose license allows it (Wikimedia Commons, OpenGameArt, the player's own). The license and
  source are logged with the asset. A fetched battle map can become a grid map: `map from-image <asset> --w 30 --h 20`,
  then `map paint` the walls so movement and line of sight work.

## Points of interest (perceived objects)

**Whenever the characters perceive a notable object in a place, pin it.** Examples: a statue, a weapon rack, a desk with a
ledger, a strange door, an altar, a loose grate. Use `map poi <map> x,y --name "..." --text "what they perceived"`, or
`--id <journal-id>` to link an entry you already showed. Put it **on the tile the object physically occupies**: check the
grid with `map ascii <map>` and pick the statue's plinth, the rack's tile, the desk, the door itself, never an empty floor
square beside it. Players see a small blue marker there (once that tile is revealed) and click it to open the journal entry.
Markers are **permanent**. When you update a revisited place, move markers whose objects moved
(`map poi-move ... --reason`) and remove those that are gone (`map poi-remove ... --reason`). The journal entry stays.

## Handouts & cards

Everything shown lands in the players' **Journal**. The viewer cross-links automatically: any journal title, crew
name or NPC with known facts that appears in a handout becomes a link, and each card lists what it's
**Connected** to (links out and back). So **write handouts with the exact names** of existing entries ("The
Silver Key", "Captain Rhosk" or "Rhosk") so they connect. Use CAPS labels ("TARGET:", "PROBLEM 2, THE CURSE'S
CLOCK:") to start bold sections.

**Magic items start unidentified.** Anything found, looted, stolen or given arrives as "Unidentified magic dagger"
(players see neither its rarity nor its rules) until someone casts *Identify* (`item identify ... --how`) or focuses on it
through a Short Rest (`rest short --focus who:item`). Bought and starting items are known. If a clue tells the characters
the item's name (a label, a tag, a legend), give it that name with `item note --alias`, since the name alone doesn't reveal
its properties. Use `--identified` on `item add` only when the characters genuinely already know what it does.

**Notable items get a note.** Anything with a story or a look the SRD name does not capture (an heirloom blade, a weapon disguised as something else, a guild token, a cursed trinket) gets `item note <who> <item> --alias "Display name" --text "what it is and looks like"` the moment it enters play. Mechanics still use the SRD base item.

`show …` pops a card up on the player's screen: item cards (icon, rarity colour, SRD text), creature cards
(portrait, name, type — no stats), text handouts on parchment, or any image asset. `show clear` dismisses it.

## Static snapshots (no browser)

If the player can't open the live table: `map render <id>` writes `campaigns/<slug>/views/map-<id>.svg`
(player view) and `campaigns/<slug>/views/current-map.svg` is refreshed after every command — share that file.
