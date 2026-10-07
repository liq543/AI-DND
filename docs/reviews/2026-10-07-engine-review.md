# Game engine review and proposed improvements

Date: 2026-10-07. Status: review complete; owner selected B, implemented as a broad spell-support expansion. Other packages remain proposals.

## Recommendation

The highest-impact work is **A: reliable commits** and **B: complete spell effects**. A protects the engine's promise that a command either happens completely or does not happen. B fixes everyday gameplay where a legal spell can spend resources without delivering its benefit, or keep delivering a benefit after it should end.

The owner selected B and requested breadth of spellcasting with room for imaginative DM rulings. Its implementation is documented below and in [the spell support guide](../spell-support.md). Other packages can be scoped separately; their descriptions remain proposals.

## Scope and method

Reviewed the current working files, rather than only committed changes. Focused on the path from CLI or browser intent to rules validation, rolls, events, verified replay, save/load, snapshots, and player-visible output. Inspected character creation, dice generation, SRD parsing, combat, movement interfaces, items, and rests as supporting systems. Art generation and the viewer's visual design were outside this review's focus. This is a targeted engine review, not a claim that every SRD feature has been audited.

The review and this implementation do not load or modify a production campaign. Existing local source and viewer changes are preserved. The initial review produced this document and diagnostic artifacts; B subsequently added engine source, tests and support documentation.

- Existing test suite: `python -m unittest discover -s tests` — **148 tests passed**, 45.650 seconds.
- The initial sandboxed attempt failed because temporary campaign directories were inaccessible. The same suite passed with normal temporary-directory permissions. Those initial setup failures are not counted as engine defects.
- The passing run emitted a ResourceWarning for an unclosed test HTTP socket.
- Additional diagnostics reproduced **11 findings** in disposable fixtures. Their assertions deliberately confirm current faulty behavior; they are **not** regression tests asserting the desired behavior.
- Rules checks used the relevant repository spell and spellcasting files, cross-checked with the official [SRD 5.2](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.pdf). The review retains the project's 5.2 target; it does not propose a rules-version migration.

Evidence:

- [Reproducible diagnostics](../../artifacts/engine-review-2026-10-07/probes.py)
- [Recorded CLI commands, outputs, and findings](../../artifacts/engine-review-2026-10-07/probe-results.json)
- [Reviewed source hashes and baseline test record](../../artifacts/engine-review-2026-10-07/review-manifest.json)

The [interactive proposal view](<C:/Users/ggore/.cursor/projects/c-Users-ggore-Documents-Coding-Projects-dnd/canvases/engine-review.canvas.tsx>) presents the same six packages for inspection. Its package selector is a viewing control, not implementation approval. TypeScript validation passed against the installed canvas SDK; visual runtime rendering was not separately verified.

To repeat the diagnostics from the repository root: `python artifacts/engine-review-2026-10-07/probes.py`. They create and remove their own temporary campaigns and rewrite only their review evidence file in this repository. Run with ordinary temporary-directory permissions. Fault injection in F11 wraps the engine's own append operation; the diagnostic does not manually edit event files or keys.

## A — Make commits complete and reject commands from an obsolete history

Priority: highest integrity risk. Relative size: medium. Findings: F10, F11.

