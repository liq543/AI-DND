# Spell coverage inventory

Generated from the local SRD dataset and `engine/spells.py`; refresh with `python tools/spell_coverage.py`.

339 SRD entries; 57 explicit profiles. Classification counts: mechanical: 34, narrative: 128, partial: 177.

**Mechanical** means the listed profile mechanics are implemented. **Partial** lists an explicit remaining DM responsibility or uses the existing general parser. **Narrative** tracks casting resources/concentration while the DM resolves the description. No label certifies every clause of the spell.

See [the usage guide](spell-support.md) for shared limitations, choices and compatibility. All entries, including parsed and narrative spells, are in [spell-coverage.json](spell-coverage.json).

## Explicit profiles

- **Chill Touch** (level 0, mechanical): Damage plus the specific on-hit rider with the correct turn owner and expiry.
- **Guidance** (level 0, mechanical): Bonus dice on checks using the selected skill.
  Choice category: `skill`.
- **Ray of Frost** (level 0, mechanical): Damage plus the specific on-hit rider with the correct turn owner and expiry.
- **Resistance** (level 0, mechanical): Selected damage reduction once per turn.
  Choice category: `damage`.
- **Shocking Grasp** (level 0, mechanical): Damage plus the specific on-hit rider with the correct turn owner and expiry.
- **Spare the Dying** (level 0, mechanical): Stabilization and level-scaled range.
- **Bane** (level 1, mechanical): Charisma save; attack/save penalty dice and concentration.
- **Bless** (level 1, mechanical): Attack/save bonus dice and concentration.
- **Comprehend Languages** (level 1, partial): Timed literal language comprehension capability.
  DM: Touching written surfaces, reading time and secret messages are adjudicated by the DM.
- **Detect Evil and Good** (level 1, partial): Timed detection capability and concentration lifecycle.
  DM: What is detected, obstruction and auras require DM narration.
- **Detect Magic** (level 1, partial): Timed detection capability and concentration lifecycle.
  DM: What is detected, obstruction and auras require DM narration.
- **Detect Poison and Disease** (level 1, partial): Timed detection capability and concentration lifecycle.
  DM: What is detected, obstruction and auras require DM narration.
- **Expeditious Retreat** (level 1, mechanical): Immediate Dash and bonus-action Dash while concentrating.
- **Faerie Fire** (level 1, partial): Dexterity saves; attack advantage and suppression of Invisible benefits.
  DM: DM lists creatures in the cube and describes outlined objects and emitted light.
- **False Life** (level 1, mechanical): Temporary HP roll and upcasting; temporary HP do not stack.
- **Guiding Bolt** (level 1, mechanical): Damage plus the specific on-hit rider with the correct turn owner and expiry.
- **Heroism** (level 1, mechanical): Frightened immunity and temporary HP at the start of each turn.
- **Hex** (level 1, partial): Extra damage on weapon/spell attack hits; selected ability-check disadvantage and slot-scaled duration.
  Choice category: `ability`.
  DM: Moving the curse to a new target is not automated in this release.
- **Hunter's Mark** (level 1, partial): Extra Force damage on attack hits and concentration duration.
  DM: Retargeting and tracking-check advantage are not automated.
- **Longstrider** (level 1, mechanical): Movement speed bonus and timed expiry.
- **Mage Armor** (level 1, mechanical): Unarmored AC calculation, eight-hour expiry and ending on donning armor.
- **Protection from Evil and Good** (level 1, partial): Specified creature types attack with disadvantage; sourced Charmed/Frightened immunity.
  DM: Possession and saves against unsourced existing effects need DM resolution.
- **Ray of Sickness** (level 1, mechanical): Damage plus the specific on-hit rider with the correct turn owner and expiry.
- **Shield** (level 1, mechanical): AC bonus, Magic Missile protection and next-caster-turn expiry.
- **Shield of Faith** (level 1, mechanical): AC bonus and concentration.
- **Speak with Animals** (level 1, partial): Timed communication capability with the corresponding creatures.
  DM: Creature knowledge, cooperation and plant-terrain changes are narrated.
- **Aid** (level 2, mechanical): Upcast maximum/current HP increase, nonstacking and timed expiry.
- **Barkskin** (level 2, mechanical): Minimum AC and timed expiry.
- **Blindness/Deafness** (level 2, mechanical): Selected condition, Constitution saves and end-of-turn repeat saves.
  Choice category: `blindness`.
