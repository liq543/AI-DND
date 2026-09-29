"""Generated item illustrations: every item in the game gets a picture drawn from what it is and what it's made of.

The shape comes from the item (its SRD base, name, alias); materials and colours come from its name, alias and
note ("silver dagger", "a ruby-set ring", "cloak of midnight blue"); magic items glow in their rarity colour once
identified, and unidentified ones shimmer without giving anything away. Deterministic: the same item always draws
the same picture. Anything without a dedicated drawing falls back to its game-icons.net emblem on a plaque.

item_svg(item, size)  -> 256x256 SVG (transparent background, so it sits on cards, rows and the map)
"""
import hashlib
import math
import re

from . import assets
from .art import darken, lighten, mix, seeded
from .core import item_known

RARITY_GLOW = {"Common": "#c8ccd0", "Uncommon": "#4fd06a", "Rare": "#4a8cf0", "Very Rare": "#b060f0",
               "Legendary": "#f0a030", "Artifact": "#f04a3a"}
METALS = {  # light, mid, dark
    "steel": ("#f2f5f8", "#a9b4be", "#4a525c"), "iron": ("#c8ccd0", "#7a8088", "#383c42"),
    "silver": ("#ffffff", "#c8d0da", "#6a7480"), "gold": ("#fff4c0", "#e0b448", "#7a5418"),
    "bronze": ("#f4d0a0", "#b8783a", "#5a3414"), "copper": ("#f8c0a0", "#c0683a", "#5a2a14"),
    "mithral": ("#f4fbff", "#b8d8f0", "#5a7a9a"), "adamant": ("#c0b8d8", "#5a5474", "#1e1a2a"),
    "obsidian": ("#8a8a9a", "#2a2830", "#0a0a0e"), "bone": ("#fffaf0", "#e0d4b8", "#8a7a5a"),
    "rust": ("#d8a078", "#8a5030", "#3a2010"), "crystal": ("#ffffff", "#b8e8ff", "#4a8ab0"),
    "jade": ("#c8f0d8", "#4aa878", "#1a5a3a"), "wood": ("#d8a878", "#8a5a32", "#3e2410"),
}
MATERIAL_WORDS = [("mithral", "mithral"), ("mithril", "mithral"), ("adamantine", "adamant"), ("gilded", "gold"), ("golden", "gold"),
                  ("gold", "gold"), ("silvered", "silver"), ("silver", "silver"), ("bronze", "bronze"), ("brass", "bronze"),
                  ("copper", "copper"), ("rusted", "rust"), ("rusty", "rust"), ("obsidian", "obsidian"), ("black", "obsidian"),
                  ("ebon", "obsidian"), ("bone", "bone"), ("ivory", "bone"), ("crystal", "crystal"), ("glass", "crystal"),
                  ("jade", "jade"), ("iron", "iron"), ("steel", "steel")]
GEMS = {"ruby": "#d0203a", "garnet": "#9a1a2a", "red": "#d0203a", "blood": "#a01020", "sapphire": "#2a5ad0", "blue": "#2a6ad0",
        "emerald": "#1fa05a", "green": "#2a9a4a", "amethyst": "#9a4ad8", "purple": "#8a3ac8", "violet": "#8a3ac8",
        "diamond": "#e8f6ff", "white": "#eef4f8", "topaz": "#f0a820", "amber": "#e09020", "yellow": "#f0c020",
        "onyx": "#2a2a34", "pearl": "#f4f0e4", "opal": "#cfe8f4", "moonstone": "#d8e4f8", "citrine": "#f0c040",
        "aquamarine": "#5ac8d8", "turquoise": "#2ab8b0", "jet": "#1a1a20", "obsidian": "#1e1c24", "star": "#a8c8ff"}
CLOTH = {"black": "#24222a", "midnight": "#1a1e3a", "white": "#e8e4d8", "grey": "#6a6c72", "gray": "#6a6c72", "red": "#9a2226",
         "crimson": "#8a1a24", "scarlet": "#a82020", "green": "#2f6a34", "forest": "#24402a", "elven": "#3a6a4a",
         "blue": "#2a4a8a", "navy": "#1e2a5a", "purple": "#5a2a7a", "violet": "#6a3a9a", "brown": "#6a4a2a",
         "gold": "#b8902a", "yellow": "#c8a030", "orange": "#c0601e", "teal": "#1f6a6a", "pink": "#b85a7a"}
POTION = [("supreme healing", "#6a0a3a"), ("superior healing", "#8a1048"), ("greater healing", "#b01838"), ("healing", "#d8203a"),
          ("fire breath", "#f06a1a"), ("fire", "#f06a1a"), ("alchemist", "#ff6a1a"), ("poison", "#4a9a2a"), ("acid", "#9ae02a"),
          ("invisibility", "#dff2ff"), ("water breathing", "#2a8ad0"), ("climbing", "#9a7a4a"), ("giant strength", "#c07a3a"),
          ("heroism", "#e0b020"), ("speed", "#f0e04a"), ("flying", "#a0d0ff"), ("mind reading", "#b070d0"),
          ("diminution", "#70c0a0"), ("growth", "#6a9a3a"), ("resistance", "#6a8ac0"), ("animal friendship", "#8aa04a"),
          ("antitoxin", "#b8e0a0"), ("holy water", "#d8f0ff"), ("oil", "#c8a040"), ("perfume", "#e0a0c8"), ("ink", "#1a1a2a"),
          ("longevity", "#f0e8c0"), ("vitality", "#f05a6a"), ("clairvoyance", "#6a5ad0"), ("gaseous", "#c8c8d0"),
          ("philter", "#e060a0"), ("love", "#e060a0"), ("sleep", "#6a6ad0"), ("elixir", "#40c8b0")]

# form keywords, most specific first
FORMS = [
    ("greatsword", "greatsword"), ("longsword", "sword"), ("shortsword", "shortsword"), ("scimitar", "scimitar"),
    ("rapier", "rapier"), ("sword", "sword"), ("blade", "sword"), ("dagger", "dagger"), ("knife", "dagger"), ("stiletto", "dagger"),
    ("sickle", "sickle"), ("greataxe", "greataxe"), ("battleaxe", "axe"), ("battle axe", "axe"), ("handaxe", "handaxe"),
    ("hatchet", "handaxe"), ("axe", "axe"), ("warhammer", "warhammer"), ("light hammer", "hammer"), ("maul", "maul"),
    ("war pick", "pick"), ("morningstar", "morningstar"), ("flail", "flail"), ("mace", "mace"), ("greatclub", "club"),
    ("club", "club"), ("quarterstaff", "staff"), ("staff", "staff"), ("trident", "trident"), ("halberd", "halberd"),
    ("glaive", "halberd"), ("javelin", "javelin"), ("spear", "spear"), ("pike", "spear"), ("lance", "spear"),
    ("light crossbow", "crossbow"), ("hand crossbow", "crossbow"), ("heavy crossbow", "crossbow"), ("crossbow", "crossbow"),
    ("longbow", "bow"), ("shortbow", "bow"), ("bow", "bow"), ("sling", "sling"), ("dart", "dart"), ("blowgun", "blowgun"),
    ("whip", "whip"), ("net", "net"),
    ("wand", "wand"), ("rod", "rod"),
    ("plate", "plate"), ("breastplate", "plate"), ("chain", "chain"), ("ring mail", "chain"), ("scale mail", "chain"),
    ("splint", "chain"), ("studded leather", "leather"), ("leather armor", "leather"), ("padded", "leather"),
    ("hide armor", "leather"), ("shield", "shield"), ("buckler", "shield"), ("helm", "helm"), ("helmet", "helm"),
    ("cloak", "cloak"), ("cape", "cloak"), ("mantle", "cloak"), ("robe", "robe"), ("vestments", "robe"),
    ("boots", "boots"), ("slippers", "boots"), ("gauntlets", "gloves"), ("gloves", "gloves"), ("bracers", "bracers"),
    ("belt", "belt"), ("girdle", "belt"), ("hat", "hat"), ("headband", "circlet"), ("circlet", "circlet"),
    ("crown", "crown"), ("diadem", "circlet"), ("tiara", "circlet"),
    ("ring", "ring"), ("signet", "ring"), ("amulet", "amulet"), ("necklace", "amulet"), ("periapt", "amulet"),
    ("pendant", "amulet"), ("medallion", "amulet"), ("talisman", "amulet"), ("brooch", "amulet"), ("locket", "amulet"),
    ("holy symbol", "holy"), ("reliquary", "holy"), ("emblem", "holy"),
    ("potion", "potion"), ("philter", "potion"), ("elixir", "potion"), ("oil of", "vial"), ("flask of oil", "vial"),
    ("antitoxin", "vial"), ("vial", "vial"), ("poison", "vial"), ("acid", "vial"), ("alchemist", "vial"),
    ("holy water", "vial"), ("perfume", "vial"), ("ink", "vial"),
    ("spell scroll", "scroll"), ("scroll", "scroll"), ("spellbook", "book"), ("tome", "book"), ("manual", "book"),
    ("book", "book"), ("journal", "book"), ("ledger", "book"), ("diary", "book"), ("grimoire", "book"),
    ("letter", "letter"), ("note", "letter"), ("deed", "letter"), ("writ", "letter"), ("contract", "letter"),
    ("invitation", "letter"), ("map", "map"), ("chart", "map"), ("key", "key"),
    ("gem", "gem"), ("ruby", "gem"), ("sapphire", "gem"), ("emerald", "gem"), ("diamond", "gem"), ("pearl", "gem"),
    ("jewel", "gem"), ("luckstone", "gem"), ("ioun", "gem"), ("stone", "gem"), ("crystal", "orb"),
    ("coin", "coin"), ("token", "coin"), ("chit", "coin"), ("orb", "orb"), ("crystal ball", "orb"),
    ("backpack", "backpack"), ("pack", "backpack"), ("knapsack", "backpack"), ("bag", "pouch"), ("pouch", "pouch"),
    ("sack", "pouch"), ("purse", "pouch"), ("chest", "chest"), ("coffer", "chest"), ("box", "chest"), ("casket", "chest"),
    ("candle", "candle"), ("torch", "torch"), ("lantern", "lantern"), ("lamp", "lantern"), ("rope", "rope"),
    ("arrows", "arrows"), ("arrow", "arrows"), ("bolts", "arrows"), ("quiver", "arrows"), ("needles", "arrows"),
    ("bullets", "coin"), ("lute", "lute"), ("lyre", "lute"), ("viol", "lute"), ("instrument", "lute"),
    ("horn", "horn"), ("flute", "flute"), ("pan flute", "flute"), ("pipes", "flute"), ("drum", "drum"),
    ("thieves", "kit"), ("lockpick", "kit"), ("tools", "kit"), ("kit", "kit"), ("supplies", "kit"),
    ("waterskin", "waterskin"), ("flask", "waterskin"), ("bottle", "vial"), ("rations", "rations"), ("bread", "rations"),
    ("mirror", "mirror"), ("figurine", "figurine"), ("statuette", "figurine"), ("idol", "figurine"),
    ("feather", "feather"), ("quill", "feather"), ("bedroll", "bedroll"), ("blanket", "bedroll"),
    ("crowbar", "crowbar"), ("clothes", "tunic"), ("costume", "tunic"), ("vestment", "robe"), ("tunic", "tunic"),
    ("dust", "pouch"), ("bead", "amulet"), ("bell", "bell"), ("hourglass", "hourglass"), ("caltrops", "caltrops"),
]


