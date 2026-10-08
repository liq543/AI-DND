# Engine Reference

Everything is `python -m engine <command>`. `-h` after any command shows its options.
Output lines are what happened (also pushed to the live table). `✖ RULE:` = refused, nothing changed.
Refer to creatures by id (`kira`, `goblin-warrior-a`) — ids are shown when they're created and in `state.md`.

## Batch: a whole turn in one command (use this by default)
One process, one load, one save, one table update: a 20-step turn takes well under a second instead of ~15 s.
Every step obeys the same rules as on its own. A refused step stops the batch there: the steps before it stand,
the rest are listed as "not run". Never chain past a refusal: fix it and send the rest.
```
py -m engine batch <<'EOF'
# one engine command per line (the `py -m engine` prefix is optional); # comments; end a line with \ to continue it
scene "The Wheel Inn" --desc "Dusk, rain on the shutters" --map wheel-inn --lighting dim --ambient rain
npc add commoner --at 12,4 --side neutral --name "Oswin Hale" --desc "Bald innkeeper, leather apron" --align "lawful neutral"
say --as "Oswin Hale" --at oswin-hale "Rooms are two silver, friend."
move wren 10,6
time 10m --reason "settling in"
EOF
```
- `batch steps.txt` reads a file instead; `-q` hides the step echo; `--atomic` keeps nothing if any step is refused.
- `--dry-run` checks moves, placements and costs and saves nothing. It stops before any dice (a roll is final, so it
  can't be previewed): use it to test a path or a plan, never to peek at a roll.
- Put a roll the player must see resolved *last* in a batch, or on its own, and read its result before narrating.
- Not inside a batch (run alone): campaign, verify, quicksave/quickload, repair, rekey, serve, rules.
- One-command shortcuts: `scene ... --lighting dim --ambient rain --map <id>` (banner, lighting, weather and map
  together); `npc add ... --desc "..." --align "..."` (add, place, describe and align in one line).

## Campaign & session
```
campaign new "The Sunken Crown" --set player_rolls=viewer --set xp_mode=xp --set difficulty=standard --set start_level=1
campaign list | switch <slug> | archive <slug>
campaign new "The Iron Vale" --from the-sunken-crown --set start_level=6   # the next chapter of a saga (writes chronicle.md)
set player_rolls=viewer|auto        # viewer: the player clicks Roll for their own d20s; auto: engine rolls immediately
session start | session end
status                              # full DM snapshot (also in campaigns/<slug>/state.md)
log -n 20                           # recent public events (read this after the player clicks Roll)
audit [--hidden]                    # overrides, homebrew, hidden rolls
verify | repair [--restore]         # integrity check / restore last fully-signed backup
rekey                               # re-sign an intact log with a fresh in-repo key (lost/legacy key)
serve                               # live table at http://localhost:8765
rules spell|monster|item|condition <name>   # print the SRD entry
```

## Characters
```
char roll-stats "Name"                          # 4d6-drop-lowest ×6, logged once — no rerolls
char create --name "Kira Vale" --player "Sam" --class Fighter --species Human --background Soldier \
  --method standard|pointbuy|roll --scores str=15,dex=13,con=14,int=8,wis=12,cha=10 --bonus str+2,con+1 \
  --skills perception,survival --languages Elvish,Dwarvish --equipment A --bg-equipment A \
  [--species-skill insight --species-feat Alert]  (Human) [--species-skill perception] (Elf) \
  [--ancestry red] (Dragonborn / Tiefling legacy) [--size Small] \
  [--fighting-style Defense] [--masteries longsword,javelin] [--expertise stealth,perception] (Rogue) \
  [--mi-cantrips "light,mage hand" --mi-spell shield --mi-list Wizard] (Magic Initiate)
spells set wren --cantrips "fire bolt,light,mage hand" --prepared "magic missile,sleep" [--spellbook six,level-1,...]
spells scribe wren --spell "fireball" --source "spell scroll found in the vault" | spells list wren
spells refund wren --level 1 --source "the spell was countered"   # public: a spent slot comes back (Counterspell, a DM error)
spells refund wren --spell "shield" --source "..."                 # public: a spent free cast (Magic Initiate) comes back
spells support ["spell name"]                                  # automated mechanics, choices and remaining DM rulings; no campaign needed
char levelup kira [--class Rogue] [--hp avg|roll] [--subclass Champion] [--feat "Ability Score Improvement" --asi str+2]
         [--fighting-style Archery] [--expertise a,b]
char masteries kira --masteries longsword,javelin,greatsword   # change Weapon Mastery weapons after a Long Rest
char leave wren "parts ways at the crossroads" | char rejoin wren "back for the finale"   # alive, sheet kept, off the party panel
char bio kira appearance "Scarred, braided red hair, soldier's posture"
char inspire kira "Brilliant plan at the bridge" | char use-inspiration kira
char show kira
char import kira [--from the-sunken-crown]   # carry a character or companion over from the previous chapter: the
                                            # same sheet (items, coins, XP, spells, look), rested; XP up to start_level
```

## Creatures & tokens
```
npc add goblin-warrior --count 3 --at 12,8 [--map crypt] [--hidden] [--side enemy|ally|neutral] [--hp roll] [--name "Snag"]
npc reveal|hide|remove <ids,...> | npc rename <id> --name "..." | npc side <id> --side ally | npc show <id>
npc leave <ids,...> | npc return <id>   # walks out of the scene (off the table, out of fights here); faces stay in the log
npc describe <id> --text "Tall, grey coat, a pistol on one hip"   # what anyone can SEE (info panel); do it whenever you describe them
npc unarmored <id>  |  npc armored <id>   # a creature caught without its stat-block armour (bathing, asleep, stripped): AC 10 + Dex; `armored` restores it
npc alignment <id> --text "Lawful Evil"   # every named NPC gets their own alignment (shown on their info card);
                                          # PCs never do: the player plays their character's outlook
npc lore <id> --text "Resistant to fire; hates mirrors"   # public knowledge the party has earned (knowledge check, clue)
                                                           # → shown on the creature's click-to-inspect panel
encounter plan goblin-warrior:4 bugbear-warrior:1        # XP budget check vs party
encounter spawn goblin-warrior:4 --near 20,10 [--hidden]   # refuses above High budget without --override
place kira 3,4 [--map crypt]          # put a token down (out of combat)
move kira 8,4                         # validated path, speed, difficult terrain, corners, opportunity-attack warnings
move kira --path "4,4 5,4 6,5"        # exact squares
party-move 10,12                      # whole party, exploration only
stand kira                            # costs half Speed
```

## Combat
```
combat start [--surprised goblin-warrior-a,goblin-warrior-b]   # everyone with a token on the current map
combat swap kira,wren        # Alert feat: Initiative Swap with a willing ally, right after initiative (before anyone acts)
combat next                  # end turn → next creature (recharges, conditions, death saves handled)
combat status | combat add <id> | combat remove <id> | combat end
combat reset-turn --reason "..."   # public repair: restore the current creature's action economy (e.g. after voiding a mistaken roll with `ruling`)
combat reset-turn wren --reason "..."   # replay an earlier creature's turn this round (played wrong): the order rewinds to it; undo its results first
attack kira goblin-warrior-a greatsword [--adv "reason"] [--dis "reason"] [--sneak] [--smite 1] [--offhand] [--versatile] [--reaction] [--knockout]
attack goblin-warrior-a kira scimitar           # monster actions come from the stat block
attack adult-red-dragon kira "fire breath"       # save-based actions: the target(s) roll saves
action kira dash|disengage|dodge|help --target wren|hide|search|study|influence|utilize|ready|magic [--bonus --via "Cunning Action"]
action kira grapple --target goblin-a | action kira shove --target goblin-a [--prone] | action goblin-a escape   # Unarmed Strike: Grapple/Shove
cast wren "magic missile" --targets goblin-a,goblin-a,goblin-b [--level 2]
cast wren "burning hands" --targets goblin-a,goblin-b
cast cleric "hold person" --targets bandit --condition paralyzed
cast cleric "cure wounds" --targets kira
cast cleric guidance --targets kira --choice stealth
cast cleric resistance --targets kira --choice fire
cast druid "enhance ability" --level 3 --targets kira,wren --choice strength,intelligence
cast cleric "mass heal" --targets kira,wren --choice 120,80
cast wren "wall of fire" --wall "10,8 21,8" --hot south   # drawn on the map at once; everyone on its squares saves; the hot side burns
#   whoever ends a turn within 10 ft of it (or inside), entering it burns once a turn, it blocks sight, and it goes when Concentration ends.
#   Ring: --ring 12,8 --hot inside|outside. Already cast before the engine drew it: map spell-wall --caster wren --spell "wall of fire" --line "x,y x,y" --hot south
cast wren "detect magic" --ritual | cast wren shield --free "Magic Initiate" | cast wren fireball --scroll <item-id>
feature kira "second wind" | feature bruna rage | feature pal "lay on hands" --amount 5 --target kira | feature kira "action surge"
bardic <who>                  # spend a Bardic Inspiration die
deathsave kira | stabilize wren kira | legendary-resist adult-red-dragon
```

Spell choices, supported families and remaining narrative work: [spell support guide](../docs/spell-support.md).
PC spell attacks and repeat saves create Roll requests in viewer mode. Self spells supply their caster target automatically.
Haste's additional action is used after the ordinary action; its Attack action permits one attack. Expeditious Retreat enables `action <who> dash --bonus --via "Expeditious Retreat"`.

## Checks, saves, damage, conditions
```
check kira athletics --dc 15 [--adv "rope"] [--hidden]      # several: check kira,wren perception --dc 12
contest bandit-captain deception --vs kira --vs-skill insight --passive --hidden   # opposed check (NPC lie vs passive Insight)
contest kira deception --vs guard --vs-skill insight --passive          # PC lie vs NPC; drop --passive if they actively read
ruling --what "The captain's confession stands" --reason "..."            # public DM ruling / correction (override list)
save kira,wren dex --dc 13 --damage "4d6 fire" --half --source "fire trap"
save bandit wis --dc 13 --condition frightened --repeat --source "Frightful Presence"
damage kira 2d6 bludgeoning --source "falling 20 ft"
condition add goblin-a prone --source "shoved" | condition remove goblin-a prone
exhaustion kira +1 --source "forced march"
roll 1d100 --purpose "random encounter table" [--hidden]
request list | request roll <id> | request cancel <id>       # pending player rolls
```
`heal` / `temphp` for party members require `--override "reason"` — healing must come from a spell, potion,
feature, rest, or a paid NPC service.

## Agenda: scheduled events the engine remembers
```
agenda add --at "Day 7 09:00" --text "A gem buyer arrives with scales"          # announced on the table when it falls due
agenda add --in 6d --text "The steward's cart sales" --pay 600+2d40 --to treasury --auto   # paid automatically then
agenda add --at "Day 30" --text "Wages" --pay=-430gp --to treasury --auto      # money out (note the =)
agenda add --at "Day 20" --text "The rival's spies reach town" --secret        # DM only
agenda list | agenda done a3 --note "paid by hand" | agenda cancel a4 --reason "..."
```
Every promised delivery, debt, payday, visit and villain-clock step goes in the agenda the moment it's agreed, so it
can't be forgotten: `time`, `travel` and `rest` announce each one as it falls due (state.md lists the open ones).

## Quicksave / quickload (player's choice only)
```
quicksave [name] [--label "before the duel"]   # a restore point now (a timestamped name if none given)
quicksave name --at-seq 1234                  # a restore point at an earlier event (after event 1234)
quicksave list | quicksave delete <name>
quickload [name]                              # restore exactly: log, notes, views (default: the latest save)
```
After a quickload, everything past the save point never happened: don't mention it or let it shape anything.

## Rest, time, travel
```
rest short --hd kira:2,wren:1 | rest long               # 16-hour spacing, 1 HP minimum, all rules applied
travel over several days credits a Long Rest each night (no extra time); repair a missed one: rest long --ended-at "Day 9, 06:00" --reason "..."
time 2h --reason "searching the library"
travel 24 --pace normal | travel --to 55,30 --pace slow   # region map: terrain & roads, moves the party marker
```

## Items & money
```
item add kira "Longsword" --source "loot: bandit captain"        # source must start with loot/reward/found/starting/crafted/gift/stolen/quest
item add kira "Rope, Hempen" --purchase [--price 1gp]          # deducts coins at SRD price
item add kira "Potion of Healing" --purchase                    # Common magic items are buyable in towns
item add kira "Longsword +1" --source "reward: the Duke"        # rarity capped by party tier unless --override
item add kira "Spell Scroll (Fireball)" --source "loot: ..."
item equip|unequip|attune|unattune|use|light|drop|sell <who> <item-id> [--to <target>] [--qty N]
item use kira dagger-of-venom-1     # Bonus Action: coat the blade BEFORE the attack (it poisons the next hit)
item venom-hit kira dagger-of-venom-1 --to goblin-a --how "..."   # repair: the coat came first but was recorded after the hit
item give kira <item-id> --to wren | item recover-ammo kira Arrows | item card kira <item-id>
item drop kira dagger-1 --qty 1      # lands on the map at the token's square (gold diamond marker, shown to players)
item pickup kira floor-1             # must be in/next to that square; in combat uses the free object interaction
map container crypt 12,7 --name "Iron-bound chest" [--text "..."] [--id chest-1]   # a tile that holds items (clickable)
item stash kira rope-1 --to chest-1 [--qty 2]   # put an item into a container (in/next to it)
item stash kira plate-armor-1 --to bag-of-holding-1 [--qty 4]   # into a carried Bag of Holding (500 lb; no bag in a bag) · item unbag kira <item-id> takes it out
# Loot is decided before anyone searches, and the engine holds you to it:
loot list                                   # loot owed by defeated notable foes + every sealed cache and its contents (DM)
loot suggest [--rarity Rare] [--kind weapon]   # SRD magic items within the party's tier cap
loot body captain-rhosk --items "Longsword +1; 2x Potion of Healing" --coins 30gp   # seal a foe's gear at its body (clears "owed")
loot none captain-rhosk --reason "lost it all in the river"    # or record why there's nothing
loot cache crypt 12,7 --name "Iron strongbox" --items "Ledger=a merchant ledger; Potion of Healing" --coins 140gp [--lock 15] [--id box]
loot open kira box [--unlocked "Thieves' Tools 18 vs DC 15"]   # reveals the contents on the table; then item pickup / coins --from
# Forces: the units a character commands (numbers, kit, pay, attitude) live in the engine, not the notes:
forces add militia --name "Oakhollow militia" --stat commoner --count 12 --where "Oakhollow" --captain "Oswin Hale" --pay "2sp/day"
forces equip militia --from armoury --armor "Chain Shirt" --shield --weapon Spear   # one piece per man out of a container; AC follows the SRD armor table
forces share militia --coins 20gp --from kira --reason "spoils"   # a crown a man or more: attitude one step up (Friendly+ = Advantage on Influence with them)
forces split|enlist|muster|set|list   # split off a detachment; enlist creatures already on the map; muster men onto a map; recount (--reason)
# `combat end` lists loot owed for notable foes (CR 1+, named, custom); `status` and every passage of time nag until decided.
# A DM-run companion's turn start prints its whole kit (slots, features, potions, wand charges, unlit Flame Tongue).
item identify kira <item-id> --how "Identify spell (cast by wren)"   # magic items start UNIDENTIFIED unless bought, starting or --identified
rest short --focus kira:<item-id>     # SRD: focus on one magic item through a Short Rest to learn its properties
item obscure kira <item-id> --how "..." | item refresh kira <item-id>   # DM repair: mark unidentified / re-read an item from the SRD
item unpack kira burglars-pack-1        # opens an SRD equipment pack into its listed contents (Hooded Lantern, Oil, Rations...)
item note kira longsword-1 --alias "Oathkeeper" --text "Her father's sword, the grip wrapped in faded blue cord..."   # flavour only: display name + description on the sheet and item card.
#   ALWAYS do this for notable items: anything with a story, a disguise, a maker, or a look the rules name does not capture
#   (an heirloom blade, a weapon disguised as something else, a guild token, a cursed trinket). Mechanics still use the SRD base item.
coins kira +25gp --source "loot: goblin pouches" | coins kira -5sp --source "spent: ferry"
coins wren +40gp --from kira              # hand money between characters (no loot cap; nothing new enters the game)
xp award --encounter | xp award --amount 200 --reason "negotiated the goblins' surrender" | xp milestone --reason "..."
xp award --overcome boss-id,guard-b --reason "captured / routed"   # stat-block XP for foes overcome without killing them; uncapped (a dragon is worth a dragon). --amount awards (story/quest) stay capped at the High budget unless --override.
xp sync wren                                # a late joiner comes up to the party's XP (new characters join at it automatically)
homebrew add monsters|items|subclasses|species|backgrounds --file thing.json --reason "..."   # public
```

## Maps, visuals, handouts — see dm/visuals.md
```
map gen region|town|dungeon|cave|wilderness|interior|arena [--preset road-ambush] [--biome swamp] [--building tavern]
        [--name "..."] [--id crypt] [--seed 42] [--w 40 --h 30] [--show]
map show <id> | map list | map ascii <id> | map render <id> [--dm]
map set <region> --kv world=on           # the world map of record: always open on the table, travel uses it
map import-grid <region> --out land.txt  # hand-drawn region terrain (codes: O C s p g f F h M K w d L); clears generated towns/roads
map settlement <region> 12,8 --name "Oakhollow" --type hamlet|village|town|city|capital|castle|abbey [--text "known"] [--hidden]
map site <region> 30,14 --name "The Grey Barrow" --type ruins|dungeon|tower|cave|shrine|camp|lair|battlefield|grove|barrow|mine|bridge|inn|mill|stones [--text] [--hidden]
map route <region> road|river --path "12,8 20,10 31,15" [--name "the King's Road"]   # straight runs between waypoints
map discover <region> <id> [--text "what they learn"]   # a hidden town or site appears on the players' map (+ journal)
map region-remove <region> --id <id|road-N|river-N> --reason "burned"
map reveal <id> --room 3 | --rect 0,0,10,10 | --all      map hide <id> --rect ...
map poi <id> x,y --name "Weathered Statue" --text "What they perceive"   # pin a perceived notable object to its tile
map poi <id> x,y --name "..." --id j12   # ...or link an existing journal entry; players click the marker to open it
map poi <id> x,y --name "..." --text "..." --clue   # a story clue: filed under Handouts & clues (default: Places & objects)
map set temple --kv level=interior --kv parent=west-ward   # the hierarchy: region > area (town) > section (quarter) > interior
map set temple --kv anchor=poi-3          # clicking that place on the parent map opens this map, once known
map set cellar --kv known=on              # a place the party already knows: its tab stays up whenever they're anywhere linked to it
journal file j36,j40 --as clue|place     # move journal entries between Handouts & clues and Places & objects
map icons <words>                          # search 4,100+ game-icons for props: `map icons cauldron`, `map icons book pile`
map prop <id> x,y --icon globe --name "Brass globe" [--size small|large] [--color #hex] [--rotate 30] [--blocks]
map prop-move <id> x,y --id prop-2 --reason "shoved aside" | map prop-remove <id> --id prop-2 --reason "smashed"
map poi-move <id> x,y --id poi-2 --reason "dragged aside" | map poi-remove <id> --id poi-2 --reason "carted away"
map set <id> --kv theme=bathhouse --kv walls=brick ...  (repeat --kv for several) | walls=brick | floor=mosaic | wood=herringbone | stone=hex | accent=#8a1c2a   # look per map
map door <id> 12,7 open|close|reveal|break                map feature <id> 5,5 reveal|add|remove
map crop <id> --room 4 --pad 2 --show                     map paint <id> "3,3 5,5-9,5" --char "#"
map set <id> --kv lighting=dark                           map party 40,30   map label <id> 10,10 --name "Old Mill"   map unlabel <id> 10,10
map from-image <asset-id> --w 30 --h 20
asset look kira --hair "long auburn braid" --eyes green --marks "scar across left cheek" --outfit "crimson robes" [--headwear hood] [--clear eyes|all]
asset look kira --like oswin-hale        # keep another creature's face: an NPC who joins the party as a character keeps the look the players know
asset look kira --species Elf --presentation female  # visual identity only; never changes mechanical species or traits
asset look kira --clear-like            # stop preserving another creature's appearance
asset identity kira                    # read-only species, presentation, face/body selection and missing/conflicting facts
asset identity                         # inspect party and current map
asset identity --all --issues-only      # audit every creature, including corpses; does not pin guesses or write events
asset stabilize --all                  # retain each existing creature's first authored visual identity and chosen face
asset stabilize kira --refresh         # intentionally choose again using saved appearance and current visual pins
asset faces kira                       # list compatible local portrait bases for this creature
asset faces kira --choose portraits-human/04  # choose and retain one compatible face explicitly
asset art kira [--crop face] [--out file.svg] | asset art kira:<item-id> | asset art srd:flame-tongue     # write the generated picture to look at
asset portrait kira [--style heraldic] [--clear] | asset icon "dragon" | asset fetch <url> --name "Cave art" --license CC0 --credit "..." [--portrait kira] [--item kira:<item-id>]
asset import path/to/file.png --license "own work" | asset draw drawing.svg --name "Sister Maren" --portrait maren
say "The torch gutters." | say --as "Brother Aldric" "Welcome, travellers." | say --at kira "Kira draws her sword."
#   the live table shows each beat on the map: speech bubbles over the speaker, --at captions by that creature, a story strip
scene "The Sunken Shrine" --desc "Rain hammers the broken roof." [--image <asset>] [--map shrine]
journal add "What the note says" --title "..."   # players' Journal tab (every `show` is added automatically)
journal edit j12 --text "..." [--title "..."]     # correct a handout's wording in place (the revision is announced)
show item kira:<item-id> | show creature <id> | show asset <id> | show text "The letter reads..." --title "Letter" | show srd-item "Bag of Holding" | show clear
fx status | fx preset cinematic|standard|quick|off | fx set speed=1.5 camera=off dice=off tokens=art|icon ...
fx ambient rain|snow|fog|embers|ash|motes|storm|none [--intensity 0.1-1]
fx camera kira|12,7|fit | fx play burst|ring|sparkle|smoke|ping --on <id>|--at x,y [--color fire|#hex] [--radius 20]
fx play beam|bolt|projectile --from <id|x,y> --to <id|x,y> [--color ...] | fx play banner --text "..." | fx play float --on <id> --text "..." | fx play flash|shake
```
