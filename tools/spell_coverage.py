"""Regenerate the spell support inventory without opening a campaign."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import spells, srd  # noqa: E402


def main():
    rows = [{"slug": s["slug"], "name": s["name"], "level": s["level"],
             "explicit_profile": s["slug"] in spells.PROFILES, **spells.support(s)}
            for s in sorted(srd.data()["spells"].values(), key=lambda s: (s["level"], s["name"]))]
    counts = Counter(r["status"] for r in rows)
    data = {"rules": "SRD 5.2", "explicit_profiles": len(spells.PROFILES),
            "spell_count": len(rows), "counts": dict(counts), "spells": rows}
    dest = ROOT / "docs"
    dest.mkdir(exist_ok=True)
    (dest / "spell-coverage.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Spell coverage inventory", "", "Generated from the local SRD dataset and `engine/spells.py`; refresh with `python tools/spell_coverage.py`.", "",
             f"{len(rows)} SRD entries; {len(spells.PROFILES)} explicit profiles. Classification counts: " +
             ", ".join(f"{name}: {count}" for name, count in sorted(counts.items())) + ".", "",
             "**Mechanical** means the listed profile mechanics are implemented. **Partial** lists an explicit remaining DM responsibility or uses the existing general parser. **Narrative** tracks casting resources/concentration while the DM resolves the description. No label certifies every clause of the spell.", "",
             "See [the usage guide](spell-support.md) for shared limitations, choices and compatibility. All entries, including parsed and narrative spells, are in [spell-coverage.json](spell-coverage.json).", "", "## Explicit profiles", ""]
    for row in rows:
        if not row["explicit_profile"]:
            continue
        lines.append(f"- **{row['name']}** (level {row['level']}, {row['status']}): {row['mechanics']}")
        if row["choice"]:
            lines.append(f"  Choice category: `{row['choice']}`.")
        if row["remaining"]:
            lines.append(f"  DM: {row['remaining']}")
    (dest / "spell-coverage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Documented {len(rows)} spells and {len(spells.PROFILES)} explicit profiles.")


if __name__ == "__main__":
    main()
