# Independent portrait review — final v5

Reviewed 8 October 2026. Final visual score: **8.3/10 — approved**. No remaining observed blocker to the requested 8/10 threshold for this portrait expansion.

## Evidence inspected

- All twenty actual rendered collection screenshots, `portrait-v5-00.png` through `portrait-v5-19.png`: all 320 new large portraits and their production map-face crops.
- Refreshed final `portrait-v5-proof.png` and `portrait-v5-company.png`, captured after catalogue corrections, canonical outfit parsing and explicit hair-colour filtering. The complete company screenshot was also inspected in six readable, original-width review crops.
- The catalogue, extraction cells, selected enlarged trait crops, persistence implementation and pure in-memory reproduction probes. Catalogue validation confirms 320 unique collection/index pairs across twenty collections of sixteen.

The collections cover twelve Human presentation/skin groups and eight fantasy-species groups. The collection study pins individual cells to make every asset inspectable; the company study exercises ordinary portrait selection.

## Visual assessment

The new paintings have convincing facial anatomy, coherent lighting, clear eyes and hair, and well-rendered cloth, leather and metal. Portrait and map crops retain complete heads, distinctive ears and horns, and readable expressions. No material head clipping, adjacent-cell leakage, definite species swap or presentation-group swap was observed across the 320 new cells. Skin groups and visible hair colours are consistent with the final catalogue at the level supported by these paintings. The fantasy species remain recognizable at token size; Dragonborn retain reptilian muzzles and scales.

The refreshed company contains 48 masculine Human soldiers and **32 distinct selected assets**, independently confirmed through the selection probe. All selected outfit families match the intended armour, leather or tunic family. The actual screenshot shows that variety in both large portraits and map crops. Age, complexion, hair and facial-hair variation materially reduce the earlier uniform appearance.

The main limitation is repeated face families. Many sheet columns repeat a pose, facial structure, hair and outfit through successive ages; some Human families also recur across complexion groups. These are **320 painted bases/variants**, not 320 unrelated identities. Several faces are similarly handsome, symmetrical and serious. This limits distinctiveness and keeps the score below 9. Future improvement should prioritize unrelated facial structures, expressions, asymmetry and silhouettes rather than more age or complexion variants of the same families.

## Metadata corrections

With explicit authorization, the critic corrected 49 clearly visible cosmetic fields on 49 catalogue records. The exact old/new values are retained in `assets/generated/portrait-v5-metadata-corrections.json`. No pixels, species, presentation, skin, age or hair-colour groups were changed.

Most corrections identify facial hair that the prompt-derived metadata had labelled absent: short beards, goatees, stubble and a few long beards. Other corrections distinguish short from long or stubble beards. Dwarf cells 03/07/11/15 show a topknot/bun and now use `hair_style: bun`. The visible braided Human cells retain their braid metadata. Uncertain very light facial hair was not overclassified. Preserve these observed corrections if regenerating the catalogue from prompts.

## Identity persistence and selection

The final browser proof visibly retains the same dark-haired Human feminine face after a description mentions an Orc and a Dwarf acting nearby. The two large portraits and map crops match. The earlier auburn-versus-dark-hair selection issue is resolved in the refreshed proof.

Independent source and pure in-memory probes covered established descriptions, dotted and whole biography updates, movement, rename, narrative-only first descriptions, entity-ID reuse, implicit Human subject terms, deliberate asset-look changes, procedural profiles and catalogue growth. Previously reproduced failures were repaired and rechecked. Established painted and procedural choices remain stable through ordinary descriptive and scene updates; explicit asset-look changes remain intentional identity changes. Incoming biography descriptions and visual prefixes before relative/passive narrative clauses now establish the subject correctly. Thirteen profile tests were independently run during the audit; the implementing agent additionally reports 32 final focused identity/profile checks and 286 isolated regression tests passing.

No remaining failure was reproduced in these reviewed cases. This is evidence for the covered inputs, not a universal guarantee for arbitrary natural-language descriptions. A finite catalogue still approximates unsupported combinations of age, hair, outfit and other traits; it should not be described as providing every possible exact appearance. Visual presentation labels describe artwork and do not establish a person's gender independently of supplied identity data.

## Scope and performance limits

This signoff covers the new portrait art, final generic selection/proof screenshots, metadata corrections and the reviewed persistence cases. It does not replace the separate all-map or corpse-library review. No campaign files or signing material were accessed for this portrait audit, and no gameplay state was changed by the critic.

The art is prepared offline and selected locally; there is no image-generation request on the ordinary portrait-render path. This review did not independently benchmark the expanded library or certify browser FPS, animation timing or fluidity. Still screenshots cannot support those claims. Earlier corpse-library performance measurements should not be presented as measurements of this new 320-portrait expansion.
