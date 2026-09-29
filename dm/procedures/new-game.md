# Procedure: New Game (Session Zero)

## 0. Clean slate
- If this chat already contains play from another campaign: stop and ask the player to open a **new chat** and
  say "new game" there. Do not read any existing campaign folder.
- Read `dm/engine-reference.md`, `dm/dm-guide.md`, and `dm/visuals.md` (once per chat).

## 1. Session-zero questions (one message, with defaults)
1. **Setting & vibe** — offer 3 short, distinct pitches or invite their own.
2. **Tone** — heroic / gritty / horror / lighthearted; combat vs roleplay vs exploration balance.
3. **Difficulty** — forgiving / standard / deadly (does death stick?).
4. **Party** — how many PCs; a DM-run companion?; starting level (default 1).
5. **Ability scores** — standard array (default), point buy, or rolled (engine rolls, logged, no rerolls).
6. **Dice** — click **Roll** in the live table (default, `player_rolls=viewer`) or let the engine auto-roll
   (`player_rolls=auto`). Either way every roll is real and shown.
7. **XP or milestones** (default XP). Lines & veils.

## 2. Create the campaign
```
python -m engine campaign new "<Title>" --set player_rolls=viewer --set xp_mode=xp --set difficulty=standard --set start_level=1
```
Start the live table (see AGENTS.md §2) and give the player the link. Fill in `campaign.md` (pitch, setting,
tone, lines/veils, house rules). House rules can't contradict the engine; if you want one that does, it's
homebrew — register it publicly.

## 3. Characters
Follow `character-creation.md` for each PC. Each PC's portrait is drawn from their appearance bio and `asset look` (show the player and adjust), or draw one.

## 4. World prep (silently — never shown)
- `map gen region --name "..." --show`, pick the start settlement → `map party x,y`.
- Starting location map: `map gen town|interior|wilderness ... --show`.
- `secrets.md`: the truth behind the hook, the opposition (wants, 4–6 step clock), 2–3 secrets with 3 clues each,
  2–3 set-piece encounters (check them with `encounter plan`).
- `locations.md` (starting place + 2 nearby, keyed to map ids), `npcs.md` (3–5 NPCs with a want and a quirk;
  note the SRD stat block each would use), `quests.md` (the hook + 2 rumours).
- Tie each PC's backstory into the hook or a secret.

## 5. The player briefing (mandatory, BEFORE the first scene)
Never open cold. Before any dice, give the player a **"Previously, in your life…" briefing** of everything
their character already knows. Write it as player-facing prose with short headed sections:
1. **Who you are:** name, pronouns, look, age, how others see them, their reputation, their skills and
   signature moves (in plain words, tied to their sheet), personality, and a quirk or two.
2. **Your past:** the backstory beats that matter *now*, including the wound or want that drives them.
3. **The world as you know it:** the city or region, who holds power, the factions they've heard of, and
   the local rumours. Only what the character would know.
4. **The people:** every other PC or companion, with how well this character knows them (stranger, by
   reputation, old friend) and what they know or think of each. If they are strangers, say so explicitly.
5. **Why you're here tonight:** what the character came to do, what they want from this scene, and what
   they're carrying.
6. **What you can do:** a two-line reminder of the character's best tools for this kind of situation.
Then ask for pronouns/tweaks ("Anything you'd change about <character> before we start?") and wait for a reply.

## 6. Begin
```
python -m engine session start
python -m engine place <pc> x,y      (for each PC, on the starting map)
python -m engine scene "<Opening scene title>" --desc "<one line>"
```
Create `log/session-001.md` entries as you go. Open with a **short, calm establishing beat first**: a
paragraph or two of the place, the people, what the character sees and can do. Let the player act at
least once before trouble starts. Then bring the scene **in motion** with something that demands a
response. End with *"What do you do?"* Never start combat in the very first message.
