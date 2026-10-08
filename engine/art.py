"""Generated art: characters drawn from what they look like, and creatures drawn from what they are.

Everything here is deterministic. Engine events store the resolved face and original appearance separately from
scene description; rendering never writes state. What establishes a portrait, in priority order:
1. `look` fields the DM set with `asset look <id> --hair ... --eyes ...` (free text, one field per feature);
2. the creature's public description (`npc describe` / `char bio <id> appearance`), read for hair, eyes, skin,
   scars, headwear, clothing and so on;
3. defaults from species, class (or NPC role) and equipped armor, with a per-character seed for the rest.

portrait_svg(e)  320x400 framed bust with a name plate (party panel, sheet, info cards)
face_svg(e)      square head-and-shoulders crop (tokens, initiative bar, avatars)
Non-humanoid creatures get atmospheric creature art built on their game-icons.net silhouette.
"""
import hashlib
import math
import random
import re

from . import assets
from .assets import esc
from . import illustration
from . import painted

# ============================================================== colour helpers


def _rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(r, g, b):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in (r, g, b))


def mix(a, b, t):
    ra, rb = _rgb(a), _rgb(b)
    return _hex(*(x + (y - x) * t for x, y in zip(ra, rb)))


def lighten(c, t):
    return mix(c, "#ffffff", t)


def darken(c, t):
    return mix(c, "#000000", t)


def seeded(*parts):
    return random.Random(int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:12], 16))


# ============================================================== vocabulary

HAIR_COLORS = {
    "black": "#1d1a1c", "raven": "#16141a", "jet": "#121014", "ebony": "#1a1512", "dark": "#2a1d16",
    "brown": "#5a3a22", "chestnut": "#6e3a1f", "auburn": "#7f2f1a", "red": "#9b3218", "crimson": "#8a1f24",
    "scarlet": "#a8241c", "ginger": "#c0541f", "copper": "#b5602a", "rust": "#9a4a22", "orange": "#c86a24",
    "strawberry": "#d08a5a", "blonde": "#d9b46a", "blond": "#d9b46a", "golden": "#d8a946", "gold": "#d8a946",
    "honey": "#c9953f", "sandy": "#c2a070", "straw": "#dcc17a", "flaxen": "#e0c98a", "platinum": "#e8e2cf",
    "white": "#efefe9", "snow": "#f4f4f0", "silver": "#c9cdd2", "grey": "#8e8f93", "gray": "#8e8f93",
    "greying": "#9a948a", "graying": "#9a948a", "ash": "#a6a39a", "ashen": "#a6a39a", "salt": "#b0aca4",
    "blue": "#3a5fb0", "teal": "#2a8a86", "green": "#3f8a4a", "purple": "#6b3fa0", "violet": "#7a4ab0",
    "lavender": "#a58ad0", "pink": "#d77aa6", "rose": "#c85a7a", "mahogany": "#5a2418",
}
EYE_COLORS = {
    "brown": "#5a3a1e", "dark": "#2a1a10", "black": "#141014", "hazel": "#8a6a2a", "amber": "#c8891a",
    "gold": "#d8b030", "golden": "#d8b030", "yellow": "#d8c030", "green": "#3f8a3a", "emerald": "#1f9a5a",
    "jade": "#3a9a6a", "grey": "#8a949c", "gray": "#8a949c", "steel": "#7a8a9a", "blue": "#3a78c0",
    "ice": "#9cc8e8", "pale": "#a8c0d0", "sapphire": "#2a4ab0", "violet": "#7a4ab0", "purple": "#6a3aa0",
    "red": "#c02a20", "crimson": "#a81a20", "silver": "#c9cdd2", "white": "#ecebe6", "milky": "#dcdcd4",
    "orange": "#d8761a", "copper": "#b86a30",
}
SKIN_TONES = {
    "pale": "#f3d6bf", "porcelain": "#f5dccb", "fair": "#f0c9a6", "light": "#e8b98f", "freckled": "#eab894",
    "ruddy": "#e0a080", "rosy": "#e8b0a0", "olive": "#c89a6a", "tan": "#c58a5c", "tanned": "#c58a5c",
    "sun-browned": "#b87a4c", "weathered": "#b98560", "bronze": "#a8683e", "brown": "#8d5634", "dark": "#6b3f24",
    "deep": "#4f2d1a", "ebony": "#3f2416", "black": "#3a2418", "ashen": "#b8b0a8", "grey": "#9aa0a6", "gray": "#9aa0a6",
    "blue": "#6a86b8", "green": "#7a9a5a", "red": "#b8453d", "crimson": "#9a2f34", "purple": "#7a4a8e",
    "violet": "#7a4a8e", "lavender": "#9a86b8", "white": "#dde2e6", "gold": "#c9a13a", "golden": "#c9a13a",
    "copper": "#b56a3a", "brass": "#c9a45a", "silver": "#aab4bf", "stone": "#9aa0a6", "sallow": "#d8c090",
}
CLOTH_COLORS = {
    "black": "#1e1c22", "white": "#e8e4d8", "grey": "#6a6c72", "gray": "#6a6c72", "red": "#8e2226", "crimson": "#7a1a24",
    "scarlet": "#a02020", "maroon": "#5a1a1e", "burgundy": "#5e1a2a", "orange": "#b8601e", "yellow": "#c8a030",
    "gold": "#b8902a", "golden": "#b8902a", "ochre": "#a8762a", "brown": "#5a3a22", "tan": "#a8845a",
    "green": "#2f5a2e", "olive": "#5a5a2a", "forest": "#24402a", "emerald": "#1f6a4a", "teal": "#1f5a5a",
    "blue": "#24407a", "navy": "#1a2448", "azure": "#2f6aa8", "sky": "#5a8ac0", "purple": "#4a2a6a",
    "violet": "#5a3a8a", "indigo": "#2a2a6a", "plum": "#5a2448", "pink": "#b85a7a", "silver": "#9aa0a8",
    "patched": "#6a5a44", "drab": "#6a624e", "dun": "#7a6a4e", "cream": "#e0d4b0", "ivory": "#e8dfc8",
}
DRAGON_SCALES = {"red": "#a8322a", "blue": "#2f5fa8", "green": "#3f7a3a", "black": "#2e2c34", "white": "#d0d8de",
                 "gold": "#c9a13a", "silver": "#9eaab6", "bronze": "#a0703a", "copper": "#b56a3a", "brass": "#c29a52"}
HUMAN_TONES = ["#f3d2b8", "#eec09c", "#e0ac86", "#c99268", "#b07a52", "#8d5634", "#6b3f24", "#4f2d1a"]
SPECIES_SKIN = {
    "Human": HUMAN_TONES, "Elf": ["#f3d6bf", "#eec4a0", "#d8a882", "#b88a64", "#8a6448", "#5a4a5a"],
    "Dwarf": ["#eab896", "#e0a080", "#c58a5c", "#a8683e", "#8d5634"], "Halfling": ["#f0c9a6", "#e0ac86", "#c99268", "#9a6440"],
    "Gnome": ["#f0c9a6", "#e8b98f", "#c58a5c", "#8d5634"], "Orc": ["#8a9a6a", "#7a8f5f", "#9aa27e", "#6f7d63", "#a3a08a"],
    "Tiefling": ["#b8453d", "#9c3f5c", "#7a4a8e", "#c6705a", "#a04a4a", "#6a4a7a"],
    "Goliath": ["#9aa0a6", "#8c8f96", "#a8a095", "#7f858c", "#b0a8a0"], "Goblin": ["#8a9a4a", "#9aa050", "#c8883a", "#7a8a44"],
    "Kobold": ["#9a4a2a", "#6a5a3a", "#8a3a2a"], "Lizardfolk": ["#4a7a4a", "#5a6a3a", "#3a6a5a"],
}
SPECIES_WORDS = {"elf": "Elf", "elven": "Elf", "elvish": "Elf", "drow": "Elf", "half-elf": "Elf", "dwarf": "Dwarf",
                 "dwarven": "Dwarf", "duergar": "Dwarf", "halfling": "Halfling", "gnome": "Gnome", "gnomish": "Gnome",
                 "orc": "Orc", "orcish": "Orc", "half-orc": "Orc", "tiefling": "Tiefling", "dragonborn": "Dragonborn",
                 "goliath": "Goliath", "human": "Human", "goblin": "Goblin", "hobgoblin": "Hobgoblin", "bugbear": "Bugbear",
                 "kobold": "Kobold", "lizardfolk": "Lizardfolk", "ogre": "Ogre", "troll": "Troll", "zombie": "Zombie"}
CREATURE_WORDS={word:species for species,words in (
    ('Wolf',('wolf',)),('Mastiff',('mastiff','dog')),('Horse',('horse','pony')),('Mule',('mule',)),
    ('Rat',('rat',)),('Spider',('spider',)),('Raven',('raven','crow')),('Owl',('owl',)),('Lion',('lion',)),
    ('Tiger',('tiger',)),('Bear',('bear',)),('Boar',('boar',)),('Goat',('goat',)),('Sheep',('sheep',)),
    ('Crocodile',('crocodile','alligator')),('Owlbear',('owlbear',)),('Skeleton',('skeleton',)),
    ('Mummy',('mummy',)),('Animated Armor',('animated armor','animated armour')),('Bat',('bat',)),
    ('Frog',('frog','toad')),('Snake',('snake','serpent')),('Scorpion',('scorpion',)),('Eagle',('eagle',)),
    ('Griffon',('griffon','griffin')),('Ant',('ant',)),('Deer',('deer','elk'))
    ) for word in words}
CREATURE_WORDS.update({colour+' dragon':colour.title()+' Dragon' for colour in DRAGON_SCALES})
CREATURE_WORDS['dragon']='Dragon'

CLASS_STYLE = {
    "Barbarian": {"bg": ("#8a3a1c", "#1e0c06"), "outfit": "furs", "cloth": "#6b4a2e", "paint": .5},
    "Bard": {"bg": ("#8a2f72", "#1e0a1a"), "outfit": "doublet", "cloth": "#8e2a4a", "headwear": ("feather cap", .35)},
    "Cleric": {"bg": ("#a8862e", "#221a08"), "outfit": "vestments", "cloth": "#e4dcc6", "pendant": "sun", "headwear": ("circlet", .25)},
    "Druid": {"bg": ("#3a7a3a", "#0a1c0c"), "outfit": "druid", "cloth": "#4a6a34", "headwear": ("antlers", .4)},
    "Fighter": {"bg": ("#3f6488", "#0c1622"), "outfit": "chain", "cloth": "#7a2a2a"},
    "Monk": {"bg": ("#2a8a80", "#08201e"), "outfit": "monk", "cloth": "#c07a2a"},
    "Paladin": {"bg": ("#b0924a", "#18223e"), "outfit": "plate", "cloth": "#2f5aa8", "pendant": "sun"},
    "Ranger": {"bg": ("#4a6a2e", "#0c1608"), "outfit": "leather", "cloth": "#3f5a2e", "headwear": ("hood", .5)},
    "Rogue": {"bg": ("#4a3464", "#0c0812"), "outfit": "leather", "cloth": "#2a2a34", "headwear": ("hood", .55)},
    "Sorcerer": {"bg": ("#9a2448", "#1c060e"), "outfit": "robe", "cloth": "#6a1f3a", "glow": .35},
    "Warlock": {"bg": ("#4a2e72", "#0a0614"), "outfit": "robe", "cloth": "#2a1f3a", "glow": .45, "collar": True},
    "Wizard": {"bg": ("#2a4a8a", "#060c1e"), "outfit": "robe", "cloth": "#2a3f7a", "headwear": ("wizard hat", .3)},
}
# NPC roles (by SRD stat block or name): clothing and headwear
ROLE_STYLE = [
    ("knight", {"outfit": "plate", "cloth": "#7a1a24"}), ("paladin", {"outfit": "plate"}),
    ("guard", {"outfit": "chain", "headwear": ("helm", .6), "cloth": "#24407a"}), ("soldier", {"outfit": "chain", "headwear": ("helm", .5)}),
    ("veteran", {"outfit": "chain"}), ("gladiator", {"outfit": "furs"}), ("berserker", {"outfit": "furs", "paint": .7}),
    ("bandit", {"outfit": "leather", "headwear": ("bandana", .4)}), ("thug", {"outfit": "leather"}),
    ("pirate", {"outfit": "coat", "headwear": ("tricorn", .5), "cloth": "#5a1a1e"}), ("sailor", {"outfit": "tunic", "headwear": ("bandana", .5)}),
    ("spy", {"outfit": "leather", "headwear": ("hood", .6)}), ("assassin", {"outfit": "leather", "headwear": ("hood", .8), "cloth": "#1e1c22"}),
    ("scout", {"outfit": "leather", "headwear": ("hood", .5), "cloth": "#3f5a2e"}), ("thief", {"outfit": "leather", "headwear": ("hood", .6)}),
    ("archmage", {"outfit": "robe", "cloth": "#3a2a6a"}), ("mage", {"outfit": "robe"}), ("apprentice", {"outfit": "robe"}),
    ("wizard", {"outfit": "robe", "headwear": ("wizard hat", .5)}), ("warlock", {"outfit": "robe", "collar": True}),
    ("cult fanatic", {"outfit": "robe", "headwear": ("hood", .9), "cloth": "#5a1a1e"}), ("cultist", {"outfit": "robe", "headwear": ("hood", .9), "cloth": "#4a1418"}),
    ("priest", {"outfit": "vestments", "pendant": "sun"}), ("acolyte", {"outfit": "vestments", "pendant": "sun"}),
    ("druid", {"outfit": "druid", "headwear": ("antlers", .4)}), ("noble", {"outfit": "coat", "cloth": "#4a2a6a", "pendant": "gem"}),
    ("merchant", {"outfit": "coat", "cloth": "#5a3a22"}), ("commoner", {"outfit": "tunic"}), ("peasant", {"outfit": "tunic"}),
    ("innkeeper", {"outfit": "tunic"}), ("barkeep", {"outfit": "tunic"}), ("tough", {"outfit": "leather"}),
    ("warrior", {"outfit": "leather"}), ("captain", {"outfit": "coat", "cloth": "#24407a"}),
]
SIDE_BG = {"pc": ("#2f5a8a", "#0a1422"), "ally": ("#2a7a6a", "#08201a"), "enemy": ("#8a2a26", "#1e0808"),
           "neutral": ("#8a7a3a", "#1e1a0a")}
TYPE_STYLE = {  # creature art palettes: (backdrop, backdrop dark, silhouette light, silhouette dark, glow)
    "aberration": ("#3a2a6a", "#08061a", "#b89ae8", "#3a2a5a", "#9a6af0"),
    "beast": ("#5a4a2a", "#120e06", "#d8b888", "#4a3a22", "#e0a860"),
    "celestial": ("#b8a060", "#2a2210", "#fff6d8", "#b89a50", "#ffe28a"),
    "construct": ("#4a5a6a", "#0c1016", "#c8d4dc", "#4a5660", "#8ac0e8"),
    "dragon": ("#8a2a1a", "#1e0806", "#f0b070", "#6a2014", "#ff8a3a"),
    "elemental": ("#2a6a8a", "#06141e", "#b8ecff", "#2a5a7a", "#6ad8ff"),
    "fey": ("#6a3a7a", "#140a1a", "#f0c8f0", "#5a3a6a", "#ff9ae0"),
    "fiend": ("#7a1a1a", "#140404", "#ff9a6a", "#5a1010", "#ff4a2a"),
    "giant": ("#5a6070", "#10121a", "#d8d0c0", "#5a5048", "#c0b8a0"),
    "humanoid": ("#5a4a3a", "#120e0a", "#e8d4b8", "#4a3a2a", "#e0c090"),
    "monstrosity": ("#5a5a2a", "#12120a", "#d8d890", "#4a4a22", "#c8d060"),
    "ooze": ("#3a6a2a", "#0a1406", "#c8f0a0", "#3a6a2a", "#9af06a"),
    "plant": ("#2f5a2a", "#081208", "#b8e0a0", "#2f4a26", "#8ad06a"),
    "undead": ("#2f4a4a", "#060e10", "#c8e8e0", "#2f4040", "#7af0d0"),
}
HUMANLIKE_NAMES = ("vampire", "hag", "doppelganger", "drow", "duergar", "cultist", "goblin", "hobgoblin", "bugbear", "kobold",
                   "lizardfolk", "orc", "ogre", "troll", "zombie")


# ============================================================== reading a description

def _words(text):
    return re.findall(r"[a-z]+(?:-[a-z]+)?", str(text or "").lower())


