"""Visual assets: icons, tokens, portraits, cards, and imported public images.

Sources
- game-icons.net (CC BY 3.0, 4,100+ fantasy icons) vendored in assets/vendor/game-icons — offline.
- Generated SVG: tokens, portraits (heraldic medallions), item/character/monster/handout cards.
- Imported public images (`asset fetch <url>`): any image URL with a stated license, downloaded
  once into the campaign, hashed, and recorded in the signed log with its source and license.
"""
import base64
import hashlib
import html
import json
import mimetypes
import re
import textwrap
import urllib.request
from functools import lru_cache
from pathlib import Path

from . import srd

ROOT = Path(__file__).resolve().parent.parent
ICON_FILE = ROOT / "assets" / "vendor" / "game-icons" / "icons.json"

CLASS_ICONS = {"Barbarian": "barbarian", "Bard": "harp", "Cleric": "holy-symbol", "Druid": "curling-vines",
               "Fighter": "crossed-swords", "Monk": "fist", "Paladin": "cross-shield", "Ranger": "bow-arrow",
               "Rogue": "hooded-assassin", "Sorcerer": "magic-swirl", "Warlock": "warlock-eye", "Wizard": "wizard-staff"}
TYPE_ICONS = {"aberration": "brain-tentacle", "beast": "wolf-head", "celestial": "angel-wings",
              "construct": "rock-golem", "dragon": "dragon-head", "elemental": "whirlwind", "fey": "fairy",
              "fiend": "devil-mask", "giant": "giant", "humanoid": "hooded-figure", "monstrosity": "harpy",
              "ooze": "slime", "plant": "carnivorous-plant", "undead": "crowned-skull"}
NAME_ICONS = {"goblin": "goblin-head", "hobgoblin": "goblin-head", "orc": "orc-head", "skeleton": "skeleton",
              "zombie": "shambling-zombie", "ghost": "ghost", "vampire": "vampire-dracula", "wolf": "wolf-head",
              "werewolf": "werewolf", "bear": "bear-head", "spider": "spider-alt", "snake": "snake", "bat": "bat",
              "rat": "rat", "boar": "boar", "horse": "horse-head", "eagle": "eagle-head", "shark": "shark-jaws",
              "crab": "crab", "troll": "troll", "ogre": "ogre", "golem": "golem-head", "mimic": "mimic-chest",
              "animated armor": "black-knight-helm", "flying sword": "bouncing-sword",
              "bandit": "bandit", "knight": "black-knight-helm", "guard": "black-knight-helm", "mage": "wizard-face",
              "priest": "sun-priest", "cultist": "hood", "dwarf": "dwarf-face", "elf": "woman-elf-face",
              "harpy": "harpy", "minotaur": "minotaur", "centaur": "centaur", "cyclops": "cyclops",
              "hydra": "hydra", "wyvern": "wyvern", "griffon": "griffin-symbol", "gnoll": "wolf-howl",
              "kobold": "lizardman", "lich": "crowned-skull", "mummy": "mummy-head", "ghoul": "shambling-zombie",
              "wight": "crowned-skull", "specter": "spectre", "wraith": "spectre", "imp": "imp", "demon": "devil-mask",
              "devil": "devil-mask", "angel": "angel-wings", "unicorn": "unicorn", "owlbear": "bear-head",
              "dragon": "dragon-head", "wyrmling": "dragon-head", "giant": "giant", "ooze": "slime",
              "pudding": "slime", "cube": "transparent-slime", "shrieker": "mushroom-gills", "bugbear": "orc-head",
              "merfolk": "mermaid", "lizardfolk": "lizardman", "deer": "deer", "cat": "cat", "dog": "sitting-dog",
              "mastiff": "sitting-dog", "hawk": "hawk-emblem", "owl": "owl", "frog": "frog", "toad": "frog",
              "octopus": "octopus", "squid": "giant-squid", "scorpion": "scorpion", "wasp": "wasp-sting",
              "bee": "bee", "ape": "gorilla", "elephant": "elephant", "lion": "lion", "tiger": "tiger-head",
              "crocodile": "croc-jaws", "dinosaur": "dinosaur-rex", "allosaurus": "dinosaur-rex",
              "tyrannosaurus": "dinosaur-rex", "triceratops": "triceratops-head", "commoner": "farmer",
              "noble": "crown", "scout": "bow-arrow", "spy": "cloak-dagger", "thug": "punch", "veteran": "sword-brandish",
              "gladiator": "gladius", "assassin": "hooded-assassin", "druid": "curling-vines", "berserker": "barbarian",
              "pirate": "pirate-captain", "sahuagin": "fish-monster", "nightmare": "horse-head", "basilisk": "lizard-tongue",
              "medusa": "medusa-head", "chimera": "lion", "gorgon": "bull-horns", "manticore": "lion",
              "roc": "eagle-emblem", "kraken": "kraken-tentacle", "sphinx": "greek-sphinx", "treant": "evil-tree",
              "dryad": "evil-tree", "pixie": "fairy", "sprite": "fairy", "satyr": "bull-horns", "hag": "witch-face",
              "elemental": "whirlwind", "salamander": "salamander", "gargoyle": "gargoyle", "rust monster": "rusty-sword",
              "gelatinous": "transparent-slime", "worm": "worm-mouth", "otyugh": "tentacle-strike",
              "doppelganger": "duality-mask", "ettin": "giant", "djinni": "djinn", "efreeti": "djinn"}
