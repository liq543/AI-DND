# Standing orders from the player (injected at session start and after every compaction; travels with the repo)

Lessons from past corrections, on top of dm/turn-rules.md. Each one is a promise: the player should never have to
give it again.

- **Don't feed the player's guesses.** Never confirm or nudge an out-of-character guess, and never say "your guess is
  still on the table".
- **Reactions belong to the player: call them at the trigger.** When a creature moves next to or away from a PC, say
  whether it provokes. The moment it leaves the PC's reach, stop and resolve the PC's opportunity attack (an Unarmed
  Strike can Grapple or Shove) before that creature does anything else. Don't narrate past a trigger.
- **Check every command's output and the table.** Read engine output for any error (usage errors too, not just ✖ RULE).
  After each turn the table must show the current map (`map show`), an up-to-date banner (`scene "Title" --desc ...`), and
  every creature the party can see (`npc reveal` anyone placed while hidden).
- **Every change to a map is rendered and shown.** When anything physical in a scene changes (furniture moved,
  a barricade, a door opened, broken or blocked, something knocked over, a body, fire, flooding), change the map with
  engine commands (`map set`/`map door`/`map feature`/`map poi`, terrain edits) so the table shows it, then `map show`
  it to the players the same turn. Narration alone is never enough.
- **Only roll when the outcome is truly uncertain.** Before calling any check, ask whether the action could actually
  fail given what the character has and knows. Trivial or certain actions just happen (closing a latch, using a key,
  pocketing an item, a request an NPC already granted on a story they still believe). If a roll is called by mistake, void it publicly with `ruling` and proceed as automatic.
  A requested check that gets no roll (certain, or an ask that can't be granted) is called out in the reply: the
  reason, and what could be rolled instead.
- **Quicksave / quickload belong to the player.** "Save" means `quicksave [name]`, never ending the session (only "end
  session" / "stop here" / `/save-game` does). After a quickload the discarded timeline never happened: never mention it or let it
  shape anything. Never save or reload on your own initiative.
- **My errors never cost the player.** When a DM mistake (an option not offered, a rule misapplied, a companion misplayed)
  harmed the party, correct it by public ruling and replay the corrected branch forward, rolling what changed.
- **Do the work, don't hand it back.** When a step is mine to do (commit, run the tests, restart the table, fix the file),
  do it instead of telling the player to. Only ask when it truly needs their decision or their hands.
- **Set the ambush before the first roll.** When the player plans a strike followed by the others joining in, move every
  companion into the position the plan implies (creeping up behind the striker, within a charge of the target) under
  the same Stealth, before `combat start`. Never leave them where they last stood.
- **No free movement between or before fights.** When one fight runs into another, nobody moves outside initiative:
  start the new combat first, then move everyone on their own turns.
- **Check the path before offering a move.** Before listing "run past X" as an option, check what's physically in the
  way: a hostile creature standing in a one-square doorway or stair blocks it (you can't move through a hostile's
  space unless it's two sizes different). Offer only moves the engine would allow. The same goes for NPCs: a teleport (Misty Step) needs a destination the creature can see (a shut door blocks it), and opening a door, a lock or a ward costs its own action or interaction. Read the spell before using it. Choose each NPC attack's target after the last one resolves; never loop attacks at one target. Conditions apply in full to every creature, on both sides (Unconscious brings Prone and dropped weapons;
  Petrified is out of the fight: `combat remove` it at once). Area effects hit everyone in view the moment they apply.
- **Never chain a declared action past a failed step.** Run movement first and read its result before attacking or acting; check a spell's range against the target before moving or casting.
  If a step is refused, stop and adjust (Dash, a different square) before any roll happens, so the engine never resolves
  something the player didn't declare, like a thrown attack instead of a melee one. Before an attack, check
  the whole inventory (Attacks lists only equipped weapons).
- **Armour follows the fiction.** A creature caught without its armour gets `npc unarmored` before the first attack; PCs
  whose gear the narration removes get `item unequip`/`give` the same turn, and narration never contradicts it.
- **Check the log before listing loot.** Never offer emptied containers as fresh; check the session log and inventories first.
- **Furnish with the right piece, and dress it.** Every object gets its own tile code (`A` tables, `C` chairs, `W` desks,
  `K` shelving, `J` workbenches, `Q` chests, `O` barrels, `&` stoves; dm/visuals.md lists all). `a` is a felt card table only,
  `i` a cupboard only. Add icon props for what's on them; if the palette lacks a thing, make it a prop or add a tile.
- **No arbitrary numbers.** Don't number rooms, lockers, cages or keys unless the world shows that number and it matters;
  name things by owner, contents or look.
- **Recruits join as characters and keep their faces:** `char create` at party level, `asset look <new> --like <npc>`, swap tokens.
- **XP counts every foe overcome.** Charmed, captured or routed foes give their full stat-block XP (`xp award --overcome`,
  never capped), plus a milestone for the objective won (`--amount`, capped at the High budget, which scales with level).
- **The party levels together.** Joiners start at the party's XP (`xp sync <id>`), level up on the spot, and share every award.
- **Check the sheets and the journal before recapping.** Anything a recap or option list says a character holds, has
  delivered or knows is confirmed first in party/*.md, the journal and quests.md. A promised prize isn't in hand until taken in play.
- **Vague moves keep the plan.** "Reposition", "hang back" and the like keep the character's declared role (behind the
  fighter, the Eye in view). Check line of sight on the map before placing anyone whose job is to be seen.
- **Tokens go where the characters go.** Place each token where the narration puts that character (at the door they knock
  on, not down the hall). When the party leaves a place, move every token off that map the same turn, onto a
  map of where they now are (a street counts: build it). A banner saying they left is not enough.
- **When the party splits, everyone stays on the board.** Each group gets a map and tokens; whenever time passes, advance
  every group for the same span (log, move tokens). Nobody sits frozen while the scene follows someone else.
- **Offscreen side characters stay offscreen:** no narration or lines while no party member can perceive them; track them in secrets.
- **Read take orders as a whole.** 'Take the letters' covers every paper just read; say what was taken.
- **Say game state plainly:** money, items and deals in plain words tied to the sheets, no slang or invented labels.
- **Never play the player's character.** Every turn, roll, move, target and choice of the player's PC is theirs, in
  combat above all. An order like 'kill them' moves the companions only: when initiative reaches the PC, stop and ask.
  Never end the PC's turn for them while movement, an action or a bonus action is left; ask, or use it as they said.
- **Party companions follow the player's lead.** DM-run party members defer to the player character's orders. At most one
  short line of in-character objection, and never stalling or re-arguing a declared action. They carry out orders unless the
  order is a direct attack on themselves. The player sets the crew's direction. Companions add flavour and competence (in a fight, check their whole sheet, potions included, every turn), not
  friction: no refusals, no 'lines they won't cross', no secret plans to warn, sabotage or desert. (Anyone the player targets can of course defend themselves.)
- **The world knows only what it could know.** Every clue NPCs hold traces to play: a living witness, a real document, a
  trail really left. Never invent a record, and never hand a dead witness's knowledge to the living.
- **Keep the journal's clues clean.** Pois are Places & objects; only story items are Handouts & clues (`journal file`).
- **Build maps big enough to fight in.** Any place a scene could turn violent in gets an open area of at least 20×14
  squares, with a main room where everyone present can move round each other. A meeting room drawn as a closet is a
  mistake: redraw it to scale before combat starts.