def _near(words, nouns, table, back=4, fwd=0):
    """Colour word nearest before (or right after) any of the nouns: 'long auburn braid', 'eyes of ice'."""
    for i, w in enumerate(words):
        base = w.split("-")[-1]
        if base in nouns or w in nouns:
            parts = w.split("-")
            if len(parts) > 1 and parts[0] in table:  # "silver-haired", "green-eyed"
                return parts[0]
            for j in range(i - 1, max(-1, i - 1 - back), -1):
                ww = words[j]
                for part in reversed(ww.split("-")):
                    if part in table:
                        return part
                if ww.split("-")[-1] in ALL_NOUNS:
                    break
            for j in range(i + 1, min(len(words), i + 1 + fwd)):
                if words[j] in table:
                    return words[j]
    return None


HAIR_NOUNS = {"hair", "haired", "braid", "braids", "braided", "locks", "mane", "curls", "ponytail", "topknot", "bun",
              "dreadlocks", "dreads", "mohawk", "tresses", "plait", "plaits"}
BEARD_NOUNS = {"beard", "bearded", "beards", "moustache", "mustache", "goatee", "whiskers", "sideburns", "stubble"}
EYE_NOUNS = {"eye", "eyes", "eyed", "gaze", "stare"}
SKIN_NOUNS = {"skin", "skinned", "complexion", "scales", "scaled", "hide", "flesh"}
CLOTH_NOUNS = {"cloak", "robe", "robes", "coat", "tunic", "doublet", "vestments", "cape", "hood", "hooded", "cowl",
               "dress", "gown", "jerkin", "tabard", "surcoat", "mantle", "shawl", "scarf", "sash", "uniform", "livery",
               "shirt", "vest", "leathers", "garb", "clothes", "clothing", "habit", "armor", "armour"}
ALL_NOUNS = HAIR_NOUNS | BEARD_NOUNS | EYE_NOUNS | SKIN_NOUNS | CLOTH_NOUNS


def read_description(text):
    """Visual traits found in free text. Only what the text says; everything else stays a default."""
    t = str(text or "").lower()
    w = _words(t)
    out = {}
    if not t.strip():
        return out
    c = _near(w, HAIR_NOUNS, HAIR_COLORS)
    if c:
        out["hair_color"] = HAIR_COLORS[c]
    if re.search(r"\bbald\b(?!\s+(?:at|on)\s+(?:the\s+)?(?:elbows|knees|seams))|shaved head|shaven head|shaved scalp|hairless|clean[- ]shaven head", t):
        out["hair_style"] = "bald"
    elif re.search(r"\bmohawk|crest of hair", t):
        out["hair_style"] = "mohawk"
    elif re.search(r"\bdread", t):
        out["hair_style"] = "dreads"
    elif re.search(r"\bbraid|plait", t):
        out["hair_style"] = "braid"
    elif re.search(r"\bponytail|tied back|queue\b", t):
        out["hair_style"] = "ponytail"
    elif re.search(r"\btopknot|top-knot|\bbun\b", t):
        out["hair_style"] = "bun"
    elif re.search(r"\bcurly\b|\bcurls\b|ringlets|curled hair", t):
        out["hair_style"] = "curly"
    elif re.search(r"\b(wild|unkempt|shaggy|tangled|messy|spiky|mane)\b", t):
        out["hair_style"] = "wild"
    elif re.search(r"\b(long|flowing|waist-length|shoulder-length)\b[^.;,]{0,20}\b(hair|locks|tresses)", t):
        out["hair_style"] = "long"
    elif re.search(r"\b(short|cropped|close-cropped|buzzed|shorn)\b[^.;,]{0,20}\b(hair|haired)", t) or "crew cut" in t:
        out["hair_style"] = "short"
    if re.search(r"\bshaved sides|undercut|shaved at the sides", t):
        out["undercut"] = True
    if re.search(r"clean[- ]shaven|beardless", t):
        out["beard"] = "none"
    elif re.search(r"\b(long|great|forked|braided|flowing|magnificent|bushy) [a-z ,-]{0,20}beard|beard[a-z ,]{0,12}(braid|to (his|her|their) (belt|chest|waist))", t):
        out["beard"] = "long"
    elif "stubble" in t or "unshaven" in t:
        out["beard"] = "stubble"
    elif "goatee" in t:
        out["beard"] = "goatee"
    elif re.search(r"\bbeard", t):
        out["beard"] = "short"
    elif re.search(r"mustache|moustache", t):
        out["beard"] = "mustache"
    bc = _near(w, BEARD_NOUNS, HAIR_COLORS)
    if bc:
        out["beard_color"] = HAIR_COLORS[bc]
    ec = _near(w, EYE_NOUNS, EYE_COLORS, fwd=0)
    if ec:
        out["eye_color"] = EYE_COLORS[ec]
    if re.search(r"glowing eyes|eyes (that )?glow|burning eyes|eyes (burn|blaze|shine)|luminous eyes", t):
        out["eye_glow"] = True
    if re.search(r"eye ?patch|missing (an|one|his|her|their|the) (left |right )?eye|one-eyed", t):
        out["eyepatch"] = "left" if re.search(r"left eye|patch over (his|her|their|the) left", t) else "right"
        if re.search(r"(silver|steel|gold|golden|brass)(en)? eye ?patch", t):
            out["eyepatch_color"] = "#d4b460" if re.search(r"(gold|brass)(en)? eye ?patch", t) else "#c9cdd2"
    if re.search(r"spectacles|eyeglasses|\bglasses\b|pince-nez|lenses", t):
        out["spectacles"] = "half-moon" if "half-moon" in t or "half moon" in t else "round"
    if re.search(r"\bblind\b|milky eyes|clouded eyes", t):
        out["eye_color"] = EYE_COLORS["milky"]
    sc = _near(w, SKIN_NOUNS, SKIN_TONES)
    if sc:
        out["skin"] = SKIN_TONES[sc]
    else:
        m = re.search(r"\b(pale|porcelain|fair|ruddy|olive|tanned|tan|sun-browned|weathered|dark|ebony|ashen|sallow)[- ](skinned|complexion|face|faced|features)", t)
        if m:
            out["skin"] = SKIN_TONES[m.group(1)]
    if "freckle" in t:
        out["freckles"] = True
    for m in re.finditer(r"scar(?:red|s)?\b([^.;,]{0,40})", t):
        after = m.group(1)
        body = re.search(r"palm|hand|knuckle|finger|wrist|arm|elbow|shoulder|back|chest|belly|side|leg|knee|thigh|foot|feet", after)
        face = re.search(r"eye|brow|lip|mouth|cheek|face|jaw|chin|nose|temple|forehead", after)
        if body and (not face or body.start() < face.start()):
            continue  # a scar the bust doesn't show
        ctx =m.group(1) if re.search(r"eye|brow|lip|mouth|cheek|face|jaw|chin|nose", m.group(1)) else t[max(0, m.start() - 30):m.start()]
        side = "left" if "left" in ctx else "right" if "right" in ctx else None
        hit = re.search(r"eye|brow|lip|mouth|cheek|jaw|chin", ctx)
        part = hit.group(0) if hit else "cheek"
        where = "eye" if part in ("eye", "brow") else "lip" if part in ("lip", "mouth") else "cheek"
        out.setdefault("scars", []).append({"side": side or "right", "where": where})
    if re.search(r"burn(ed)? scar|burn(s|ed)? (on|across)", t):
        out.setdefault("scars", []).append({"side": "left", "where": "burn"})
    if re.search(r"war ?paint|painted face|face paint|woad", t):
        out["paint"] = True
    if re.search(r"tattoo|inked|tribal (marks|markings)|markings|runes? (on|across) (his|her|their) (face|cheek|brow)", t):
        out["tattoo"] = True
    if re.search(r"\bold\b(?!\s+(?:breaks|scars|wounds|injuries|clothes|coat|armor|armour|boots|sword|hat|book)\b)|elderly|\baged\b|wrinkl|venerable|grizzled|ancient|weathered face|in (his|her|their) (sixties|seventies|eighties)"
                 r"|\b(sixty|seventy|eighty|ninety)\b|\b[6-9]\d(-| )years?(-| )old", t):
        out["age"] = "old"
    elif re.search(r"\byoung\b|youth|boyish|girlish|teen|barely an adult|fresh-faced", t):
        out["age"] = "young"
    if re.search(r"\b(stocky|broad|burly|brawny|hulking|heavyset|barrel|muscular|thickset|stout|portly|heavy)\b", t):
        out["build"] = "broad"
    elif re.search(r"\b(thin|gaunt|slender|wiry|lanky|slight|willowy|skinny|lean|bony)\b", t):
        out["build"] = "slender"
    if re.search(r"\b(smil|grin|cheerful|warm|jovial|laugh)", t):
        out["expression"] = "smile"
    elif re.search(r"\bsmirk|sly|wry|mocking|knowing look", t):
        out["expression"] = "smirk"
    elif re.search(r"\b(scowl|grim|stern|frown|glower|dour|severe|hard-faced|cold)", t):
        out["expression"] = "stern"
    for word, hw in (("tricorn", "tricorn"), ("wizard's hat", "wizard hat"), ("pointed hat", "wizard hat"),
                     ("pointy hat", "wizard hat"), ("feathered", "feather cap"), ("crown", "crown"), ("diadem", "circlet"),
                     ("circlet", "circlet"), ("tiara", "circlet"), ("helm", "helm"), ("helmet", "helm"),
                     ("bandana", "bandana"), ("headscarf", "bandana"), ("kerchief", "bandana"), ("antler", "antlers"),
                     ("hood", "hood"), ("cowl", "hood"), ("hat", "hat"), ("cap", "hat"), ("veil", "veil")):
        # whole words only: "crowns" is money, "captain"/"cape" aren't caps, "hatch" isn't a hat
        tail = r"(ed)?\b" if word == "crown" else r"(s|ed)?\b"
        if re.search(r"\b" + re.escape(word) + tail, t) and not re.search(r"(hood|hat|helm)[a-z]* (down|off|thrown back|pushed back)", t):
            out["headwear"] = hw
            break
    if re.search(r"\b(no|without a|bare)[- ]?(hat|hood|helm)|bareheaded|hood (down|thrown back|pushed back)", t):
        out["headwear"] = "none"
    if re.search(r"\b(plate|full plate|plate armor|breastplate|cuirass|half plate)", t):
        out["outfit"] = "plate"
    elif re.search(r"chain ?mail|chain shirt|ring mail|scale mail|mail shirt|hauberk", t):
        out["outfit"] = "chain"
    elif re.search(r"\bleathers\b|leather armor|leather jerkin|studded leather|brigandine", t):
        out["outfit"] = "leather"
    elif re.search(r"\bfurs?\b|pelts?\b|bearskin|wolfskin", t):
        out["outfit"] = "furs"
    elif re.search(r"vestments|cassock|surplice|habit\b|priestly", t):
        out["outfit"] = "vestments"
    elif re.search(r"\brobes?\b|gown\b", t):
        out["outfit"] = "robe"
    elif re.search(r"doublet|finery|silks\b|brocade|velvet|fine clothes|embroidered", t):
        out["outfit"] = "doublet"
    elif re.search(r"\bcoat\b|frock|greatcoat|longcoat", t):
        out["outfit"] = "coat"
    elif re.search(r"\brags|tunic|homespun|apron|work clothes|smock|peasant|\bdress\b", t):
        out["outfit"] = "tunic"
    cc = _near(w, CLOTH_NOUNS, CLOTH_COLORS)
    if cc:
        out["cloth"] = CLOTH_COLORS[cc]
    if re.search(r"\bcloak|cape|mantle", t):
        out["cloak"] = True
        ck = _near(w, {"cloak", "cape", "mantle"}, CLOTH_COLORS)
        if ck:
            out["cloak_color"] = CLOTH_COLORS[ck]
    if re.search(r"earring|ear-ring|pierced ear|hoops? in (his|her|their) ear", t):
        out["earrings"] = True
    if re.search(r"nose ?ring|pierced nose", t):
        out["nosering"] = True
    if re.search(r"holy symbol|sun pendant|amulet of|medallion", t):
        out["pendant"] = "sun"
    elif re.search(r"necklace|pendant|amulet|locket|chain around (his|her|their) neck", t):
        out["pendant"] = "gem"
    if re.search(r"curl(ing|ed)? horns|ram'?s? horns|ram-like", t):
        out["horns"] = "ram"
    elif re.search(r"swept(-back)? horns|backswept horns", t):
        out["horns"] = "swept"
    elif re.search(r"broken horn|chipped horn|snapped horn", t):
        out["horns"] = "broken"
    elif re.search(r"\bhorns?\b|horned", t):
        out["horns"] = "tall"
    if re.search(r"pointed ears|pointy ears|long ears", t):
        out["ears"] = "pointed"
    if re.search(r"tusks?\b", t):
        out["tusks"] = True
    presentation=presentation_from(t)
    if presentation:out['presentation']=presentation
    for word, sp in SPECIES_WORDS.items():
        if re.search(r"\b" + word + r"\b", t):
            out["species_hint"] = sp
            break
    if re.search(r'hair (?:up )?(?:in|tied in|twisted (?:in|into)) (?:a )?knot|\bbun\b',t):
        out['hair_style']='bun'
    return out


# ============================================================== what a creature looks like

def _style_for(e):
    if e["kind"] == "pc":
        cls = max(e.get("classes", {"Fighter": 1}).items(), key=lambda kv: kv[1])[0]
        return dict(CLASS_STYLE.get(cls, CLASS_STYLE["Fighter"]))
    name = (e.get('srd_name') or e.get('name') or '').lower()
    for key, st in ROLE_STYLE:
        if key in name:
            s = dict(st)
            break
    else:
        s = {"outfit": "tunic"}
    s["bg"] = SIDE_BG.get(e.get("side", "enemy"), SIDE_BG["neutral"])
    return s


def species_of(e):
    return visual_identity(e)['species']


def is_humanlike(e):
    if e["kind"] == "pc":
        return True
    t = (e.get("type") or "").lower()
    name = (e.get('srd_name') or e.get('name') or '').lower()
    declared=e.get('species') or e.get('race') or (e.get('look') or {}).get('species') or (e.get('art_of') or {}).get('species')
    return t.startswith('humanoid') or (species_of(e) in set(SPECIES_WORDS.values()) and bool(declared)) or any(re.search(r'\b'+k+r'\b',name) for k in HUMANLIKE_NAMES)


LOOK_FIELDS = ("hair", "beard", "eyes", "skin", "marks", "headwear", "outfit", "cloak", "build", "age",
               "expression", "horns", "accent", "background", "presentation", "species")


def canonical_species(value):
    """Normalize visual species without changing the entity's mechanical species."""
    text=str(value or '').strip()
    return (SPECIES_WORDS.get(text.lower()) or CREATURE_WORDS.get(text.lower()) or text.title()) if text else None


def presentation_from(value):
    """Read the subject's first identity cue, not clothing or a later person's pronouns."""
    value=re.sub(r'\b(?:men[ -]at[ -]arms|man[ -]at[ -]arms|guardsmen|guardsman|townsmen|townsman|armsmen|armsman|spearmen|spearman|watchmen|watchman|footmen|footman)\b','man',str(value),flags=re.I)
    value=re.sub(r'\b(?:townswoman|townswomen|washerwoman|washerwomen)\b','woman',value,flags=re.I)
    words={'feminine':'feminine','female':'feminine','woman':'feminine','women':'feminine','girl':'feminine','lady':'feminine',
           'matron':'feminine','maiden':'feminine','mother':'feminine','sister':'feminine','queen':'feminine','she':'feminine','her':'feminine','hers':'feminine','herself':'feminine',
           'masculine':'masculine','male':'masculine','man':'masculine','men':'masculine','boy':'masculine','lord':'masculine',
           'gentleman':'masculine','sir':'masculine','father':'masculine','brother':'masculine','king':'masculine','he':'masculine','him':'masculine','his':'masculine','himself':'masculine',
           'androgynous':'androgynous','neutral':'androgynous','nonbinary':'androgynous','non-binary':'androgynous',
           'they':'androgynous','them':'androgynous','their':'androgynous'}
    for word in _words(value):
        if word in words:return words[word]
    return None


def subject_description(text):
    """Only the opening description of this subject; later scene actions are not appearance."""
    opening=re.split(r'(?:[.!?;]\s|\n)',str(text or '').strip(),maxsplit=1)[0]
    return re.split(r'\b(?:grabbed|seized|dragged|restrained|pushed|struck|attacked|escorted|carried|pulled|followed|helped|standing beside|next to|beside)\b',opening,maxsplit=1,flags=re.I)[0].strip(' ,;:')[:600]