ITEM_ICONS = {"sword": "broadsword", "longsword": "broadsword", "shortsword": "stiletto", "greatsword": "relic-blade",
              "rapier": "sai", "scimitar": "croc-sword", "dagger": "plain-dagger", "axe": "battle-axe",
              "handaxe": "axe-swing", "greataxe": "battered-axe", "battleaxe": "battle-axe", "mace": "flanged-mace",
              "warhammer": "war-pick", "maul": "flat-hammer", "hammer": "thor-hammer", "flail": "flail",
              "morningstar": "spiked-mace", "spear": "barbed-spear", "trident": "harpoon-trident", "pike": "spears",
              "halberd": "sharp-halberd", "glaive": "sharp-halberd", "lance": "spears", "whip": "whip",
              "club": "wood-club", "greatclub": "wood-club", "quarterstaff": "bo", "staff": "wizard-staff",
              "sickle": "sickle", "javelin": "thrown-spear", "sling": "sling", "shortbow": "high-shot",
              "longbow": "bow-arrow", "bow": "bow-arrow", "crossbow": "crossbow", "dart": "dart",
              "net": "fishing-net", "blowgun": "bamboo", "armor": "chest-armor", "mail": "chain-mail",
              "plate": "breastplate", "breastplate": "breastplate", "leather": "leather-armor", "hide": "leather-vest",
              "shield": "round-shield", "helm": "crested-helmet", "potion": "potion-ball", "healing": "health-potion",
              "scroll": "scroll-unfurled", "ring": "ring", "amulet": "gem-pendant", "necklace": "gem-necklace",
              "periapt": "gem-pendant", "cloak": "cloak", "cape": "cape", "robe": "robe", "boots": "boots",
              "slippers": "boots", "gloves": "gloves", "gauntlets": "gauntlet", "bracers": "bracers", "belt": "belt",
              "wand": "crystal-wand", "rod": "orb-wand", "orb": "crystal-ball", "bag": "swap-bag",
              "pack": "knapsack", "backpack": "knapsack", "rope": "rope-coil", "torch": "torch", "lantern": "lantern",
              "candle": "candle-light", "rations": "meat", "waterskin": "water-flask", "book": "book-cover",
              "tome": "spell-book", "manual": "book-cover", "coins": "coins", "gem": "gems", "key": "key",
              "chest": "locked-chest", "tools": "toolbox", "kit": "first-aid-kit", "thieves": "lockpicks",
              "arrows": "arrow-cluster", "bolts": "arrow-cluster", "quiver": "quiver", "holy": "holy-symbol",
              "symbol": "holy-symbol", "focus": "crystal-ball", "instrument": "lyre", "lute": "lyre", "drum": "drum",
              "flute": "flute", "horn": "hunting-horn", "carpet": "red-carpet", "broom": "magic-broom",
              "lamp": "magic-lamp", "mirror": "mirror-mirror", "hat": "pointy-hat", "headband": "headband-knot",
              "circlet": "crown", "crown": "crown", "deck": "card-random", "figurine": "stone-bust",
              "stone": "rune-stone", "gem of": "gems", "oil": "oil-drum", "elixir": "magic-potion", "dust": "powder",
              "bead": "prayer-beads", "feather": "feather", "eyes": "eye-target", "goggles": "steampunk-goggles",
              "helm of": "crested-helmet", "hammock": "sleeping-bag", "bedroll": "sleeping-bag", "tent": "camping-tent",
              "crowbar": "crowbar", "pole": "wood-stick", "caltrops": "caltrops", "ball bearings": "ball-glow",
              "acid": "acid", "alchemist": "fire-bottle", "antitoxin": "vial", "poison": "poison-bottle",
              "map": "treasure-map", "clothes": "shirt", "costume": "domino-mask", "mirror,": "mirror-mirror"}
