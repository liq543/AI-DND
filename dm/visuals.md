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
  secrets of hidden rooms into `secrets.md`), keyed by map id and room name, so descriptions stay consistent. Room
  numbers are the DM's key only: they are drawn on the DM render, never on the players' table.
- **Custom touches:** `map paint` terrain codes: `#` wall, `.` floor, `,` grass, `:` road, `t` undergrowth (difficult),
  `^` rubble (difficult), `w` shallow water, `~` deep water, `T` tree, `P` pillar, `o` boulder (half cover),
  `h` furniture, `c` counter, `D` door, `d` open door, `S` secret door, `<` `>` stairs, `x` chasm, `b` bridge.
- **More terrain codes:** `k` carpet, `q` marble floor, `a` gaming table (half cover), `g` railing (half cover),
  `v` crates/barrels (half cover), `l` lamp/candelabrum (a pool of light, walkable), `u` statue or display plinth
  (¾ cover), `n` mast/column (¾ cover), `p` potted plant (half cover), `e` bench (difficult, half cover; joins its
  neighbours), `i` cupboard/wardrobe (¾ cover, blocks sight), `y` bed, `j` tub/basin (half cover), `z` tiled floor.
  Built pools and channels (`w`/`~` indoors) get a stone coping drawn automatically.
- **Furnishings: use the piece the fiction names.** Each has its own top-down art; long pieces join their neighbours
  and wall pieces sit against the wall. `A` table (plain wood: anything you eat, work or talk at), `C` chair/stool
  (difficult; its back turns away from the table), `W` writing desk, `K` bookshelf/shelving (¾ cover, blocks sight),
  `Q` chest/trunk, `O` barrel/keg, `U` sacks/bales, `J` workbench, `R` rack (weapons, tools, drying lines), `!` anvil,
  `F` forge/kiln, `&` stove/oven/range, `@` cauldron/vat, `*` brazier (casts light), `X` altar, `H` throne/great chair,
  `Y` coffin/sarcophagus, `$` strongbox/safe, `N` cage, `M` market stall (striped awning), `+` signpost/notice board,
  `|` curtain/screen (walkable, blocks sight), `L` ladder (difficult), `Z` hay/straw (difficult), `G` grate/drain,
  `%` hedge/shrubs (¾ cover, blocks sight). **`a` is a card or dice table only** (green felt and chips): never use it
  for a desk, a bench or a dining table. **`i` is a cupboard or wardrobe only**: shelves of books or goods are `K`.
  A room built from two codes looks like nobody lives in it. Vary it.
- **Props: anything else, from 4,100+ icons.** `map icons <words>` searches the vendored game-icons library, and
  `map prop <id> x,y --icon <name> --name "What it is" [--size small|large] [--color #hex] [--rotate 30] [--blocks]`
  sets it on the tile: a globe on a desk, a skull on a shelf, a harp in a corner, a cauldron, a telescope, a birdcage.
  `--blocks` makes it fill the square; without it the prop is set dressing on top of whatever is there. Change it with
  `map prop-move <id> x,y --id prop-2 --reason "..."` or `map prop-remove <id> --id prop-2 --reason "..."`. Dress every
  room with a few: what's on the tables, the tools of the trade, the owner's one vanity. Props are decoration; anything
  a character can walk up to and examine still gets a `map poi`.
- **Every place must look like itself.** Never reuse a generator layout for a different kind of place with the
  furniture shuffled. Set a **theme** (`map set <id> --kv theme=stone|ship|sewer|marble|bathhouse|timber|manor|temple|cellar`:
  palette, textures, trim, backdrop) and override its textures per map so two places in the same theme still differ:
  `walls=hatch|brick|ashlar|timber|plaster`, `floor=marble|mosaic|checker|terrazzo` (the `q` squares),
  `wood=planks|herringbone|parquet` (`=`), `stone=flag|hex|slate` (`.`), `accent=#rrggbb` (trim, rugs, gilt).
  `map gen interior --building tavern|inn|house|shop|temple|bathhouse|manor|library|warehouse|workshop` varies the
  layout by seed (which side the back rooms are on, how many, their sizes, chamfered corners, where the door is) and
  furnishes by kind, with a matching theme.
- **Shape before furniture.** A generated interior is a starting point; for any place the story lingers in, draw it
  (write the grid as a text file, one row per line, and `map import-grid <id> --out grid.txt`). **Draw to fight in:** any place a scene could turn violent in needs an open area of at least 20×14 squares (100×70 ft), and its main room should be big enough for everyone present to move round each other. The engine refuses smaller grids unless you pass `--small "why"` for a place that truly is that small (a skiff, a cell). Avoid the box-of-boxes
  habit: vary room sizes, break the outline (apses, bays, chamfered corners, alcoves, a round pool or court, a
  colonnade), put rooms where the building's work needs them (a kitchen by the hall, stores by the loading door,
  private rooms off a passage), and give every room at least one thing only that room has. Before importing, compare
  it with the last few maps you drew: if it could pass for one of them with the labels swapped, redraw it.