def subject_species(text,words):
    nominal=re.split(r'\b(?:with|who|whose|by|after|beside|next to|from|in|wearing|tending|guarding|holding|watching|speaking|talking)\b',subject_description(text),maxsplit=1,flags=re.I)[0]
    hits=[(match.start(),-len(word),sp) for word,sp in words.items()
          if (match:=re.search(r'\b'+re.escape(word)+r'\b',nominal.lower()))]
    implied=re.search(r'\b(?:townswom[ae]n|townsm[ae]n|washerwom[ae]n|woman|women|man|men)\b',nominal,re.I)
    if implied:hits.append((implied.start(),-len(implied.group()),'Human'))
    if hits:return min(hits)[2]
    return None


def visual_identity(e):
    """One identity for portraits, map faces and bodies; unknown presentation stays neutral.

    Visual pins and preserved appearances precede structured identity, public description,
    then stat block/name hints. A job, equipped armor or costume never defines identity.
    """
    look=e.get('look') or {};kept=e.get('art_of') or {};bio=e.get('bio') or {};profile=e.get('portrait_profile') or {}
    desc=profile.get('source_description') if profile else subject_description(e.get('appearance') or bio.get('appearance') or '')
    species=None;species_source='unspecified'
    for source,value in (('look',look.get('species')),('preserved',kept.get('species')),
                         ('profile',(profile.get('identity') or {}).get('species')),
                         ('entity',e.get('species') or e.get('race')),('bio',bio.get('species') or bio.get('race'))):
        if value:
            species=canonical_species(value)
            species_source=(profile['identity'].get('species_source','unspecified') if source=='profile' else source)
            break
    if not species:
        humanoid=e.get('kind')=='pc' or str(e.get('type','')).lower().startswith('humanoid')
        words=SPECIES_WORDS if humanoid else {**SPECIES_WORDS,**CREATURE_WORDS}
        hints=(('description',desc),('stat block',e.get('srd_name','')),('name',e.get('name',''))) if humanoid else (
            ('stat block',e.get('srd_name','')),('description',desc),('name',e.get('name','')))
        for source,value in hints:
            # Earliest subject species wins; related people mentioned later do not take precedence.
            found=subject_species(value,words) if source=='description' else canonical_species(value) if str(value).lower() in words else None
            if not found and source!='description':
                hits=[(match.start(),-len(word),sp) for word,sp in words.items() if (match:=re.search(r'\b'+re.escape(word)+r'\b',str(value).lower()))]
                found=min(hits)[2] if hits else None
            if found:species=found;species_source=source;break
    presentation=None;presentation_source='unspecified'
    for source,value in (('look',look.get('presentation')),('preserved',kept.get('presentation') or (kept.get('traits') or kept.get('look') or {}).get('presentation')),
                         ('profile',(profile.get('identity') or {}).get('presentation')),
                         ('entity',e.get('presentation') or e.get('gender') or e.get('sex') or e.get('pronouns')),
                         ('bio',bio.get('presentation') or bio.get('gender') or bio.get('sex') or bio.get('pronouns')),
                         ('description',desc),('name',e.get('name',''))):
        found=presentation_from(re.split(r'\b(?:with|who|whose|by|after|beside|next to|from)\b',str(value or ''),maxsplit=1,flags=re.I)[0] if source=='description' else value)
        if found:
            presentation=found
            presentation_source=(profile['identity'].get('presentation_source','unspecified') if source=='profile' else source)
            break
    return dict(species=species or 'Human',presentation=presentation or 'androgynous',
                species_source=species_source,presentation_source=presentation_source)


def _art_id(e):
    """The seed a creature's art is drawn from: its own id, or the creature whose face it keeps (`asset look --like`)."""
    return (e.get("art_of") or {}).get("seed") or e["id"]


def look_of(e):
    """The resolved visual traits used to draw a humanlike creature (defaults ← description ← DM's look fields)."""
    kept = e.get("art_of") or {}
    identity=visual_identity(e);sp=identity['species']
    r = seeded("look", _art_id(e), kept.get("name") or e.get("name", ""))
    st = dict(kept["style"]) if kept.get("style") else _style_for(e)
    st.update({k: tuple(v) for k, v in st.items() if isinstance(v, list)})   # stored styles come back from JSON as lists
    tones = SPECIES_SKIN.get(sp, HUMAN_TONES)
    L = {"species": sp, "skin": r.choice(tones), "hair_color": r.choice(["#1d1a1c", "#3b2618", "#5a3a22", "#6e3a1f", "#7f2f1a",
                                                                          "#c9953f", "#d9b46a", "#2a1d16"]),
         "hair_style": r.choice(["short", "short", "long", "long", "ponytail", "curly", "braid", "wild", "bun"]),
         "eye_color": r.choice(["#5a3a1e", "#3a78c0", "#3f8a3a", "#8a6a2a", "#8a949c", "#2a1a10"]),
         "beard": "none", "build": "average", "age": "adult", "expression": r.choice(["neutral", "neutral", "smile", "smirk", "stern"]),
         "outfit": st.get("outfit", "tunic"), "cloth": st.get("cloth", r.choice(list(CLOTH_COLORS.values()))),
         "headwear": "none", "bg": st.get("bg", ("#3a3a4a", "#0a0a12")), "pendant": st.get("pendant"),
         "paint": r.random() < st.get("paint", 0), "eye_glow": r.random() < st.get("glow", 0), "collar": st.get("collar", False),
         "ears": "round", "horns": None, "tusks": False, "scars": [], "freckles": False, "tattoo": False, "earrings": r.random() < .2,
         "cloak": r.random() < .3, "cloak_color": None, "eyepatch": None, "nosering": False, "undercut": False, "seed": _art_id(e)}
    L["cloak_color"] = darken(L["cloth"], .25) if r.random() < .5 else r.choice(["#3a2a1e", "#2a3a2a", "#2a2a3a", "#5a1a1e"])
    if st.get("headwear") and r.random() < st["headwear"][1]:
        L["headwear"] = st["headwear"][0]
    if L["hair_style"] in ("long", "braid") and L["headwear"] == "helm":
        L["headwear"] = "none"
    # species defaults
    if sp == "Elf":
        L["ears"] = "long"
        L["hair_color"] = r.choice(["#1d1a1c", "#d9b46a", "#e8e2cf", "#c9cdd2", "#7f2f1a", "#5a3a22", "#2a3a5a"])
        L["hair_style"] = r.choice(["long", "long", "braid", "ponytail", "short"])
    elif sp == "Dwarf":
        L["beard"] = r.choice(["long", "long", "short", "none"])
        L["hair_style"] = r.choice(["braid", "short", "wild", "bald", "long"])
        L["build"] = "broad"
        L["hair_color"] = r.choice(["#7f2f1a", "#1d1a1c", "#5a3a22", "#c0541f", "#8e8f93", "#d8a946"])
    elif sp == "Halfling":
        L["ears"] = "point"
        L["hair_style"] = r.choice(["curly", "curly", "short", "long"])
        L["expression"] = r.choice(["smile", "smirk", "neutral"])
    elif sp == "Gnome":
        L["ears"] = "point"
        L["hair_style"] = r.choice(["wild", "curly", "short", "bun"])
        L["hair_color"] = r.choice(["#e8e2cf", "#c0541f", "#3a5fb0", "#d77aa6", "#5a3a22", "#d9b46a"])
    elif sp == "Orc":
        L["ears"] = "point"
        L["tusks"] = True
        L["build"] = "broad"
        L["hair_color"] = r.choice(["#1d1a1c", "#2a1d16", "#3b2618"])
        L["hair_style"] = r.choice(["mohawk", "long", "braid", "bald", "wild"])
    elif sp == "Tiefling":
        L["ears"] = r.choice(["point", "long"])
        L["horns"] = r.choice(["ram", "tall", "swept"])
        L["hair_color"] = r.choice(["#1d1a1c", "#6b3fa0", "#8a1f24", "#16141a", "#3a5fb0"])
        L["eye_color"] = r.choice(["#d8b030", "#c02a20", "#ecebe6", "#d8761a"])
        L["solid_eyes"] = r.random() < .6
        leg = str(e.get("ancestry", "")).lower()
        L["skin"] = {"infernal": r.choice(["#b8453d", "#a04a4a", "#c6705a"]), "abyssal": r.choice(["#9c3f5c", "#7a4a8e"]),
                     "chthonic": r.choice(["#6a4a7a", "#7a7a8a"])}.get(leg, L["skin"])
    elif sp == "Dragonborn":
        anc = str(e.get("ancestry") or "").lower()
        L["skin"] = DRAGON_SCALES.get(anc) or r.choice(list(DRAGON_SCALES.values()))
        L["hair_style"] = "bald"
        L["beard"] = "none"
        L["eye_color"] = r.choice(["#d8b030", "#c8891a", "#c02a20", "#3f8a3a"])
        L["reptile"] = True
        L["build"] = "broad"
    elif sp == "Goliath":
        L["hair_style"] = r.choice(["bald", "bald", "short", "braid"])
        L["tattoo"] = True
        L["build"] = "broad"
    elif sp in ("Goblin",):
        L["ears"] = "wide"
        L["tusks"] = r.random() < .3
        L["eye_color"] = r.choice(["#d8b030", "#c02a20", "#c8891a"])
        L["hair_style"] = r.choice(["bald", "bald", "short", "ponytail"])
        L["hair_color"] = r.choice(["#1d1a1c", "#2a1d16", "#3b2618"])
    elif sp in ("Kobold", "Lizardfolk"):
        L["reptile"] = True
        L["hair_style"] = "bald"
        L["eye_color"] = r.choice(["#d8b030", "#c02a20"])
    if L["beard"] == "none" and sp in ("Human", "Tiefling", "Orc", "Goliath") and r.random() < .22 and identity['presentation']=='masculine':
        L["beard"] = r.choice(["short", "stubble", "mustache", "goatee"])
    # armor actually worn by a PC decides the outfit
    if e["kind"] == "pc" and not kept:
        worn = [it for it in e.get("inventory", []) if it.get("kind") == "armor" and it.get("equipped") and it.get("category") != "shield"]
        if worn:
            cat = worn[0].get("category")
            n = worn[0].get("name", "").lower()
            L["outfit"] = "plate" if cat == "heavy" or "plate" in n else "chain" if cat == "medium" else "leather"
        elif L["outfit"] in ("plate", "chain", "leather"):
            L["outfit"] = {"Monk": "monk", "Barbarian": "furs"}.get(max(e["classes"].items(), key=lambda kv: kv[1])[0], "tunic")
    # what the description says
    profile=e.get('portrait_profile') or {}
    desc = profile.get('source_description') if profile else e.get("appearance") or (e.get("bio") or {}).get("appearance") or ""
    _apply(L, read_description(desc))
    _apply(L,profile.get('traits') or {})
    _apply(L,kept.get('traits') or {})
    # what the DM pinned with `asset look`
    for field, text in (e.get("look") or {}).items():
        _apply(L, _read_field(field, text))
    L.update(species=sp,presentation=identity['presentation'])
    if L["age"] == "old" and not _mentions_hair_color(desc, e.get("look")):
        L["hair_color"] = mix(L["hair_color"], "#d8d8d4", .75)
    L.setdefault("beard_color", L["hair_color"])
    if isinstance(L.get('bg'),list):L['bg']=tuple(L['bg'])
    return L


def _mentions_hair_color(desc, look):
    return bool(read_description(desc).get("hair_color") or (look or {}).get("hair"))


def _apply(L, found):
    for k, v in found.items():
        if k == "species_hint":
            continue
        if k == "scars":
            L["scars"] = L.get("scars", []) + [s for s in v if s not in L.get("scars", [])]
        else:
            L[k] = v


def _read_field(field, text):
    """A single `asset look` field: '--hair "long silver braid"' reads only hair traits from it, and so on."""
    t = str(text or "").strip()
    low = t.lower()
    if not t:
        return {}
    if low.startswith("#") and re.match(r"^#[0-9a-f]{6}$", low):
        key = {"hair": "hair_color", "eyes": "eye_color", "skin": "skin", "outfit": "cloth", "cloak": "cloak_color",
               "accent": "cloth", "beard": "beard_color"}.get(field)
        return {key: low} if key else {}
    if field == "hair":
        f = read_description(t + " hair")
        out = {k: v for k, v in f.items() if k in ("hair_color", "hair_style", "undercut")}
        if re.search(r"\bnone|bald|shaved", low):
            out["hair_style"] = "bald"
        return out
    if field == "beard":
        if re.search(r"\bnone|clean|no beard", low):
            return {"beard": "none"}
        f = read_description(t if re.search(r"beard|stubble|mustache|moustache|goatee", low) else t + " beard")
        out = {k: v for k, v in f.items() if k in ("beard",)}
        c = next((HAIR_COLORS[w] for w in _words(low) if w in HAIR_COLORS), None)
        if c:
            out["beard_color"] = c
        return out
    if field == "eyes":
        out = {}
        c = next((EYE_COLORS[w] for w in _words(low) if w in EYE_COLORS), None)
        if c:
            out["eye_color"] = c
        if "glow" in low:
            out["eye_glow"] = True
        if "patch" in low:
            out["eyepatch"] = "left" if "left" in low else "right"
        if re.search(r"solid|no whites|pupilless|black sclera", low):
            out["solid_eyes"] = True
        return out
    if field == "skin":
        out = {}
        c = next((SKIN_TONES[w] for w in _words(low) if w in SKIN_TONES), None)
        if c:
            out["skin"] = c
        if "freckle" in low:
            out["freckles"] = True
        return out
    if field == "presentation":
        return {'presentation':presentation_from(t)}
    if field == 'species':return {'species':canonical_species(t)}
    if field in ("marks", "face"):
        f = read_description(t)
        return {k: v for k, v in f.items() if k in ("scars", "freckles", "paint", "tattoo", "eyepatch", "eyepatch_color",
                                                     "spectacles", "earrings", "nosering",
                                                     "tusks", "ears", "expression", "eye_glow", "presentation")}
    if field == "headwear":
        if re.search(r"\bnone|bare|no hat", low):
            return {"headwear": "none"}
        return {"headwear": read_description(t).get("headwear") or ("hood" if "hood" in low else "hat")}
    if field == "outfit":
        f = read_description(t)
        out = {k: v for k, v in f.items() if k in ("outfit", "cloth", "pendant", "cloak", "cloak_color")}
        if low in {'plate','chain','leather','robe','tunic','doublet','vestments','coat','furs','druid','monk'}:
            out['outfit']=low
        if "cloth" not in out:
            c = next((CLOTH_COLORS[w] for w in _words(low) if w in CLOTH_COLORS), None)
            if c:
                out["cloth"] = c
        return out
    if field == "cloak":
        if re.search(r"\bnone|no cloak", low):
            return {"cloak": False}
        c = next((CLOTH_COLORS[w] for w in _words(low) if w in CLOTH_COLORS), None)
        return {"cloak": True, **({"cloak_color": c} if c else {})}
    if field == "build":
        return {"build": "broad" if re.search(r"broad|stock|burly|big|heavy|muscular|stout", low) else
                "slender" if re.search(r"slen|thin|lean|wiry|slight|gaunt", low) else "average"}
    if field == "age":
        return {"age": "old" if re.search(r"old|elder|aged|grey|gray|venerable", low) else "young" if "young" in low else "adult"}
    if field == "expression":
        f = read_description(t)
        return {"expression": f.get("expression", "neutral")}
    if field == "horns":
        if re.search(r"\bnone|no horns", low):
            return {"horns": None}
        return {"horns": "ram" if re.search(r"ram|curl", low) else "swept" if "swept" in low or "back" in low else
                "broken" if "broken" in low else "tall"}
    if field in ("accent", "background"):
        c = next((CLOTH_COLORS[w] for w in _words(low) if w in CLOTH_COLORS), None)
        if not c:
            return {}
        return {"bg": (lighten(c, .15), darken(c, .82))} if field == "background" else {"cloth": c}
    return {}