CONDITION_ICONS = {"blinded": "blindfold", "charmed": "charm", "deafened": "silenced", "exhaustion": "tired-eye",
                   "frightened": "screaming", "grappled": "grab", "incapacitated": "knocked-out-stars",
                   "invisible": "invisible", "paralyzed": "frozen-body", "petrified": "stone-bust",
                   "poisoned": "poison-bottle", "prone": "falling", "restrained": "manacles",
                   "stunned": "knockout", "unconscious": "sleepy", "concentrating": "concentration-orb",
                   "raging": "enrage", "dodging": "dodging", "bloodied": "open-wound", "dead": "dead-head"}
RARITY_COLORS = {"Common": "#9aa0a6", "Uncommon": "#3fa34d", "Rare": "#3d7be0", "Very Rare": "#9b4de0",
                 "Legendary": "#e08a1e", "Artifact": "#c23b3b", "Mundane": "#8a7a5a", "Varies": "#8a7a5a"}
SIDE_COLORS = {"pc": "#2f8fdd", "ally": "#2fb59b", "enemy": "#d9443b", "neutral": "#d8b33a"}
FALLBACK_ICONS = ["perspective-dice-six-faces-random", "rolling-dices", "uncertainty", "swords-emblem", "shield"]


@lru_cache(maxsize=1)
def icons():
    if not ICON_FILE.exists():
        return {}
    return json.loads(ICON_FILE.read_text(encoding="utf-8"))["icons"]


def has_icon(name):
    return name in icons()


def fallback():
    return next((f for f in FALLBACK_ICONS if has_icon(f)), next(iter(icons()), None))


def search_icons(query, limit=20):
    words = [w for w in re.split(r"[^a-z]+", query.lower()) if len(w) > 2]
    scored = []
    for name in icons():
        score = sum(3 if w == name else 2 if w in name.split("-") else 1 if w in name else 0 for w in words)
        if score:
            scored.append((-score, len(name), name))
    return [n for _, _, n in sorted(scored)[:limit]]


def resolve(*candidates):
    for c in candidates:
        if c and has_icon(c):
            return c
    return fallback()


def icon_for_entity(e):
    if e.get("icon") and has_icon(e["icon"]):
        return e["icon"]
    if e["kind"] == "pc":
        cls = max(e.get("classes", {"Fighter": 1}).items(), key=lambda kv: kv[1])[0]
        return resolve(CLASS_ICONS.get(cls))
    name = (e.get("srd_name") or e["name"]).lower()
    for key in sorted(NAME_ICONS, key=len, reverse=True):
        if key in name:
            return resolve(NAME_ICONS[key], TYPE_ICONS.get(e.get("type", "").split()[0].lower() if e.get("type") else ""))
    t = (e.get("type") or "humanoid").split()[0].lower()
    return resolve(TYPE_ICONS.get(t), *search_icons(name, 3))


def icon_for_item(name, kind=None):
    n = name.lower()
    for key in sorted(ITEM_ICONS, key=len, reverse=True):
        if key in n:
            return resolve(ITEM_ICONS[key])
    return resolve(*search_icons(n, 3), "swap-bag")


def icon_body(name):
    ic = icons().get(name) or icons().get(fallback(), {"body": ""})
    return ic["body"]


