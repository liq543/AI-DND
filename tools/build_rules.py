"""Build the rules/ library from the SRD 5.2 markdown source.

Source: https://github.com/springbov/dndsrd5.2_markdown (SRD 5.2, CC-BY-4.0)

Usage:
    git clone --depth 1 https://github.com/springbov/dndsrd5.2_markdown <tmp>
    python tools/build_rules.py <tmp>/src

Core chapters are copied whole; spells, monsters and magic items are split into
one file per entry with an _index.md table, so the DM can open exactly one entry
instead of loading a 300 KB chapter into context.
"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "rules"

CORE = {
    "01_PlayingTheGame.md": "01-playing-the-game.md",
    "02_CharacterCreation.md": "02-character-creation.md",
    "04_CharacterOrigins.md": "04-character-origins.md",
    "05_Feats.md": "05-feats.md",
    "06_Equipment.md": "06-equipment.md",
    "08_RulesGlossary.md": "08-rules-glossary.md",
    "09_GameplayToolbox.md": "09-gameplay-toolbox.md",
    "11_Monsters.md": "11-reading-stat-blocks.md",
}


def slug(name: str) -> str:
    s = name.lower().replace("’", "").replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def split_entries(lines, is_entry_heading):
    """Yield (name, body_lines) for every entry heading; stops at None-returning headings."""
    name, body = None, []
    for line in lines:
        hit = is_entry_heading(line)
        if hit is not None:
            if name:
                yield name, body
            if hit is False:  # a non-entry heading (e.g. "### B Spells") ends the current entry
                name, body = None, []
                continue
            name, body = hit, [line]
        elif name:
            body.append(line)
    if name:
        yield name, body


def write_entries(folder: Path, entries, describe, columns, title):
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    used = set()
    for name, body in entries:
        s = slug(name)
        while s in used:
            s += "-2"
        used.add(s)
        text = "\n".join(body).strip() + "\n"
        text = re.sub(r"^#{2,4} ", "# ", text, count=1)
        (folder / f"{s}.md").write_text(text, encoding="utf-8")
        rows.append((name, s, *describe(body)))
    rows.sort(key=lambda r: r[0].lower())
    out = [f"# {title} ({len(rows)})", "",
           "Open the linked file for the full entry. Grep this table to filter.", "",
           "| Name | " + " | ".join(columns) + " |",
           "|---|" + "---|" * len(columns)]
    for name, s, *rest in rows:
        out.append(f"| [{name}]({s}.md) | " + " | ".join(c.replace("|", "/") for c in rest) + " |")
    (folder / "_index.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    return len(rows)


def first_italic(body):
    for line in body[1:8]:
        m = re.match(r"^\*(?!\*)(.+?)\*\s*$", line.strip())
        if m:
            return m.group(1).strip()
    return ""


def build_spells(src: Path):
    lines = src.joinpath("07_Spells.md").read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("## Spell Descriptions"))
    (RULES / "core" / "07-spellcasting-rules.md").write_text("\n".join(lines[:start]) + "\n", encoding="utf-8")

    def heading(line):
        m = re.match(r"^(###|####) (.+?)\s*$", line)
        if not m:
            return None
        name = m.group(2).strip("* ")
        if m.group(1) == "###" and name.endswith("Spells"):
            return False
        return name

    def describe(body):
        meta = first_italic(body)
        level = "Cantrip" if "Cantrip" in meta else (re.search(r"Level (\d)", meta) or [None, "?"])[1]
        school = re.sub(r"Level \d|Cantrip|\(.*\)", "", meta).strip()
        classes = (re.search(r"\((.*)\)", meta) or [None, ""])[1]
        return level, school, classes

    return write_entries(RULES / "spells", split_entries(lines[start + 1:], heading), describe,
                         ["Level", "School", "Classes"], "Spells")


def build_magic_items(src: Path):
    lines = src.joinpath("10_MagicItems.md").read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("## Magic Items A"))
    (RULES / "core" / "10-magic-item-rules.md").write_text("\n".join(lines[:start]) + "\n", encoding="utf-8")

    def heading(line):
        m = re.match(r"^#### (.+?)\s*$", line)
        return m.group(1).strip("* ") if m else None

    def describe(body):
        meta = first_italic(body)
        attune = "Yes" if "Attunement" in meta else ""
        kind, _, rarity = meta.partition("),") if "(" in meta.split(",")[0] else meta.partition(",")
        kind = kind + (")" if "(" in kind and ")" not in kind else "")
        rarity = re.sub(r"\(Requires Attunement.*?\)", "", rarity).strip()
        return kind.strip(), rarity, attune

    return write_entries(RULES / "magic-items", split_entries(lines[start + 1:], heading), describe,
                         ["Type", "Rarity", "Attune"], "Magic Items")


def build_monsters(src: Path):
    entries = []
    for fname in ("12_MonstersA-Z.md", "13_Animals.md"):
        lines = src.joinpath(fname).read_text(encoding="utf-8").splitlines()

        def heading(line):
            m = re.match(r"^## (.+?)\s*$", line)
            return m.group(1).strip("* ") if m else None

        entries.extend(split_entries(lines[1:], heading))

    def describe(body):
        text = "\n".join(body)
        cr = re.search(r"\*\*CR\*\*\s*([\d/]+)", text)
        return (cr.group(1) if cr else "?"), first_italic(body)

    return write_entries(RULES / "monsters", entries, describe, ["CR", "Size / Type / Alignment"],
                         "Monsters & Animals")


# Words split by a stray space in the upstream PDF conversion; the engine parses these class-table cells.
TYPO_FIXES = {
    "Ath letics": "Athletics", "In sight": "Insight", "Na ture": "Nature", "Persua sion": "Persuasion",
    "Leather Ar mor": "Leather Armor", "En tertainer's": "Entertainer's", "Druidic Fo cus": "Druidic Focus",
    "20 Ar rows": "20 Arrows", "Ar cane Focus": "Arcane Focus",
}


def fix_typos(path: Path):
    text = path.read_text(encoding="utf-8")
    for bad, good in TYPO_FIXES.items():
        text = text.replace(bad, good)
    path.write_text(text, encoding="utf-8")


def main():
    src = Path(sys.argv[1])
    for sub in ("core", "classes", "spells", "monsters", "magic-items"):
        shutil.rmtree(RULES / sub, ignore_errors=True)
    (RULES / "core").mkdir(parents=True)
    (RULES / "classes").mkdir(parents=True)
    for s, d in CORE.items():
        shutil.copy(src / s, RULES / "core" / d)
    for f in sorted((src / "03_Classes").glob("*.md")):
        if f.name != "00_Classes.md":
            dest = RULES / "classes" / (slug(f.stem.split("_", 1)[1]) + ".md")
            shutil.copy(f, dest)
            fix_typos(dest)
    shutil.copy(src / "00_Legal.md", RULES / "LEGAL.md")
    print("spells", build_spells(src))
    print("magic items", build_magic_items(src))
    print("monsters", build_monsters(src))


if __name__ == "__main__":
    main()
