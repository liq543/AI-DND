# Visuals — Maps, Scenes, Tokens, Handouts, Art

The player watches the **live table** (http://localhost:8765). Anything you do through the engine appears
there within a fraction of a second. Keep it current: whenever the characters' situation changes visually,
change the table.

## When to update the table

| Moment | Do |
|---|---|
| Campaign start | `map gen region --show` (the world), then `map party x,y` on the starting town |
| Arriving in a settlement | `map gen town --name "Quinvale" --show`; place the party with `party-move` or `place` |
| Entering a building | `map gen interior --building tavern|shop|temple --show` |
| Entering a dungeon / cave | `map gen dungeon|cave --show` — fog of war is automatic; PCs reveal what they can see as they move |
| Fight breaks out | Use the current map, or `map crop <id> --room N --show` / `map gen arena --preset ... --show` |
| New scene or location | `scene "Title" --desc "one evocative line"` |
| NPC speaks at length | `say --as "Name" "..."` for key lines (keep the full dialogue in chat) |
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
- **Lighting drives fog of war**: `map set <id> --kv lighting=bright|dim|dark`. In the dark, characters see only
  with Darkvision or a lit torch/lantern (`item light kira torch-1`).

## Tokens & portraits

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

## Handouts & cards

`show …` pops a card up on the player's screen: item cards (icon, rarity colour, SRD text), creature cards
(portrait, name, type — no stats), text handouts on parchment, or any image asset. `show clear` dismisses it.

## Static snapshots (no browser)

If the player can't open the live table: `map render <id>` writes `campaigns/<slug>/views/map-<id>.svg`
(player view) and `campaigns/<slug>/views/current-map.svg` is refreshed after every command — share that file.
