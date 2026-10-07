# Spell support: engine implementation B

Implemented on 2026-10-07 at the owner's request: prioritize many kinds of spellcasting and preserve room for D&D imagination. The engine now has **57 explicit SRD 5.2 spell profiles**, in addition to its existing parsed damage, healing, attack and saving-throw spells. This is a substantial expansion, not complete automation of every SRD spell.

## Playing with the expanded spells

All examples use generic creatures and require the usual known/prepared spells, resources, components, action economy and range. Use the CLI's actual creature ids.

```text
python -m engine spells support
python -m engine spells support "guidance"
python -m engine cast cleric bless --targets kira,wren,bruna
python -m engine cast cleric guidance --targets kira --choice stealth
python -m engine cast cleric resistance --targets kira --choice fire
python -m engine cast druid "enhance ability" --level 3 --targets kira,wren --choice strength,intelligence
python -m engine cast cleric "protection from energy" --targets kira --choice cold
python -m engine cast wizard "blindness deafness" --targets bandit --choice deafened
python -m engine cast wizard "enlarge reduce" --targets kira --choice enlarge
python -m engine cast cleric "lesser restoration" --targets kira --choice poisoned
python -m engine cast cleric "greater restoration" --targets kira --choice exhaustion
python -m engine cast cleric "mass heal" --targets kira,wren --choice 120,80
python -m engine cast cleric "power word heal" --targets kira --choice stand
python -m engine cast warlock hex --targets bandit --choice dexterity
python -m engine cast wizard "see invisibility"
python -m engine cast wizard "expeditious retreat"
python -m engine action wizard dash --bonus --via "Expeditious Retreat"
```

`spells support [spell]` is read-only and works without loading a campaign. It describes what is automated and what needs a ruling. `--choice` supplies a spell-specific decision rather than arbitrary mechanical values. Choices are validated before the spell spends resources. Most choices select one option; Enhance Ability accepts one ability per target, and Mass Heal accepts healing allocations in target order totalling at most 700. Blindness/Deafness defaults to Blinded. Power Word Heal's `stand` choice is optional and spends the recipient's Reaction when needed.

Self spells implicitly target their caster. Area spells use the DM's explicit creature list; supported save profiles can use `--targets none` for an empty area. The engine checks listed targets, not the placement or entire contents of a cube or sphere.

In viewer roll mode, PC spell attacks now create Roll requests, including individual beams. Casting spends the slot/action once; fulfilling a request rolls the attack, damage and rider without charging the casting again. PC saving throws and repeat saves also use Roll requests. Current buffs are read when the roll resolves. Requests retain the existing request lifecycle; comprehensive cancellation, stale-turn validation and multi-step orchestration from proposal F remain separate work.

## Spell families

- **Roll bonuses and penalties:** Bless, Bane, Guidance, Enhance Ability, Foresight, Hex. Bless/Bane affect attack rolls and saving throws, including death saves. Guidance's chosen skill gets its bonus on each applicable check during its duration. Hex penalizes checks using the chosen ability, not saves.
- **Defense:** Mage Armor, Shield, Shield of Faith, Barkskin, Blur, Stoneskin, Protection from Energy, Protection from Poison, Protection from Evil and Good, Death Ward, Mind Blank, Heroism. Shield also blocks Magic Missile; timed defenses work on NPCs as well as PCs. Heroism refreshes temporary HP at the recipient's turn start. Condition immunity suppresses an existing condition while immunity lasts; it does not erase that condition's underlying source.
- **Movement and action economy:** Longstrider, Fly, Spider Climb, Haste, Slow, Freedom of Movement, Expeditious Retreat. Haste grants a restricted extra action and one attack with its extra Attack action. Ending Haste causes lethargy until the recipient's next turn ends. Slow changes speed, AC and Dexterity saves; blocks Reactions; allows an Action or Bonus Action; limits all attacks to one per turn; and can make a somatic spell fail while consuming its resources.
- **Healing and recovery:** Aid, False Life, Heal, Power Word Heal, Mass Heal, Lesser Restoration, Greater Restoration, Spare the Dying. Aid changes maximum/current HP and expires; the engine clamps current HP to the resulting maximum when an effect ends. Healing follows the SRD 5.2 spell clauses rather than a blanket Undead/Construct exclusion. Greater Restoration currently handles Charmed, Petrified or one Exhaustion level.
- **Visibility, control and stealth:** Invisibility, Greater Invisibility, Blindness/Deafness, Faerie Fire, See Invisibility, Darkvision, Pass without Trace. Normal Invisibility breaks independently for each recipient; Greater Invisibility persists. Darkvision supplies 150-foot darkvision to map reveal. Pass without Trace's selected creatures gain the Stealth bonus while within 30 feet of their caster on the same map.
- **Attack riders:** Ray of Frost slows movement; Ray of Sickness inflicts Poisoned on a hit; Chill Touch blocks healing; Shocking Grasp prevents Opportunity Attacks; Guiding Bolt benefits the next attack against its recipient. Each uses its own SRD turn owner and expiry. Hex and Hunter's Mark add damage to both weapon and spell attack hits; higher slots extend their duration.
- **Exploration and communication:** Water Breathing, Water Walk, Tongues, Comprehend Languages, Speak with Animals, Speak with Plants, Detect Magic, Detect Evil and Good, Detect Poison and Disease. The engine tracks the capability, its source and lifetime. The DM supplies discoveries, conversations, environmental changes and creative interpretations.

