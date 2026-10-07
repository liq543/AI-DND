# Independent identity art review

Reviewed 2026-10-07. This report covers the expanded generic identity library, separately from the earlier campaign map review.

**Final expanded identity-library visual score: 8.2/10 — approved.** The repaired artwork earns this score at normal playable scale. All specifically identified asset and identity-selection defects passed independent rechecks, including the final cache-cleared browser batch. The previous 7.2 score described superseded extractions with material head/foot clipping; it no longer describes the current library.

## Evidence

- All 180 catalogue body cells and 116 catalogue portrait cells, inspected as their actual prepared WebPs. Review-only labeled contacts are saved as `critic-cells-*.jpg`.
- All 55 actual browser screenshots: eleven identity studies, each with an overview and four playable sections. Every viewport was inspected through derived browser contacts; representative sections were also inspected at original resolution. The evidence is `identity-map-00.png` through `identity-map-10.png` and their `-section-0` through `-section-3` captures.
- Catalogue metadata and read-only generic selection probes, including neutral Human/Dwarf/Dragonborn, explicit female and unknown Lion/Deer, Pony, colored dragons, and species-like nicknames.
- Source review of species/presentation constraints, copied portrait compatibility, and stat-block priority. No game mechanics or campaign facts were modified or used in this report.

## Assessment

The library now has consistent painted materials, substantial species and outfit coverage, complete readable silhouettes, and clear paired living portraits and fallen bodies. The actual browser sections preserve recognizable anatomy and species colors, while compact death markers explain the relaxed poses without obscuring the art. The replacement colored Dragonborn faces have clearly reptilian muzzles. The re-extracted animal and neutral monster portraits have clean crowns, ears, and lower borders.

Major head/foot loss and large neighboring-body fragments in the previous prepared cells are resolved. I found no definite species-order or declared presentation swaps in the current catalogue. Gender cannot be established from a face or hairstyle alone; the review checks explicit compatibility metadata and visibly sex-specific animal traits rather than guessing a person's identity.

Neutral Dwarf body cells 02/03 now have clean faces consistent with their neutral portraits. Neutral selection constrains both face and body. Explicit female Lion/Deer use the new mane-free/antler-free pairs, and unspecified presentation uses the compatible neutral variants; the older full-maned lion and antlered stag are restricted to masculine presentation. Pony uses Horse anatomy. Blue/Gold dragons retain matching painted colors, while unsupported explicit colors use compatible anatomical fallback rather than a red painted dragon. Stat-block species takes precedence over misleading nicknames, and copied painted portraits are checked against resolved identity before reuse.

## Final repair verification

All 14 flagged prepared sprites were reinspected after individual ImageGen cleanup: Human feminine 05/06; Fantasy neutral 00/01/04/05/12/13/14/15; gendered monsters 12/13; beasts 14/15. Their heads, limbs, tails, clothing, and declared identities remain intact, with no material neighboring fragments or colored matte halos observed. Creature 07 was also reinspected after expanding its source crop; its complete detached helmet is now included and clearly belongs to the armor. Actual prepared output contacts are `critic-repaired-main.jpg` and `critic-repaired-extra.jpg`.

Final source probes initially found two additional consistency errors: creature selectors ignored species appearance pins, and an unsupported authoritative species could fall through to a nickname's different species. Both were fixed and independently rechecked in fresh processes:

- Wolf pinned as Cat: no incompatible painted Wolf pair; both fallback paths use Cat anatomy.
- Black Dragon pinned as Blue Dragon: matching blue portrait and body, index 02.
- Unsupported Black Dragon named Red Dragon Hunter: no red painted pair; compatible dragon fallback.
- Wolf named Goblin Slayer: matching Wolf portrait/body, index 00.

No remaining blocking asset or reproduced identity-selection defect is known in the reviewed library. After the final changes, all 55 cache-cleared browser viewports were reinspected using newly regenerated screenshot contacts. Five affected fantasy, monster, and animal sections were also inspected at original screenshot resolution. The repaired sprites load correctly, remain complete and readable, and retain matching species/presentation/color cues in the final rendered evidence.

## Limits and performance

Neutral Human faces remain aesthetically narrow in shape and expression. Several fallen poses, especially arthropods and curled dragons, depend on the explicit death marker to distinguish death from rest. Procedural fallback and user-supplied portraits cannot guarantee the same painted finish or automatically establish personal identity.

This is a still-image and source inspection, not a certification of animation timing or FPS. The supplied local benchmark records warm identity-map assembly medians of 7.48–52.67 ms, worst recorded cold assembly 89.92 ms, and portrait warm medians of 0.56–0.99 ms. Supplied browser readiness samples were 86–234 ms including image loading and frame readiness. These measurements were produced by the implementation workflow, not independently timed by this critic. Bundled prepared assets avoid an online image generation step during play.

Read-only review except for QA contact sheets and this report. Final corrected prepared cells and generic identity probes have been verified.