def describe_look(e):
    """Human-readable summary of what the generator will draw (for the DM's CLI)."""
    if not is_humanlike(e):
        t = (e.get("type") or "creature").split()[0].lower()
        return f"{e['name']}: creature art ({t} palette, emblem '{assets.icon_for_entity(e)}')"
    L = look_of(e)
    name_of = lambda table, v: next((k for k, x in table.items() if x == v), v)  # noqa: E731
    bits = [f"species {L['species']}", f"presentation {L['presentation']}", f"skin {name_of(SKIN_TONES, L['skin'])}",
            f"hair {L['hair_style']} {name_of(HAIR_COLORS, L['hair_color'])}", f"eyes {name_of(EYE_COLORS, L['eye_color'])}"
            + (" (glowing)" if L.get("eye_glow") else ""), f"beard {L['beard']}", f"outfit {L['outfit']} {name_of(CLOTH_COLORS, L['cloth'])}",
            f"headwear {L['headwear']}", f"build {L['build']}", f"age {L['age']}", f"expression {L['expression']}"]
    extras = [k for k in ("freckles", "tattoo", "paint", "earrings", "nosering", "tusks", "cloak") if L.get(k)]
    if L.get("horns"):
        extras.append(f"{L['horns']} horns")
    if L.get("eyepatch"):
        extras.append(f"eyepatch ({L['eyepatch']})")
    if L.get("spectacles"):
        extras.append(f"{L['spectacles']} spectacles")
    if L.get("scars"):
        extras.append("scars: " + ", ".join(f"{s['side']} {s['where']}" for s in L["scars"]))
    return f"{e['name']}: " + "; ".join(bits) + (f"; also {', '.join(extras)}" if extras else "")


def identity_report(e):
    """Read-only DM audit: resolved identity, selected art and actionable missing data."""
    identity=visual_identity(e);face=portrait_choice(e);body=painted.corpse_selection(e)
    show=lambda pair:f'{pair[0]}/{pair[1]:02d}' if pair else 'neutral/anatomical fallback'
    warnings=[]
    if is_humanlike(e):
        if identity['presentation_source']=='unspecified':warnings.append('Presentation unspecified: neutral art. Pin --presentation when known.')
        if identity['species_source']=='unspecified':warnings.append('Species unspecified: Human fallback. Pin --species when known.')
        if not face:warnings.append('No compatible painted face; using an anatomical fallback.')
        if not body:warnings.append('No compatible body; using a covered fallback.')
    if e.get('portrait'):warnings.append('Pinned portrait takes precedence; its identity cannot be verified automatically. Clear/re-pin it after correcting the look.')
    structured=canonical_species(e.get('species') or e.get('race'))
    if structured and structured!=identity['species']:warnings.append(f"Visual species {identity['species']} differs from stored species {structured}; stats are unchanged.")
    from .portrait_profiles import descriptive
    raw=e.get('appearance') or (e.get('bio') or {}).get('appearance') or ''
    text=subject_description(raw) if descriptive(raw) else ''
    description=read_description(text)
    description['species_hint']=subject_species(text,{**SPECIES_WORDS,**CREATURE_WORDS})
    description['presentation']=presentation_from(re.split(r'\b(?:with|who|whose|by|after|beside|next to|from)\b',text,maxsplit=1,flags=re.I)[0])
    if description.get('species_hint') and description['species_hint']!=identity['species']:warnings.append('Public description and resolved species disagree; check the subject or pin.')
    if description.get('presentation') and description['presentation']!=identity['presentation']:warnings.append('Public description and resolved presentation disagree; check the pin or description.')
    summary=(f"{e['id']}: {identity['species']} / {identity['presentation']} "
             f"(species: {identity['species_source']}; presentation: {identity['presentation_source']}); face {show(face)}; body {show(body)}")
    return dict(identity=identity,face=face,body=body,warnings=warnings,summary=summary)


# ============================================================== drawing a bust

CX = 160


def _head_path(w, top, chin, jaw):
    L, R, jw = CX - w, CX + w, w * jaw
    cheek = top + (chin - top) * .62
    return (f"M{CX},{top} C{CX + w * .6:.1f},{top} {R},{top + 22} {R-3},{top + 58} "
            f"C{R+2},{cheek - 4:.1f} {R - 3},{cheek + 12:.1f} {CX + jw:.1f},{chin - 18} "
            f"C{CX + jw - 9:.1f},{chin - 5} {CX + 11},{chin} {CX},{chin} "
            f"C{CX - 11},{chin} {CX - jw + 9:.1f},{chin - 5} {CX - jw:.1f},{chin - 18} "
            f"C{L + 3},{cheek + 12:.1f} {L-2},{cheek - 4:.1f} {L+3},{top + 58} "
            f"C{L},{top + 22} {CX - w * .6:.1f},{top} {CX},{top} Z")


