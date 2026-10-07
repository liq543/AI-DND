# Art review fixture

Run `python tools/visual_preview.py` and open http://localhost:8767. The fixture uses the production renderers and animation layer with twelve generic in-memory maps, characters and equipment. It never writes game events. Optional `--campaign` reads verified active maps selected by the `DND_REVIEW_MAPS` environment variable; it cannot alter them.

Review the woodland, inn, vault, bathhouse, region, library, smithy, chapel, manor and fog/body study. Inspect rooms cycles four enlarged quadrants. The study distinguishes fallen bodies, an unconscious character and hidden creatures. Rain, Mist, Storm, Snow, Ash, Embers and Motion off exercise the production ambient layer. Rain, snow and ash are clipped to revealed outdoor ground. Freeze frame pauses visible effects; Resume animation restores playback.

Run `python tools/visual_preview.py --benchmark` for SVG generation measurements across the same fixtures. Cold asset reads and fifteen warm calls are reported separately. Generation times do not measure browser paint time or network latency.

For responsive review, run the live table on port 8766 and open `/mobile` on this fixture server. It embeds the live viewer inside a 391 × 844 iframe, exercising the actual CSS breakpoint rather than shrinking a screenshot. This route is a read-only view of the active table; keep any resulting campaign-specific screenshots in that campaign's own log directory.

Regression checks: `python -m unittest discover -s tests`. Renderer invariants and isolated visual checks are in `test_illustration.py` and `test_visuals.py`.

The Lamplight and Darkness studies compare the same room layout under dim and dark illumination. Light washes sit below tokens and opaque fog, so decorative lighting never changes visibility rules.

Use `--all-maps --port 8768` to audit every map in the verified active campaign. These development-only full art studies disable fog on deep copies, retain hidden entity/POI suppression, and never change discovery or write events. The compact catalogue supports duplicate display names through numeric option values. Save an overview plus all four `Inspect rooms` quarters; wait for `data-ready-index` after a map change and `data-camera-ready` after a camera change before capturing.

`python tools/isolated_regression.py` runs the complete suite from a disposable copy of generic source, assets, rules and templates, containing no real campaign or signing keys. The report is saved under `artifacts/visual-review`.

Review-only browser instrumentation measures map fetch, insertion, decoding of used images and two animation frames. It records `data-paint-ready-ms` on the status output. A separate 120-frame sample records median and 95th-percentile frame intervals on that output; these measurements describe the local review session, not guaranteed device performance. No instrumentation is added to the production viewer.

Use `--identity-study --port 8769` for disposable generic alive/dead pairs: human skin tones and outfits, all supported humanoid species/presentations, monsters, beasts, dragon colours and dark elves. The body clone preserves the living example's visual seed and selected face. These fixtures use the same production face and map renderers, load no campaign, and write no events. Save enlarged room sections and compare the visible face with its corresponding body; review prepared sprite cells as well as their source sheets.