def icon_svg(name, color="#222", size=64, bg=None):
    body = icon_body(name).replace('fill="currentColor"', f'fill="{color}"')
    rect = f'<rect width="512" height="512" rx="80" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="{size}" height="{size}">'
            f'{rect}{body}</svg>')


def icon_symbol(name, sym_id):
    return f'<symbol id="{sym_id}" viewBox="0 0 512 512">{icon_body(name)}</symbol>'


# ------------------------------------------------------------ colour helpers

def hue_from(text):
    return int(hashlib.sha256(text.encode()).hexdigest()[:4], 16) % 360


def esc(s):
    return html.escape(str(s), quote=True)


def wrap(text, width):
    out = []
    for para in str(text).split("\n"):
        out.extend(textwrap.wrap(para, width) or [""])
    return out


def side_of(e):
    return "pc" if e["kind"] == "pc" else e.get("side", "enemy")


# ------------------------------------------------------------ token & portrait

def nest_svg(svg, x, y, w, h):
    """Place a standalone SVG document inside another one at (x, y) with size w×h."""
    svg = re.sub(r'\s(width|height)="[\d.]+"', "", svg, count=2)
    return svg.replace("<svg ", f'<svg x="{x}" y="{y}" width="{w}" height="{h}" ', 1)


def token_svg(e, size=128, portrait_href=None, face=None):
    """Round token: side-coloured ring around the creature's picture (an image href, an inline SVG, or its emblem)."""
    color = SIDE_COLORS.get(side_of(e), "#888")
    hue = hue_from(e["id"])
    if face:  # inline generated art, clipped to the disc
        inner = f'<clipPath id="c"><circle cx="64" cy="64" r="54"/></clipPath><g clip-path="url(#c)">{nest_svg(face, 10, 10, 108, 108)}</g>'
    elif portrait_href:
        inner = (f'<clipPath id="c"><circle cx="64" cy="64" r="54"/></clipPath>'
                 f'<image href="{esc(portrait_href)}" x="10" y="10" width="108" height="108" clip-path="url(#c)" preserveAspectRatio="xMidYMid slice"/>')
    else:
        inner = f'<g transform="translate(24 24) scale(0.15625)" fill="#f4efe6">{icon_body(icon_for_entity(e)).replace("currentColor", "#f4efe6")}</g>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="{size}" height="{size}">'
            f'<defs><radialGradient id="g" cx="40%" cy="35%"><stop offset="0" stop-color="hsl({hue},35%,42%)"/>'
            f'<stop offset="1" stop-color="hsl({hue},40%,18%)"/></radialGradient></defs>'
            f'<circle cx="64" cy="64" r="60" fill="{color}"/><circle cx="64" cy="64" r="54" fill="url(#g)"/>'
            f'{inner}<circle cx="64" cy="64" r="57" fill="none" stroke="#111" stroke-opacity=".35" stroke-width="2"/></svg>')


def portrait_svg(e, width=320, height=400):
    """Procedural heraldic portrait: colours from the name, emblem from class or creature type."""
    hue = hue_from(e["name"])
    hue2 = (hue + 140) % 360
    icon = icon_for_entity(e)
    sub = (" / ".join(f"{c} {l}" for c, l in e.get("classes", {}).items()) if e["kind"] == "pc"
           else f"{e.get('size', '')} {e.get('type', '')}".strip())
    species = e.get("species", "")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 400" width="{width}" height="{height}">
<defs>
 <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="hsl({hue},45%,30%)"/><stop offset="1" stop-color="hsl({hue},50%,10%)"/></linearGradient>
 <linearGradient id="sh" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="hsl({hue2},55%,55%)"/><stop offset="1" stop-color="hsl({hue2},60%,28%)"/></linearGradient>
 <pattern id="dots" width="16" height="16" patternUnits="userSpaceOnUse"><circle cx="8" cy="8" r="1.2" fill="#fff" fill-opacity=".07"/></pattern>