def bust_svg(e, mode="portrait", size=None):
    """mode: 'portrait' (framed, name plate), 'face' (square crop for tokens/avatars), 'bust' (unframed 320x400)."""
    L = look_of(e)
    r = seeded("draw", L["seed"])
    P = f"b{hashlib.md5(e['id'].encode()).hexdigest()[:5]}"  # id prefix so inlined copies never collide
    skin = L["skin"]
    skin_hi, skin_lo, skin_line = lighten(skin, .12), darken(skin, .38), darken(skin, .58)
    hair, hair_hi, hair_lo = L["hair_color"], lighten(L["hair_color"], .28), darken(L["hair_color"], .35)
    cloth = L["cloth"]
    sp = L["species"]
    small = sp in ("Halfling", "Gnome", "Goblin", "Kobold")
    anatomy_rng = seeded('anatomy', L['seed'])
    w = {"Dwarf": 63, "Orc": 62, "Goliath": 61, "Elf": 53, "Gnome": 56, "Halfling": 55, "Goblin": 54, "Dragonborn": 57}.get(sp, 57)
    w += anatomy_rng.uniform(-4, 4)
    top, chin = (94, 223) if not small else (98, 220)
    jaw = {"Orc": .78, "Dwarf": .75, "Goliath": .76, "Dragonborn": .8, "Elf": .5, "Goblin": .55}.get(sp, .62)
    if sp == "Dragonborn":
        chin = 238
    if L["build"] == "broad":
        jaw += .06
    jaw += anatomy_rng.uniform(-.045,.045)
    pres = L.get("presentation")
    if pres == "feminine":
        jaw -= .07
    elif pres == "masculine":
        jaw += .05
    ey = 158 if not small else 160
    ex = 23 if sp not in ("Goblin", "Gnome") else 25
    bg1, bg2 = L["bg"]
    out = []
    add = out.append

    # ---------------------------------------------------------------- defs
    add(f'<defs>'
        f'<radialGradient id="{P}bg" cx="35%" cy="30%" r="75%"><stop offset="0" stop-color="{mix(bg1, "#ac9571", .3)}"/>'
        f'<stop offset=".55" stop-color="{darken(bg1, .35)}"/><stop offset="1" stop-color="{bg2}"/></radialGradient>'
        f'<radialGradient id="{P}vig" cx="50%" cy="42%" r="70%"><stop offset=".55" stop-color="#000" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="#000" stop-opacity=".55"/></radialGradient>'
        f'<radialGradient id="{P}skin" cx="24%" cy="25%" r="85%"><stop offset="0" stop-color="{skin_hi}"/>'
        f'<stop offset=".4" stop-color="{skin}"/><stop offset="1" stop-color="{skin_lo}"/></radialGradient>'
        f'<linearGradient id="{P}hair" x1="0" y1="0" x2=".3" y2="1"><stop offset="0" stop-color="{hair_hi}"/>'
        f'<stop offset=".5" stop-color="{hair}"/><stop offset="1" stop-color="{hair_lo}"/></linearGradient>'
        f'<linearGradient id="{P}cloth" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{lighten(cloth, .14)}"/>'
        f'<stop offset="1" stop-color="{darken(cloth, .45)}"/></linearGradient>'
        f'<linearGradient id="{P}metal" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#eef2f5"/>'
        f'<stop offset=".35" stop-color="#a9b3bd"/><stop offset=".7" stop-color="#6a747e"/><stop offset="1" stop-color="#3a4048"/></linearGradient>'
        f'<linearGradient id="{P}leather" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8a5a34"/>'
        f'<stop offset="1" stop-color="#3a2212"/></linearGradient>'
        f'<linearGradient id="{P}horn" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6a5448"/>'
        f'<stop offset="1" stop-color="#1e1614"/></linearGradient>'
        f'<pattern id="{P}chain" width="7" height="6" patternUnits="userSpaceOnUse"><rect width="7" height="6" fill="#5a646e"/>'
        f'<circle cx="3.5" cy="3" r="2.4" fill="none" stroke="#b8c2cc" stroke-width="1.1"/></pattern>'
        f'<pattern id="{P}scales" width="10" height="8" patternUnits="userSpaceOnUse"><path d="M0 8 Q5 0 10 8" fill="none" '
        f'stroke="{darken(skin, .3)}" stroke-width="1" stroke-opacity=".55"/></pattern>'
        f'<filter id="{P}glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.4" result="b"/>'
        f'<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
        f'<filter id="{P}soft"><feGaussianBlur stdDeviation="6"/></filter>'
        f'<clipPath id="{P}head"><path d="{_head_path(w, top, chin, jaw)}"/></clipPath>'
        f'</defs>')

    # ---------------------------------------------------------------- backdrop
    add(f'<rect width="320" height="400" fill="url(#{P}bg)"/>')
    # Engraved architectural arch: a quiet, shared visual language across portraits.
    add(f'<path d="M38 360 V142 A122 122 0 0 1 282 142 V360 M48 360 V142 A112 112 0 0 1 272 142 V360" '
        f'fill="none" stroke="#d9bd82" stroke-width="1" opacity=".18"/>'
        f'<circle cx="160" cy="142" r="92" fill="none" stroke="#d9bd82" stroke-width=".7" opacity=".13"/>')
    for i in range(5):  # soft light rays
        a = -40 + i * 20 + r.uniform(-6, 6)
        add(f'<path d="M160 -20 L{160 + 420 * math.sin(math.radians(a - 4)):.0f} 420 '
            f'L{160 + 420 * math.sin(math.radians(a + 4)):.0f} 420 Z" fill="#fff" fill-opacity=".035"/>')
    for _ in range(14):
        add(f'<circle cx="{r.uniform(10, 310):.0f}" cy="{r.uniform(10, 300):.0f}" r="{r.uniform(.8, 2.4):.1f}" '
            f'fill="{lighten(bg1, .6)}" fill-opacity="{r.uniform(.12, .35):.2f}"/>')
    add(f'<ellipse cx="160" cy="330" rx="140" ry="60" fill="#000" fill-opacity=".35" filter="url(#{P}soft)"/>')

    # ---------------------------------------------------------------- behind the head
    hw = L["headwear"]
    cloak_col = L.get("cloak_color") or darken(cloth, .25)
    if hw == "hood":
        add(f'<path d="M{CX - 82},330 C{CX - 92},190 {CX - 62},68 {CX},60 C{CX + 62},68 {CX + 92},190 {CX + 82},330 Z" '
            f'fill="{darken(cloak_col, .35)}"/>')
    style = L["hair_style"] if hw not in ("hood", "helm") else ("long" if L["hair_style"] in ("long", "braid", "dreads") else "hidden")
    if style in ("long", "curly", "wild", "dreads") and hw not in ("hood", "helm"):
        spread = {"curly": 26, "wild": 30, "dreads": 18}.get(style, 16)
        ln = 312 if style != "curly" else 268
        add(f'<path d="M{CX - w - 8},{top + 40} C{CX - w - spread - 14},{top + 120} {CX - w - spread - 8},{ln - 40} {CX - w - spread + 4},{ln} '
            f'L{CX + w + spread - 4},{ln} C{CX + w + spread + 8},{ln - 40} {CX + w + spread + 14},{top + 120} {CX + w + 8},{top + 40} '
            f'C{CX + w},{top - 20} {CX - w},{top - 20} {CX - w - 8},{top + 40} Z" fill="url(#{P}hair)"/>')
        add(f'<path d="M{CX - w - 8},{top + 40} C{CX - w - spread - 14},{top + 120} {CX - w - spread - 8},{ln - 40} {CX - w - spread + 4},{ln} '
            f'L{CX + w + spread - 4},{ln} C{CX + w + spread + 8},{ln - 40} {CX + w + spread + 14},{top + 120} {CX + w + 8},{top + 40}" '
            f'fill="none" stroke="{hair_lo}" stroke-opacity=".5" stroke-width="2"/>')
    elif style == "ponytail":
        add(f'<path d="M{CX + 30},{top + 20} C{CX + 90},{top + 10} {CX + 96},{top + 110} {CX + 80},{top + 190} '
            f'C{CX + 74},{top + 150} {CX + 66},{top + 80} {CX + 30},{top + 50} Z" fill="url(#{P}hair)"/>')
    # dragonborn crest horns sweep back behind the head
    if L.get("reptile"):
        for s in (-1, 1):
            add(f'<path d="M{CX + s * 30},{top + 24} C{CX + s * 60},{top - 6} {CX + s * 86},{top - 20} {CX + s * 104},{top - 34} '
                f'C{CX + s * 86},{top - 2} {CX + s * 66},{top + 22} {CX + s * 46},{top + 44} Z" fill="url(#{P}horn)"/>')
            add(f'<path d="M{CX + s * 40},{top + 44} C{CX + s * 66},{top + 30} {CX + s * 80},{top + 30} {CX + s * 96},{top + 22} '
                f'C{CX + s * 82},{top + 44} {CX + s * 64},{top + 58} {CX + s * 46},{top + 64} Z" fill="{darken(skin, .3)}"/>')

    # ---------------------------------------------------------------- body
    sw = {"broad": 128, "slender": 104}.get(L["build"], 116)
    if small:
        sw -= 8
    sh_y = 236
    body = (f"M{CX - sw},402 C{CX - sw},{sh_y + 70} {CX - sw + 16},{sh_y + 22} {CX - 56},{sh_y + 6} "
            f"Q{CX},{sh_y - 4} {CX + 56},{sh_y + 6} C{CX + sw - 16},{sh_y + 22} {CX + sw},{sh_y + 70} {CX + sw},402 Z")
    # neck
    nw = 27 if L["build"] != "broad" else 32
    add(f'<path d="M{CX - nw},{chin - 26} L{CX - nw - 2},{sh_y + 8} Q{CX},{sh_y + 20} {CX + nw + 2},{sh_y + 8} L{CX + nw},{chin - 26} Z" fill="{skin_lo}"/>')
    add(f'<path d="M{CX - nw},{chin - 12} Q{CX},{chin + 12} {CX + nw},{chin - 12} L{CX + nw},{chin - 26} L{CX - nw},{chin - 26} Z" fill="{darken(skin, .38)}" fill-opacity=".55"/>')
    if L.get("reptile"):
        add(f'<path d="M{CX - nw},{chin - 26} L{CX - nw - 2},{sh_y + 8} Q{CX},{sh_y + 20} {CX + nw + 2},{sh_y + 8} L{CX + nw},{chin - 26} Z" fill="url(#{P}scales)"/>')
    add(_outfit(L, P, body, sw, sh_y, r))
    add(f'<defs><clipPath id="{P}foldclip"><path d="{body}"/></clipPath></defs>'
        f'<g clip-path="url(#{P}foldclip)" fill="none" stroke-linecap="round">')
    for s in (-1, 1):
        for k in range(5):
            x, y = CX+s*(46+k*11), sh_y+18+k*12
            add(f'<path d="M{x},{y} Q{x+s*7},{y+28} {x+s*3},{y+66}" '
                f'stroke="{darken(cloth,.65)}" stroke-width="{2.8-k*.3}" opacity=".3"/>'
                f'<path d="M{x-s*2},{y+2} Q{x+s*5},{y+28} {x+s},{y+64}" '
                f'stroke="{lighten(cloth,.5)}" stroke-width=".8" opacity=".22"/>')
    add('</g>')
    if L.get("pendant"):
        add(_pendant(L["pendant"], sh_y, L))
    if L.get("cloak") and hw != "hood" and L["outfit"] not in ("furs",):
        cc = cloak_col
        for s in (-1, 1):
            add(f'<path d="M{CX + s * 50},{sh_y + 4} C{CX + s * (sw - 4)},{sh_y + 10} {CX + s * (sw + 8)},{sh_y + 70} {CX + s * (sw + 6)},402 '
                f'L{CX + s * (sw - 30)},402 C{CX + s * (sw - 26)},{sh_y + 80} {CX + s * 80},{sh_y + 40} {CX + s * 50},{sh_y + 4} Z" fill="{cc}"/>')
            add(f'<path d="M{CX + s * (sw - 8)},{sh_y + 60} C{CX + s * (sw - 6)},{sh_y + 90} {CX + s * (sw - 10)},{sh_y + 110} {CX + s * (sw - 14)},402" '
                f'stroke="{darken(cc, .35)}" stroke-width="2" fill="none" stroke-opacity=".6"/>')
        add(f'<circle cx="{CX - 44}" cy="{sh_y + 12}" r="7" fill="#c9a14a" stroke="#6a4a1a" stroke-width="2"/>')
    if hw == "hood":  # hood drapes over the shoulders
        add(f'<path d="M{CX - 80},{sh_y - 2} C{CX - 60},{sh_y + 30} {CX + 60},{sh_y + 30} {CX + 80},{sh_y - 2} '
            f'L{CX + 96},{sh_y + 26} C{CX + 60},{sh_y + 64} {CX - 60},{sh_y + 64} {CX - 96},{sh_y + 26} Z" fill="{cloak_col}"/>')

    # ---------------------------------------------------------------- ears (behind the head edge)
    ears = L["ears"]
    for s in (-1, 1):
        ex0 = CX + s * (w - 2)
        if L.get("reptile"):
            continue
        if ears == "long":
            add(f'<path d="M{ex0},{ey - 10} C{ex0 + s * 14},{ey - 18} {ex0 + s * 30},{ey - 40} {ex0 + s * 42},{ey - 58} '
                f'C{ex0 + s * 34},{ey - 28} {ex0 + s * 22},{ey + 6} {ex0 - s * 2},{ey + 22} Z" fill="{skin}" stroke="{skin_lo}" stroke-width="1.5"/>')
            add(f'<path d="M{ex0 + s * 4},{ey - 6} C{ex0 + s * 16},{ey - 18} {ex0 + s * 26},{ey - 34} {ex0 + s * 34},{ey - 46}" fill="none" stroke="{skin_lo}" stroke-width="2"/>')
        elif ears in ("point", "pointed"):
            add(f'<path d="M{ex0},{ey - 8} C{ex0 + s * 12},{ey - 14} {ex0 + s * 18},{ey - 24} {ex0 + s * 24},{ey - 32} '
                f'C{ex0 + s * 22},{ey - 10} {ex0 + s * 16},{ey + 10} {ex0 - s * 2},{ey + 20} Z" fill="{skin}" stroke="{skin_lo}" stroke-width="1.5"/>')
        elif ears == "wide":
            add(f'<path d="M{ex0},{ey - 12} C{ex0 + s * 20},{ey - 22} {ex0 + s * 44},{ey - 30} {ex0 + s * 58},{ey - 34} '
                f'C{ex0 + s * 46},{ey - 8} {ex0 + s * 26},{ey + 12} {ex0 - s * 2},{ey + 18} Z" fill="{skin}" stroke="{skin_lo}" stroke-width="1.5"/>')
        else:
            add(f'<ellipse cx="{ex0 + s * 3}" cy="{ey + 6}" rx="9" ry="15" fill="{skin}" stroke="{skin_lo}" stroke-width="1.5"/>')
            add(f'<path d="M{ex0 + s * 5},{ey - 2} q{s * 4},8 0,16" fill="none" stroke="{skin_lo}" stroke-width="1.5"/>')
        if L.get("earrings") and not L.get("reptile"):
            add(f'<circle cx="{ex0 + s * 4}" cy="{ey + 24}" r="3.6" fill="none" stroke="#e0c060" stroke-width="2"/>')

    # ---------------------------------------------------------------- head
    add(f'<path d="{_head_path(w, top, chin, jaw)}" fill="url(#{P}skin)" stroke="{darken(skin, .4)}" stroke-width="1.5"/>')
    add(illustration.portrait_finish(P, skin, w, top, chin, ey))
    add(f'<g clip-path="url(#{P}head)">')
    if L.get("reptile"):
        add(f'<rect x="{CX - w}" y="{top}" width="{2 * w}" height="{chin - top}" fill="url(#{P}scales)"/>')
        add(f'<ellipse cx="{CX}" cy="{chin - 30}" rx="{w * .62:.0f}" ry="30" fill="{lighten(skin, .25)}" fill-opacity=".55"/>')
        add(f'<path d="M{CX},{top + 4} L{CX},{top + 48}" stroke="{darken(skin, .3)}" stroke-width="3" stroke-opacity=".6"/>')
    # jaw/cheek shading
    add(f'<ellipse cx="{CX - w + 6}" cy="{ey + 26}" rx="16" ry="30" fill="{skin_lo}" fill-opacity=".35"/>'
        f'<ellipse cx="{CX + w - 6}" cy="{ey + 26}" rx="16" ry="30" fill="{skin_lo}" fill-opacity=".35"/>')
    if L["age"] == "old":
        for s in (-1, 1):
            add(f'<path d="M{CX + s * (ex + 14)},{ey + 2} l{s * 7},-3 M{CX + s * (ex + 14)},{ey + 7} l{s * 7},1" stroke="{skin_line}" stroke-width="1" stroke-opacity=".5"/>')
            add(f'<path d="M{CX + s * 16},{ey + 30} Q{CX + s * 22},{ey + 44} {CX + s * 20},{ey + 50}" fill="none" stroke="{skin_line}" stroke-width="1.2" stroke-opacity=".45"/>')
        add(f'<path d="M{CX - 22},{top + 34} q22,-5 44,0 M{CX - 18},{top + 42} q18,-4 36,0" fill="none" stroke="{skin_line}" stroke-width="1" stroke-opacity=".4"/>')
    if L.get("tattoo") and not L.get("reptile"):
        tc = darken(skin, .55) if sp == "Goliath" else "#2a4a7a"
        add(f'<path d="M{CX + 26},{top + 28} l10,14 l-8,10 l12,16 M{CX + 36},{ey + 12} l8,14 M{CX - 44},{ey + 16} l10,-6 l10,6" fill="none" '
            f'stroke="{tc}" stroke-width="2.4" stroke-opacity=".75" stroke-linecap="round" stroke-linejoin="round"/>')
    if L.get("paint"):
        pc = r.choice(["#2a4aa8", "#a8241c", "#1e1c22", "#e8e4d8"])
        for s in (-1, 1):
            add(f'<path d="M{CX + s * 10},{ey + 10} L{CX + s * 44},{ey + 6} L{CX + s * 42},{ey + 14} L{CX + s * 12},{ey + 18} Z" fill="{pc}" fill-opacity=".7"/>')
    add('</g>')
    # blush
    if not L.get("reptile") and sp not in ("Goliath",):
        add(f'<ellipse cx="{CX - 26}" cy="{ey + 24}" rx="10" ry="5.5" fill="#e0707a" fill-opacity=".16"/>'
            f'<ellipse cx="{CX + 26}" cy="{ey + 24}" rx="10" ry="5.5" fill="#e0707a" fill-opacity=".16"/>')
    if L.get("freckles"):
        for _ in range(16):
            s = r.choice((-1, 1))
            add(f'<circle cx="{CX + s * r.uniform(8, 34):.1f}" cy="{ey + r.uniform(12, 30):.1f}" r="{r.uniform(.8, 1.4):.1f}" fill="{darken(skin, .35)}" fill-opacity=".6"/>')

    # ---------------------------------------------------------------- eyes, brows, nose, mouth
    ec = L["eye_color"]
    glow = L.get("eye_glow")
    slant = {"Elf": 8, "Tiefling": 6, "Goblin": 10}.get(sp, 0)
    for s in (-1, 1):
        x = CX + s * ex
        patched = L.get("eyepatch") and ((L["eyepatch"] == "left") == (s == 1))
        rot = f' transform="rotate({-s * slant} {x} {ey})"' if slant else ""
        almond = f"M{x - 11},{ey} C{x - 6},{ey - 5} {x + 6},{ey - 5} {x + 11},{ey} C{x + 6},{ey + 3.5} {x - 6},{ey + 3.5} {x - 11},{ey} Z"
        if patched:
            continue
        add(f'<g{rot}>')
        add(f'<clipPath id="{P}eye{s + 1}"><path d="{almond}"/></clipPath>')
        solid = L.get("solid_eyes")
        add(f'<path d="{almond}" fill="{ec if solid else (mix(skin, "#e9dec9", .7) if not glow else lighten(ec, .6))}"/>')
        add(f'<g clip-path="url(#{P}eye{s + 1})">')
        if not solid:
            gf = f' filter="url(#{P}glow)"' if glow else ""
            add(f'<circle cx="{x}" cy="{ey + .5}" r="5.2" fill="{ec}"{gf}/>')
            if L.get("reptile"):
                add(f'<ellipse cx="{x}" cy="{ey + .5}" rx="1.2" ry="4.6" fill="#111"/>')
            else:
                add(f'<circle cx="{x}" cy="{ey + .5}" r="2.3" fill="#141014"/>')
        else:
            add(f'<ellipse cx="{x}" cy="{ey}" rx="11" ry="3" fill="{lighten(ec, .35)}" fill-opacity=".5"/>')
        add(f'<path d="M{x - 11},{ey} C{x - 6},{ey - 7.5} {x + 6},{ey - 7.5} {x + 11},{ey} L{x + 11},{ey - 8} L{x - 11},{ey - 8} Z" fill="{skin_lo}" fill-opacity=".35"/>')
        add('</g>')
        add(f'<circle cx="{x - 1.8}" cy="{ey - 1.3}" r=".9" fill="#fff" fill-opacity=".85"/>')
        add(f'<path d="M{x - 12},{ey + .5} C{x - 6},{ey - 5.5} {x + 6},{ey - 5.5} {x + 12},{ey + .5}" fill="none" stroke="{skin_line}" stroke-width="1.6" stroke-linecap="round"/>'
            f'<path d="M{x-10},{ey+6} Q{x},{ey+10} {x+9},{ey+6}" fill="none" stroke="{skin_lo}" opacity=".45" stroke-width=".8"/>')
        if pres == "feminine" and not L.get("reptile"):
            add(f'<path d="M{x + s * 10},{ey - 2} l{s * 5},-4 M{x + s * 7},{ey - 5} l{s * 4},-5" stroke="{skin_line}" stroke-width="1.6" stroke-linecap="round"/>')
        if glow:
            add(f'<circle cx="{x}" cy="{ey}" r="9" fill="{ec}" fill-opacity=".25" filter="url(#{P}glow)"/>')
        add('</g>')
    # eyepatch
    if L.get("eyepatch"):
        s = 1 if L["eyepatch"] == "left" else -1
        x = CX + s * ex
        add(f'<path d="M{CX - s * w},{top + 38} L{CX + s * (w + 2)},{ey + 14}" stroke="#1a1410" stroke-width="3"/>')
        pc = L.get("eyepatch_color") or "#1a1410"
        add(f'<path d="M{x - 13},{ey - 6} Q{x},{ey - 12} {x + 13},{ey - 6} Q{x + 12},{ey + 12} {x},{ey + 13} Q{x - 12},{ey + 12} {x - 13},{ey - 6} Z" '
            f'fill="{pc}" stroke="{darken(pc, .4)}" stroke-width="1.2"/>')
    # spectacles
    if L.get("spectacles"):
        fr = "#c9a24a" if L["spectacles"] == "half-moon" else "#3a3036"
        for s in (-1, 1):
            x = CX + s * ex
            if L.get("eyepatch") and ((L["eyepatch"] == "left") == (s == 1)):
                continue
            if L["spectacles"] == "half-moon":
                add(f'<path d="M{x - 12},{ey + 2} L{x + 12},{ey + 2} A12,10 0 0 1 {x - 12},{ey + 2} Z" fill="#dfe8f0" fill-opacity=".18" '
                    f'stroke="{fr}" stroke-width="2"/>')
            else:
                add(f'<circle cx="{x}" cy="{ey}" r="12.5" fill="#dfe8f0" fill-opacity=".15" stroke="{fr}" stroke-width="2.2"/>')
            add(f'<path d="M{x + s * 12.5},{ey - 1} L{CX + s * (w - 2)},{ey - 4}" stroke="{fr}" stroke-width="1.8"/>')
        by = ey + 2 if L["spectacles"] == "half-moon" else ey - 2
        add(f'<path d="M{CX - ex + 12},{by} Q{CX},{by - 5} {CX + ex - 12},{by}" fill="none" stroke="{fr}" stroke-width="2"/>')
    # brows
    bcol = darken(hair, .15) if L["hair_style"] != "bald" or sp not in ("Dragonborn",) else darken(skin, .4)
    if L.get("reptile"):
        bcol = darken(skin, .35)
    bw = 6 if sp in ("Dwarf", "Orc", "Goliath") else 4.2
    ex_ = L["expression"]
    for s in (-1, 1):
        x = CX + s * ex
        inner = ey - (9 if ex_ == "stern" else 14)
        outer = ey - 14 if ex_ != "smile" else ey - 16
        add(f'<path d="M{x - s * 12},{inner} Q{x},{ey - 19} {x + s * 13},{outer}" fill="none" stroke="{bcol}" stroke-width="{bw}" stroke-linecap="round"/>')
    # nose
    ny = ey + 26
    if L.get("reptile"):
        add(f'<path d="M{CX - 8},{ny} q3,-3 5,0 M{CX + 3},{ny} q3,-3 5,0" stroke="{skin_line}" stroke-width="2" fill="none"/>')
    elif sp == "Gnome":
        add(f'<ellipse cx="{CX}" cy="{ny - 2}" rx="10" ry="9" fill="{mix(skin, "#e08070", .2)}" stroke="{skin_lo}" stroke-width="1.5"/>'
            f'<circle cx="{CX - 3}" cy="{ny - 5}" r="2.5" fill="#fff" fill-opacity=".35"/>')
    elif sp in ("Orc", "Goblin"):
        add(f'<path d="M{CX - 4},{ey + 6} Q{CX - 7},{ny - 6} {CX - 12},{ny} Q{CX},{ny + 5} {CX + 12},{ny} Q{CX + 7},{ny - 6} {CX + 4},{ey + 6}" fill="{skin_lo}" fill-opacity=".45" stroke="{skin_line}" stroke-width="1.6"/>'
            f'<ellipse cx="{CX - 5}" cy="{ny}" rx="2.4" ry="1.6" fill="{skin_line}"/><ellipse cx="{CX + 5}" cy="{ny}" rx="2.4" ry="1.6" fill="{skin_line}"/>')
    else:
        add(f'<path d="M{CX - 2},{ey + 4} Q{CX - 3},{ny - 8} {CX - 8},{ny - 1} Q{CX},{ny + 4} {CX + 8},{ny - 1}" fill="none" stroke="{skin_line}" stroke-width="1.8" stroke-linecap="round" stroke-opacity=".8"/>'
            f'<path d="M{CX + 2},{ey + 6} Q{CX + 3},{ny - 10} {CX + 5},{ny - 6}" fill="none" stroke="{skin_hi}" stroke-width="2" stroke-opacity=".6"/>')
    if L.get("nosering"):
        add(f'<circle cx="{CX + 7}" cy="{ny + 1}" r="3" fill="none" stroke="#e0c060" stroke-width="1.6"/>')
    # mouth
    my = chin - 22 if not L.get("reptile") else chin - 20
    mw = 13 if not L.get("reptile") else 22
    lip = mix(skin, "#b03a4a", .5 if pres == "feminine" else .35)
    mouth = {"smile": f"M{CX - mw - 1},{my - 2} Q{CX},{my + 10} {CX + mw + 1},{my - 2}",
             "smirk": f"M{CX - mw},{my + 1} Q{CX + 2},{my + 4} {CX + mw + 2},{my - 5}",
             "stern": f"M{CX - mw},{my + 2} Q{CX},{my - 3} {CX + mw},{my + 2}"}.get(ex_, f"M{CX - mw},{my} Q{CX},{my + 3} {CX + mw},{my}")
    add(f'<path d="{mouth}" fill="none" stroke="{darken(lip, .35)}" stroke-width="2.6" stroke-linecap="round"/>')
    if not L.get("reptile"):
        add(f'<path d="M{CX - 8},{my + 6} Q{CX},{my + 10} {CX + 8},{my + 6}" fill="none" stroke="{lip}" stroke-width="2.4" stroke-linecap="round" stroke-opacity=".55"/>')
    if L.get("tusks"):
        for s in (-1, 1):
            add(f'<path d="M{CX + s * 9},{my + 4} L{CX + s * 13},{my - 12} L{CX + s * 16},{my + 3} Z" fill="#f2ead6" stroke="#8a7a5a" stroke-width="1"/>')
    elif L.get("reptile"):
        add(f'<path d="M{CX - 18},{my + 1} l3,5 l3,-5 M{CX + 12},{my + 1} l3,5 l3,-5" fill="#f2ead6" stroke="none"/>')
    # scars
    scar, scar_hi = mix(skin, "#7a1e24", .45), mix(skin, "#ffffff", .35)
    for sc in L.get("scars", [])[:3]:
        s = 1 if sc["side"] == "left" else -1
        if sc["where"] == "eye":
            x = CX + s * ex
            add(f'<path d="M{x - s * 4},{ey - 22} L{x + s * 5},{ey + 18}" stroke="{scar}" stroke-width="3.4" stroke-linecap="round"/>'
                f'<path d="M{x - s * 3},{ey - 21} L{x + s * 6},{ey + 17}" stroke="{scar_hi}" stroke-width="1" stroke-opacity=".7"/>')
        elif sc["where"] == "lip":
            add(f'<path d="M{CX + s * 6},{my - 10} L{CX + s * 3},{my + 8}" stroke="{scar}" stroke-width="2.6" stroke-linecap="round"/>')
        elif sc["where"] == "burn":
            add(f'<ellipse cx="{CX + s * 30}" cy="{ey + 22}" rx="15" ry="18" fill="#c8606a" fill-opacity=".35"/>')
        else:
            add(f'<path d="M{CX + s * 16},{ey + 10} L{CX + s * 42},{ey + 36}" stroke="{scar}" stroke-width="3" stroke-linecap="round"/>'
                f'<path d="M{CX + s * 17},{ey + 9} L{CX + s * 43},{ey + 35}" stroke="{scar_hi}" stroke-width="1" stroke-opacity=".6"/>'
                + "".join(f'<path d="M{CX + s * (21 + i * 7)},{ey + 19 + i * 7} l{s * 5},-6" stroke="{scar}" stroke-width="1.6"/>' for i in range(3)))

    # ---------------------------------------------------------------- facial hair
    beard = L["beard"]
    bc = L.get("beard_color") or hair
    if beard in ("short", "long"):
        bl = 16 if beard == "short" else 70
        add(f'<path d="M{CX - w + 3},{ey + 2} C{CX - w + 2},{chin - 10} {CX - 34},{chin + bl * .7:.0f} {CX},{chin + bl} '
            f'C{CX + 34},{chin + bl * .7:.0f} {CX + w - 2},{chin - 10} {CX + w - 3},{ey + 2} '
            f'L{CX + w - 12},{ey + 22} C{CX + 24},{my - 14} {CX + 16},{my - 10} {CX + 15},{my + 2} Q{CX},{my + 10} {CX - 15},{my + 2} '
            f'C{CX - 16},{my - 10} {CX - 24},{my - 14} {CX - w + 12},{ey + 22} Z" fill="{bc}" stroke="{darken(bc, .35)}" stroke-width="1.2"/>')
        for i in range(7):  # strands
            x = CX - 30 + i * 10
            add(f'<path d="M{x},{my + 8} Q{x + r.uniform(-4, 4):.0f},{chin + bl * .5:.0f} {x + (CX - x) * .3:.0f},{chin + bl - 6}" fill="none" stroke="{lighten(bc, .25)}" stroke-width="1.2" stroke-opacity=".5"/>')
        if beard == "long" and sp == "Dwarf":
            for s in (-1, 1):
                add(f'<path d="M{CX + s * 14},{chin + bl - 20} l{s * 2},18" stroke="#c9a14a" stroke-width="5" stroke-linecap="round"/>')
    if beard in ("short", "long", "mustache"):
        add(f'<path d="M{CX - 24},{my + 3} C{CX - 16},{my - 12} {CX - 5},{my - 11} {CX},{my - 7} C{CX + 5},{my - 11} {CX + 16},{my - 12} {CX + 24},{my + 3} '
            f'C{CX + 13},{my - 3} {CX + 4},{my - 2} {CX},{my - 1} C{CX - 4},{my - 2} {CX - 13},{my - 3} {CX - 24},{my + 3} Z" fill="{bc}" stroke="{darken(bc, .3)}" stroke-width="1"/>')
    elif beard == "goatee":
        add(f'<path d="M{CX - 12},{my + 6} Q{CX},{my + 4} {CX + 12},{my + 6} L{CX + 6},{chin + 12} Q{CX},{chin + 16} {CX - 6},{chin + 12} Z" fill="{bc}"/>'
            f'<path d="M{CX - 16},{my + 1} Q{CX},{my - 10} {CX + 16},{my + 1} Q{CX},{my - 4} {CX - 16},{my + 1} Z" fill="{bc}"/>')
    elif beard == "stubble":
        add(f'<path d="M{CX - w + 6},{ey + 16} C{CX - w + 8},{chin - 8} {CX - 20},{chin + 2} {CX},{chin + 1} C{CX + 20},{chin + 2} {CX + w - 8},{chin - 8} {CX + w - 6},{ey + 16} '
            f'C{CX + 20},{my - 12} {CX - 20},{my - 12} {CX - w + 6},{ey + 16} Z" fill="{bc}" fill-opacity=".28"/>')

    # ---------------------------------------------------------------- hair (front)
    hair_art = _hair_front(style, L, P, w, top, hair_lo, r)
    add(hair_art)
    if hair_art:
        add(f'<defs><clipPath id="{P}hairclip">{hair_art}</clipPath></defs>'
            f'<g clip-path="url(#{P}hairclip)" fill="none" stroke="{hair_hi}" stroke-width=".7" opacity=".26">')
        hair_rng = seeded('strands', L['seed'])
        for i in range(42):
            x = CX - w - 12 + i * (2*w+24)/42
            length = hair_rng.uniform(80, 210) if style in ('long','braid','dreads') else hair_rng.uniform(35,65)
            add(f'<path d="M{x:.1f},{top-12} C{x-16:.1f},{top+18} {x+13:.1f},{top+50} {x+3:.1f},{top+length:.1f}"/>')
        add('</g>')
    if L.get("undercut") and style not in ("bald", "hidden"):
        for s in (-1, 1):
            add(f'<path d="M{CX + s * (w - 2)},{top + 40} Q{CX + s * (w + 2)},{top + 60} {CX + s * (w - 1)},{ey + 4}" stroke="{hair}" stroke-width="7" stroke-opacity=".35" fill="none"/>')

    # ---------------------------------------------------------------- horns & headwear
    if L.get("horns") and not L.get("reptile"):
        add(_horns(L["horns"], top, P))
    add(_headwear(hw, L, P, w, top, ey, cloak_col, r))

    # ---------------------------------------------------------------- finish
    # Fine etched strokes over the face and cloth give the illustration a drawn finish.
    finish_rng = seeded('finish', L['seed'])
    add(f'<g clip-path="url(#{P}head)" stroke="{skin_line}" stroke-width=".5" opacity=".12">')
    for i in range(80):
        x, y = finish_rng.uniform(CX-w, CX+w), finish_rng.uniform(top+12, chin)
        add(f'<path d="M{x:.1f},{y:.1f} l{finish_rng.uniform(1,3):.1f},-1.5"/>')
    add('</g>')
    add(f'<defs><clipPath id="{P}bodyclip"><path d="{body}"/></clipPath></defs>'
        f'<g clip-path="url(#{P}bodyclip)" fill="none" stroke="#eddfb8" opacity=".09" stroke-width=".7">')
    for i in range(65):
        x, y = finish_rng.uniform(30,290), finish_rng.uniform(sh_y+16,400)
        add(f'<path d="M{x:.1f},{y:.1f} l-3,5"/>')
    add('</g>')
    add(f'<rect width="320" height="400" fill="url(#{P}vig)"/>')
    body_svg = "".join(out)
    if mode == "face":
        sz = size or 256
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="72 70 176 176" width="{sz}" height="{sz}">'
                f'{body_svg}</svg>')
    if mode == "bust":
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="40 35 240 300" width="{size or 320}" height="{int((size or 320) * 1.25)}">{body_svg}</svg>'
    return _framed(e, body_svg, P, size)


