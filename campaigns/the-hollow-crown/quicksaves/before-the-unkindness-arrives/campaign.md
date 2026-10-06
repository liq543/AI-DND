# The Hollow Crown

Created: 2026-10-02  ·  Ruleset: D&D 5.2 SRD (2024)  ·  Status: in play (chapter 2 of **The Jackdaw Saga**)
Previous chapter: `campaigns/the-meridian-job/` (The Meridian Job). The saga's history lives in `chronicle.md`.

## Pitch
Two years after they robbed the unrobbable and killed their buyer, Kit's crew has gone to ground on the far side of the
world, in a forest kingdom tearing itself apart. The old king is three years dead, the Antler Crown has vanished, and the
**Crownless War** has every faction in the Hollowmark at every other's throat. Under a grey hill in the Marchwood the crew has
built themselves a palace no army can find, powered by a god they stole. Now they start from nothing (no name, no army, no
allies) and climb. By the end of this chapter, Kit wants a crown. Any crown. Preferably the real one.

## The shape of the chapter (player-agreed, 2026-10-02)
- **Land:** the Hollowmark: a mostly wooded kingdom of towns of every size, from hamlets to a royal capital. There's lots of
  travel, and no more water. The world map `hollowmark` is the **source of truth** and is always open on the table.
- **Three acts, three regions:**
  - **Act I, the Marchwood:** the lair, the village, the frontier.
  - **Act II, the Elderwild:** the old forest, the rebels, ruins, a dragon.
  - **Act III, the Crownvale and Kingsholt:** the capital, the court, the coup.
- **The war:** three-plus factions fight a civil war (think Skyrim). Kit climbs by seizing one, or by building his own from
  the grass roots. Intrigue, diplomacy and open war grow with his power. **We start at square one.**
- **The lair:** the starting point. It's the crew's hidden, lavish base near a village, bought and built with the
  Emissary's gems. **The Ysmeran Eye is its power source.** Asche found a god's soul in the Eye and turned its gaze inside
  out into a veil (the Stillness): no enemy can see the lair or find a way in. Only an incredibly powerful foe could
  recognise it, let alone try to break it. The Eye is in play and out of it at once. The player approved the design (the Rookery
  under the Grey Barrow, and the Stillness's rules) on 2026-10-02.
- **Abundance:** the crew is filthy rich. The lair is lavish, and there are crowns to spare.
- **Nib** is sixteen. He's mostly in the background for now. He'll grow into a man and into a place in the guild, and may one
  day be given something demonic. Nothing up front.
- **Retcon:** the statue called "The Thief" in the Meridian was **never Kit's mother**. That plotline is gone. Kit's mother
  is long dead and nothing to anyone; he still wears her magpie-feather pin. Kit enjoys that the Meridian's victims are
  still stone. His only regret is not smashing a few and keeping them as pet rocks.
- **Old threads:** the DM's choice, to surprise the player.
- **Length:** level 6 to 10 over roughly 8 to 12 sessions.
- **Tone:** evil, all the way up. The crew is evil and motivated by evil, and fiercely loyal to each other (to whoever
  Kit is loyal to).
- **Time skip:** two years, with lots happening offscreen (see `log/summary.md` → The Lost Years).

## The guild
- **The Unkindness** (Ottilie's name, adopted by Kit on Day 3 at the parley with Mother Gallows). Its first vassals:
  the Hanged Men.

## Setting
- **The Hollowmark:** an old forest kingdom of oak, beech, yew and pine, cut by royal roads, with farmland in the great
  clearings and castles on the crags. Its kings ruled by the **Thornpact**, the old bargain between the first king and the
  wood, worn as the **Antler Crown**. Its faith is the **Dawn** (sun, hearth and harvest; abbeys and village chapels), with
  older forest rites in the deep wood. A foreign faith is spreading fast: the **Watchful Church of the Unblinking**.
- **Calendar:** chapter time starts on Day 1, in early spring of the third year of the Crownless War. Two years have passed
  since the night on the Mole.
- **Money:** Hollowmark crowns (gp), with shillings and pennies (sp, cp). The Charter League's notes of credit change hands
  in the towns.

## Party
- **Player character:** Kit Corvell, "the Jackdaw" (Rogue 6, Thief).
- **DM-run crew (full characters):** Brakka Holloway (Fighter 6, Champion), Corvin Asche (Wizard 6, Evoker; forger,
  necromancer-in-training, the lair's engineer), Ottilie Marsh (Bard 6, College of Lore; the convincer). They defer the big
  decisions to Kit, give at most one line of objection, and never sabotage.
- **Companion NPC:** Nib (16), Brakka's nephew.
- **Settings:** start_level 6, XP advancement, `player_rolls=auto` (the engine rolls everything, logged and shown),
  standard difficulty. Death is possible and always telegraphed.

## House Rules
- SRD 5.2 as enforced by the engine. Beta engine bugs are fixed mid-play (AGENTS.md §1.8).
- DM-run crew never become a loophole for extra loot or healing.
- Quicksave and quickload are the player's tools.
- **Travel is narrated** (player's choice, Day 2): no forced-march saves on ordinary journeys (`set forced_march=narrated`). The DM summarises the road, keeps the clock honest and stops for encounters and arrivals. Travel Exhaustion only on a deliberate, punishing push (`travel --push`), always warned first. Applies to everyone, enemies included.
- **The Unkindness's treasury** (player's rule, Day 4): every member's money goes into the vault (`treasury`, the great
  strongbox in the Counting Room, `coins treasury <amt> --from <who>`); each carries 100 crowns. No more shares.
- **The Stillness** (the lair's ward) has written rules: `secrets.md` → The Stillness. They are shared with the player as a
  journal handout once the lair is final.

## The saga (player-stated goals; carry into every chapter)
See `campaigns/the-meridian-job/campaign.md` → The saga. In short:
- The crew rises to level 20 as the warlords of the realm's most powerful evil guild.
- Their lair grows into an *Overlord*-style fortress filled with the spoils of every chapter.
- They command evil forces in a real military campaign, like *Pathfinder: Wrath of the Righteous* but evil.
- At the end they kill an incredibly powerful being and take godlike power.
- Kit is a narcissistic sociopath bent on becoming an almighty god-emperor.

## Household routines (player's orders)
- **Quist's daily report** (Day 13): every morning at breakfast Quist reports the treasury, money in and out, and all open items. Bastian reports on the prisoners when asked.