</defs>
<rect width="320" height="400" rx="18" fill="url(#bg)"/><rect width="320" height="400" rx="18" fill="url(#dots)"/>
<rect x="8" y="8" width="304" height="384" rx="14" fill="none" stroke="#d8c08a" stroke-width="3"/>
<rect x="14" y="14" width="292" height="372" rx="10" fill="none" stroke="#d8c08a" stroke-opacity=".4"/>
<path d="M160 40 L262 70 L262 170 C262 240 214 282 160 306 C106 282 58 240 58 170 L58 70 Z" fill="url(#sh)" stroke="#f1dfae" stroke-width="5"/>
<g transform="translate(92 84) scale(0.265625)" fill="#fbf6ea">{icon_body(icon).replace("currentColor", "#fbf6ea")}</g>
<rect x="30" y="318" width="260" height="46" rx="8" fill="#1a140e" fill-opacity=".75" stroke="#d8c08a"/>
<text x="160" y="347" text-anchor="middle" font-family="Georgia,serif" font-size="22" fill="#f6e7c1">{esc(e["name"][:24])}</text>
<text x="160" y="384" text-anchor="middle" font-family="Georgia,serif" font-size="13" fill="#d8c08a">{esc((species + " " + sub).strip()[:44])}</text>
</svg>'''


# ------------------------------------------------------------ cards

def _card_frame(title, subtitle, color, icon, body_lines, footer="", w=360, h=520):
    lines = "".join(f'<tspan x="24" dy="{19 if i else 0}">{esc(l)}</tspan>' for i, l in enumerate(body_lines[:17]))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
<defs><linearGradient id="p" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f7ecd2"/><stop offset="1" stop-color="#e6d3a8"/></linearGradient></defs>
<rect width="{w}" height="{h}" rx="16" fill="{color}"/><rect x="8" y="8" width="{w - 16}" height="{h - 16}" rx="12" fill="url(#p)"/>
<text x="24" y="44" font-family="Georgia,serif" font-size="22" font-weight="bold" fill="#2b1d0e">{esc(title[:28])}</text>
<text x="24" y="66" font-family="Georgia,serif" font-size="13" font-style="italic" fill="#5a4630">{esc(subtitle[:52])}</text>
<line x1="24" y1="78" x2="{w - 24}" y2="78" stroke="{color}" stroke-width="2"/>
<rect x="{w // 2 - 70}" y="92" width="140" height="140" rx="70" fill="{color}" fill-opacity=".15" stroke="{color}" stroke-width="3"/>
<g transform="translate({w // 2 - 52} 110) scale(0.203125)" fill="#2b1d0e">{icon_body(icon).replace("currentColor", "#2b1d0e")}</g>
<text x="24" y="262" font-family="Georgia,serif" font-size="13.5" fill="#2b1d0e">{lines}</text>
<text x="{w // 2}" y="{h - 22}" text-anchor="middle" font-family="Georgia,serif" font-size="11" fill="#6a5438">{esc(footer)}</text>
</svg>'''


def srd_text(kind, slug_, max_chars=900):
    folder = {"magic_items": "magic-items", "spells": "spells", "monsters": "monsters"}[kind]
    p = ROOT / "rules" / folder / f"{slug_}.md"
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8")
    text = re.sub(r"^#.*$|^\*[^*].*\*\s*$", "", text, flags=re.M)
    text = re.sub(r"[*_#|]", "", text)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


def item_card(item):
    from .core import item_display_name, item_known
    if not item_known(item):
        item = {"name": item_display_name(item), "kind": item.get("kind", "gear"), "base_name": item.get("base_name"),
                "note": item.get("note"), "alias": None, "source": item.get("source"), "magic": False,
                "description": "Unidentified. It hums with magic when you hold it, but its properties are unknown. Identify it with "
                               "the Identify spell, or by focusing on it through a Short Rest."}
    rarity = item.get("rarity") or ("Mundane" if not item.get("magic") else "Varies")
    color = RARITY_COLORS.get(rarity, "#8a7a5a")
    sub = item.get("meta") or f"{item.get('kind', 'gear').title()}" + (f", {rarity}" if item.get("magic") else "")
    desc = item.get("description") or (srd_text("magic_items", item["ref"]) if item.get("magic") and item.get("ref") else "")
    if not desc and item.get("kind") == "weapon":
        w = srd.find("weapons", item.get("base_name", item["name"])) or {}
        desc = f"Damage: {w.get('damage')} {w.get('type')}\nProperties: {', '.join(w.get('properties', [])) or '—'}\nMastery: {w.get('mastery', '—')}"
    if not desc and item.get("kind") == "armor":
        a = srd.find("armor", item.get("base_name", item["name"])) or {}
        desc = f"AC {a.get('base')}{' + Dex' if a.get('adds_dex') else ''}{' (max 2)' if a.get('dex_max') == 2 else ''}\nCategory: {a.get('category', '')}"
    if item.get("alias"):
        sub = f"{item['name']} · {sub}"
    if item.get("note"):
        desc = item["note"] + ("\n\n" + desc if desc else "")
    return _card_frame(item.get("alias") or item["name"], sub, color, icon_for_item(item["name"], item.get("kind")),
                       wrap(desc or "—", 44), footer=f"Source: {item.get('source', 'SRD 5.2')}")