def _framed(e, inner, P, size=None):
    sub = (" / ".join(f"{c} {l}" for c, l in e.get("classes", {}).items()) if e["kind"] == "pc"
           else f"{e.get('size', '')} {e.get('type', '')}".strip())
    if e["kind"] == "pc" and e.get("species"):
        sub = f"{e['species']} · {sub}"
    name = e["name"] if len(e["name"]) <= 24 else e["name"][:23] + "…"
    fs = 22 if len(name) <= 16 else 18
    corner = lambda x, y, sx, sy: (f'<path d="M{x} {y + sy * 26} L{x} {y} L{x + sx * 26} {y}" fill="none" stroke="#f1dfae" stroke-width="3"/>'  # noqa: E731
                                   f'<path d="M{x + sx * 7} {y + sy * 7} l{sx * 7} {sy * 7} m0 {-sy * 7} l{-sx * 7} {sy * 7}" stroke="#f1dfae" stroke-width="1.5"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 400" width="{size or 320}" height="{int((size or 320) * 1.25)}">'
            f'<defs><clipPath id="{P}frame"><rect x="6" y="6" width="308" height="388" rx="14"/></clipPath>'
            f'<linearGradient id="{P}plate" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2a1e14" stop-opacity=".2"/>'
            f'<stop offset=".35" stop-color="#140e08" stop-opacity=".88"/><stop offset="1" stop-color="#0a0604" stop-opacity=".95"/></linearGradient></defs>'
            f'<rect width="320" height="400" rx="18" fill="#1a130c"/>'
            f'<g clip-path="url(#{P}frame)">{inner}'
            f'<rect x="0" y="318" width="320" height="82" fill="url(#{P}plate)"/></g>'
            f'<rect x="6" y="6" width="308" height="388" rx="14" fill="none" stroke="#c9a45a" stroke-width="3"/>'
            f'<rect x="12" y="12" width="296" height="376" rx="10" fill="none" stroke="#c9a45a" stroke-opacity=".35"/>'
            + corner(16, 16, 1, 1) + corner(304, 16, -1, 1) + corner(16, 384, 1, -1) + corner(304, 384, -1, -1) +
            f'<text x="160" y="354" text-anchor="middle" font-family="Georgia,serif" font-size="{fs}" fill="#f6e7c1" letter-spacing=".5">{esc(name)}</text>'
            f'<path d="M100 364 H220" stroke="#c9a45a" stroke-opacity=".6"/><circle cx="160" cy="364" r="2.5" fill="#c9a45a"/>'
            f'<text x="160" y="380" text-anchor="middle" font-family="Georgia,serif" font-size="12" font-style="italic" fill="#d8c08a">{esc(sub[:44])}</text>'
            f'</svg>')