def _text(item):
    return " ".join(str(item.get(k) or "") for k in ("alias", "name", "base_name", "note", "meta")).lower()


def form_of(item):
    base = f"{item.get('base_name') or ''} {item.get('name') or ''} {item.get('alias') or ''}".lower()
    for key, form in FORMS:
        if re.search(r"\b" + re.escape(key), base):
            return form
    kind = item.get("kind")
    if kind == "weapon":
        return "sword"
    if kind == "armor":
        return "shield" if item.get("category") == "shield" else "leather"
    if kind == "consumable":
        return "potion"
    return None


def palette(item):
    t = _text(item)
    r = seeded("item", item.get("name"), item.get("alias"), item.get("id"))
    metal = next((m for w, m in MATERIAL_WORDS if re.search(r"\b" + w, t)), None)
    gem = next((c for w, c in GEMS.items() if re.search(r"\b" + w, t)), None)
    cloth = next((c for w, c in CLOTH.items() if re.search(r"\b" + w, t)), None)
    liquid = next((c for w, c in POTION if w in t), None)
    known = item_known(item)
    rar = item.get("rarity") if known else None
    magic = bool(item.get("magic"))
    return {"metal": METALS[metal or "steel"], "trim": METALS["gold" if metal != "silver" and (magic or r.random() < .45) else "silver"],
            "gem": gem or r.choice(["#d0203a", "#2a5ad0", "#1fa05a", "#9a4ad8", "#f0a820"]),
            "cloth": cloth or r.choice(["#6a2a2a", "#2a4a6a", "#3a5a2a", "#4a2a5a", "#5a4a2a", "#2a2a34"]),
            "liquid": liquid or r.choice(["#d8203a", "#2a8ad0", "#4ab06a", "#b070d0", "#e0a020"]),
            "wood": METALS["obsidian" if metal == "obsidian" else "bone" if metal == "bone" else "wood"],
            "leather": ("#b07a4a", "#6a4020", "#2a160a"), "magic": magic, "known": known,
            "glow": (RARITY_GLOW.get(rar, "#e0c070") if magic and known else "#a88af0" if magic else None),
            "rare": rar, "rng": r, "has_metal": bool(metal), "has_gem": bool(gem)}


# ============================================================== drawing kit

def _grad(pid, stops, x2=1, y2=0):
    s = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in stops)
    return f'<linearGradient id="{pid}" x1="0" y1="0" x2="{x2}" y2="{y2}">{s}</linearGradient>'


def _defs(P, pal):
    m, t, w, lth = pal["metal"], pal["trim"], pal["wood"], pal["leather"]
    g = pal["gem"]
    return ("<defs>" + _grad(f"{P}m", [(0, m[0]), (.45, m[1]), (1, m[2])]) + _grad(f"{P}mv", [(0, m[0]), (.5, m[1]), (1, m[2])], 0, 1)
            + _grad(f"{P}t", [(0, t[0]), (.5, t[1]), (1, t[2])]) + _grad(f"{P}w", [(0, w[0]), (.5, w[1]), (1, w[2])])
            + _grad(f"{P}l", [(0, lth[0]), (.5, lth[1]), (1, lth[2])])
            + _grad(f"{P}c", [(0, lighten(pal["cloth"], .25)), (1, darken(pal["cloth"], .45))], 0, 1)
            + _grad(f"{P}p", [(0, "#fbf3dc"), (1, "#dcc79a")], 0, 1)
            + f'<radialGradient id="{P}g" cx="35%" cy="30%"><stop offset="0" stop-color="{lighten(g, .7)}"/>'
              f'<stop offset=".45" stop-color="{g}"/><stop offset="1" stop-color="{darken(g, .55)}"/></radialGradient>'
            + f'<radialGradient id="{P}aura"><stop offset="0" stop-color="{pal["glow"] or "#fff"}" stop-opacity=".55"/>'
              f'<stop offset=".6" stop-color="{pal["glow"] or "#fff"}" stop-opacity=".12"/><stop offset="1" stop-color="{pal["glow"] or "#fff"}" stop-opacity="0"/></radialGradient>'
            + f'<filter id="{P}sh" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="3" dy="5" stdDeviation="4" flood-color="#000" flood-opacity=".45"/></filter>'
            + f'<filter id="{P}gl" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
            + "</defs>")


def _gem(P, x, y, r):
    return (f'<circle cx="{x}" cy="{y}" r="{r}" fill="url(#{P}g)" stroke="#1a1410" stroke-opacity=".5" stroke-width="1.2"/>'
            f'<path d="M{x - r * .6},{y - r * .1} L{x},{y - r * .7} L{x + r * .6},{y - r * .1}" fill="none" stroke="#fff" stroke-opacity=".45" stroke-width="1"/>'
            f'<circle cx="{x - r * .35}" cy="{y - r * .35}" r="{max(1, r * .22):.1f}" fill="#fff" fill-opacity=".85"/>')


def _rot(inner, deg):
    return f'<g transform="rotate({deg} 128 128)">{inner}</g>'


def _outline():
    return 'stroke="#15100c" stroke-width="2.2" stroke-linejoin="round"'


# ---------------------------------------------------------------- weapons