- **Blur** (level 2, mechanical): Attacks against target have disadvantage, except Blindsight/Truesight.
- **Darkvision** (level 2, mechanical): Darkvision range used by map reveal and expiry.
- **Enhance Ability** (level 2, mechanical): Advantage on checks using selected ability; upcasting adds targets.
  Choice category: `enhance`.
- **Enlarge/Reduce** (level 2, partial): Strength check/save advantage or disadvantage and weapon/unarmed damage dice.
  Choice category: `size`.
  DM: Size, occupied space, object targets and unwilling-target saves require DM adjudication; creature targets here must be willing.
- **Invisibility** (level 2, mechanical): Invisible condition, concentration, duration and distinct break rules.
- **Lesser Restoration** (level 2, mechanical): Remove one selected eligible condition.
  Choice category: `lesser`.
- **Pass without Trace** (level 2, partial): Selected creatures gain a Stealth bonus only within the caster's aura.
  DM: Tracks and environmental detection are described by the DM.
- **Protection from Poison** (level 2, mechanical): Poisoned removal, poison resistance and poison-condition save advantage.
- **See Invisibility** (level 2, partial): Invisible attack penalties are suppressed for the observer; timed sight capability.
  DM: Ethereal-plane visibility is narrated.
- **Spider Climb** (level 2, partial): Climb Speed equal to Speed and timed climbing capability.
  DM: Vertical positions and ceilings require DM description.
- **Fly** (level 3, partial): Fly Speed, hover capability, concentration and expiry.
  DM: Altitude and falling after expiry require DM resolution; the map is two-dimensional.
- **Haste** (level 3, mechanical): Doubled speed, AC, Dexterity save advantage, restricted additional action and ending lethargy.
- **Protection from Energy** (level 3, mechanical): Selected elemental damage resistance.
  Choice category: `energy`.
- **Slow** (level 3, partial): Speed, AC/save penalties, reaction/action restrictions, spell-failure chance and repeat saves.
  DM: DM lists creatures inside the cube.
- **Speak with Plants** (level 3, partial): Timed communication capability with the corresponding creatures.
  DM: Creature knowledge, cooperation and plant-terrain changes are narrated.
- **Tongues** (level 3, partial): Timed spoken/signed language comprehension and communication capability.
  DM: Dialogue, knowledge and cooperation are narrated.
- **Water Breathing** (level 3, partial): Underwater breathing capability with target limit and duration.
  DM: Underwater environment and suffocation hazards require DM resolution.
- **Water Walk** (level 3, partial): Liquid-surface walking capability with target limit and duration.
  DM: Liquid transitions, heat and terrain are adjudicated by the DM.
- **Death Ward** (level 4, partial): First damage-induced drop to zero becomes one HP; ward is consumed.
  DM: Instant-death effects without damage still require a DM ruling.
- **Freedom of Movement** (level 4, partial): Swim Speed, magical slowdown suppression and immunity to new magical Paralysis/Restraint.
  DM: Terrain costs and escape from existing nonmagical restraints require DM resolution.
- **Greater Invisibility** (level 4, mechanical): Invisible condition, concentration, duration and distinct break rules.
- **Stoneskin** (level 4, mechanical): Physical damage resistances and concentration.
- **Greater Restoration** (level 5, partial): Remove one supported condition or one Exhaustion level.
  Choice category: `greater`.
  DM: Curses, attunement and ability/max-HP reductions without a structured engine source require DM resolution.
- **Heal** (level 6, mechanical): Fixed healing with upcasting and removal of Blinded, Deafened and Poisoned.
- **Mind Blank** (level 8, partial): Psychic immunity and Charmed immunity, timed capability tracking.
  DM: Information gathering, remote observation and mind control are adjudicated by the DM.
- **Foresight** (level 9, mechanical): Advantage on checks, saves, attacks and initiative; attacks against target have disadvantage.
- **Mass Heal** (level 9, mechanical): Allocated healing pool and condition removal.
  Choice category: `allocation`.
- **Power Word Heal** (level 9, mechanical): Full healing and condition removal; optional reaction to stand.
  Choice category: `stand`.
