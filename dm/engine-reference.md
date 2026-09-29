# Engine Reference

Everything is `python -m engine <command>`. `-h` after any command shows its options.
Output lines are what happened (also pushed to the live table). `✖ RULE:` = refused, nothing changed.
Refer to creatures by id (`kira`, `goblin-warrior-a`) — ids are shown when they're created and in `state.md`.

## Campaign & session
```
campaign new "The Sunken Crown" --set player_rolls=viewer --set xp_mode=xp --set difficulty=standard --set start_level=1
campaign list | switch <slug> | archive <slug>
set player_rolls=viewer|auto        # viewer: the player clicks Roll for their own d20s; auto: engine rolls immediately
session start | session end
status                              # full DM snapshot (also in campaigns/<slug>/state.md)
log -n 20                           # recent public events (read this after the player clicks Roll)
audit [--hidden]                    # overrides, homebrew, hidden rolls
verify | repair [--restore]         # integrity check / restore last fully-signed backup
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
char levelup kira [--class Rogue] [--hp avg|roll] [--subclass Champion] [--feat "Ability Score Improvement" --asi str+2]
         [--fighting-style Archery] [--expertise a,b]
char bio kira appearance "Scarred, braided red hair, soldier's posture"
char inspire kira "Brilliant plan at the bridge" | char use-inspiration kira
char show kira
```

## Creatures & tokens
```
npc add goblin-warrior --count 3 --at 12,8 [--map crypt] [--hidden] [--side enemy|ally|neutral] [--hp roll] [--name "Snag"]
npc reveal|hide|remove <ids,...> | npc rename <id> --name "..." | npc side <id> --side ally | npc show <id>
npc describe <id> --text "Tall, grey coat, a pistol on one hip"   # what anyone can SEE (info panel); do it whenever you describe them
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
combat next                  # end turn → next creature (recharges, conditions, death saves handled)
combat status | combat add <id> | combat remove <id> | combat end
attack kira goblin-warrior-a greatsword [--adv "reason"] [--dis "reason"] [--sneak] [--smite 1] [--offhand] [--versatile] [--reaction] [--knockout]
attack goblin-warrior-a kira scimitar           # monster actions come from the stat block
attack adult-red-dragon kira "fire breath"       # save-based actions: the target(s) roll saves
action kira dash|disengage|dodge|help --target wren|hide|search|study|influence|utilize|ready|magic [--bonus --via "Cunning Action"]
cast wren "magic missile" --targets goblin-a,goblin-a,goblin-b [--level 2]
cast wren "burning hands" --targets goblin-a,goblin-b
cast cleric "hold person" --targets bandit --condition paralyzed
cast cleric "cure wounds" --targets kira
cast wren "detect magic" --ritual | cast wren shield --free "Magic Initiate" | cast wren fireball --scroll <item-id>
feature kira "second wind" | feature bruna rage | feature pal "lay on hands" --amount 5 --target kira | feature kira "action surge"
bardic <who>                  # spend a Bardic Inspiration die
deathsave kira | stabilize wren kira | legendary-resist adult-red-dragon
```

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

## Rest, time, travel
```
rest short --hd kira:2,wren:1 | rest long               # 16-hour spacing, 1 HP minimum, all rules applied
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
item give kira <item-id> --to wren | item recover-ammo kira Arrows | item card kira <item-id>
item drop kira dagger-1 --qty 1      # lands on the map at the token's square (gold diamond marker, shown to players)
item pickup kira floor-1             # must be in/next to that square; in combat uses the free object interaction
item identify kira <item-id> --how "Identify spell (cast by wren)"   # magic items start UNIDENTIFIED unless bought, starting or --identified
rest short --focus kira:<item-id>     # SRD: focus on one magic item through a Short Rest to learn its properties
item obscure kira <item-id> --how "..." | item refresh kira <item-id>   # DM repair: mark unidentified / re-read an item from the SRD
item unpack kira burglars-pack-1        # opens an SRD equipment pack into its listed contents (Hooded Lantern, Oil, Rations...)
item note kira longsword-1 --alias "Oathkeeper" --text "Her father's sword, the grip wrapped in faded blue cord..."   # flavour only: display name + description on the sheet and item card.
#   ALWAYS do this for notable items: anything with a story, a disguise, a maker, or a look the rules name does not capture
#   (an heirloom blade, a weapon disguised as something else, a guild token, a cursed trinket). Mechanics still use the SRD base item.
coins kira +25gp --source "loot: goblin pouches" | coins kira -5sp --source "spent: ferry"
xp award --encounter | xp award --amount 200 --reason "negotiated the goblins' surrender" | xp milestone --reason "..."
homebrew add monsters|items|subclasses|species|backgrounds --file thing.json --reason "..."   # public
```

## Maps, visuals, handouts — see dm/visuals.md
```
map gen region|town|dungeon|cave|wilderness|interior|arena [--preset road-ambush] [--biome swamp] [--building tavern]
        [--name "..."] [--id crypt] [--seed 42] [--w 40 --h 30] [--show]
map show <id> | map list | map ascii <id> | map render <id> [--dm]
map reveal <id> --room 3 | --rect 0,0,10,10 | --all      map hide <id> --rect ...
map poi <id> x,y --name "Weathered Statue" --text "What they perceive"   # pin a perceived notable object to its tile
map poi <id> x,y --name "..." --id j12   # ...or link an existing journal entry; players click the marker to open it
map poi-move <id> x,y --id poi-2 --reason "dragged aside" | map poi-remove <id> --id poi-2 --reason "carted away"
map door <id> 12,7 open|close|reveal|break                map feature <id> 5,5 reveal|add|remove
map crop <id> --room 4 --pad 2 --show                     map paint <id> "3,3 5,5-9,5" --char "#"
map set <id> --kv lighting=dark                           map party 40,30   map label <id> 10,10 --name "Old Mill"
map from-image <asset-id> --w 30 --h 20
asset portrait kira | asset icon "dragon" | asset fetch <url> --name "Cave art" --license CC0 --credit "..." [--portrait kira]
asset import path/to/file.png --license "own work" | asset draw drawing.svg --name "Sister Maren" --portrait maren
say "The torch gutters." | say --as "Brother Aldric" "Welcome, travellers."
scene "The Sunken Shrine" --desc "Rain hammers the broken roof." [--image <asset>] [--map shrine]
journal add "What the note says" --title "..."   # players' Journal tab (every `show` is added automatically)
show item kira:<item-id> | show creature <id> | show asset <id> | show text "The letter reads..." --title "Letter" | show srd-item "Bag of Holding" | show clear
```