def _sword(P, pal, form):
    O = _outline()
    top, bw, guard, grip = {"greatsword": (8, 15, 176, 36), "shortsword": (46, 11, 170, 30), "dagger": (84, 10, 168, 28),
                            "rapier": (14, 4, 170, 32)}.get(form, (22, 12, 172, 32))
    if form == "scimitar":
        blade = f'<path d="M116,{guard} C108,130 112,70 154,22 C146,66 146,120 140,{guard} Z" fill="url(#{P}m)" {O}/>' \
                f'<path d="M124,{guard - 6} C120,130 124,80 148,36" fill="none" stroke="{pal["metal"][0]}" stroke-width="2" stroke-opacity=".8"/>'
    else:
        blade = (f'<path d="M128,{top} L{128 + bw},{top + bw * 2.2:.0f} L{128 + bw},{guard} L{128 - bw},{guard} L{128 - bw},{top + bw * 2.2:.0f} Z" fill="url(#{P}m)" {O}/>'
                 f'<path d="M128,{top + bw * 2 + 6:.0f} L128,{guard - 8}" stroke="{pal["metal"][2]}" stroke-width="{max(1.5, bw / 4):.1f}" stroke-opacity=".7"/>'
                 f'<path d="M{128 - bw + 3},{top + bw * 2.4:.0f} L{128 - bw + 3},{guard - 4}" stroke="#fff" stroke-width="1.5" stroke-opacity=".55"/>')
    gw = {"greatsword": 44, "dagger": 22, "rapier": 30}.get(form, 34)
    if form == "rapier":
        hilt = (f'<path d="M{128 - gw},{guard} Q128,{guard + 10} {128 + gw},{guard}" fill="none" stroke="url(#{P}t)" stroke-width="6" stroke-linecap="round"/>'
                f'<path d="M{128 + gw - 4},{guard} C{128 + gw + 16},{guard + 30} 150,{guard + grip + 6} 134,{guard + grip + 8}" fill="none" stroke="url(#{P}t)" stroke-width="4"/>'
                f'<ellipse cx="128" cy="{guard + 4}" rx="16" ry="6" fill="none" stroke="url(#{P}t)" stroke-width="4"/>')
    else:
        hilt = (f'<path d="M{128 - gw},{guard - 4} Q{128 - gw - 8},{guard + 2} {128 - gw - 2},{guard + 10} L{128 + gw + 2},{guard + 10} '
                f'Q{128 + gw + 8},{guard + 2} {128 + gw},{guard - 4} Z" fill="url(#{P}t)" {O}/>'
                + _gem(P, 128, guard + 3, 5))
    g0 = guard + 10
    grip_s = (f'<rect x="121" y="{g0}" width="14" height="{grip}" rx="3" fill="url(#{P}l)" {O}/>'
              + "".join(f'<path d="M121,{g0 + 5 + i * 7} L135,{g0 + 1 + i * 7}" stroke="#1a0e06" stroke-width="1.5" stroke-opacity=".7"/>' for i in range(grip // 7)))
    pom = f'<circle cx="128" cy="{g0 + grip + 7}" r="{9 if form != "dagger" else 7}" fill="url(#{P}t)" {O}/>'
    return _rot(blade + grip_s + hilt + pom, 45 if form != "scimitar" else 38)


def _sickle(P, pal):
    O = _outline()
    return _rot(f'<path d="M128,120 C126,60 176,30 206,56 C176,48 146,70 140,122 Z" fill="url(#{P}m)" {O}/>'
                f'<rect x="120" y="118" width="16" height="96" rx="5" fill="url(#{P}w)" {O}/>', 20)


def _haft(P, top=24, bot=238, w=12):
    return (f'<rect x="{128 - w / 2}" y="{top}" width="{w}" height="{bot - top}" rx="{w / 2}" fill="url(#{P}w)" {_outline()}/>'
            f'<path d="M{128 - w / 4},{top + 10} L{128 - w / 4},{bot - 10}" stroke="#fff" stroke-opacity=".18" stroke-width="2"/>'
            f'<rect x="{128 - w / 2 - 1}" y="{bot - 58}" width="{w + 2}" height="40" rx="3" fill="url(#{P}l)" stroke="#15100c" stroke-width="1.5"/>')


def _axe(P, pal, form):
    O = _outline()
    head = (f'<path d="M134,46 C170,40 202,20 214,30 C224,64 220,110 206,132 C196,112 170,98 134,100 Z" fill="url(#{P}m)" {O}/>'
            f'<path d="M208,36 C218,64 216,104 206,126" fill="none" stroke="#fff" stroke-opacity=".6" stroke-width="2.5"/>')
    if form == "greataxe":
        head += (f'<path d="M122,46 C86,40 54,20 42,30 C32,64 36,110 50,132 C60,112 86,98 122,100 Z" fill="url(#{P}m)" {O}/>')
    elif form != "handaxe":
        head += f'<path d="M122,58 L96,66 L96,84 L122,90 Z" fill="url(#{P}m)" {O}/>'
    head += f'<rect x="118" y="40" width="20" height="64" rx="4" fill="url(#{P}t)" {O}/>'
    bot = 238 if form != "handaxe" else 200
    inner = _haft(P, 30, bot) + head
    if form == "handaxe":
        inner = f'<g transform="translate(0 20)">{inner}</g>'
    return _rot(inner, 32)


def _hammer(P, pal, form):
    O = _outline()
    if form in ("warhammer", "hammer", "maul"):
        hw, hh = (48, 30) if form != "maul" else (62, 44)
        head = (f'<rect x="{128 - hw}" y="30" width="{hw * 2}" height="{hh}" rx="6" fill="url(#{P}mv)" {O}/>'
                f'<rect x="{128 - 10}" y="26" width="20" height="{hh + 8}" rx="3" fill="url(#{P}t)" {O}/>'
                f'<path d="M{128 - hw + 4},34 L{128 - hw + 4},{26 + hh}" stroke="#fff" stroke-opacity=".5" stroke-width="2"/>')
        if form == "warhammer":
            head = head.replace(f'x="{128 - hw}" y="30" width="{hw * 2}"', f'x="{128 - hw}" y="30" width="{hw + 10}"')
            head += f'<path d="M138,32 L200,46 L138,58 Z" fill="url(#{P}m)" {O}/>'
    elif form == "pick":
        head = (f'<path d="M60,70 C90,30 166,30 196,70 C166,50 90,50 60,70 Z" fill="url(#{P}m)" {O}/>'
                f'<rect x="118" y="36" width="20" height="30" rx="3" fill="url(#{P}t)" {O}/>')
    elif form == "morningstar":
        spikes = "".join(f'<path d="M{128 + 30 * math.cos(math.radians(a)):.0f},{62 + 30 * math.sin(math.radians(a)):.0f} '
                         f'L{128 + 50 * math.cos(math.radians(a)):.0f},{62 + 50 * math.sin(math.radians(a)):.0f}" stroke="url(#{P}m)" stroke-width="7" stroke-linecap="round"/>'
                         for a in range(0, 360, 40))
        head = spikes + f'<circle cx="128" cy="62" r="32" fill="url(#{P}mv)" {O}/>'
    elif form == "flail":
        chain = "".join(f'<ellipse cx="{150 + i * 9}" cy="{78 - i * 12}" rx="4" ry="7" fill="none" stroke="{pal["metal"][1]}" stroke-width="3"/>' for i in range(4))
        spikes = "".join(f'<path d="M{190 + 20 * math.cos(math.radians(a)):.0f},{24 + 20 * math.sin(math.radians(a)):.0f} L{190 + 34 * math.cos(math.radians(a)):.0f},{24 + 34 * math.sin(math.radians(a)):.0f}" stroke="url(#{P}m)" stroke-width="5" stroke-linecap="round"/>' for a in range(0, 360, 45))
        return _rot(_haft(P, 90, 238) + f'<rect x="120" y="84" width="16" height="14" rx="3" fill="url(#{P}t)"/>' + chain + spikes
                    + f'<circle cx="190" cy="24" r="22" fill="url(#{P}mv)" {O}/>', 20)
    elif form == "club":
        return _rot(f'<path d="M116,238 L112,110 C106,60 118,24 128,24 C150,24 156,60 146,110 L140,238 Z" fill="url(#{P}w)" {O}/>'
                    + "".join(f'<ellipse cx="{128 + (i % 2) * 8 - 4}" cy="{60 + i * 22}" rx="4" ry="2.5" fill="{pal["wood"][2]}" fill-opacity=".6"/>' for i in range(4)), 35)
    else:  # mace
        head = (f'<ellipse cx="128" cy="64" rx="28" ry="34" fill="url(#{P}mv)" {O}/>'
                + "".join(f'<path d="M{128 + s * 26},{40 + i * 16} L{128 + s * 44},{46 + i * 16} L{128 + s * 26},{56 + i * 16} Z" fill="url(#{P}m)" {O}/>'
                          for s in (-1, 1) for i in range(3)))
    return _rot(_haft(P, 40, 238) + head, 35)


def _polearm(P, pal, form):
    O = _outline()
    shaft = _haft(P, 50 if form != "javelin" else 70, 246 if form != "javelin" else 226, 10)
    if form == "trident":
        tip = (f'<path d="M100,70 L100,30 L94,34 L100,12 L106,34 L100,30 M156,70 L156,30 L150,34 L156,12 L162,34 L156,30" fill="url(#{P}m)" stroke="#15100c" stroke-width="2"/>'
               f'<path d="M98,74 Q128,92 158,74 L158,66 Q128,82 98,66 Z" fill="url(#{P}m)" {O}/>'
               f'<path d="M128,76 L128,18 L122,24 L128,4 L134,24 L128,18" fill="url(#{P}m)" stroke="#15100c" stroke-width="2.2"/>')
    elif form == "halberd":
        tip = (f'<path d="M128,6 L138,40 L128,74 L118,40 Z" fill="url(#{P}m)" {O}/>'
               f'<path d="M134,56 C170,50 196,40 204,48 C208,78 206,104 196,118 C186,104 164,98 134,100 Z" fill="url(#{P}m)" {O}/>'
               f'<path d="M122,64 L98,78 L122,88 Z" fill="url(#{P}m)" {O}/>')
    else:
        top = 10 if form != "javelin" else 34
        tip = (f'<path d="M128,{top} C142,{top + 24} 142,{top + 44} 128,{top + 64} C114,{top + 44} 114,{top + 24} 128,{top} Z" fill="url(#{P}m)" {O}/>'
               f'<path d="M128,{top + 8} L128,{top + 58}" stroke="{pal["metal"][2]}" stroke-width="2"/>'
               f'<rect x="122" y="{top + 60}" width="12" height="12" rx="2" fill="url(#{P}t)" {O}/>')
    return _rot(shaft + tip, 40)


def _bow(P, pal, form):
    O = _outline()
    if form == "crossbow":
        return _rot(f'<rect x="118" y="60" width="20" height="176" rx="6" fill="url(#{P}w)" {O}/>'
                    f'<path d="M36,96 Q128,40 220,96" fill="none" stroke="#15100c" stroke-width="12" stroke-linecap="round"/>'
                    f'<path d="M36,96 Q128,40 220,96" fill="none" stroke="url(#{P}m)" stroke-width="8" stroke-linecap="round"/>'
                    f'<path d="M38,98 L128,120 L218,98" fill="none" stroke="#e8e0cc" stroke-width="2"/>'
                    f'<path d="M128,20 L128,120" stroke="{pal["metal"][1]}" stroke-width="4"/><path d="M122,28 L128,14 L134,28 Z" fill="url(#{P}m)"/>'
                    f'<rect x="120" y="150" width="16" height="30" rx="3" fill="url(#{P}t)"/>', 0)
    if form == "sling":
        return (f'<path d="M60,40 C80,120 110,170 128,190 C146,170 176,120 196,40" fill="none" stroke="url(#{P}l)" stroke-width="7" stroke-linecap="round"/>'
                f'<ellipse cx="128" cy="192" rx="26" ry="16" fill="url(#{P}l)" {O}/><circle cx="128" cy="186" r="11" fill="#8a8a90" {O}/>')
    if form in ("dart", "blowgun"):
        return _rot(f'<rect x="122" y="20" width="12" height="200" rx="6" fill="url(#{P}w)" {O}/>' if form == "blowgun" else
                    f'<path d="M128,20 L136,70 L128,200 L120,70 Z" fill="url(#{P}m)" {O}/><path d="M128,190 L150,230 L128,214 L106,230 Z" fill="#c8402a" {O}/>', 45)
    long = form == "bow" and "short" not in form
    return _rot(f'<path d="M96,14 C176,60 176,196 96,242" fill="none" stroke="#15100c" stroke-width="13" stroke-linecap="round"/>'
                f'<path d="M96,14 C176,60 176,196 96,242" fill="none" stroke="url(#{P}w)" stroke-width="9" stroke-linecap="round"/>'
                f'<path d="M96,14 L96,242" stroke="#efe6cc" stroke-width="2"/>'
                f'<rect x="146" y="112" width="12" height="32" rx="3" fill="url(#{P}l)" stroke="#15100c" stroke-width="1.5"/>'
                f'<path d="M60,128 L190,128" stroke="{pal["wood"][1]}" stroke-width="3"/><path d="M190,128 l-12,-6 l0,12 Z" fill="url(#{P}m)"/>'
                f'<path d="M60,128 l10,-8 l6,8 l-6,8 Z" fill="#c8402a"/>', 30 if long else 30)


def _whip(P, pal):
    return (f'<rect x="40" y="170" width="54" height="16" rx="6" fill="url(#{P}l)" {_outline()} transform="rotate(-35 67 178)"/>'
            f'<path d="M86,158 C140,110 220,150 196,196 C176,232 110,214 150,180 C176,160 214,176 222,150" fill="none" stroke="#3a2212" stroke-width="7" stroke-linecap="round"/>'
            f'<path d="M86,158 C140,110 220,150 196,196 C176,232 110,214 150,180 C176,160 214,176 222,150" fill="none" stroke="#8a5a32" stroke-width="3.5" stroke-linecap="round"/>')


def _staff(P, pal, form):
    O = _outline()
    if form == "wand":
        glow = pal["glow"] or pal["gem"]
        return _rot(f'<path d="M124,230 L120,70 C120,58 136,58 136,70 L132,230 Z" fill="url(#{P}w)" {O}/>'
                    f'<rect x="119" y="176" width="18" height="40" rx="4" fill="url(#{P}t)" {O}/>'
                    f'<circle cx="128" cy="50" r="18" fill="{glow}" fill-opacity=".35" filter="url(#{P}gl)"/>' + _gem(P, 128, 52, 10), 35)
    if form == "rod":
        return _rot(f'<rect x="120" y="60" width="16" height="176" rx="5" fill="url(#{P}m)" {O}/>'
                    f'<path d="M104,40 L128,20 L152,40 L146,70 L110,70 Z" fill="url(#{P}t)" {O}/>' + _gem(P, 128, 46, 10)
                    + f'<rect x="116" y="200" width="24" height="14" rx="4" fill="url(#{P}t)" {O}/>', 35)
    top = (f'<path d="M128,50 C104,50 96,24 112,14 C126,6 146,14 144,32" fill="none" stroke="url(#{P}w)" stroke-width="10" stroke-linecap="round"/>'
           if pal["rng"].random() < .4 and not pal["magic"] else
           f'<circle cx="128" cy="30" r="22" fill="{pal["glow"] or pal["gem"]}" fill-opacity=".3" filter="url(#{P}gl)"/>' + _gem(P, 128, 30, 14)
           + f'<path d="M110,44 Q128,64 146,44" fill="none" stroke="url(#{P}w)" stroke-width="6"/>')
    return _rot(f'<path d="M122,246 L120,52 C120,44 136,44 136,52 L134,246 Z" fill="url(#{P}w)" {O}/>'
                + "".join(f'<ellipse cx="{128 + (i % 2) * 4 - 2}" cy="{90 + i * 34}" rx="3" ry="2" fill="{pal["wood"][2]}"/>' for i in range(4))
                + f'<rect x="119" y="130" width="18" height="34" rx="3" fill="url(#{P}l)" stroke="#15100c" stroke-width="1.5"/>' + top, 30)


# ---------------------------------------------------------------- armor & clothing

def _armor(P, pal, form):
    O = _outline()
    torso = "M72,64 C92,50 108,46 128,56 C148,46 164,50 184,64 L200,104 L186,116 L184,196 C160,214 96,214 72,196 L70,116 L56,104 Z"
    if form == "plate":
        return (f'<path d="{torso}" fill="url(#{P}m)" {O}/>'
                f'<path d="M128,58 L128,206" stroke="#fff" stroke-opacity=".5" stroke-width="2.5"/>'
                f'<path d="M84,140 Q128,160 172,140 M86,172 Q128,190 170,172" fill="none" stroke="{pal["metal"][2]}" stroke-width="2"/>'
                f'<path d="M50,78 C54,52 96,48 102,74 L96,108 C82,112 58,106 50,78 Z" fill="url(#{P}m)" {O}/>'
                f'<path d="M206,78 C202,52 160,48 154,74 L160,108 C174,112 198,106 206,78 Z" fill="url(#{P}m)" {O}/>'
                f'<path d="M108,58 Q128,76 148,58 L148,48 Q128,62 108,48 Z" fill="url(#{P}t)" {O}/>'
                + "".join(f'<circle cx="{x}" cy="{y}" r="2.5" fill="{pal["trim"][0]}"/>' for x, y in ((70, 70), (82, 64), (186, 70), (174, 64))))
    if form == "chain":
        pat = f'<pattern id="{P}ch" width="8" height="7" patternUnits="userSpaceOnUse"><rect width="8" height="7" fill="{pal["metal"][2]}"/><circle cx="4" cy="3.5" r="2.7" fill="none" stroke="{pal["metal"][0]}" stroke-width="1.2"/></pattern>'
        return (f'<defs>{pat}</defs><path d="{torso}" fill="url(#{P}ch)" {O}/>'
                f'<path d="M104,56 Q128,82 152,56" fill="none" stroke="{pal["metal"][1]}" stroke-width="8"/>'
                f'<path d="M72,176 L184,176 L186,196 C160,214 96,214 70,196 Z" fill="url(#{P}l)" {O}/>'
                f'<rect x="120" y="172" width="16" height="14" rx="2" fill="url(#{P}t)"/>')
    return (f'<path d="{torso}" fill="url(#{P}l)" {O}/>'
            f'<path d="M104,56 L128,110 L152,56" fill="{pal["leather"][2]}" stroke="#15100c" stroke-width="2"/>'
            + "".join(f'<path d="M122,{122 + i * 16} L134,{128 + i * 16} M134,{122 + i * 16} L122,{128 + i * 16}" stroke="#e8d0a8" stroke-width="1.6"/>' for i in range(4))
            + f'<path d="M78,80 Q96,130 86,196 M178,80 Q160,130 170,196" fill="none" stroke="#e8d0a8" stroke-width="1.4" stroke-dasharray="4 3"/>'
            + ("".join(f'<circle cx="{x}" cy="{y}" r="2.4" fill="{pal["metal"][1]}"/>' for x in (92, 110, 146, 164) for y in (100, 140, 180)) if "stud" in form else ""))


def _shield(P, pal, item):
    O = _outline()
    t = _text(item)
    col = pal["cloth"]
    if re.search(r"round|buckler|wood", t):
        return (f'<circle cx="128" cy="128" r="96" fill="url(#{P}w)" {O}/>'
                + "".join(f'<path d="M{128 + 92 * math.cos(math.radians(a)):.0f},{128 + 92 * math.sin(math.radians(a)):.0f} L128,128" stroke="{pal["wood"][2]}" stroke-width="1.5"/>' for a in range(0, 360, 30))
                + f'<circle cx="128" cy="128" r="96" fill="none" stroke="url(#{P}m)" stroke-width="10"/>'
                f'<circle cx="128" cy="128" r="26" fill="url(#{P}mv)" {O}/><circle cx="120" cy="120" r="6" fill="#fff" fill-opacity=".5"/>')
    heater = "M40,40 L216,40 L216,110 C216,170 176,206 128,232 C80,206 40,170 40,110 Z"
    return (f'<path d="{heater}" fill="{col}" {O}/>'
            f'<path d="{heater}" fill="none" stroke="url(#{P}m)" stroke-width="10"/>'
            f'<path d="M128,44 L128,226 M44,110 L212,110" stroke="{pal["trim"][1]}" stroke-width="10" stroke-opacity=".85"/>'
            f'<path d="M64,56 L110,56 L110,98 C96,98 64,96 64,56 Z" fill="#fff" fill-opacity=".15"/>'
            + _gem(P, 128, 110, 11))


def _helm(P, pal):
    O = _outline()
    return (f'<path d="M52,150 C52,70 88,36 128,36 C168,36 204,70 204,150 L204,196 L168,196 L164,148 L92,148 L88,196 L52,196 Z" fill="url(#{P}m)" {O}/>'
            f'<path d="M120,148 L136,148 L134,206 L122,206 Z" fill="url(#{P}m)" {O}/>'
            f'<path d="M60,120 L196,120" stroke="{pal["metal"][2]}" stroke-width="3"/>'
            f'<path d="M128,36 C136,20 150,14 168,16" fill="none" stroke="{pal["cloth"]}" stroke-width="10" stroke-linecap="round"/>'
            f'<path d="M72,70 C84,52 104,44 120,42" fill="none" stroke="#fff" stroke-opacity=".6" stroke-width="3"/>')


def _cloak(P, pal, form):
    O = _outline()
    if form in ("robe", "tunic"):
        return (f'<path d="M96,40 L160,40 L214,92 L196,114 L172,96 L178,226 L78,226 L84,96 L60,114 L42,92 Z" fill="url(#{P}c)" {O}/>'
                f'<path d="M110,40 L128,78 L146,40" fill="{darken(pal["cloth"], .3)}" stroke="#15100c" stroke-width="1.6"/>'
                + (f'<path d="M128,78 L128,226" stroke="{pal["trim"][1]}" stroke-width="3"/><path d="M84,200 L172,200" stroke="{pal["trim"][1]}" stroke-width="4"/>' if form == "robe" else
                   f'<path d="M84,150 L172,150" stroke="#5a3a1e" stroke-width="8"/>'))
    return (f'<path d="M90,52 C60,110 44,170 36,228 C80,214 176,214 220,228 C212,170 196,110 166,52 Z" fill="url(#{P}c)" {O}/>'
            f'<path d="M92,56 C88,30 106,16 128,16 C150,16 168,30 164,56 C150,70 106,70 92,56 Z" fill="{darken(pal["cloth"], .2)}" {O}/>'
            f'<path d="M104,54 C104,36 114,28 128,28 C142,28 152,36 152,54 Z" fill="#000" fill-opacity=".55"/>'
            + "".join(f'<path d="M{104 + i * 16},76 C{100 + i * 18},140 {96 + i * 20},190 {92 + i * 22},220" fill="none" stroke="{darken(pal["cloth"], .45)}" stroke-width="2" stroke-opacity=".6"/>' for i in range(4))
            + f'<circle cx="128" cy="70" r="10" fill="url(#{P}t)" {O}/>')


def _boots(P, pal):
    O = _outline()
    one = lambda dx: (f'<path d="M{dx + 40},40 L{dx + 84},40 L{dx + 86},150 C{dx + 110},160 {dx + 124},170 {dx + 124},192 L{dx + 36},192 L{dx + 36},150 Z" fill="url(#{P}l)" {O}/>'  # noqa: E731
                      f'<path d="M{dx + 36},40 L{dx + 88},40 L{dx + 88},60 L{dx + 36},60 Z" fill="{pal["leather"][2]}" {O}/>'
                      f'<path d="M{dx + 36},184 L{dx + 124},184" stroke="#15100c" stroke-width="5"/>')
    return one(8) + one(80)


def _gloves(P, pal, form):
    O = _outline()
    fill = f"url(#{P}m)" if form == "gloves" and "gauntlet" in pal.get("_t", "") else f"url(#{P}l)"
    one = lambda dx, fl: (f'<g transform="translate({dx} 0) scale({fl} 1) translate({-128 if fl < 0 else 0} 0)"><path d="M40,210 L40,120 C40,110 48,104 56,108 L56,60 C56,50 70,50 70,60 L70,100 L72,48 C72,38 86,38 86,48 L86,100 L90,54 '  # noqa: E731
                          f'C90,44 104,44 104,54 L102,108 L106,74 C106,64 120,64 120,74 L116,150 L104,210 Z" fill="{fill}" {O}/>'
                          f'<rect x="36" y="196" width="72" height="22" rx="4" fill="{pal["cloth"]}" {O}/></g>')
    return one(0, 1) + one(256, -1)


def _belt(P, pal):
    O = _outline()
    return (f'<path d="M20,130 C60,104 196,104 236,130 L236,158 C196,132 60,132 20,158 Z" fill="url(#{P}l)" {O}/>'
            f'<rect x="104" y="104" width="48" height="52" rx="6" fill="none" stroke="url(#{P}t)" stroke-width="8"/>'
            f'<path d="M128,110 L128,150" stroke="url(#{P}t)" stroke-width="5"/>'
            + "".join(f'<circle cx="{x}" cy="{128 + abs(x - 128) * .05:.0f}" r="3" fill="{pal["trim"][1]}"/>' for x in (44, 70, 186, 212)))


def _bracers(P, pal):
    O = _outline()
    one = lambda x: (f'<path d="M{x},60 L{x + 70},52 L{x + 76},200 L{x - 6},196 Z" fill="url(#{P}l)" {O}/>'  # noqa: E731
                     f'<path d="M{x + 4},80 L{x + 70},74 M{x + 2},176 L{x + 72},172" stroke="url(#{P}t)" stroke-width="6"/>'
                     + _gem(P, x + 36, 126, 9))
    return one(28) + one(152)


def _hat(P, pal):
    O = _outline()
    return (f'<ellipse cx="128" cy="186" rx="110" ry="30" fill="{darken(pal["cloth"], .15)}" {O}/>'
            f'<path d="M70,186 C80,120 110,60 150,20 C144,70 170,120 186,186 Z" fill="url(#{P}c)" {O}/>'
            f'<path d="M76,168 Q128,150 182,168 L184,182 Q128,164 74,182 Z" fill="url(#{P}t)"/>')


def _circlet(P, pal, form):
    O = _outline()
    if form == "crown":
        pts = " ".join(f"{40 + i * 22},{(90 if i % 2 == 0 else 128)}" for i in range(9))
        return (f'<path d="M40,184 L{pts} L216,184 Q128,204 40,184 Z" fill="url(#{P}t)" {O}/>'
                + "".join(_gem(P, 40 + i * 44, 150, 7) for i in range(1, 4)) + "".join(f'<circle cx="{40 + i * 44}" cy="88" r="6" fill="url(#{P}t)" {O}/>' for i in range(5)))
    return (f'<ellipse cx="128" cy="138" rx="96" ry="46" fill="none" stroke="#15100c" stroke-width="13"/>'
            f'<ellipse cx="128" cy="138" rx="96" ry="46" fill="none" stroke="url(#{P}t)" stroke-width="9"/>'
            f'<path d="M128,166 L142,184 L128,202 L114,184 Z" fill="url(#{P}t)" {O}/>' + _gem(P, 128, 184, 9))


# ---------------------------------------------------------------- jewelry & holy

def _ring(P, pal):
    return (f'<ellipse cx="128" cy="150" rx="70" ry="62" fill="none" stroke="#15100c" stroke-width="26"/>'
            f'<ellipse cx="128" cy="150" rx="70" ry="62" fill="none" stroke="url(#{P}t)" stroke-width="20"/>'
            f'<path d="M72,130 C80,104 100,92 118,90" fill="none" stroke="#fff" stroke-opacity=".6" stroke-width="3"/>'
            f'<path d="M100,92 L128,70 L156,92 L128,112 Z" fill="url(#{P}t)" {_outline()}/>' + _gem(P, 128, 76, 22))


def _amulet(P, pal, holy=False):
    chain = "".join(f'<ellipse cx="{128 + 80 * math.sin(math.radians(a)):.0f}" cy="{40 + 90 * (1 - math.cos(math.radians(a))) * .9:.0f}" rx="4" ry="6" '
                    f'fill="none" stroke="{pal["trim"][1]}" stroke-width="2.5" transform="rotate({a} {128 + 80 * math.sin(math.radians(a)):.0f} {40 + 90 * (1 - math.cos(math.radians(a))) * .9:.0f})"/>'
                    for a in range(-90, 91, 12))
    if holy:
        rays = "".join(f'<path d="M128,170 L{128 + 58 * math.cos(math.radians(a)):.0f},{170 + 58 * math.sin(math.radians(a)):.0f}" stroke="url(#{P}t)" stroke-width="8" stroke-linecap="round"/>' for a in range(0, 360, 30))
        return chain + rays + f'<circle cx="128" cy="170" r="30" fill="url(#{P}t)" {_outline()}/><circle cx="128" cy="170" r="16" fill="none" stroke="{pal["trim"][2]}" stroke-width="3"/>'
    return (chain + f'<path d="M128,120 L166,160 L128,222 L90,160 Z" fill="url(#{P}t)" {_outline()}/>' + _gem(P, 128, 164, 22))


# ---------------------------------------------------------------- consumables & documents

def _potion(P, pal, form):
    O = _outline()
    liq = pal["liquid"]
    clear = liq in ("#dff2ff", "#d8f0ff")
    if form == "vial":
        body = "M104,60 L152,60 L152,200 C152,226 104,226 104,200 Z"
        return (f'<defs><clipPath id="{P}v"><path d="{body}"/></clipPath></defs>'
                f'<path d="{body}" fill="#dff0f8" fill-opacity=".25" {O}/>'
                f'<g clip-path="url(#{P}v)"><rect x="96" y="110" width="64" height="130" fill="{liq}" fill-opacity="{.4 if clear else .9}"/>'
                f'<ellipse cx="128" cy="110" rx="26" ry="5" fill="{lighten(liq, .35)}"/></g>'
                f'<path d="M112,70 L112,196" stroke="#fff" stroke-opacity=".6" stroke-width="4" stroke-linecap="round"/>'
                f'<rect x="98" y="36" width="60" height="26" rx="5" fill="#9a6a3a" {O}/><path d="M98,62 L158,62" stroke="#15100c" stroke-width="3"/>')
    body = "M108,40 L148,40 L148,92 C188,104 204,134 204,164 C204,208 170,236 128,236 C86,236 52,208 52,164 C52,134 68,104 108,92 Z"
    bubbles = "".join(f'<circle cx="{pal["rng"].uniform(80, 176):.0f}" cy="{pal["rng"].uniform(150, 222):.0f}" r="{pal["rng"].uniform(2, 6):.1f}" fill="#fff" fill-opacity=".45"/>' for _ in range(6))
    return (f'<defs><clipPath id="{P}v"><path d="{body}"/></clipPath>'
            f'<radialGradient id="{P}liq" cx="40%" cy="40%"><stop offset="0" stop-color="{lighten(liq, .45)}"/><stop offset="1" stop-color="{darken(liq, .45)}"/></radialGradient></defs>'
            f'<path d="{body}" fill="#e8f4fa" fill-opacity=".22" {O}/>'
            f'<g clip-path="url(#{P}v)"><rect x="40" y="128" width="180" height="120" fill="url(#{P}liq)" fill-opacity="{.45 if clear else .95}"/>'
            f'<ellipse cx="128" cy="128" rx="76" ry="9" fill="{lighten(liq, .4)}" fill-opacity=".9"/>{bubbles}</g>'
            f'<path d="{body}" fill="none" {O}/>'
            f'<path d="M78,150 C80,126 96,112 110,106" fill="none" stroke="#fff" stroke-opacity=".75" stroke-width="6" stroke-linecap="round"/>'
            f'<rect x="100" y="18" width="56" height="26" rx="6" fill="#9a6a3a" {O}/>'
            f'<path d="M106,56 Q128,64 150,56 L150,76 Q128,84 106,76 Z" fill="{pal["cloth"]}" fill-opacity=".85"/>')


def _scroll(P, pal):
    O = _outline()
    lines = "".join(f'<path d="M84,{76 + i * 18} Q{110 + (i % 3) * 8},{70 + i * 18} {170 - (i % 2) * 18},{76 + i * 18}" stroke="#6a4a2a" stroke-width="2.4" stroke-opacity=".7" fill="none"/>' for i in range(6))
    return (f'<path d="M66,50 L190,50 L190,206 L66,206 Z" fill="url(#{P}p)" {O}/>{lines}'
            f'<rect x="54" y="36" width="148" height="24" rx="12" fill="url(#{P}p)" {O}/>'
            f'<rect x="54" y="196" width="148" height="24" rx="12" fill="url(#{P}p)" {O}/>'
            f'<ellipse cx="54" cy="48" rx="7" ry="12" fill="#c8a870" {O}/><ellipse cx="202" cy="208" rx="7" ry="12" fill="#c8a870" {O}/>'
            f'<circle cx="170" cy="186" r="16" fill="#a8202a" {O}/><path d="M162,200 L156,226 M176,200 L182,226" stroke="#a8202a" stroke-width="6"/>'
            f'<path d="M164,182 L176,190 M176,182 L164,190" stroke="#6a0a10" stroke-width="2"/>')


def _book(P, pal):
    O = _outline()
    col = pal["cloth"]
    return (f'<path d="M60,40 L196,40 L204,48 L204,222 L68,222 L60,214 Z" fill="#f2e6c8" {O}/>'
            + "".join(f'<path d="M{196 - i * 3},{44 + i * 2} L{196 - i * 3},{218}" stroke="#c8b890" stroke-width="1"/>' for i in range(4))
            + f'<rect x="52" y="34" width="140" height="182" rx="6" fill="{col}" {O}/>'
            f'<rect x="52" y="34" width="22" height="182" rx="5" fill="{darken(col, .3)}"/>'
            f'<path d="M74,34 L74,216" stroke="#15100c" stroke-width="1.5"/>'
            + "".join(f'<path d="M{x},{y} l14,0 l0,14" fill="none" stroke="url(#{P}t)" stroke-width="5" transform="rotate({a} {x} {y})"/>'
                      for x, y, a in ((178, 44, 0), (178, 206, 90)))
            + f'<rect x="96" y="80" width="72" height="90" rx="6" fill="none" stroke="url(#{P}t)" stroke-width="3"/>'
            + _gem(P, 132, 125, 14)
            + "".join(f'<path d="M52,{70 + i * 40} L74,{70 + i * 40}" stroke="url(#{P}t)" stroke-width="3"/>' for i in range(4)))


def _letter(P, pal):
    O = _outline()
    return (f'<path d="M40,70 L216,70 L216,196 L40,196 Z" fill="url(#{P}p)" {O}/>'
            f'<path d="M40,70 L128,140 L216,70" fill="none" stroke="#8a6a3a" stroke-width="2.5"/>'
            f'<path d="M40,196 L108,128 M216,196 L148,128" stroke="#8a6a3a" stroke-width="1.5" stroke-opacity=".6"/>'
            f'<circle cx="128" cy="140" r="20" fill="#a8202a" {O}/><circle cx="128" cy="140" r="11" fill="none" stroke="#6a0a10" stroke-width="2.5"/>')


def _map(P, pal):
    O = _outline()
    return (f'<path d="M34,54 L92,40 L162,58 L222,42 L222,202 L162,218 L92,200 L34,216 Z" fill="url(#{P}p)" {O}/>'
            f'<path d="M92,40 L92,200 M162,58 L162,218" stroke="#b8a070" stroke-width="2"/>'
            f'<path d="M58,180 C80,150 110,160 120,130 C130,100 160,110 176,90" fill="none" stroke="#8a2a1a" stroke-width="3" stroke-dasharray="7 6"/>'
            f'<path d="M168,78 L188,98 M188,78 L168,98" stroke="#a8202a" stroke-width="5" stroke-linecap="round"/>'
            f'<path d="M60,90 l10,-16 l10,16 M80,96 l8,-12 l8,12" fill="none" stroke="#6a5a3a" stroke-width="2"/>'
            f'<circle cx="190" cy="180" r="14" fill="none" stroke="#6a5a3a" stroke-width="2"/><path d="M190,166 L190,194 M176,180 L204,180" stroke="#6a5a3a"/>')


def _key(P, pal):
    O = _outline()
    return _rot(f'<circle cx="128" cy="62" r="36" fill="none" stroke="#15100c" stroke-width="18"/>'
                f'<circle cx="128" cy="62" r="36" fill="none" stroke="url(#{P}t)" stroke-width="13"/>'
                f'<rect x="120" y="94" width="16" height="130" rx="4" fill="url(#{P}t)" {O}/>'
                f'<path d="M136,176 L166,176 L166,190 L150,190 L150,200 L166,200 L166,216 L136,216 Z" fill="url(#{P}t)" {O}/>'
                + (_gem(P, 128, 62, 12) if pal["has_gem"] or pal["magic"] else ""), 40)


def _gem_item(P, pal):
    g = pal["gem"]
    return (f'<path d="M72,96 L100,56 L156,56 L184,96 L128,212 Z" fill="url(#{P}g)" {_outline()}/>'
            f'<path d="M72,96 L184,96 M100,56 L112,96 L128,212 L144,96 L156,56 M112,96 L128,56 L144,96" fill="none" stroke="{lighten(g, .6)}" stroke-opacity=".7" stroke-width="1.6"/>'
            f'<path d="M102,64 L118,64 L108,88 Z" fill="#fff" fill-opacity=".7"/>')


def _coin(P, pal):
    O = _outline()
    stack = "".join(f'<ellipse cx="92" cy="{200 - i * 12}" rx="46" ry="14" fill="url(#{P}t)" {O}/>' for i in range(5))
    return (stack + f'<circle cx="156" cy="124" r="62" fill="url(#{P}t)" {O}/>'
            f'<circle cx="156" cy="124" r="48" fill="none" stroke="{pal["trim"][2]}" stroke-width="3"/>'
            f'<path d="M156,92 l10,22 l24,2 l-18,16 l6,24 l-22,-13 l-22,13 l6,-24 l-18,-16 l24,-2 Z" fill="{pal["trim"][2]}" fill-opacity=".7"/>')


def _orb(P, pal):
    O = _outline()
    glow = pal["glow"] or pal["gem"]
    return (f'<path d="M84,214 L172,214 L160,184 L96,184 Z" fill="url(#{P}w)" {O}/>'
            f'<circle cx="128" cy="116" r="72" fill="{glow}" fill-opacity=".25" filter="url(#{P}gl)"/>'
            f'<circle cx="128" cy="116" r="64" fill="url(#{P}g)" fill-opacity=".85" {O}/>'
            f'<path d="M90,120 C100,90 150,80 164,110 C150,96 112,100 104,130" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="4"/>'
            f'<circle cx="104" cy="92" r="10" fill="#fff" fill-opacity=".7"/>')


# ---------------------------------------------------------------- containers & gear

def _pouch(P, pal):
    O = _outline()
    return (f'<path d="M96,70 C60,100 44,160 60,196 C76,230 180,230 196,196 C212,160 196,100 160,70 Z" fill="url(#{P}l)" {O}/>'
            f'<path d="M92,72 C110,58 146,58 164,72 L158,84 C140,74 116,74 98,84 Z" fill="{pal["leather"][2]}" {O}/>'
            f'<path d="M100,78 C110,100 104,120 96,128 M158,78 C150,100 156,120 164,128" fill="none" stroke="#e8d0a8" stroke-width="3"/>'
            f'<circle cx="96" cy="130" r="5" fill="#e8d0a8"/><circle cx="164" cy="130" r="5" fill="#e8d0a8"/>'
            f'<path d="M84,150 C100,170 156,170 172,150" fill="none" stroke="#1a0e06" stroke-opacity=".4" stroke-width="2"/>')


def _backpack(P, pal):
    O = _outline()
    return (f'<rect x="58" y="58" width="140" height="170" rx="30" fill="url(#{P}l)" {O}/>'
            f'<path d="M58,110 C58,60 198,60 198,110 L198,136 C150,150 106,150 58,136 Z" fill="{pal["cloth"]}" {O}/>'
            f'<rect x="116" y="126" width="24" height="22" rx="4" fill="url(#{P}t)" {O}/>'
            f'<rect x="84" y="170" width="88" height="44" rx="10" fill="{pal["leather"][1]}" {O}/>'
            f'<path d="M100,58 C100,30 156,30 156,58" fill="none" stroke="{pal["leather"][2]}" stroke-width="8"/>'
            f'<ellipse cx="128" cy="236" rx="80" ry="10" fill="#6a4a2a" {O}/>')


def _chest(P, pal):
    O = _outline()
    return (f'<rect x="40" y="110" width="176" height="104" rx="6" fill="url(#{P}w)" {O}/>'
            f'<path d="M40,112 C40,60 216,60 216,112 Z" fill="url(#{P}w)" {O}/>'
            + "".join(f'<rect x="{x}" y="72" width="16" height="142" fill="url(#{P}m)" {O}/>' for x in (64, 176))
            + f'<rect x="40" y="104" width="176" height="14" fill="url(#{P}m)" {O}/>'
            f'<rect x="114" y="112" width="28" height="36" rx="4" fill="url(#{P}t)" {O}/><circle cx="128" cy="126" r="4" fill="#15100c"/><rect x="126" y="126" width="4" height="12" fill="#15100c"/>')


def _candle(P, pal, form):
    O = _outline()
    flame = (f'<circle cx="128" cy="56" r="34" fill="#ffb347" fill-opacity=".3" filter="url(#{P}gl)"/>'
             f'<path d="M128,20 C146,48 144,72 128,80 C112,72 110,48 128,20 Z" fill="#ffcf5a" {O}/><path d="M128,44 C136,58 134,70 128,74 C122,70 120,58 128,44 Z" fill="#fff6c8"/>')
    if form == "torch":
        return _rot(f'<path d="M120,236 L114,92 L142,92 L136,236 Z" fill="url(#{P}w)" {O}/><rect x="108" y="84" width="40" height="24" rx="6" fill="url(#{P}l)" {O}/>'
                    + flame.replace("cy=\"56\"", "cy=\"60\"").replace("128,80", "128,90"), 20)
    if form == "lantern":
        return (f'<path d="M104,40 C104,20 152,20 152,40" fill="none" stroke="url(#{P}m)" stroke-width="7"/>'
                f'<rect x="84" y="40" width="88" height="24" rx="6" fill="url(#{P}m)" {O}/>'
                f'<rect x="92" y="64" width="72" height="120" rx="6" fill="#ffcf5a" fill-opacity=".55" {O}/>'
                f'<circle cx="128" cy="124" r="44" fill="#ffb347" fill-opacity=".35" filter="url(#{P}gl)"/>'
                f'<path d="M128,98 C140,118 138,134 128,140 C118,134 116,118 128,98 Z" fill="#fff6c8"/>'
                + "".join(f'<path d="M{x},64 L{x},184" stroke="url(#{P}m)" stroke-width="6"/>' for x in (92, 128, 164))
                + f'<rect x="80" y="184" width="96" height="26" rx="6" fill="url(#{P}m)" {O}/>')
    return (f'<rect x="104" y="80" width="48" height="140" rx="6" fill="#f2ead0" {O}/>'
            f'<path d="M104,96 C112,110 116,90 124,104 C130,116 136,98 152,100" fill="none" stroke="#e0d4b0" stroke-width="5"/>'
            f'<ellipse cx="128" cy="222" rx="60" ry="14" fill="url(#{P}t)" {O}/>' + flame)


def _rope(P, pal):
    out = []
    for i in range(5):
        rx, ry = 92 - i * 12, 56 - i * 7
        out.append(f'<ellipse cx="128" cy="{140 - i * 6}" rx="{rx}" ry="{ry}" fill="none" stroke="#6a4a24" stroke-width="16"/>'
                   f'<ellipse cx="128" cy="{140 - i * 6}" rx="{rx}" ry="{ry}" fill="none" stroke="#c8a064" stroke-width="11" stroke-dasharray="6 4"/>')
    return "".join(out) + '<path d="M208,150 C230,190 214,220 196,236" fill="none" stroke="#c8a064" stroke-width="11" stroke-linecap="round"/>'


def _arrows(P, pal):
    O = _outline()
    arrows = "".join(f'<path d="M{96 + i * 16},{150} L{84 + i * 20},{30 + (i % 2) * 10}" stroke="{pal["wood"][1]}" stroke-width="4"/>'
                     f'<path d="M{84 + i * 20},{30 + (i % 2) * 10} l-8,14 l14,2 Z" fill="#c8402a"/>' for i in range(4))
    return (arrows + f'<path d="M72,110 L184,110 L172,236 L84,236 Z" fill="url(#{P}l)" {O}/>'
            f'<path d="M72,110 L184,110 L182,128 L74,128 Z" fill="{pal["leather"][2]}"/>'
            f'<path d="M100,150 L156,150 M96,190 L160,190" stroke="#e8d0a8" stroke-width="2" stroke-dasharray="5 3"/>')


def _lute(P, pal):
    O = _outline()
    return _rot(f'<rect x="120" y="16" width="16" height="120" rx="3" fill="url(#{P}w)" {O}/>'
                f'<path d="M112,14 L144,14 L140,36 L116,36 Z" fill="{pal["wood"][2]}" {O}/>'
                f'<path d="M128,110 C176,110 190,160 180,196 C170,236 86,236 76,196 C66,160 80,110 128,110 Z" fill="url(#{P}w)" {O}/>'
                f'<circle cx="128" cy="170" r="16" fill="#1a0e06"/><circle cx="128" cy="170" r="20" fill="none" stroke="url(#{P}t)" stroke-width="3"/>'
                + "".join(f'<path d="M{124 + i * 3},20 L{124 + i * 3},212" stroke="#f0e6cc" stroke-width="1"/>' for i in range(3))
                + f'<rect x="108" y="206" width="40" height="8" rx="2" fill="#1a0e06"/>', 30)


def _horn(P, pal, form):
    O = _outline()
    if form == "flute":
        return _rot(f'<rect x="120" y="20" width="16" height="216" rx="7" fill="url(#{P}w)" {O}/>'
                    + "".join(f'<circle cx="128" cy="{70 + i * 24}" r="4" fill="#1a0e06"/>' for i in range(6)), 40)
    if form == "drum":
        return (f'<rect x="56" y="96" width="144" height="100" fill="url(#{P}w)" {O}/>'
                f'<ellipse cx="128" cy="96" rx="72" ry="24" fill="#f0e6cc" {O}/><ellipse cx="128" cy="196" rx="72" ry="24" fill="url(#{P}w)" {O}/>'
                + "".join(f'<path d="M{64 + i * 32},108 L{80 + i * 32},200" stroke="#e8d0a8" stroke-width="2"/>' for i in range(4)))
    return (f'<path d="M40,80 C90,70 170,120 200,196 L226,176 C200,110 110,40 44,54 Z" fill="url(#{P}t)" {O}/>'
            f'<ellipse cx="213" cy="186" rx="18" ry="24" fill="#3a2a1a" transform="rotate(-40 213 186)"/>'
            f'<path d="M80,64 Q130,70 150,100" fill="none" stroke="{pal["cloth"]}" stroke-width="8"/>')


def _kit(P, pal):
    O = _outline()
    return (f'<rect x="36" y="86" width="184" height="120" rx="10" fill="url(#{P}l)" {O}/>'
            f'<path d="M100,86 C100,56 156,56 156,86" fill="none" stroke="url(#{P}m)" stroke-width="9"/>'
            f'<rect x="36" y="126" width="184" height="14" fill="{pal["leather"][2]}"/>'
            f'<rect x="116" y="120" width="24" height="26" rx="4" fill="url(#{P}t)" {O}/>'
            + "".join(f'<path d="M{160 + i * 12},96 L{164 + i * 12},70" stroke="url(#{P}m)" stroke-width="4" stroke-linecap="round"/>' for i in range(3)))


def _waterskin(P, pal):
    O = _outline()
    return (f'<path d="M104,56 C50,80 40,190 90,220 C120,238 170,232 196,200 C226,160 200,80 150,56 Z" fill="url(#{P}l)" {O}/>'
            f'<rect x="112" y="24" width="32" height="38" rx="6" fill="{pal["wood"][1]}" {O}/>'
            f'<path d="M84,100 C110,160 170,170 200,140" fill="none" stroke="{pal["cloth"]}" stroke-width="7"/>')


def _rations(P, pal):
    O = _outline()
    return (f'<path d="M36,160 C36,110 150,96 170,130 C186,160 160,192 100,196 C60,198 36,190 36,160 Z" fill="#c8883a" {O}/>'
            + "".join(f'<path d="M{70 + i * 24},{130 + i * 2} q10,10 20,0" fill="none" stroke="#8a5a1a" stroke-width="3"/>' for i in range(4))
            + f'<path d="M140,190 L224,150 L224,196 L140,226 Z" fill="#f0d060" {O}/><path d="M140,190 L224,150 L204,138 L124,172 Z" fill="#f8e890" {O}/>'
            + "".join(f'<circle cx="{176 + i * 14}" cy="{190 - i * 6}" r="4" fill="#c8a830"/>' for i in range(3)))


def _mirror(P, pal):
    O = _outline()
    return _rot(f'<rect x="120" y="150" width="16" height="86" rx="5" fill="url(#{P}t)" {O}/>'
                f'<ellipse cx="128" cy="92" rx="62" ry="76" fill="url(#{P}t)" {O}/>'
                f'<ellipse cx="128" cy="92" rx="50" ry="64" fill="#cfe4f0" {O}/>'
                f'<path d="M96,70 C104,48 124,38 140,40" fill="none" stroke="#fff" stroke-width="6" stroke-opacity=".8"/>', 25)


def _feather(P, pal):
    return _rot(f'<path d="M128,16 C176,60 170,150 128,210 C86,150 80,60 128,16 Z" fill="{lighten(pal["cloth"], .5)}" {_outline()}/>'
                f'<path d="M128,20 L128,240" stroke="#3a2a1a" stroke-width="3"/>'
                + "".join(f'<path d="M128,{50 + i * 18} l{-30 + i * 2},-16 M128,{50 + i * 18} l{30 - i * 2},-16" stroke="{darken(pal["cloth"], .1)}" stroke-width="1.5"/>' for i in range(8)), 35)


def _bedroll(P, pal):
    O = _outline()
    return (f'<rect x="40" y="96" width="160" height="80" rx="40" fill="url(#{P}c)" {O}/>'
            f'<ellipse cx="200" cy="136" rx="26" ry="40" fill="{darken(pal["cloth"], .2)}" {O}/>'
            f'<ellipse cx="200" cy="136" rx="14" ry="24" fill="none" stroke="{lighten(pal["cloth"], .3)}" stroke-width="3"/>'
            + "".join(f'<rect x="{x}" y="90" width="14" height="92" fill="url(#{P}l)" {O}/>' for x in (80, 150)))


def _crowbar(P, pal):
    return _rot(f'<path d="M122,236 L122,40 C122,20 150,16 158,34" fill="none" stroke="#15100c" stroke-width="16" stroke-linecap="round"/>'
                f'<path d="M122,236 L122,40 C122,20 150,16 158,34" fill="none" stroke="url(#{P}m)" stroke-width="11" stroke-linecap="round"/>', 30)


def _bell(P, pal):
    O = _outline()
    return (f'<path d="M72,190 C80,150 84,70 128,60 C172,70 176,150 184,190 Z" fill="url(#{P}t)" {O}/>'
            f'<rect x="60" y="186" width="136" height="16" rx="6" fill="url(#{P}t)" {O}/><circle cx="128" cy="210" r="11" fill="url(#{P}t)" {O}/>'
            f'<path d="M116,60 C116,40 140,40 140,60" fill="none" stroke="url(#{P}t)" stroke-width="7"/>')


def _hourglass(P, pal):
    O = _outline()
    return (f'<rect x="64" y="30" width="128" height="18" rx="4" fill="url(#{P}w)" {O}/><rect x="64" y="208" width="128" height="18" rx="4" fill="url(#{P}w)" {O}/>'
            f'<path d="M84,48 C84,100 124,112 124,128 C124,144 84,156 84,208 L172,208 C172,156 132,144 132,128 C132,112 172,100 172,48 Z" fill="#dff0f8" fill-opacity=".35" {O}/>'
            f'<path d="M98,190 Q128,160 158,190 L166,206 L90,206 Z" fill="#e0c070"/><path d="M104,70 Q128,100 152,70 Z" fill="#e0c070"/>')


def _caltrops(P, pal):
    out = []
    for cx, cy in ((90, 150), (160, 120), (150, 190)):
        for a in (0, 120, 240):
            out.append(f'<path d="M{cx},{cy} L{cx + 34 * math.cos(math.radians(a - 90)):.0f},{cy + 34 * math.sin(math.radians(a - 90)):.0f}" stroke="url(#{P}m)" stroke-width="7" stroke-linecap="round"/>')
        out.append(f'<circle cx="{cx}" cy="{cy}" r="7" fill="url(#{P}m)"/>')
    return "".join(out)


def _net(P, pal):
    lines = "".join(f'<path d="M{40 + i * 22},40 Q{128},{140} {40 + i * 22},226" fill="none" stroke="#b89a64" stroke-width="3"/>' for i in range(9))
    lines += "".join(f'<path d="M40,{40 + i * 22} Q128,{60 + i * 22} 216,{40 + i * 22}" fill="none" stroke="#b89a64" stroke-width="3"/>' for i in range(9))
    return lines


def _figurine(P, pal, item):
    icon = assets.icon_for_item(item.get("alias") or item.get("name", ""), item.get("kind"))
    return _plaque(P, pal, icon, stone=True)


def _plaque(P, pal, icon, stone=False):
    body = assets.icon_body(icon).replace('fill="currentColor"', f'fill="url(#{P}{"mv" if not stone else "t"})"')
    shadow = assets.icon_body(icon).replace('fill="currentColor"', 'fill="#000"')
    return (f'<rect x="28" y="28" width="200" height="200" rx="38" fill="#2a2018" fill-opacity=".9" {_outline()}/>'
            f'<rect x="36" y="36" width="184" height="184" rx="32" fill="none" stroke="url(#{P}t)" stroke-width="4"/>'
            f'<g transform="translate(62 66) scale(.258)" opacity=".5">{shadow}</g>'
            f'<g transform="translate(58 60) scale(.258)">{body}</g>')


# ============================================================== entry point

DRAW = {
    "sword": _sword, "greatsword": _sword, "shortsword": _sword, "scimitar": _sword, "rapier": _sword, "dagger": _sword,
    "axe": _axe, "greataxe": _axe, "handaxe": _axe, "warhammer": _hammer, "hammer": _hammer, "maul": _hammer, "pick": _hammer,
    "morningstar": _hammer, "flail": _hammer, "mace": _hammer, "club": _hammer, "spear": _polearm, "javelin": _polearm,
    "trident": _polearm, "halberd": _polearm, "bow": _bow, "crossbow": _bow, "sling": _bow, "dart": _bow, "blowgun": _bow,
    "staff": _staff, "wand": _staff, "rod": _staff, "plate": _armor, "chain": _armor, "leather": _armor,
    "cloak": _cloak, "robe": _cloak, "tunic": _cloak, "circlet": _circlet, "crown": _circlet, "potion": _potion, "vial": _potion,
}


def item_svg(item, size=None):
    form = form_of(item)  # the physical shape shows (a ring looks like a ring) ...
    if not item_known(item):  # ... but colours and materials come only from what the characters can see
        from .core import item_display_name
        item = {"id": item.get("id"), "name": item_display_name(dict(item, alias=None)), "alias": item.get("alias"),
                "note": item.get("note"), "base_name": item.get("base_name"), "kind": item.get("kind"),
                "category": item.get("category"), "magic": True, "identified": False}
    pal = palette(item)
    pal["_t"] = _text(item)
    P = "i" + hashlib.md5(f"{item.get('id')}|{item.get('name')}|{item.get('alias')}".encode()).hexdigest()[:6]
    if form in DRAW:
        art = DRAW[form](P, pal, form)
    else:
        art = {"sickle": lambda: _sickle(P, pal), "whip": lambda: _whip(P, pal), "net": lambda: _net(P, pal),
               "shield": lambda: _shield(P, pal, item), "helm": lambda: _helm(P, pal), "boots": lambda: _boots(P, pal),
               "gloves": lambda: _gloves(P, pal, form), "bracers": lambda: _bracers(P, pal), "belt": lambda: _belt(P, pal),
               "hat": lambda: _hat(P, pal), "ring": lambda: _ring(P, pal), "amulet": lambda: _amulet(P, pal),
               "holy": lambda: _amulet(P, pal, holy=True), "scroll": lambda: _scroll(P, pal), "book": lambda: _book(P, pal),
               "letter": lambda: _letter(P, pal), "map": lambda: _map(P, pal), "key": lambda: _key(P, pal),
               "gem": lambda: _gem_item(P, pal), "coin": lambda: _coin(P, pal), "orb": lambda: _orb(P, pal),
               "pouch": lambda: _pouch(P, pal), "backpack": lambda: _backpack(P, pal), "chest": lambda: _chest(P, pal),
               "candle": lambda: _candle(P, pal, "candle"), "torch": lambda: _candle(P, pal, "torch"),
               "lantern": lambda: _candle(P, pal, "lantern"), "rope": lambda: _rope(P, pal), "arrows": lambda: _arrows(P, pal),
               "lute": lambda: _lute(P, pal), "horn": lambda: _horn(P, pal, "horn"), "flute": lambda: _horn(P, pal, "flute"),
               "drum": lambda: _horn(P, pal, "drum"), "kit": lambda: _kit(P, pal), "waterskin": lambda: _waterskin(P, pal),
               "rations": lambda: _rations(P, pal), "mirror": lambda: _mirror(P, pal), "feather": lambda: _feather(P, pal),
               "bedroll": lambda: _bedroll(P, pal), "crowbar": lambda: _crowbar(P, pal), "bell": lambda: _bell(P, pal),
               "hourglass": lambda: _hourglass(P, pal), "caltrops": lambda: _caltrops(P, pal),
               "figurine": lambda: _figurine(P, pal, item)}.get(form, lambda: _plaque(P, pal, assets.icon_for_item(item.get("name", ""), item.get("kind"))))()
    back = ""
    if pal["glow"]:
        r = pal["rng"]
        sparkles = "".join(
            f'<path d="M{x:.0f},{y - s:.0f} Q{x:.0f},{y:.0f} {x + s:.0f},{y:.0f} Q{x:.0f},{y:.0f} {x:.0f},{y + s:.0f} Q{x:.0f},{y:.0f} {x - s:.0f},{y:.0f} Q{x:.0f},{y:.0f} {x:.0f},{y - s:.0f} Z" '
            f'fill="{lighten(pal["glow"], .5)}" fill-opacity=".9"/>'
            for x, y, s in ((r.uniform(24, 70), r.uniform(24, 90), r.uniform(6, 11)), (r.uniform(186, 232), r.uniform(150, 232), r.uniform(5, 10)),
                            (r.uniform(190, 230), r.uniform(20, 60), r.uniform(4, 7))))
        back = f'<circle cx="128" cy="128" r="124" fill="url(#{P}aura)"/>'
        art = art + sparkles
        if not pal["known"]:
            back += (f'<text x="206" y="232" font-family="Georgia,serif" font-size="40" font-weight="bold" fill="{pal["glow"]}" fill-opacity=".85" '
                     f'stroke="#140c1e" stroke-width="3" paint-order="stroke">?</text>')
    sz = size or 256
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="{sz}" height="{sz}">{_defs(P, pal)}{back}'
            f'<g filter="url(#{P}sh)">{art}</g></svg>')


def item_art_version(item):
    keys = ("name", "alias", "base_name", "note", "rarity", "magic", "identified", "kind", "category", "meta")
    return hashlib.sha1(repr([item.get(k) for k in keys] + [ITEM_ART_REV]).encode()).hexdigest()[:10]


ITEM_ART_REV = 1


def _lint():  # every form keyword maps to something drawable
    return [f for _, f in FORMS if f not in DRAW and f not in (
        "sickle", "whip", "net", "shield", "helm", "boots", "gloves", "bracers", "belt", "hat", "ring", "amulet", "holy", "scroll",
        "book", "letter", "map", "key", "gem", "coin", "orb", "pouch", "backpack", "chest", "candle", "torch", "lantern", "rope",
        "arrows", "lute", "horn", "flute", "drum", "kit", "waterskin", "rations", "mirror", "feather", "bedroll", "crowbar",
        "bell", "hourglass", "caltrops", "figurine")]