**F11: a failed command can leave a valid partial commit.** `Store.append_many()` writes each event separately. The fault-injection diagnostic interrupts the second write in one command containing two events. The first event remains on disk, and a fresh verified Game accepts it. Per-event signatures prove the authenticity of surviving events; they do not prove the completeness of the command. A command containing resource spending and its consequence could consequently stop between them. Evidence: [store.py:203](../../engine/store.py#L203).

**F10: the concurrency check accepts a different history of the same length.** `Game.commit()` supplies only an expected event count. The diagnostic loads a Game on branch A, quickloads an earlier save, adds a different event on branch B, and commits the old Game. The histories have different heads but equal lengths, so the stale commit succeeds. This is a branch-identity failure, not evidence that ordinary concurrent appends silently overwrite each other; different event counts are already rejected. Evidence: [core.py:214](../../engine/core.py#L214), [store.py:203](../../engine/store.py#L203).

Proposed change:

- Compare the expected full chain head, plus a restore generation where necessary, under the campaign lock before appending.
- Introduce a recoverable command boundary or another durable commit strategy that exposes either all events of a command or none. Preserve compatibility with existing signed histories; do not rewrite old outcomes.
- Serialize restore/repair/key rotation with mutations and publish generated snapshots from a consistent committed version.
- Give the CLI and roll API an explicit conflict response. Do not automatically reroll a conflict after randomness has been consumed.

Acceptance: interrupted writes and process termination at each commit boundary never replay a partial command; equal-length divergent histories reject stale commits; concurrent CLI/browser commands preserve signed state; duplicate roll submissions cannot produce a second committed result. Verify log, backup, snapshot-failure, and legacy-log behavior.

## B — Apply spell effects and expire them consistently

Priority: largest routine gameplay benefit. Relative size: medium for an initial slice; large for broad spell coverage. Findings: F01, F04.

**F01: Bless succeeds without its bonus.** The engine spends the spell slot and starts concentration, then reports that the effect is narrative. It adds no target effect or condition, and a subsequent saving throw includes no bonus die. Merely registering a `blessed` condition would not fix this: the d20 resolution paths also need to apply it. Evidence: [mechanics.py:1231](../../engine/mechanics.py#L1231), [mechanics.py:216](../../engine/mechanics.py#L216), local [Bless rules](../../rules/spells/bless.md).

**F04: Mage Armor does not expire.** The engine adds an effect without an expiry. After time advances beyond the spell's duration, the effect remains and armor calculation continues to use it. `after_time()` currently expires concentration rather than all timed effects. Combat rounds also do not call a common duration resolver; elapsed combat time is added when combat ends. Evidence: [mechanics.py:1233](../../engine/mechanics.py#L1233), [mechanics.py:1586](../../engine/mechanics.py#L1586), [cli.py:599](../../engine/cli.py#L599).

Proposed initial slice:

- Represent effect source, targets, roll modifiers, stacking rules, duration, and termination conditions explicitly.
- Implement Bless across weapon attacks, spell attacks, and saves, including viewer fulfillment.
- Give Mage Armor an explicit lifetime and expire it through time, rest, travel, and combat transitions.
- Expose support status for each spell: fully handled, partially handled, or narrative. A spell with an unresolved mechanical consequence needs a supported engine resolution path, rather than a successful cast that silently loses the consequence.

Acceptance: bonus dice are securely rolled and recorded exactly once; target limits and concentration termination work; timed effects expire at the correct boundary; recasting cannot stack forbidden duplicate benefits; quickload restores pending and active effects. Later slices can add Guidance, Bane, attack riders, positional auras, and other missing mechanics according to player priorities.

## C — Tighten casting requirements and remove inherited rules mistakes

Priority: high rules accuracy. Relative size: medium. Findings: F02, F03, F05.

**F02: explicit costly components bypass validation.** Passing an inventory ID through `--component` selects that item without checking whether it satisfies the required material and value. Identify accepts a purchased Dagger as its costly component. The auto-selection branch checks value heuristically; the explicit branch skips even that check. Evidence: [mechanics.py:1077](../../engine/mechanics.py#L1077), local [Identify rules](../../rules/spells/identify.md).

**F03: rituals omit normal casting time.** Identify as a ritual advances the clock by the extra ritual time alone. The normal casting time is not included. Ordinary long casts outside combat also need a shared elapsed-time path. Evidence: [mechanics.py:1052](../../engine/mechanics.py#L1052), local [Ritual rules](../../rules/core/08-rules-glossary.md#ritual).

**F05: Cure Wounds wrongly excludes Undead and Constructs.** A legal cast targeting an injured allied Skeleton consumes a slot and reports no effect solely because of its creature type. The repository's SRD 5.2 Cure Wounds text contains no such exclusion. Remove only unsupported blanket restrictions; keep exclusions belonging to other individual spells. Evidence: [mechanics.py:1167](../../engine/mechanics.py#L1167), local [Cure Wounds rules](../../rules/spells/cure-wounds.md).

Proposed change: structured component requirements validated identically for automatic and explicit selection; consume only the required quantity; shared casting-time handling; per-spell target restrictions instead of a legacy universal healing rule. Audit clear paths, sight, target eligibility, and area geometry alongside this work, but add individual reproductions before calling those audit candidates confirmed bugs.

Acceptance: wrong and undervalued components are refused without spending resources; valid components work; consumed stacks retain unused quantity; ritual and ordinary long casting advance the correct elapsed time and process due effects; Cure Wounds heals eligible Undead/Construct targets while spell-specific exceptions remain enforced.

## D — Make save/load restore the whole supported campaign state

Priority: high continuity and recoverability. Relative size: small to medium for missing files; medium for key rotation and interrupted restore. Findings: F08, F09.

**F08: player notes and pins survive quickload from the discarded future.** Quicksave includes selected narrative files plus `log/` and `views/`, but omits `player-notes.md` and `player-pins.json`. The diagnostic changes both after saving; both changes remain after quickload. The same allowlist also omits `chronicle.md`, which matters for saga continuity. The player notes/pins case is reproduced; the chronicle omission is source inspection. Evidence: [quicksave.py:19](../../engine/quicksave.py#L19), [server.py:178](../../engine/server.py#L178).

**F09: rekey invalidates existing quicksaves.** Key rotation re-signs the live log and rotating engine backups, but does not handle named quicksave logs. A save that loads successfully becomes unloadable after `rekey`. Evidence: [store.py:69](../../engine/store.py#L69), [quicksave.py:75](../../engine/quicksave.py#L75).

Proposed change: a versioned save manifest specifying mutable files, optional-file absence, and referenced assets; prepare and validate a restore before publishing it; preserve the previous slot until an overwrite succeeds. Validate and handle all legitimate signed save artifacts during key rotation before discarding the old key. Define `--at-seq` honestly: it currently saves an earlier event prefix alongside today's narrative notes, so it cannot promise historical narrative reconstruction.

Acceptance: notes, pins, chronicle, table state, and missing-file state round-trip; assets referenced by the restored state remain available; valid saves survive supported rekey; interrupted save overwrite preserves the prior slot; interrupted restore does not expose mixed histories. Repeated quickload keeps discarded events out of repair backups.

## E — Enforce visibility in player responses and detail routes

Priority: high exploration integrity. Relative size: small to medium. Finding: F06.

**F06: fogged creatures expose their coordinates in player JSON.** `player_view()` filters by the `hidden` flag rather than the fog-aware `_seen()` predicate. The diagnostic places an enemy on an unrevealed map tile; `_seen()` returns false, but `others` contains its token coordinates and current status. Hiding a token in the rendered map cannot remove information already sent to the browser. Several creature detail/art routes also use `hidden` checks instead of a shared visibility policy. Evidence: [views.py:302](../../engine/views.py#L302), [views.py:396](../../engine/views.py#L396), [server.py:99](../../engine/server.py#L99).

Proposed change: centralize current visibility and remembered knowledge. For previously known creatures, preserve appropriate journal/portrait access without exposing unseen current position, health status, or conditions. Apply the policy to state, initiative, detail endpoints, feed metadata, and animation cues.

Acceptance: unseen coordinates and current state do not occur anywhere in the player payload or reachable detail endpoints; discovered information remains available in the journal; intentionally hidden creatures and secret rolls remain protected. Test complete JSON responses, not only rendered SVG.

## F — Make player roll requests cover every supported player d20 path

Priority: medium to high player control and consistency. Relative size: medium to large. Finding: F07.

**F07: PC spell attacks ignore viewer roll mode.** `spell_attack()` directly calls `g.roll()`, even when `player_rolls=viewer` and the cast was not requested with `--now`. Ray of Frost produces a roll immediately and no Roll request. Weapon attacks already have a request path, so the experience differs by action type. `fulfill()` has no spell-attack operation. Source inspection also finds other forced immediate PC checks worth auditing, including Hide and some end-of-turn saves; those are not separately reproduced here. Evidence: [mechanics.py:1244](../../engine/mechanics.py#L1244), [cli.py:2801](../../engine/cli.py#L2801).

Proposed change: typed action/request records supporting spell attacks, follow-up effects, and multi-roll actions; record the originating combat/turn and resource reservation; define lifecycle rules for cancellation, invalid targets, ending combat, and restore. Preserve the secure engine RNG and the explicit player-authorized roll-for-me path.

Acceptance: supported PC d20 tests create Roll requests in viewer mode; clicks resolve once; costs are charged once; beam/dart sequences and concentration saves retain their ordering; cancellation and stale requests cannot bypass turn or resource validation; CLI and HTTP conflict responses are clear.

## Additional design risks and follow-up work

These are source-inspection risks or design recommendations, not additional reproduced defects in the count above.

- **Whole-tail deletion:** a valid prefix still verifies, because verification has no independent committed-head anchor. The existing deletion test removes a middle event. Document the limit and design an anchor/generation compatible with explicitly authorized quickload. This protects against accidental rollback or casual log truncation; it cannot make an owner-controlled computer tamper-proof.
- **Lock lifetime:** `Store.lock()` removes locks older than thirty seconds without checking whether their owning process is still running. A slow valid writer can lose mutual exclusion. Use process-aware or operating-system locking, with ownership-aware release and tests for live and abandoned locks.
- **Event contract:** replay uses string-dispatched dictionaries and silently ignores unknown event types after advancing sequence. Version and validate schemas so an incompatible event fails clearly rather than producing incomplete state.
- **Rules-cache correctness:** the disk signature uses file count and the greatest rounded modification time, rather than every source file's content. `data()` also has a process-lifetime cache. Editing an older rule file while another file remains the newest can leave cached rules unchanged; a running server needs an explicit invalidation policy.
- **Scaling:** each mutation verifies/replays the history, verifies it again for append, copies the full log to backup, and regenerates views. Measure synthetic small/large histories before proposing a verified checkpoint or incremental replay optimization. No live-campaign performance measurements were taken.
- **Maintainability:** the CLI and mechanics modules are large and contain many feature-specific branches. After the correctness slices are protected by meaningful tests, extract spell resolution, effects, combat actions, inventory, and request handling behind explicit interfaces. A broad rewrite first would make rule corrections harder to assess.
- **Test infrastructure:** add deterministic rule fixtures, transaction fault injection, HTTP boundary tests, process-level concurrency tests, and complete resource teardown. The current passing suite is useful but does not establish full rules coverage.

## Implementation and documentation requirements for selected work

For each approved package, record the chosen scope here, convert the relevant diagnostic into a regression test for the correct behavior, implement the smallest compatible change, and run the full existing suite plus the package's targeted tests. Record files changed, observable before/after behavior, validation results, remaining limits, and migration/recovery considerations.

Tests must use disposable campaigns. Existing rolled outcomes, production event logs, signing keys, generated character sheets, and campaign state are not to be manually edited. Changes should remain campaign-agnostic.

## Work record

1. Inspected repository instructions and the current source/test layout; identified existing local edits.
2. Reviewed storage, replay, CLI dispatch, request fulfillment, save/load, spell resolution, player views, and their tests.
3. Ran the baseline suite; distinguished sandbox fixture-access failures from the successful normal-permission run.
4. Cross-checked targeted rules claims against repository SRD text and the official SRD 5.2.
5. Built disposable diagnostics, corrected their setup/CLI syntax, and reproduced F01–F11. Saved command/output evidence and reviewed-source hashes.
6. Documented six proposed implementation packages and separate design risks. No production implementation package has been started.
7. Validated all repository documentation links, captured 45 CLI commands in the diagnostic evidence, checked the proposal view with TypeScript, and confirmed reviewed source hashes had not changed since capture.

Owner decision: **B selected**, expanded from the proposed initial Bless/Mage Armor slice to many spell families. The owner explicitly prioritized breadth and imaginative D&D adjudication over unrelated integrity work.

## B implementation record — 2026-10-07

Implemented **57 explicit SRD 5.2 profiles** and a shared effect model alongside the existing parsed spells. Profiles cover roll buffs/debuffs, defenses, movement, action economy, healing/restoration, visibility/control, attack riders, a Stealth aura and exploration/communication capabilities. [Usage, examples and limits](../spell-support.md), [per-profile inventory](../spell-coverage.md), and [all 339 spell classifications](../spell-coverage.json) are maintained together. The inventory is reproducible with `python tools/spell_coverage.py`.

Changed files: new `engine/spells.py` and `engine/effects.py`; integrations in `core.py`, `mechanics.py`, `cli.py`, `views.py`; new `tests/test_spell_effects.py`; command reference updates; generated coverage documentation and its generator. Existing art/viewer work is preserved.

Observable results:

- Bless now adds rolled bonus dice to attacks and saves instead of only spending a slot. Bane, Guidance, Enhance Ability and Foresight interact with the appropriate rolls; Bless/Foresight also affect death saves.
- Mage Armor expires after eight hours and ends on donning armor. Source-linked timed effects, concentration effects and named-turn riders expire consistently; simultaneous copies do not add duplicate bonuses.
- Haste supplies its limited extra action and ending lethargy. Slow affects AC, speed, saves, reactions, action choices, attack limits and somatic casting. Healing/restoration, NPC defenses and selected spell riders apply real effects.
- PC spell attacks now wait for viewer Roll requests, with casting resources charged once. This addresses F07's immediate-roll symptom; proposal F's broader request orchestration and stale-turn/cancellation policies remain pending.
- The blanket healing exclusion in F05 was removed as part of expanded healing. Proposal C's costly-component and casting-time work remains pending.
- Self spells supply their caster target; `cast --choice` selects supported spell options. `spells support [spell]` reports mechanics and remaining DM responsibilities without loading a campaign.

Validation: **40 new focused tests**, including all 57 profile casts, roll expressions/results, concentration/expiry/stacking, NPC defenses, Haste/Slow, riders, healing, immunity, old-effect compatibility, replay, and a disposable CLI persistence/request/sheet test. The final full-suite result is recorded after completion below. Production dice remain secure; deterministic faces exist only in tests.

Compatibility: uses existing event types and preserves historical outcomes. Legacy effects replay unchanged; recasting replaces older untimed effects with the new lifetime representation. New mechanics are not retroactively applied to earlier narrative-only casts. No manual campaign edits, migrations, key changes or save/load changes are part of B.

Limits: remaining spell clauses are listed in the support inventory. Areas use DM-listed recipients; the map is two-dimensional; detection/communication outcomes are narrated. Retargeting marks, arbitrary curses/reductions, summons, recurring areas and some environmental interactions remain manual. Support labels describe implemented mechanics, not certification of every SRD clause.

The original probes remain **historical pre-implementation evidence**. Their faulty-behavior assertions for F01/F04/F05/F07 are no longer acceptance criteria for current code. Use the regression tests above to verify the delivered behavior.

Final validation: `python -m unittest discover -s tests` — **196 tests passed**, 48.809 seconds. `python -m unittest discover -s tests -p test_spell_effects.py` — **40 tests passed**. Coverage generation and CLI support inspection succeeded; changed source passed `git diff --check`. The suite still emits the baseline unclosed HTTP test-socket ResourceWarning. The total includes other existing/concurrent test additions; this package adds 40 tests.