- **The detail standard (every map, every time).** The bar is a map the players can explore by clicking, not a floor
  plan. A finished map has all of these:
  1. **Zones by function, in the order people use them.** Public entry → staff post or counter → where guests change,
     wait or store things → the main room with a centrepiece → inner or restricted rooms → private rooms off a passage →
     staff and service routes (a staff door, a service passage, a back stair, stores). Each zone is its own shape and size.
  2. **A centrepiece and a quirk per room.** A pool, a hearth, an altar or a long table anchors the main room, and each
     lesser room gets one thing only it has. Repeated objects (four statues, a row of cabinets) each get their own
     detail: a worn patch of luck-rubbing, a lost-property dish, a real burning lamp.
  3. **A poi for every object anyone could walk up to**, written as what a character notices: material, wear, sound,
     smell, who uses it, and one hook (a stamp, a stain, a lock, a name scratched in). Doors worth naming get pois too,
     including their locks, slides and bolts.
  4. **Owned storage.** Lockers, cupboards, crates, cells and berths belong to someone: name them by owner or contents
     ("the cook's spice chest", "the cell by the drain"), not by number. Use a number only where the world itself shows
     one and it matters (a painted cell number, a tag on a key). Record in locations.md whose each one is. Anything that
     holds items is a `map container`.
  5. **People at their posts.** Staff are placed where their job keeps them (door, counter, stove, desk), and regulars
     where they'd be. Each is described and aligned, with a want, so the room reacts when things go wrong.
  6. **State kept live.** When the fiction changes something (opened, picked, bloodied, barricaded, emptied), replace
     its poi with the new state and `map show`. The map is always the truth of the room *now*.
  7. **locations.md mirrors it**: zones with coordinates, every poi, who owns what, the posts and the exits.
- **The world map of record.** A campaign that travels gets one hand-authored region map as its source of truth
  (`map import-grid` the terrain, then `map settlement`, `map site`, `map route`, and `map label` for regions), set with
  `map set <id> --kv world=on` so it is always one click away on the table. Every town and site gets `--text` for what
  the party knows (players click it for the journal entry); places the party hasn't heard of are `--hidden` until
  `map discover`. Local maps (towns, lairs, roadside ambushes) are cut to match what the world map shows there.
- **Lighting drives fog of war**: `map set <id> --kv lighting=bright|dim|dark`. In the dark, characters see only
  with Darkvision or a lit torch/lantern (`item light kira torch-1`).

## Tokens & portraits: generated from what they look like