def character_card(e, d):
    ab = d.get("abilities", {})
    lines = [f"Level {d.get('level', '?')} · AC {d['ac']} · HP {e['hp']}/{d['hp_max']} · Speed {d['speed'].get('walk', 30)} ft",
             "  ".join(f"{k.upper()} {v}" for k, v in ab.items()), "",
             f"Species: {e.get('species', '')}   Background: {e.get('background', '')}",
             f"Passive Perception {d.get('passive_perception', '')} · Initiative {d['init']:+d}", ""]
    lines += wrap(e.get("bio", {}).get("appearance", "") or "", 44)[:6]
    return _card_frame(e["name"], " / ".join(f"{c} {l}" for c, l in e["classes"].items()), SIDE_COLORS["pc"],
                       icon_for_entity(e), lines, footer=f"Player: {e.get('player', '')}")


def monster_card(e, reveal_stats=False):
    lines = [f"{e.get('size', '')} {e.get('type', '')}".strip()]
    if reveal_stats:
        lines += [f"AC {e.get('ac')} · HP {e.get('hp')}/{e.get('hp_max')} · CR {e.get('cr')}"]
    lines += [""] + wrap(e.get("description", "") or "", 44)
    return _card_frame(e["name"], e.get("alignment", ""), SIDE_COLORS.get(e.get("side", "enemy")),
                       icon_for_entity(e), lines, footer="")


def handout_card(title, text, icon="scroll-unfurled"):
    return _card_frame(title, "Handout", "#8a6a3a", resolve(icon, "scroll-unfurled"), wrap(text, 44), w=360, h=520)


# ------------------------------------------------------------ imported files

ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml"}
MAX_BYTES = 15 * 1024 * 1024


def assets_dir(campaign_dir):
    p = Path(campaign_dir) / "assets"
    p.mkdir(exist_ok=True)
    return p


def fetch(url, campaign_dir):
    """Download a public image. Returns (bytes, content_type). Only http(s), only images, ≤15 MB."""
    if not re.match(r"^https?://", url):
        raise ValueError("only http(s) URLs can be fetched")
    req = urllib.request.Request(url, headers={"User-Agent": "dnd-engine/1.0 (tabletop asset fetch)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        ctype = resp.headers.get_content_type()
        data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("file is larger than 15 MB")
    if ctype not in ALLOWED_TYPES:
        guess = mimetypes.guess_type(url)[0]
        if guess in ALLOWED_TYPES and ctype in ("application/octet-stream", "binary/octet-stream"):
            ctype = guess
        else:
            raise ValueError(f"not an image (content-type {ctype})")
    return data, ctype


def save_file(campaign_dir, data, ctype, asset_id):
    ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif",
           "image/svg+xml": ".svg"}[ctype]
    if ctype == "image/svg+xml":
        text = data.decode("utf-8", "replace")
        if re.search(r"<script|on\w+\s*=|javascript:", text, re.I):
            raise ValueError("SVG contains scripts or event handlers — refused")
    path = assets_dir(campaign_dir) / f"{asset_id}{ext}"
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def data_uri(path):
    ctype = mimetypes.guess_type(str(path))[0] or "image/png"
    if str(path).endswith(".svg"):
        ctype = "image/svg+xml"
    return f"data:{ctype};base64,{base64.b64encode(Path(path).read_bytes()).decode()}"
