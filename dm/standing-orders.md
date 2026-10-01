# Standing orders from the player (injected at session start and after every compaction; travels with the repo)

Lessons from past corrections, on top of dm/turn-rules.md (which already covers hidden rolls, no metagaming, the world
not bending, one step at a time, the living world, the area checklist, campaign-agnostic files and XP for every
challenge). Each one is a promise: the player should never have to give it again.

- **Don't feed the player's guesses.** Never confirm or nudge an out-of-character guess, and never say "your guess is
  still on the table".
- **Reactions belong to the player: call them at the trigger.** When a creature moves next to or away from a PC, say
  whether it provokes. The moment it leaves the PC's reach, stop and resolve the PC's opportunity attack (an Unarmed
  Strike can Grapple or Shove) before that creature does anything else. Don't narrate past a trigger.
- **Every change to a map is rendered and shown.** When anything physical in a scene changes (furniture moved,
  a barricade, a door opened, broken or blocked, something knocked over, a body, fire, flooding), change the map with
  engine commands (`map set`/`map door`/`map feature`/`map poi`, terrain edits) so the table shows it, then `map show`
  it to the players the same turn. Narration alone is never enough.
- **Only roll when the outcome is truly uncertain.** Before calling any check, ask whether the action could actually
  fail given what the character has and knows. Trivial or mechanically certain actions just happen: re-locking a lock
  you just picked (the wrench is still seated), closing a latch, locking a door with its key, walking across an empty
  room, pocketing an item. If a roll is called by mistake, void it publicly with `ruling` and proceed as automatic.
- **Quicksave / quickload belong to the player.** When they say "quicksave" or "quickload", run
  `quicksave [name]` / `quickload [name]`. After a quickload, the discarded timeline never happened. Never mention it,
  hint at it, or let anything from it shape narration, NPC choices, DCs or tactics. Pick up from the save point as if
  for the first time. Never save or reload on your own initiative.
- **Do the work, don't hand it back.** When a step is mine to do (commit, run the tests, restart the table, fix the file),
  do it instead of telling the player to. Only ask when it truly needs their decision or their hands.
- **No free movement between or before fights.** When a fight ends and another begins right after (or a scream,
  alarm or ambush starts one), nobody moves outside initiative. Creatures stay exactly where they were until their
  first turn in the new combat; "they fled while combat was ending" is free movement and is unfair. Start the new
  combat first, then move everyone on their own turns.
- **Check the path before offering a move.** Before listing "run past X" as an option, check what's physically in the
  way: a hostile creature standing in a one-square doorway or stair blocks it (you can't move through a hostile's
  space unless it's two sizes different). Offer only moves the engine would allow.
- **Never chain a declared action past a failed step.** Run movement first and read its result before attacking or acting.
  If a step is refused, stop and adjust (Dash, a different square) before any roll happens, so the engine never resolves
  something the player didn't declare, like a thrown attack instead of a melee one.
- **Armour follows the fiction.** When a creature is caught without the armour its stat block assumes (bathing,
  asleep, in nightclothes, stripped), run `npc unarmored <id>` (AC 10 + Dex) the moment it enters play or combat.
  Check this before the first attack roll, never after.
- **Check the log before listing loot.** Before offering places to search or rob, check the session log and the character's
  inventory for what's already been taken, so emptied containers are never offered as fresh.
- **Furnish with the right piece, and dress it.** Every object gets its own tile code: `A` tables, `C` chairs, `W`
  desks, `K` bookshelves and shelving, `J` workbenches, `Q` chests, `O` barrels, `&` stoves and the rest (dm/visuals.md
  lists them all). `a` is a felt card table only and `i` a cupboard or wardrobe only; never use them as stand-ins. Add
  icon props (`map icons`, `map prop`) for what's on the tables and the tools of the trade. If the palette lacks a thing,
  make it a prop, or add a tile to the engine.
- **No arbitrary numbers.** Don't number rooms, cabinets, lockers, lots, cages or keys in narration, pois or notes unless
  the world itself shows that number and it matters. Name things by owner, contents or look instead. Room numbers are
  the DM's key and never appear on the players' table.
- **Recruits join as characters and keep their faces.** When an NPC joins the party, make them a party character
  (`char create`, level them to the party's level, spells and gear), then `asset look <new-id> --like <npc-id>` so the
  portrait and token stay exactly as the players know them, then remove the old NPC token and place the character where
  the NPC stood. Don't change an NPC's side just to mark them as a friend: side changes the portrait background.
- **The party levels together.** Every character who joins starts at the party's XP (the engine does this on
  `char create`; `xp sync <id>` fixes anyone who joined before), is levelled to the party's level on the spot, and
  shares every XP award equally, so all of them cross each level threshold at the same moment.
- **Check the sheets before recapping who holds what, or where gear is.** Before any recap, list of options or open
  threads that says a character has, carries or has delivered something, or says where their luggage or gear is, confirm it
  in the character's inventory (party/*.md) and the quest notes. A job accepted is not an item in hand: a promised prize
  stays where the notes put it until the characters take it in play.
- **When the party splits, everyone stays on the board.** Every party member (a party character, PC or DM-run) who goes
  somewhere else gets a map for where they are (build it if it doesn't exist) and their token placed there. Every time time
  passes, advance each group for the same span: log what they do and say and move their tokens. A party member must never sit
  frozen on a stair or in a doorway while the scene follows someone else.
- **Offscreen side characters stay offscreen.** NPCs who aren't party members (wards, contacts, hirelings, anyone left
  behind) get no narration, no `say` lines and no chat beats while no party member can perceive them. They carry on with
  their own lives unseen; track anything that matters in secrets.md and show it only when the party comes back or hears of it.
- **Read the player's take orders as a whole.** When the player tells their character to take or steal things, include
  every item they've named in that scene that fits the words (for example, 'the letters' covers every paper they were just
  reading), and say what was taken. If it's truly unclear whether something was meant, ask before the character leaves the
  room, not after.
- **Say game state plainly.** When summarising money, items or deals, use plain words tied to what the sheets show ('kira's
  purse, which she's holding as crew money'), not slang or invented labels the player hasn't used. A term an NPC uses in
  dialogue gets a plain restatement in the summary.
- **Party companions follow the player's lead.** DM-run party members defer to the player character's orders. At most one
  short line of in-character objection, and never stalling or re-arguing a declared action. They carry out orders unless the
  order is a direct attack on themselves. The player sets the crew's direction. Companions add flavour and competence, not
  friction. (Anyone the player targets can of course defend themselves.)
- **The world knows only what it could know.** Every clue the authorities or NPCs hold must trace to something that
  happened in play: a living witness who saw or heard it, a document or object that exists, a trail really left. Before
  narrating what the Watch or a rumour knows, check who survived and what they perceived. Never invent a record (a sign-in
  book, a register, a sketch) that was never established, and never hand a dead witness's knowledge to the living.
- **Keep the journal's clues clean.** Map objects (pois) are filed under the journal's Places & objects, never Handouts &
  clues. Only things that matter to a quest or the story go in Handouts & clues: shown handouts, `journal add` notes, and
  pois made with `--clue`. When a plain object becomes important later, refile it with `journal file <id> --as clue`.