**Every creature you describe gets its description on the table.** The moment you narrate what an NPC or
monster looks like, run `npc describe <id> --text "what anyone can see"` (looks, clothing, gear in view,
voice, what they're doing). The players click the token and read it on the info panel. Update it when their
look changes (wounded, disguised, chained). Hidden facts go in `npc lore` only once the party learns them.

**Pictures are drawn live from that description.** Every character and humanlike NPC gets a generated portrait
(party panel, sheet, info card) and face (map token, initiative bar, log, journal), drawn from: species; class or
NPC role (guard, cultist, noble, pirate...); the armor a PC actually wears; and whatever the description says about
hair, eyes, skin, beard, scars, freckles, tattoos, war paint, eyepatch, horns, headwear, clothing, cloak, build,
age and expression. Beasts, monsters and other non-humanoids get creature art in their type's palette. Nothing
needs storing: change the description or the look and the table redraws it.

- **Pin exact features** with `asset look <id> --hair "..." --eyes "..." --skin "..." --beard "..." --marks "..."
  --headwear "..." --outfit "..." --cloak "..." --build "..." --age "..." --expression "..." --horns "..."
  --background "..." --presentation feminine|masculine`. Each field overrides what the description implies;
  `--clear eyes` (or `all`) removes pins. Every call prints what the generator will draw.
- **Set it when the player describes their character** (session zero, character creation) so the portrait
  matches their idea. Ask them to look at it on the table and adjust with `asset look` until it does.
- **See it yourself**: `asset art <id> [--crop face]` writes the SVG to `views/art/`.
- **A bespoke picture**: `asset portrait <id>` pins the current art as a fixed asset; `--style heraldic` gives the
  old heraldic card; `asset portrait <id> --clear` goes back to live art. You can also **draw** one (write an SVG,
  no scripts) and `asset draw file.svg --name "Sister Maren" --portrait maren`.
- **Public images:** `asset fetch <url> --name "..." --license CC0|CC-BY-4.0|public domain --credit "Author, source"`.
  Only use images whose license allows it (Wikimedia Commons, OpenGameArt, the player's own). The license and
  source are logged with the asset. A fetched battle map can become a grid map: `map from-image <asset> --w 30 --h 20`,
  then `map paint` the walls so movement and line of sight work.
- Token ring colour = side (blue party, teal ally, red enemy, gold neutral), health bar for the party, "bloodied"
  slash for enemies. `fx set tokens=icon` switches the table back to emblem tokens.

## Item art

Every item has an illustration: its shape comes from what it is (sword, axe, bow, potion, scroll, ring, cloak,
key, lantern...), its colours from its name, alias and note ("silver dagger", "ruby-set ring", "cloak of midnight
blue"). Identified magic items glow in their rarity colour; unidentified ones show only their shape with a "?"
shimmer, never colours taken from their true name. So **`item note --alias ... --text "what it looks like"`
also changes its picture.** For a unique look, `asset draw file.svg --item kira:<item-id>` (or `asset fetch ... --item`).

## Table animation (you control it)

Moves, attacks, damage, healing, spells, conditions, saves and turns animate on the live table automatically, in
order, before the new state appears: tokens walk their path, arrows fly, spell orbs burst, numbers float up, the
fallen fall, and each turn gets a banner. The camera follows the action. You decide how it plays:

| Want | Do |
|---|---|
| A tense boss fight | `fx preset cinematic` (slower, everything on) |
| Normal play | `fx preset standard` |
| A big fight with many creatures | `fx preset quick` (2× speed, no turn banners or dice) |
| No animation | `fx preset off` |
| Fine control | `fx set speed=1.5 moves=on attacks=on numbers=on turns=off camera=follow dice=on shake=off sync=on` |
| Weather / atmosphere | `fx ambient rain|snow|fog|embers|ash|motes|storm|none --intensity 0.6` |
| Point the players at something | `fx camera <id|x,y|fit>`, `fx play ping --at 12,7` |
| A moment the rules don't animate | `fx play burst --at 12,7 --color fire --radius 20` (explosion), `fx play bolt --from mage --to kira --color lightning`, `fx play banner --text "The ceiling gives way!"`, `fx play shake`, `fx play flash --color white`, `fx play float --on kira --text "Blessed"` |

`sync=on` holds the side panels until the animation finishes, so a result never shows before its moment.
Effects are visual only: they never change the game. Hidden creatures and fogged squares never animate for the
players. Each player can still pick "Reduced motion" or "Off" for themselves in the table's Animations menu.
Match the ambient to the scene (`fx ambient none` when they leave the storm), and don't overuse `fx play`: one
flourish at the dramatic beat is worth ten.

## Containers and stashes

Items on the floor share one marker per tile; clicking it lists **everything** on that tile. When a place holds things
(a chest, a strongbox, a wardrobe, a hidden cache, the party's stash at their base), make the tile a container:
`map container <map> x,y --name "Iron-bound chest" --text "what it looks like"` (anything already lying there goes
inside). Put things in with `item stash <who> <item-id> --to <container-id> [--qty N]`, and take them out with
`item pickup <who> <floor-id>`, both from in or next to that square. `map container-remove <map> --id ... --reason`
leaves the contents on the floor. Players click the chest marker to see what's inside.

## Points of interest (perceived objects)

**Whenever the characters perceive a notable object in a place, pin it.** Examples: a statue, a weapon rack, a desk with a
ledger, a strange door, an altar, a loose grate. Use `map poi <map> x,y --name "..." --text "what they perceived"`, or
`--id <journal-id>` to link an entry you already showed. Put it **on the tile the object physically occupies**: check the
grid with `map ascii <map>` and pick the statue's plinth, the rack's tile, the desk, the door itself, never an empty floor
square beside it. Players see a small blue marker there (once that tile is revealed) and click it to open the journal entry.
Markers are **permanent**. When you update a revisited place, move markers whose objects moved
(`map poi-move ... --reason`) and remove those that are gone (`map poi-remove ... --reason`). The journal entry stays.
**The journal keeps map objects apart from clues.** A poi's entry is filed under **Places & objects** (grouped by place),
never under **Handouts & clues**, so room furniture doesn't bury the story. Handouts & clues holds what matters to quests and
the plot: everything you `show`, `journal add`, and pois made with `--clue` (a body, a hidden cache, a sigil plate, a clue
written on a wall). If a plain object turns out to matter later, refile it: `journal file <id> --as clue`. Linking a poi to
an existing handout (`--id`) leaves that handout where it is.
**A `map label` is not enough for an object.** Labels name areas (a room, a street, a quay). Anything worth naming that
the characters can walk up to and look at (a fountain, a counter, a shrine) also gets a `map poi` with a proper description,
written the way you would describe it aloud.

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