def _outfit(L, P, body, sw, sh_y, r):
    o, cloth = L["outfit"], L["cloth"]
    out = []
    add = out.append
    if o == "plate":
        add(f'<path d="{body}" fill="url(#{P}metal)" stroke="#2a3038" stroke-width="2"/>')
        add(f'<path d="M{CX},{sh_y + 18} L{CX},402" stroke="#eef2f5" stroke-opacity=".5" stroke-width="2"/>')
        add(f'<path d="M{CX - 60},{sh_y + 70} Q{CX},{sh_y + 90} {CX + 60},{sh_y + 70}" fill="none" stroke="#2a3038" stroke-width="2" stroke-opacity=".6"/>')
        add(f'<path d="M{CX - 34},{sh_y + 4} Q{CX},{sh_y + 26} {CX + 34},{sh_y + 4} L{CX + 30},{sh_y - 12} Q{CX},{sh_y + 4} {CX - 30},{sh_y - 12} Z" fill="url(#{P}metal)" stroke="#2a3038" stroke-width="1.5"/>')
        for s in (-1, 1):
            px = CX + s * (sw - 26)
            add(f'<path d="M{px - 36},{sh_y + 40} C{px - 40},{sh_y + 4} {px + 34},{sh_y - 4} {px + 40},{sh_y + 36} '
                f'C{px + 30},{sh_y + 52} {px - 26},{sh_y + 56} {px - 36},{sh_y + 40} Z" fill="url(#{P}metal)" stroke="#2a3038" stroke-width="2"/>')
            add(f'<path d="M{px - 30},{sh_y + 46} C{px - 10},{sh_y + 56} {px + 18},{sh_y + 52} {px + 36},{sh_y + 42}" fill="none" stroke="#2a3038" stroke-width="1.5"/>')
            for k in range(3):
                add(f'<circle cx="{px - 18 + k * 18}" cy="{sh_y + 20 + (k == 1) * -6}" r="2" fill="#dfe6ec"/>')
        if L.get("pendant") == "sun" or cloth:
            add(f'<path d="M{CX - 30},{sh_y + 40} L{CX + 30},{sh_y + 40} L{CX + 34},402 L{CX - 34},402 Z" fill="url(#{P}cloth)"/>')
            add(f'<path d="M{CX - 30},{sh_y + 40} L{CX + 30},{sh_y + 40}" stroke="#c9a14a" stroke-width="3"/>')
            add(f'<path d="M{CX},{sh_y + 62} l6,14 l14,0 l-11,9 l4,14 l-13,-8 l-13,8 l4,-14 l-11,-9 l14,0 Z" fill="#e0c060" fill-opacity=".9"/>')
    elif o == "chain":
        add(f'<path d="{body}" fill="url(#{P}chain)" stroke="#2a3038" stroke-width="2"/>')
        add(f'<path d="{body}" fill="url(#{P}cloth)" fill-opacity=".0"/>')
        add(f'<path d="M{CX - 48},{sh_y + 34} L{CX + 48},{sh_y + 34} L{CX + 50},402 L{CX - 50},402 Z" fill="url(#{P}cloth)"/>')
        add(f'<path d="M{CX - 48},{sh_y + 34} L{CX + 48},{sh_y + 34}" stroke="{lighten(cloth, .3)}" stroke-width="3"/>')
        add(f'<path d="M{CX - 40},{sh_y + 2} Q{CX},{sh_y + 30} {CX + 40},{sh_y + 2}" fill="none" stroke="#3a4048" stroke-width="7"/>')
        add(f'<path d="M{CX - 90},{sh_y + 30} L{CX + 60},402" stroke="url(#{P}leather)" stroke-width="12"/>')
        add(f'<rect x="{CX - 36}" y="{sh_y + 70}" width="14" height="12" rx="2" fill="#c9a14a" transform="rotate(38 {CX - 29} {sh_y + 76})"/>')
    elif o == "leather":
        add(f'<path d="{body}" fill="url(#{P}leather)" stroke="#1e120a" stroke-width="2"/>')
        add(f'<path d="{body}" fill="{darken(cloth, .2)}" fill-opacity=".45"/>')
        add(f'<path d="M{CX - 30},{sh_y + 4} L{CX - 6},{sh_y + 60} L{CX - 6},402 M{CX + 30},{sh_y + 4} L{CX + 6},{sh_y + 60} L{CX + 6},402" fill="none" stroke="#1e120a" stroke-width="2"/>')
        add(f'<path d="M{CX - 30},{sh_y + 4} L{CX},{sh_y + 58} L{CX + 30},{sh_y + 4} Z" fill="{darken(cloth, .1)}"/>')
        for k in range(4):
            y = sh_y + 78 + k * 22
            add(f'<path d="M{CX - 8},{y} L{CX + 8},{y + 6} M{CX + 8},{y} L{CX - 8},{y + 6}" stroke="#c9a878" stroke-width="1.5"/>')
        for s in (-1, 1):
            add(f'<path d="M{CX + s * (sw - 50)},{sh_y + 18} Q{CX + s * (sw - 20)},{sh_y + 20} {CX + s * (sw - 8)},{sh_y + 60}" fill="none" stroke="#c9a878" stroke-width="1.2" stroke-dasharray="4 3"/>')
        add(f'<path d="M{CX + 96},{sh_y + 34} L{CX - 50},402" stroke="#2a180c" stroke-width="10"/>')
    elif o == "furs":
        add(f'<path d="{body}" fill="url(#{P}leather)" stroke="#1e120a" stroke-width="2"/>')
        fur = r.choice(["#7a5a3a", "#8a7a6a", "#5a4a3a", "#b8a890"])
        for s in (-1, 1):
            pts = " ".join(f"{CX + s * (40 + i * 11)},{sh_y + 2 + i * 6 + (i % 2) * 10}" for i in range(9))
            add(f'<path d="M{CX + s * 36},{sh_y - 2} L{pts} L{CX + s * (sw + 4)},{sh_y + 110} C{CX + s * 80},{sh_y + 70} {CX + s * 50},{sh_y + 40} {CX + s * 30},{sh_y + 30} Z" '
                f'fill="{fur}" stroke="{darken(fur, .35)}" stroke-width="1.5"/>')
            for i in range(7):
                add(f'<path d="M{CX + s * (48 + i * 11)},{sh_y + 16 + i * 7} l{s * 4},10" stroke="{lighten(fur, .3)}" stroke-width="1.5"/>')
        add(f'<path d="M{CX - 96},{sh_y + 40} L{CX + 70},402" stroke="#3a2212" stroke-width="12"/>')
        add(f'<circle cx="{CX - 20}" cy="{sh_y + 96}" r="7" fill="#c9c2b0" stroke="#6a5a4a" stroke-width="2"/>')
    elif o == "vestments":
        add(f'<path d="{body}" fill="url(#{P}cloth)" stroke="{darken(cloth, .5)}" stroke-width="2"/>')
        stole = "#8a1f24" if lighten(cloth, 0) > "#999999" else "#c9a14a"
        for s in (-1, 1):
            add(f'<path d="M{CX + s * 30},{sh_y + 2} L{CX + s * 22},402 L{CX + s * 44},402 L{CX + s * 48},{sh_y + 8} Z" fill="{stole}"/>')
            add(f'<path d="M{CX + s * 30},{sh_y + 70} l{s * 8},0 m{-s * 4},-5 l0,10" stroke="#f0e0a0" stroke-width="2"/>')
        add(f'<path d="M{CX - 30},{sh_y + 2} Q{CX},{sh_y + 22} {CX + 30},{sh_y + 2}" fill="none" stroke="{darken(cloth, .35)}" stroke-width="3"/>')
    elif o == "druid":
        add(f'<path d="{body}" fill="url(#{P}cloth)" stroke="{darken(cloth, .5)}" stroke-width="2"/>')
        for i in range(16):
            s = -1 if i % 2 else 1
            x = CX + s * (30 + (i // 2) * 11)
            y = sh_y + 4 + (i // 2) * 6
            leaf = r.choice(["#5a8a3a", "#7a9a3a", "#a88a2a", "#4a7a3a"])
            add(f'<path d="M{x},{y} q{s * 10},-8 {s * 18},2 q{-s * 8},10 {-s * 18},-2 Z" fill="{leaf}" stroke="{darken(leaf, .4)}" stroke-width=".8"/>')
        add(f'<path d="M{CX - 30},{sh_y + 4} Q{CX},{sh_y + 26} {CX + 30},{sh_y + 4}" fill="none" stroke="#5a3a22" stroke-width="4"/>')
    elif o == "monk":
        add(f'<path d="{body}" fill="url(#{P}cloth)" stroke="{darken(cloth, .5)}" stroke-width="2"/>')
        add(f'<path d="M{CX - 50},{sh_y + 6} L{CX + 20},{sh_y + 110} L{CX + 30},{sh_y + 96} L{CX - 34},{sh_y + 4} Z" fill="{darken(cloth, .2)}"/>')
        add(f'<path d="M{CX + 50},{sh_y + 6} L{CX - 8},{sh_y + 96}" stroke="{darken(cloth, .45)}" stroke-width="3"/>')
        add(f'<path d="M{CX - sw + 10},{sh_y + 118} Q{CX},{sh_y + 132} {CX + sw - 10},{sh_y + 118} L{CX + sw - 8},{sh_y + 138} Q{CX},{sh_y + 150} {CX - sw + 8},{sh_y + 138} Z" fill="#2a2a34"/>')
    elif o == "doublet":
        add(f'<path d="{body}" fill="url(#{P}cloth)" stroke="{darken(cloth, .5)}" stroke-width="2"/>')
        for k in range(5):
            add(f'<circle cx="{CX}" cy="{sh_y + 40 + k * 22}" r="3.5" fill="#e0c060" stroke="#6a4a1a"/>')
        add(f'<path d="M{CX},{sh_y + 26} L{CX},402" stroke="{darken(cloth, .45)}" stroke-width="2"/>')
        for s in (-1, 1):
            add(f'<path d="M{CX + s * 8},{sh_y - 4} C{CX + s * 30},{sh_y - 20} {CX + s * 50},{sh_y - 6} {CX + s * 56},{sh_y + 8} L{CX + s * 14},{sh_y + 30} Z" fill="#f0ead8" stroke="#b8ae98"/>')
            add(f'<path d="M{CX + s * (sw - 40)},{sh_y + 20} q{s * 10},30 0,60 q{-s * 10},30 0,60" fill="none" stroke="{lighten(cloth, .3)}" stroke-width="2"/>')
    elif o == "coat":
        add(f'<path d="{body}" fill="url(#{P}cloth)" stroke="{darken(cloth, .5)}" stroke-width="2"/>')
        for s in (-1, 1):
            add(f'<path d="M{CX + s * 16},{sh_y + 6} L{CX + s * 44},{sh_y + 4} L{CX + s * 30},{sh_y + 110} L{CX + s * 12},{sh_y + 110} Z" fill="{darken(cloth, .25)}" stroke="#c9a14a" stroke-width="2"/>')
        add(f'<path d="M{CX - 14},{sh_y + 4} L{CX + 14},{sh_y + 4} L{CX + 10},402 L{CX - 10},402 Z" fill="#e8e0cc"/>')
        add(f'<path d="M{CX - 14},{sh_y + 6} Q{CX},{sh_y + 30} {CX + 14},{sh_y + 6} L{CX + 6},{sh_y + 40} L{CX - 6},{sh_y + 40} Z" fill="#f4efe0" stroke="#b8ae98"/>')
    elif o == "robe":
        add(f'<path d="{body}" fill="url(#{P}cloth)" stroke="{darken(cloth, .5)}" stroke-width="2"/>')
        trim = "#c9a14a" if r.random() < .6 else lighten(cloth, .45)
        add(f'<path d="M{CX - 34},{sh_y + 2} L{CX},{sh_y + 80} L{CX + 34},{sh_y + 2}" fill="{darken(cloth, .35)}" stroke="{trim}" stroke-width="3"/>')
        add(f'<path d="M{CX},{sh_y + 80} L{CX},402" stroke="{trim}" stroke-width="3"/>')
        for k in range(3):
            y = sh_y + 100 + k * 26
            add(f'<path d="M{CX - 6},{y} l6,-7 l6,7 l-6,7 Z" fill="none" stroke="{trim}" stroke-width="1.4" stroke-opacity=".8"/>')
        if L.get("collar"):
            for s in (-1, 1):
                add(f'<path d="M{CX + s * 30},{sh_y + 4} C{CX + s * 50},{sh_y - 40} {CX + s * 70},{sh_y - 60} {CX + s * 76},{sh_y - 70} '
                    f'C{CX + s * 76},{sh_y - 30} {CX + s * 70},{sh_y + 10} {CX + s * 56},{sh_y + 24} Z" fill="{darken(cloth, .3)}" stroke="{trim}" stroke-width="2"/>')
    else:  # tunic
        add(f'<path d="{body}" fill="url(#{P}cloth)" stroke="{darken(cloth, .5)}" stroke-width="2"/>')
        add(f'<path d="M{CX - 26},{sh_y + 2} Q{CX},{sh_y + 30} {CX + 26},{sh_y + 2}" fill="{darken(cloth, .3)}"/>')
        add(f'<path d="M{CX},{sh_y + 16} L{CX},{sh_y + 60} M{CX - 5},{sh_y + 26} l10,6 M{CX - 5},{sh_y + 38} l10,6 M{CX - 5},{sh_y + 50} l10,6" stroke="#d8c8a0" stroke-width="1.5"/>')
        add(f'<path d="M{CX - sw + 20},{sh_y + 40} Q{CX - 80},{sh_y + 80} {CX - 90},402" fill="none" stroke="{darken(cloth, .4)}" stroke-width="2" stroke-opacity=".6"/>')
    return "".join(out)


def _pendant(kind, sh_y, L):
    y = sh_y + 44 if L["outfit"] not in ("plate",) else sh_y + 20
    chain = f'<path d="M{CX - 30},{sh_y + 4} Q{CX},{y + 10} {CX + 30},{sh_y + 4}" fill="none" stroke="#d8b050" stroke-width="1.6"/>'
    if kind == "sun":
        rays = "".join(f'<path d="M{CX},{y + 8} l0,-13" stroke="#f0d070" stroke-width="2" transform="rotate({a} {CX} {y + 8})"/>' for a in range(0, 360, 45))
        return chain + rays + f'<circle cx="{CX}" cy="{y + 8}" r="7" fill="#f0d070" stroke="#8a6a1a" stroke-width="1.5"/>'
    return chain + f'<path d="M{CX},{y} l7,9 l-7,11 l-7,-11 Z" fill="#3aa0c8" stroke="#d8b050" stroke-width="1.6"/>'


def _hair_front(style, L, P, w, top, hair_lo, r):
    if style in ("bald", "hidden"):
        if style == "bald" and not L.get("reptile"):
            return f'<ellipse cx="{CX - 16}" cy="{top + 20}" rx="18" ry="9" fill="#fff" fill-opacity=".12" transform="rotate(-20 {CX - 16} {top + 20})"/>'
        return ""
    Lx, Rx = CX - w, CX + w
    out = []
    fill = f"url(#{P}hair)"
    hl = top + 36  # hairline height
    if style == "mohawk":
        out.append(f'<path d="M{CX - 12},{top + 30} C{CX - 16},{top - 10} {CX - 6},{top - 36} {CX},{top - 44} C{CX + 6},{top - 36} {CX + 16},{top - 10} {CX + 12},{top + 30} Z" fill="{fill}"/>')
        out.append(f'<path d="M{Lx + 4},{top + 50} C{Lx + 6},{top + 10} {Rx - 6},{top + 10} {Rx - 4},{top + 50}" fill="none" stroke="{L["hair_color"]}" stroke-width="10" stroke-opacity=".22"/>')
        return "".join(out)
    cap_top = top - 8 if style not in ("curly", "wild") else top - 16
    side = top + 70 if style in ("long", "braid", "dreads", "curly", "wild") else top + 56
    out.append(f'<path d="M{Lx - 5},{side} C{Lx - 9},{top + 10} {CX - w * .6:.0f},{cap_top} {CX},{cap_top} '
               f'C{CX + w * .6:.0f},{cap_top} {Rx + 9},{top + 10} {Rx + 5},{side} '
               f'L{Rx - 3},{side - 6} C{Rx - 5},{hl + 4} {Rx - 14},{hl - 8} {CX + 20},{hl - 10} '
               f'C{CX + 10},{hl - 4} {CX + 4},{hl + 4} {CX - 2},{hl + 8} '
               f'C{CX - 10},{hl - 4} {CX - 30},{hl - 12} {Lx + 14},{hl - 4} '
               f'C{Lx + 6},{hl + 6} {Lx + 3},{side - 20} {Lx + 3},{side - 6} Z" fill="{fill}" stroke="{hair_lo}" stroke-width="1.2"/>')
    # fringe strands
    for i in range(5):
        x = CX - 30 + i * 14 + r.uniform(-3, 3)
        out.append(f'<path d="M{x:.0f},{cap_top + 8} Q{x + 8:.0f},{hl - 20} {x + 4:.0f},{hl - 2}" fill="none" stroke="{lighten(L["hair_color"], .35)}" stroke-width="1.4" stroke-opacity=".45"/>')
    if style in ("curly", "wild"):
        n = 16 if style == "curly" else 11
        for i in range(n):
            a = math.pi * (1.05 + i / (n - 1) * .9)
            x = CX + math.cos(a) * (w + 6)
            y = top + 56 + math.sin(a) * 62
            if style == "curly":
                out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r.uniform(10, 14):.0f}" fill="{fill}" stroke="{hair_lo}" stroke-width="1"/>')
            else:
                out.append(f'<path d="M{x - 10:.0f},{y + 6:.0f} L{x + math.cos(a) * 22:.0f},{y + math.sin(a) * 22:.0f} L{x + 10:.0f},{y + 6:.0f} Z" fill="{fill}"/>')
    if style in ("long", "braid", "dreads"):
        for s in (-1, 1):  # locks framing the face
            x0 = CX + s * (w + 2)
            if style == "braid" and s == 1:
                continue
            length = 290 if style != "braid" else 250
            out.append(f'<path d="M{x0},{top + 40} C{x0 + s * 8},{top + 110} {x0 + s * 4},{length - 50} {x0 + s * 14},{length} '
                       f'L{x0 - s * 8},{length - 10} C{x0 - s * 12},{length - 60} {x0 - s * 8},{top + 110} {x0 - s * 10},{top + 50} Z" fill="{fill}"/>')
    if style == "braid":
        x = CX + w + 8
        for i in range(7):
            y = top + 90 + i * 24
            out.append(f'<ellipse cx="{x - i * 3}" cy="{y}" rx="11" ry="14" fill="{fill}" stroke="{hair_lo}" stroke-width="1.2" transform="rotate({-18 if i % 2 else 18} {x - i * 3} {y})"/>')
        out.append(f'<rect x="{x - 26}" y="{top + 250}" width="12" height="8" rx="2" fill="#c9a14a"/>')
    if style == "dreads":
        for s in (-1, 1):
            for i in range(3):
                x = CX + s * (w - 4 - i * 9)
                out.append(f'<path d="M{x:.0f},{top + 44} Q{x + s * 10:.0f},{top + 130} {x + s * 4:.0f},{top + 196 - i * 16}" stroke="{hair_lo}" '
                           f'stroke-width="8" stroke-linecap="round" fill="none"/>')
    if style in ("bun", "ponytail"):
        if style == "bun":
            out.append(f'<circle cx="{CX}" cy="{cap_top - 10}" r="17" fill="{fill}" stroke="{hair_lo}" stroke-width="1.2"/>'
                       f'<path d="M{CX - 14},{cap_top} Q{CX},{cap_top + 6} {CX + 14},{cap_top}" stroke="#c9a14a" stroke-width="3" fill="none"/>')
    return "".join(out)


def _horns(kind, top, P):
    out = []
    for s in (-1, 1):
        if kind == "ram":
            d = (f"M{CX + s * 22},{top + 16} C{CX + s * 34},{top - 22} {CX + s * 82},{top - 26} {CX + s * 90},{top + 10} "
                 f"C{CX + s * 96},{top + 36} {CX + s * 76},{top + 54} {CX + s * 62},{top + 40} "
                 f"C{CX + s * 74},{top + 34} {CX + s * 78},{top + 16} {CX + s * 66},{top + 4} "
                 f"C{CX + s * 56},{top - 4} {CX + s * 42},{top + 6} {CX + s * 38},{top + 24} Z")
        elif kind == "swept":
            d = (f"M{CX + s * 20},{top + 18} C{CX + s * 30},{top - 14} {CX + s * 60},{top - 34} {CX + s * 100},{top - 40} "
                 f"C{CX + s * 70},{top - 20} {CX + s * 44},{top + 4} {CX + s * 36},{top + 26} Z")
        elif kind == "broken" and s == 1:
            d = f"M{CX + 18},{top + 18} C{CX + 22},{top - 4} {CX + 30},{top - 14} {CX + 36},{top - 18} L{CX + 42},{top - 6} C{CX + 38},{top + 4} {CX + 36},{top + 14} {CX + 34},{top + 26} Z"
        else:
            d = (f"M{CX + s * 18},{top + 18} C{CX + s * 22},{top - 20} {CX + s * 34},{top - 44} {CX + s * 50},{top - 62} "
                 f"C{CX + s * 42},{top - 34} {CX + s * 38},{top - 6} {CX + s * 36},{top + 26} Z")
        out.append(f'<path d="{d}" fill="url(#{P}horn)" stroke="#120c0a" stroke-width="1.5"/>')
        for k in range(3):
            out.append(f'<path d="M{CX + s * (24 + k * 6)},{top + 10 - k * 8} l{s * 10},4" stroke="#8a7064" stroke-width="1.2" stroke-opacity=".6"/>')
    return "".join(out)


def _headwear(hw, L, P, w, top, ey, cloak_col, r):  # noqa: C901
    if hw in (None, "none"):
        return ""
    if hw == "hood":
        chin = top + 130
        sh = 262
        outer = (f"M{CX - 100},{sh + 22} C{CX - 104},{top + 40} {CX - 66},{top - 42} {CX},{top - 46} "
                 f"C{CX + 66},{top - 42} {CX + 104},{top + 40} {CX + 100},{sh + 22} Q{CX},{sh + 56} {CX - 100},{sh + 22} Z")
        face = (f"M{CX - w - 7},{ey + 14} C{CX - w - 9},{top - 8} {CX + w + 9},{top - 8} {CX + w + 7},{ey + 14} "
                f"C{CX + w + 5},{chin + 14} {CX + 34},{chin + 40} {CX},{chin + 42} C{CX - 34},{chin + 40} {CX - w - 5},{chin + 14} {CX - w - 7},{ey + 14} Z")
        return (f'<path d="{outer} {face}" fill-rule="evenodd" fill="{cloak_col}" stroke="{darken(cloak_col, .5)}" stroke-width="2"/>'
                f'<path d="{face}" fill="none" stroke="{lighten(cloak_col, .18)}" stroke-width="3"/>'
                f'<path d="M{CX - 60},{top - 20} C{CX - 30},{top - 36} {CX + 30},{top - 36} {CX + 60},{top - 20}" fill="none" stroke="{darken(cloak_col, .4)}" stroke-width="2" stroke-opacity=".6"/>'
                f'<path d="M{CX - w - 2},{top + 12} Q{CX},{top - 18} {CX + w + 2},{top + 12} L{CX + w},{top + 50} Q{CX},{top + 30} {CX - w},{top + 50} Z" fill="#000" fill-opacity=".32"/>')
    if hw == "helm":
        return (f'<path d="M{CX - w - 6},{top + 64} C{CX - w - 8},{top - 6} {CX + w + 8},{top - 6} {CX + w + 6},{top + 64} '
                f'L{CX + w - 2},{top + 58} Q{CX},{top + 40} {CX - w + 2},{top + 58} Z" fill="url(#{P}metal)" stroke="#2a3038" stroke-width="2"/>'
                f'<path d="M{CX - 5},{top + 44} L{CX + 5},{top + 44} L{CX + 4},{ey + 14} L{CX - 4},{ey + 14} Z" fill="url(#{P}metal)" stroke="#2a3038" stroke-width="1.5"/>'
                f'<path d="M{CX - w - 4},{top + 50} Q{CX},{top + 30} {CX + w + 4},{top + 50}" fill="none" stroke="#dfe6ec" stroke-width="2" stroke-opacity=".7"/>')
    if hw == "circlet":
        return (f'<path d="M{CX - w + 2},{top + 32} Q{CX},{top + 20} {CX + w - 2},{top + 32}" fill="none" stroke="#e0c060" stroke-width="4"/>'
                f'<path d="M{CX},{top + 18} l6,8 l-6,9 l-6,-9 Z" fill="#6ac0e8" stroke="#e0c060" stroke-width="2"/>')
    if hw == "crown":
        pts = " ".join(f"{CX - 40 + i * 10},{top + (6 if i % 2 else -18)}" for i in range(9))
        return (f'<path d="M{CX - 42},{top + 22} L{pts} L{CX + 42},{top + 22} Q{CX},{top + 14} {CX - 42},{top + 22} Z" fill="#e0c060" stroke="#8a6a1a" stroke-width="2"/>'
                f'<circle cx="{CX}" cy="{top + 10}" r="4" fill="#c02a30"/>')
    if hw == "wizard hat":
        hc = darken(L["cloth"], .1)
        tip = r.choice([-1, 1])
        return (f'<path d="M{CX - 56},{top + 12} C{CX - 30},{top - 30} {CX - 10},{top - 90} {CX + tip * 50},{top - 110} '
                f'C{CX + 14},{top - 70} {CX + 34},{top - 30} {CX + 56},{top + 12} Z" fill="{hc}" stroke="{darken(hc, .5)}" stroke-width="2"/>'
                f'<ellipse cx="{CX}" cy="{top + 16}" rx="96" ry="18" fill="{darken(hc, .15)}" stroke="{darken(hc, .5)}" stroke-width="2"/>'
                f'<path d="M{CX - 54},{top + 4} Q{CX},{top - 8} {CX + 54},{top + 4}" stroke="#c9a14a" stroke-width="6" fill="none"/>'
                f'<path d="M{CX + 10},{top - 50} l3,-7 l3,7 l7,1 l-6,4 l2,7 l-6,-4 l-6,4 l2,-7 l-6,-4 Z" fill="#f0d070"/>')
    if hw in ("hat", "feather cap"):
        hc = darken(L["cloth"], .15)
        s = (f'<ellipse cx="{CX}" cy="{top + 18}" rx="{w + 30}" ry="14" fill="{darken(hc, .2)}" stroke="{darken(hc, .5)}" stroke-width="2"/>'
             f'<path d="M{CX - w + 6},{top + 18} C{CX - w + 4},{top - 26} {CX + w - 4},{top - 26} {CX + w - 6},{top + 18} Z" fill="{hc}" stroke="{darken(hc, .5)}" stroke-width="2"/>'
             f'<path d="M{CX - w + 6},{top + 10} Q{CX},{top + 2} {CX + w - 6},{top + 10}" stroke="#c9a14a" stroke-width="4" fill="none"/>')
        if hw == "feather cap":
            s += (f'<path d="M{CX + 30},{top + 6} C{CX + 60},{top - 30} {CX + 90},{top - 50} {CX + 110},{top - 60} C{CX + 90},{top - 30} {CX + 60},{top - 4} {CX + 34},{top + 12} Z" '
                  f'fill="#e8d8b0" stroke="#8a7a5a" stroke-width="1.2"/><path d="M{CX + 32},{top + 8} Q{CX + 70},{top - 26} {CX + 108},{top - 58}" stroke="#8a7a5a" fill="none"/>')
        return s
    if hw == "tricorn":
        hc = "#1e1c22"
        return (f'<path d="M{CX - w - 30},{top + 20} C{CX - w},{top - 20} {CX - 20},{top - 6} {CX},{top - 20} C{CX + 20},{top - 6} {CX + w},{top - 20} {CX + w + 30},{top + 20} '
                f'C{CX + 40},{top + 6} {CX - 40},{top + 6} {CX - w - 30},{top + 20} Z" fill="{hc}" stroke="#c9a14a" stroke-width="2.5"/>')
    if hw == "bandana":
        bc = r.choice(["#8e2226", "#24407a", "#2f5a2e", "#1e1c22"])
        return (f'<path d="M{CX - w - 4},{top + 46} C{CX - w - 6},{top - 8} {CX + w + 6},{top - 8} {CX + w + 4},{top + 46} Q{CX},{top + 30} {CX - w - 4},{top + 46} Z" fill="{bc}" stroke="{darken(bc, .4)}" stroke-width="1.5"/>'
                f'<path d="M{CX + w},{top + 40} l22,6 l-6,24 Z M{CX + w},{top + 42} l26,-6 l-2,14 Z" fill="{bc}"/>'
                + "".join(f'<circle cx="{CX - 30 + i * 15}" cy="{top + 14 + (i % 2) * 8}" r="2" fill="#fff" fill-opacity=".6"/>' for i in range(5)))
    if hw == "antlers":
        out = []
        for s in (-1, 1):
            out.append(f'<path d="M{CX + s * 26},{top + 14} C{CX + s * 36},{top - 20} {CX + s * 50},{top - 44} {CX + s * 66},{top - 66} '
                       f'M{CX + s * 42},{top - 26} L{CX + s * 66},{top - 30} M{CX + s * 54},{top - 50} L{CX + s * 50},{top - 70}" '
                       f'stroke="#8a6a44" stroke-width="5" stroke-linecap="round" fill="none"/>')
        out.append(f'<path d="M{CX - w + 2},{top + 30} Q{CX},{top + 16} {CX + w - 2},{top + 30}" fill="none" stroke="#5a8a3a" stroke-width="4"/>')
        for i in range(5):
            x = CX - 36 + i * 18
            out.append(f'<path d="M{x},{top + 24} q6,-8 12,0 q-6,7 -12,0 Z" fill="#6a9a3a"/>')
        return "".join(out)
    if hw == "veil":
        return f'<path d="M{CX - w - 8},{top + 20} C{CX - w},{top - 20} {CX + w},{top - 20} {CX + w + 8},{top + 20} L{CX + w + 16},{top + 200} L{CX - w - 16},{top + 200} Z" fill="#e8e4d8" fill-opacity=".35"/>'
    return ""


# ============================================================== creature art (non-humanoids)

def creature_icon(e):
    """Fallback anatomy follows the same resolved species as painted faces and bodies."""
    identity=visual_identity(e)
    if identity['species_source']=='unspecified':return assets.icon_for_entity(e)
    return assets.icon_for_entity(dict(e,srd_name=identity['species'],name=identity['species']))


def creature_svg(e, mode="portrait", size=None):
    t = (e.get("type") or "monstrosity").split()[0].lower()
    bg, bg2, lite, dark, glow = TYPE_STYLE.get(t, TYPE_STYLE["monstrosity"])
    if e.get("side") == "ally":
        glow = "#6af0d0"
    icon = creature_icon(e)
    r = seeded("creature", _art_id(e))
    P = f"c{hashlib.md5(e['id'].encode()).hexdigest()[:5]}"
    body = assets.icon_body(icon)
    sil = body.replace('fill="currentColor"', f'fill="url(#{P}sil)"')
    halo = body.replace('fill="currentColor"', f'fill="{glow}"')
    big = e.get("size") in ("Large", "Huge", "Gargantuan")
    sc = .5 if big else .44
    ox, oy = 160 - 256 * sc, (178 if big else 186) - 256 * sc
    parts = [f'<defs><radialGradient id="{P}bg" cx="50%" cy="42%" r="72%"><stop offset="0" stop-color="{lighten(bg, .18)}"/>'
             f'<stop offset=".55" stop-color="{bg}"/><stop offset="1" stop-color="{bg2}"/></radialGradient>'
             f'<linearGradient id="{P}sil" x1="0" y1="0" x2=".4" y2="1"><stop offset="0" stop-color="{lite}"/>'
             f'<stop offset="1" stop-color="{dark}"/></linearGradient>'
             f'<radialGradient id="{P}vig" cx="50%" cy="45%" r="70%"><stop offset=".5" stop-color="#000" stop-opacity="0"/>'
             f'<stop offset="1" stop-color="#000" stop-opacity=".6"/></radialGradient>'
             f'<filter id="{P}blur" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="9"/></filter>'
             f'<filter id="{P}soft"><feGaussianBlur stdDeviation="5"/></filter></defs>',
             f'<rect width="320" height="400" fill="url(#{P}bg)"/>']
    for i in range(7):
        a = math.radians(i * 360 / 7 + r.uniform(0, 30))
        parts.append(f'<path d="M160 180 L{160 + 300 * math.cos(a - .09):.0f} {180 + 300 * math.sin(a - .09):.0f} '
                     f'L{160 + 300 * math.cos(a + .09):.0f} {180 + 300 * math.sin(a + .09):.0f} Z" fill="{glow}" fill-opacity=".05"/>')
    parts.append(f'<circle cx="160" cy="180" r="118" fill="none" stroke="{glow}" stroke-opacity=".25" stroke-width="1.5"/>'
                 f'<circle cx="160" cy="180" r="128" fill="none" stroke="{glow}" stroke-opacity=".12" stroke-width="6" stroke-dasharray="2 10"/>')
    for _ in range(18):
        parts.append(f'<circle cx="{r.uniform(10, 310):.0f}" cy="{r.uniform(10, 320):.0f}" r="{r.uniform(.8, 2.6):.1f}" fill="{glow}" fill-opacity="{r.uniform(.15, .5):.2f}"/>')
    parts.append(f'<ellipse cx="160" cy="{oy + 512 * sc + 2:.0f}" rx="96" ry="16" fill="#000" fill-opacity=".45" filter="url(#{P}soft)"/>')
    study = illustration.creature_body(e, P, lite, dark, glow)
    if study:
        parts.append(study)
    else:
        parts.append(f'<g transform="translate({ox:.1f} {oy:.1f}) scale({sc})" filter="url(#{P}blur)" opacity=".7">{halo}</g>')
        parts.append(f'<g transform="translate({ox + 4:.1f} {oy + 6:.1f}) scale({sc})" opacity=".45">{body.replace("currentColor", "#000")}</g>')
        parts.append(f'<g transform="translate({ox:.1f} {oy:.1f}) scale({sc})">{sil}</g>')
    parts.append(f'<rect width="320" height="400" fill="url(#{P}vig)"/>')
    inner = "".join(parts)
    if mode == "face":
        sz = size or 256
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="40 60 240 240" width="{sz}" height="{sz}">{inner}</svg>'
    if mode == "bust":
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 400" width="{size or 320}" height="{int((size or 320) * 1.25)}">{inner}</svg>'
    return _framed(e, inner, P, size)


# ============================================================== public entry points

def portrait_svg(e, size=None):
    return _painted_art(e,"portrait",size)


def bust_svg_any(e, size=None):
    """Unframed head-and-shoulders (small portraits: party cards, sheet header)."""
    return _painted_art(e,"bust",size)


def face_svg(e, size=None):
    return _painted_art(e,"face",size)


def _painted_art(e,mode,size):
    chosen=portrait_choice(e)
    if chosen:return painted.portrait(e,chosen,mode,size)
    # Uncatalogued creatures retain a deterministic immediate illustration.
    return bust_svg(e,mode,size) if is_humanlike(e) else creature_svg(e,mode,size)


def portrait_choice(e):
    """The single asset decision used by portraits, map faces and body colour matching."""
    chosen=None
    kept=e.get('art_of') or {};saved=tuple(kept.get('portrait_asset') or ())
    record=painted.portrait_records().get(saved)
    identity=visual_identity(e)
    profile=e.get('portrait_profile') or {};fixed=tuple(profile.get('choice') or ())
    fixed_record=painted.portrait_records().get(fixed)
    if profile and (e.get('look') or {})==profile.get('source_look',{}):
        if not fixed:return None  # A stored procedural face is also a deliberate stable choice.
        stored_identity=profile.get('identity') or {}
        if identity['species']==stored_identity.get('species') and identity['presentation']==stored_identity.get('presentation'):
            if fixed_record is None or fixed_record['species']==identity['species'] and fixed_record['presentation'] in ('any',identity['presentation']):
                return fixed if painted.uri(*fixed) else None
    if fixed_record and (e.get('look') or {})==profile.get('source_look',{}) and fixed_record['species']==identity['species'] and fixed_record['presentation'] in ('any',identity['presentation']) and painted.uri(*fixed):return fixed
    if record and (e.get('look') or {})==kept.get('recipient_look',{}) and record['species']==identity['species'] and record['presentation'] in ('any',identity['presentation']) and painted.uri(*saved):return saved
    if is_humanlike(e):
        explicit=read_description(profile.get('source_description') if profile else subject_description(e.get('appearance') or (e.get('bio') or {}).get('appearance') or ''))
        for field,text in (e.get('look') or {}).items():explicit.update(_read_field(field,text))
        L=look_of(e)
        if L['species']=='Dragonborn' and e.get('ancestry'):explicit['skin']=L['skin']
        if L['species']=='Elf' and re.search(r'\bdrow\b',str(e.get('srd_name',''))+' '+str(e.get('appearance','')),re.I):
            if 'skin' not in (e.get('look') or {}):L['skin']='#4f2d1a';explicit['skin']=L['skin']
            if 'hair' not in (e.get('look') or {}):L['hair_color']='#e8e2cf';explicit['hair_color']=L['hair_color']
        # Appearance preservation records have priority, as in the procedural renderer.
        if e.get('art_of'):explicit.update(e['art_of'].get('traits') or e['art_of'].get('look') or {})
        # Neutral painted bases now cover unspecified identities; never choose a gendered face for a neutral body.
        explicit['presentation']=L['presentation']
        chosen=painted.selection(e,L,explicit,HAIR_COLORS,SKIN_TONES)
    else:chosen=painted.creature_selection(e)
    return chosen


def art_version(e):
    """Changes whenever anything the picture is drawn from changes (cache-busting for the viewer)."""
    if e.get('portrait_profile'):
        import json
        blob=json.dumps([e.get(k) for k in ('name','portrait_profile','look','art_of','portrait','icon')]+[ART_REV],sort_keys=True,separators=(',',':'))
        return hashlib.sha1(blob.encode()).hexdigest()[:10]
    keys = ("name", "species", "race", "presentation", "gender", "sex", "pronouns", "classes", "ancestry", "appearance", "look", "side", "type", "size", "srd_name", "art_of")
    worn = [(i.get("name"), i.get("category")) for i in e.get("inventory", []) if i.get("kind") == "armor" and i.get("equipped")]
    bio=e.get('bio') or {}
    blob = repr([e.get(k) for k in keys] + [tuple(bio.get(k) for k in ('appearance','species','race','presentation','gender','sex','pronouns')), worn, ART_REV])
    return hashlib.sha1(blob.encode()).hexdigest()[:10]


ART_REV = 12