The complete inventory and per-spell limits are generated in [spell-coverage.md](spell-coverage.md). [spell-coverage.json](spell-coverage.json) contains the same classifications for every spell in the local SRD dataset. Regenerate both after changing profiles: `python tools/spell_coverage.py`.

## Boundaries for imagination and rules

The DM still decides what creatures know, what magic detects, how terrain reacts, how an unusual creative use works, and which creatures lie within an area. The engine enforces the implemented costs and mechanics; casting reports remaining responsibilities rather than silently claiming to handle them.

The map remains two-dimensional. Flight, climbing and liquid movement supply capabilities/speeds, but altitude, falls, ceilings, underwater hazards and liquid transitions need adjudication. Enlarge/Reduce handles willing creature checks/saves and weapon/Unarmed Strike damage; object targets, unwilling saves, actual size and occupied cells remain manual. Willing-only handlers refuse hostile recipients; friendliness is a proxy, not a consent model.

Hex/Hunter's Mark retargeting and tracking checks are not automated. Death Ward handles damage-induced drops to zero; instant-death effects without damage remain manual. Freedom of Movement suppresses magical speed reduction and magical Paralysis/Restraint and supplies Swim Speed; difficult-terrain pricing and automatic escape from existing nonmagical restraints remain manual. Protection from Evil and Good uses structured source creature types; possession and unsourced effects remain manual. Greater Restoration cannot yet select arbitrary structured curses, item attunement, ability reductions or HP reductions.

The existing parser continues to resolve supported direct attacks, saves, damage and healing for other spells. These entries are marked partial because additional clauses, ongoing areas, summons, transformations, special targets and recurring damage may need a ruling. None of the support labels certify complete SRD coverage. Casting-time resolution, the existing general component checks and broader request lifecycle were not redesigned in this package.

## Engine design and compatibility

`engine/spells.py` contains explicit profiles, choice/target validation, effect resolution and attack riders. `engine/effects.py` contains shared effect lifecycle and contributions. An effect records its source caster, spell, potency, concentration instance, duration or named turn boundary, and mechanical fields. `core.py`, `mechanics.py` and the CLI use these contributions for rolls, AC, maximum HP, speed, conditions, defenses, turn boundaries and elapsed time. The PC projection and generated sheet expose active effect names/lifetimes; this package does not redesign the viewer's effect UI.

Different spells combine. Multiple simultaneous copies of the same spell contribute only the strongest version; other sources remain recorded and can resume if the strongest ends. Refreshing a same-source effect replaces it. Concentration ending removes linked effects from every recipient. Turn-relative riders expire on the named creature's turn rather than whichever target happens to be affected. Combat rounds participate in duration checks, and ending combat settles elapsed time without counting rounds twice.

All changes use existing `Game` events. No new event schema or log migration is required. Existing histories replay unchanged and existing rolled outcomes are not rewritten. Older untimed effects do not gain an invented historical expiration; recasting replaces an older effect with the new timed representation. Previously cast narrative-only spells do not retroactively acquire new mechanics. The compatibility test verifies recasting old Mage Armor without deleting unrelated conditions.

## Validation and work record

The implementation adds 40 focused tests in `tests/test_spell_effects.py`. A casting smoke test exercises all 57 profiles, while interaction tests check actual roll expressions/results, saves, concentration, expiry, nonstacking, defenses, Haste/Slow, riders, healing, immunity, old effects and event replay. A disposable CLI test verifies `--choice`, signed persistence, a requested player roll and generated-sheet output. Deterministic die faces exist only in tests; production retains secure engine rolls.

The full regression suite is run with `python -m unittest discover -s tests`. Its final result is recorded in the implementation section of [the engine review](reviews/2026-10-07-engine-review.md). Temporary-directory tests need ordinary Windows temporary-directory permissions in this environment. No production campaign is used by these tests.
