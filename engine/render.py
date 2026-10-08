"""SVG rendering of maps with terrain art, fog of war, tokens, labels and turn highlighting.

mode='player' hides everything the characters haven't discovered: unrevealed cells are fogged,
hidden features/labels/creatures are omitted and secret doors look like plain wall.
mode='dm' shows everything (for Claude's own reference; never sent to the viewer).
"""
import random
import re

from . import assets
from .assets import esc
from .maps import BIOMES
from .furniture import DRAW as FURNITURE_ART
from . import illustration, painted

CELL = 32

FILL = {
    "#": "#3a342e", "B": "#5b4636", ".": "#cfc4ae", "=": "#b38b5d", ",": "#8fb35e", ":": "#b89b6a",
    "_": "#a8a39a", "t": "#6f9a45", "^": "#bdb29b", "w": "#8cc3e0", "~": "#3f84bf", "m": "#7a6a4a",
    "s": "#e2d2a0", "T": "#8fb35e", "P": "#cfc4ae", "o": "#8fb35e", "h": "#b38b5d", "c": "#b38b5d",
    "f": "#b38b5d", "D": "#cfc4ae", "d": "#cfc4ae", "S": "#3a342e", "<": "#cfc4ae", ">": "#cfc4ae",
    "x": "#0c0a09", "b": "#8c6a43", "r": "#a8a39a", " ": "#000",
}
BASE_UNDER = {"T": ",", "o": None, "P": ".", "h": "=", "c": "=", "f": "=", "D": None, "d": None, "<": ".", ">": ".", "r": "_",
              "a": "k", "g": "=", "v": "=", "l": "=", "u": "q", "n": "=", "p": ".", "e": "=", "i": "=", "y": "=", "j": ".",
              **{c: "=" for c in FURNITURE_ART}, "`": "="}

# Visual themes: each map can look like its place. (palette keys: wall, wall_edge, wall_line, trim, plank, plank_line,
# flag, flag_line, water, deep, carpet, carpet_trim, marble, marble_vein, furniture, furniture_line, counter)
THEMES = {
    "stone": {"wall": "#3a342e", "wall_edge": "#4a423a", "wall_line": "#2a2521", "trim": None, "plank": "#b38b5d",
              "plank_line": "#8a6a43", "flag": "#cfc4ae", "flag_line": "#b9ad95", "water": "#8cc3e0", "deep": "#3f84bf",
              "carpet": "#7d2430", "carpet_trim": "#c9a14a", "marble": "#e6e1d8", "marble_vein": "#c9c2b5",
              "furniture": "#7a5530", "furniture_line": "#4a3018", "counter": "#6a4524", "backdrop": None},
    "ship": {"wall": "#2b1a10", "wall_edge": "#3d2415", "wall_line": "#1a0f08", "trim": "#c9a14a", "plank": "#6e3b22",
             "plank_line": "#4a2414", "flag": "#8a8478", "flag_line": "#6f6a60", "water": "#2a4d5e", "deep": "#16303d",
             "carpet": "#8e1f2b", "carpet_trim": "#d4ae55", "marble": "#e6e1d8", "marble_vein": "#c9c2b5",
             "furniture": "#4a2414", "furniture_line": "#c9a14a", "counter": "#3b1d0f", "backdrop": "#0f1d25"},
    "sewer": {"wall": "#262a24", "wall_edge": "#353b31", "wall_line": "#171a15", "trim": "#4f6b3a", "plank": "#6b5a42",
              "plank_line": "#4a3d2c", "flag": "#7f8674", "flag_line": "#626a58", "water": "#3f6b5a", "deep": "#1f3d34",
              "carpet": "#5a3a2a", "carpet_trim": "#8a7a4a", "marble": "#9aa08f", "marble_vein": "#7d8373",
              "furniture": "#4d4030", "furniture_line": "#2a2218", "counter": "#3d3226", "backdrop": None, "moss": "#5f8a3a"},
    "marble": {"wall": "#8f8576", "wall_edge": "#a89d8c", "wall_line": "#6e6557", "trim": "#d8b36a", "plank": "#9c7248",
               "plank_line": "#7a5634", "flag": "#e6e1d8", "flag_line": "#cfc8bb", "water": "#9fd0e8", "deep": "#4a8fc0",
               "carpet": "#8a1c2a", "carpet_trim": "#e0c070", "marble": "#efeae2", "marble_vein": "#cdc5b6",
               "furniture": "#5a3a22", "furniture_line": "#d8b36a", "counter": "#4a2e1a", "backdrop": None,
               "coping": "#f2ede4"},
    # baths, spas, fountain courts: rose stone, teal mosaic pools, pale copings
    "bathhouse": {"wall": "#9c6f6a", "wall_edge": "#c79a94", "wall_line": "#7a5450", "trim": "#e8c98a", "plank": "#b08a64",
                  "plank_line": "#8a6a48", "flag": "#efe2dc", "flag_line": "#d6c1b9", "water": "#7fd3cf", "deep": "#2f9a9e",
                  "carpet": "#2f7f86", "carpet_trim": "#e8c98a", "marble": "#f5e8e4", "marble_vein": "#e0c8c1",
                  "furniture": "#8a5a44", "furniture_line": "#e8c98a", "counter": "#6a3f30", "backdrop": None,
                  "coping": "#fbf6ee", "tile": "#eadbd4", "tile2": "#86cbc6", "grout": "#cdb8b0",
                  "walls": "ashlar", "fine": "mosaic", "stone_floor": "hex"},
    # taverns, cottages, inns: limewash and dark beams, warm boards
    "timber": {"wall": "#3b2a1c", "wall_edge": "#a79b80", "wall_line": "#2a1d12", "trim": "#4a321f", "plank": "#a8784a",
               "plank_line": "#7c5530", "flag": "#b9ab92", "flag_line": "#9a8c74", "water": "#8cc3e0", "deep": "#3f84bf",
               "carpet": "#6d3b22", "carpet_trim": "#d6a654", "marble": "#e2dccf", "marble_vein": "#c7bfae",
               "furniture": "#5e3d22", "furniture_line": "#2e1c0e", "counter": "#4a2e17", "backdrop": None,
               "walls": "timber", "fine": "checker", "wood": "planks"},
    # townhouses, palaces, offices: plaster, parquet, deep blue and gold
    "manor": {"wall": "#4e4a58", "wall_edge": "#e6ded0", "wall_line": "#3a3644", "trim": "#c9a44a", "plank": "#9a6a3c",
              "plank_line": "#6e4724", "flag": "#d9d2c4", "flag_line": "#bdb4a4", "water": "#8cc3e0", "deep": "#3f84bf",
              "carpet": "#233a63", "carpet_trim": "#d8b45a", "marble": "#f1eee8", "marble_vein": "#2c2a30",
              "furniture": "#4a2a18", "furniture_line": "#d8b45a", "counter": "#3a2012", "backdrop": None,
              "coping": "#ece6da", "walls": "plaster", "fine": "checker", "wood": "herringbone"},
    # shrines, chapels, cathedrals: pale ashlar, terrazzo, violet hangings
    "temple": {"wall": "#8a8578", "wall_edge": "#b8b2a4", "wall_line": "#6a665b", "trim": "#e3d3a0", "plank": "#9c7a52",
               "plank_line": "#7a5a36", "flag": "#d8d2c2", "flag_line": "#bdb6a4", "water": "#a6d4e6", "deep": "#4f8fb8",
               "carpet": "#4f2a66", "carpet_trim": "#e3c46a", "marble": "#e9e5da", "marble_vein": "#c5bfb0",
               "furniture": "#5e4630", "furniture_line": "#e3c46a", "counter": "#4a3522", "backdrop": None,
               "coping": "#efe9dc", "walls": "ashlar", "fine": "terrazzo", "stone_floor": "slate"},
    # cellars, warehouses, workshops: soot brick, dark flags, rough boards
    "cellar": {"wall": "#5a3226", "wall_edge": "#7d4634", "wall_line": "#3a1f16", "trim": None, "plank": "#6e5236",
               "plank_line": "#4a3522", "flag": "#8e8474", "flag_line": "#716858", "water": "#56788a", "deep": "#2a4656",
               "carpet": "#5a2a22", "carpet_trim": "#9a7a4a", "marble": "#b0a898", "marble_vein": "#8e8676",
               "furniture": "#4d3722", "furniture_line": "#2a1c10", "counter": "#3d2a18", "backdrop": None,
               "walls": "brick", "stone_floor": "slate"},
}
# per-map overrides (map set --kv walls=brick / floor=mosaic / wood=parquet / stone=hex / accent=#hex)
WALL_STYLES = ("hatch", "brick", "ashlar", "timber", "plaster")
FINE_STYLES = ("marble", "mosaic", "checker", "terrazzo")
WOOD_STYLES = ("planks", "herringbone", "parquet")
STONE_STYLES = ("flag", "hex", "slate")



WALLISH = set("#BNKi%g")   # walls and the barriers a door can hang in: bars, shelving, hedges, railings


def door_horizontal(grid, x, y):
    """Does the door at (x, y) sit in a wall running left-right? It lines up with the walls (or bars) it hangs between;
    in a double or triple door it lines up with the other leaves."""
    h, w = len(grid), len(grid[0])
    at = lambda xx, yy: grid[yy][xx] if 0 <= xx < w and 0 <= yy < h else " "
    left, right, up, down = at(x - 1, y), at(x + 1, y), at(x, y - 1), at(x, y + 1)
    across = left in WALLISH or right in WALLISH
    along = up in WALLISH or down in WALLISH
    if across != along:
        return across
    if left in "DdS" or right in "DdS":
        return True
    if up in "DdS" or down in "DdS":
        return False
    return across

def _styles(m, t):
    """The texture choices for a map: its theme's defaults, overridden per map."""
    m = m or {}
    return {"walls": m.get("style_walls") or t.get("walls") or "hatch", "fine": m.get("style_floor") or t.get("fine") or "marble",
            "wood": m.get("style_wood") or t.get("wood") or "planks", "stone": m.get("style_stone") or t.get("stone_floor") or "flag"}


def _palette(m, theme):
    t = dict(THEMES.get(theme, THEMES["stone"]))
    if m and m.get("accent"):
        t["trim"] = t["carpet_trim"] = t["furniture_line"] = m["accent"]
    t.setdefault("tile", t["marble"])
    t.setdefault("tile2", t["marble_vein"])
    t.setdefault("grout", t["flag_line"])
    return t


def _style_defs(t, st):
    """Extra textures: wall faces, fine floors, wood floors and stone floors in the chosen styles."""
    out = []
    wall = {"brick": f'<pattern id="wallface" width="24" height="12" patternUnits="userSpaceOnUse"><rect width="24" height="12" fill="{t["wall_edge"]}"/>'
                     f'<path d="M0 5.5H24M0 11.5H24M8 0V5.5M20 6V11.5" stroke="{t["wall_line"]}" stroke-width="1.2"/></pattern>',
            "ashlar": f'<pattern id="wallface" width="32" height="16" patternUnits="userSpaceOnUse"><rect width="32" height="16" fill="{t["wall_edge"]}"/>'
                      f'<path d="M0 7.5H32M0 15.5H32M12 0V7.5M28 8V15.5" stroke="{t["wall_line"]}" stroke-width="1"/>'
                      f'<rect x="1" y="1" width="10" height="5.5" fill="#fff" fill-opacity=".08"/></pattern>',
            "timber": f'<pattern id="wallface" width="96" height="32" patternUnits="userSpaceOnUse"><rect width="96" height="32" fill="{t["wall_edge"]}"/>'
                      f'<path d="M0 2H96M0 30H96M1 0V32M49 0V32" stroke="{t["wall"]}" stroke-width="3.5"/>'
                      f'<path d="M1 30L32 2" stroke="{t["wall"]}" stroke-width="3"/></pattern>',
            "plaster": f'<pattern id="wallface" width="32" height="32" patternUnits="userSpaceOnUse"><rect width="32" height="32" fill="{t["wall_edge"]}"/>'
                       f'<rect x="0" y="26" width="32" height="6" fill="{t["wall"]}" fill-opacity=".55"/>'
                       f'<path d="M0 25.5H32" stroke="{t["trim"] or t["wall_line"]}" stroke-width="1.2"/></pattern>'}.get(st["walls"])
    if wall:
        out.append(wall)
    out.append({
        "mosaic": f'<pattern id="fine" width="16" height="16" patternUnits="userSpaceOnUse"><rect width="16" height="16" fill="{t["grout"]}"/>'
                  f'<rect x=".6" y=".6" width="6.8" height="6.8" fill="{t["tile"]}"/><rect x="8.6" y=".6" width="6.8" height="6.8" fill="{t["tile"]}"/>'
                  f'<rect x=".6" y="8.6" width="6.8" height="6.8" fill="{t["tile"]}"/><rect x="8.6" y="8.6" width="6.8" height="6.8" fill="{t["tile2"]}" fill-opacity=".55"/></pattern>',
        "checker": f'<pattern id="fine" width="64" height="64" patternUnits="userSpaceOnUse"><rect width="64" height="64" fill="{t["marble"]}"/>'
                   f'<rect width="32" height="32" fill="{t["marble_vein"]}" fill-opacity=".8"/><rect x="32" y="32" width="32" height="32" fill="{t["marble_vein"]}" fill-opacity=".8"/></pattern>',
        "terrazzo": f'<pattern id="fine" width="40" height="40" patternUnits="userSpaceOnUse"><rect width="40" height="40" fill="{t["marble"]}"/>'
                    + "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{c}"/>' for x, y, r, c in
                              ((5, 7, 1.6, t["marble_vein"]), (19, 4, 1.1, t["carpet_trim"]), (31, 12, 2, t["marble_vein"]), (12, 22, 1.3, t["carpet"]),
                               (27, 28, 1.7, t["marble_vein"]), (6, 34, 1.2, t["carpet_trim"]), (36, 36, 1.1, t["carpet"]), (22, 16, .9, t["wall"])))
                    + '</pattern>',
    }.get(st["fine"], ""))
    out.append({
        "herringbone": f'<pattern id="wood" width="24" height="24" patternUnits="userSpaceOnUse"><rect width="24" height="24" fill="{t["plank"]}"/>'
                       f'<path d="M0 12L12 0M6 18L18 6M12 24L24 12M0 12L12 24M6 6L18 18M12 0L24 12" stroke="{t["plank_line"]}" stroke-width="1"/></pattern>',
        "parquet": f'<pattern id="wood" width="32" height="32" patternUnits="userSpaceOnUse"><rect width="32" height="32" fill="{t["plank"]}"/>'
                   f'<path d="M0 0H16V16H0ZM16 16H32V32H16Z" fill="#000" fill-opacity=".08"/>'
                   f'<path d="M0 5.3H16M0 10.6H16M21.3 16V32M26.6 16V32M21.3 0V16M26.6 0V16M16 21.3H0M16 26.6H0" stroke="{t["plank_line"]}" stroke-width=".8"/></pattern>',
    }.get(st["wood"], ""))
    out.append({
        "hex": f'<pattern id="stonef" width="18" height="31.2" patternUnits="userSpaceOnUse"><rect width="18" height="31.2" fill="{t["flag"]}"/>'
               f'<path d="M9 0L18 5.2V15.6L9 20.8L0 15.6V5.2ZM0 15.6V26M18 15.6V26M9 20.8V31.2" fill="none" stroke="{t["flag_line"]}" stroke-width="1"/></pattern>',
        "slate": f'<pattern id="stonef" width="48" height="32" patternUnits="userSpaceOnUse"><rect width="48" height="32" fill="{t["flag"]}"/>'
                 f'<rect x="1" y="1" width="21" height="14" fill="#000" fill-opacity=".06"/><rect x="25" y="17" width="22" height="14" fill="#fff" fill-opacity=".06"/>'
                 f'<path d="M0 15.5H48M0 31.5H48M23 0V15.5M11 16V31.5M36 16V31.5" stroke="{t["flag_line"]}" stroke-width="1.2"/></pattern>',
    }.get(st["stone"], ""))
    # tiled floor ('z') always has a mosaic
    out.append(f'<pattern id="tiles" width="16" height="16" patternUnits="userSpaceOnUse"><rect width="16" height="16" fill="{t["grout"]}"/>'
               f'<rect x=".6" y=".6" width="6.8" height="6.8" fill="{t["tile"]}"/><rect x="8.6" y=".6" width="6.8" height="6.8" fill="{t["tile2"]}" fill-opacity=".6"/>'
               f'<rect x=".6" y="8.6" width="6.8" height="6.8" fill="{t["tile2"]}" fill-opacity=".6"/><rect x="8.6" y="8.6" width="6.8" height="6.8" fill="{t["tile"]}"/></pattern>')
    return "".join(out)


def _defs(theme="stone", m=None):
    t = _palette(m, theme)
    st = _styles(m, t)
    return f"""<defs>{_style_defs(t, st)}
<pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="8" height="8" fill="{t['wall']}"/><line x1="0" y1="0" x2="0" y2="8" stroke="{t['wall_line']}" stroke-width="3"/></pattern>
<pattern id="waves" width="24" height="12" patternUnits="userSpaceOnUse"><path d="M0 6 Q6 0 12 6 T24 6" fill="none" stroke="#ffffff" stroke-opacity=".25" stroke-width="1.5"/></pattern>
<pattern id="planks" width="64" height="8" patternUnits="userSpaceOnUse"><rect width="64" height="8" fill="{t['plank']}"/><line x1="0" y1="7.5" x2="64" y2="7.5" stroke="{t['plank_line']}" stroke-width="1"/><line x1="23" y1="0" x2="23" y2="7.5" stroke="{t['plank_line']}" stroke-width=".8"/><line x1="51" y1="0" x2="51" y2="7.5" stroke="{t['plank_line']}" stroke-width=".8"/></pattern>
<pattern id="cobble" width="16" height="16" patternUnits="userSpaceOnUse"><rect width="16" height="16" fill="#a8a39a"/><circle cx="4" cy="4" r="3" fill="#b8b3aa"/><circle cx="12" cy="11" r="3.5" fill="#9b968d"/></pattern>
<pattern id="flag" width="32" height="32" patternUnits="userSpaceOnUse"><rect width="32" height="32" fill="{t['flag']}"/><path d="M0 16H32M16 0V16M8 16V32M24 16V32" stroke="{t['flag_line']}" stroke-width="1"/>{'<circle cx="5" cy="21" r="2.2" fill="' + t['moss'] + '" fill-opacity=".55"/><circle cx="27" cy="6" r="1.6" fill="' + t['moss'] + '" fill-opacity=".45"/>' if t.get('moss') else ''}</pattern>
<pattern id="carpet" width="32" height="32" patternUnits="userSpaceOnUse"><rect width="32" height="32" fill="{t['carpet']}"/><path d="M16 4 L28 16 L16 28 L4 16 Z" fill="none" stroke="{t['carpet_trim']}" stroke-opacity=".55" stroke-width="1.2"/><circle cx="16" cy="16" r="2" fill="{t['carpet_trim']}" fill-opacity=".6"/></pattern>
<pattern id="marble" width="64" height="64" patternUnits="userSpaceOnUse"><rect width="64" height="64" fill="{t['marble']}"/><path d="M0 40 C16 30 26 52 44 38 S60 20 64 26" fill="none" stroke="{t['marble_vein']}" stroke-width="1.2"/><path d="M10 0 C14 12 4 20 12 32" fill="none" stroke="{t['marble_vein']}" stroke-width=".8"/><path d="M0 0H64V64" fill="none" stroke="{t['marble_vein']}" stroke-opacity=".6"/></pattern>
<radialGradient id="canopy" cx="40%" cy="35%"><stop offset="0" stop-color="#5f9a3c"/><stop offset="1" stop-color="#2e5a22"/></radialGradient>
<radialGradient id="rock" cx="35%" cy="30%"><stop offset="0" stop-color="#b5aea3"/><stop offset="1" stop-color="#6b645a"/></radialGradient>
<radialGradient id="lampglow"><stop offset="0" stop-color="#ffd98a" stop-opacity=".75"/><stop offset=".45" stop-color="#ffb347" stop-opacity=".25"/><stop offset="1" stop-color="#ffb347" stop-opacity="0"/></radialGradient>
<radialGradient id="felt" cx="45%" cy="40%"><stop offset="0" stop-color="#2f7a4a"/><stop offset="1" stop-color="#174a2c"/></radialGradient>
<filter id="glow"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>"""


def _defs_legacy():
    return """<defs>
<pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="8" height="8" fill="#3a342e"/><line x1="0" y1="0" x2="0" y2="8" stroke="#2a2521" stroke-width="3"/></pattern>
<pattern id="waves" width="24" height="12" patternUnits="userSpaceOnUse"><path d="M0 6 Q6 0 12 6 T24 6" fill="none" stroke="#ffffff" stroke-opacity=".35" stroke-width="1.5"/></pattern>
<pattern id="planks" width="32" height="8" patternUnits="userSpaceOnUse"><rect width="32" height="8" fill="#b38b5d"/><line x1="0" y1="7.5" x2="32" y2="7.5" stroke="#8a6a43" stroke-width="1"/></pattern>
<pattern id="cobble" width="16" height="16" patternUnits="userSpaceOnUse"><rect width="16" height="16" fill="#a8a39a"/><circle cx="4" cy="4" r="3" fill="#b8b3aa"/><circle cx="12" cy="11" r="3.5" fill="#9b968d"/></pattern>
<pattern id="flag" width="32" height="32" patternUnits="userSpaceOnUse"><rect width="32" height="32" fill="#cfc4ae"/><path d="M0 16H32M16 0V16M8 16V32M24 16V32" stroke="#b9ad95" stroke-width="1"/></pattern>
<radialGradient id="canopy" cx="40%" cy="35%"><stop offset="0" stop-color="#5f9a3c"/><stop offset="1" stop-color="#2e5a22"/></radialGradient>
<radialGradient id="rock" cx="35%" cy="30%"><stop offset="0" stop-color="#b5aea3"/><stop offset="1" stop-color="#6b645a"/></radialGradient>
<filter id="glow"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>"""


FLOORS = set(".=,:_kqzs")


def _under(grid, x, y, c):
    """The floor drawn beneath a furnishing or door: whatever floor surrounds it (a statue on marble stands on marble)."""
    if c not in BASE_UNDER and c not in "Ddo":
        return c
    near = [grid[y + dy][x + dx] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1))
            if 0 <= y + dy < len(grid) and 0 <= x + dx < len(grid[0]) and grid[y + dy][x + dx] in FLOORS]
    if near:
        return max(sorted(set(near)), key=near.count)
    return BASE_UNDER.get(c) or {"D": ".", "d": ".", "o": ","}[c]


def _runs(row):
    """Merge equal adjacent cells into (start, length, char) runs."""
    out, start = [], 0
    for i in range(1, len(row) + 1):
        if i == len(row) or row[i] != row[start]:
            out.append((start, i - start, row[start]))
            start = i
    return out


def render_battle(m, mode="player", entities=(), current=None, show_grid=True, cell=CELL, highlight=None, live=False):
    w, h = m["w"], m["h"]
    player = mode == "player"
    grid = [list(r) for r in m["grid"]]
    if player:  # secret doors look like walls until discovered
        for f in m.get("features", []):
            if f.get("type") == "secret_door" and f.get("hidden"):
                grid[f["y"]][f["x"]] = "#"
    rng = random.Random(m.get("seed") or 1)
    theme = m.get("theme") or "stone"
    T = _palette(m, theme)
    ST = _styles(m, T)
    natural=m['kind']=='wilderness' or m['kind'] in ('interior','town','battle') and any(c in ',Tt' for row in grid for c in row)
    cold_hearths={(p['x'],p['y']) for p in m.get('props',[]) if painted.fire_state(p)=='cold'}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w * cell} {h * cell}" width="{w * cell}" height="{h * cell}" '
             f'font-family="Georgia,serif" data-cell="{cell}" data-lighting="{esc(m.get("lighting","bright"))}">', _defs(theme, m), illustration.terrain_defs()]
    fine = "url(#fine)" if ST["fine"] != "marble" else "url(#marble)"
    wood = "url(#wood)" if ST["wood"] != "planks" else "url(#planks)"
    stonef = "url(#stonef)" if ST["stone"] != "flag" else "url(#flag)"
    if illustration._atlas('terrain-materials'):
        if ST['wood'] == 'planks' and theme in ('stone', 'timber', 'cellar'):
            wood = 'url(#art-wood)'
        if ST['stone'] in ('flag', 'slate') and theme in ('stone', 'cellar', 'sewer'):
            stonef = 'url(#art-stone)'
    wallface = "url(#wallface)" if ST["walls"] != "hatch" else None
    if painted.uri('architecture',0):
        parts.append('<defs>'+''.join(f'<pattern id="painted-surface-{i}" width="128" height="128" patternUnits="userSpaceOnUse"><use href="#painted-architecture-{i}" width="128" height="128"/></pattern>' for i in range(4))+'</defs>')
        if ST['walls'] in ('ashlar','brick','hatch'):wallface='url(#painted-surface-0)'
        fine='url(#painted-surface-1)' if ST['fine']=='marble' else 'url(#painted-surface-2)'
    if painted.uri('floor-patterns',0):
        parts.append('<defs>'+''.join(f'<pattern id="painted-floor-{i}" width="128" height="128" patternUnits="userSpaceOnUse"><use href="#painted-floor-patterns-{i}" width="128" height="128"/></pattern>' for i in range(4))+'</defs>')
        if ST['wood'] in ('herringbone','parquet'):wood=f'url(#painted-floor-{0 if ST["wood"]=="herringbone" else 1})'
        stonef='url(#painted-floor-3)' if m['kind'] in ('dungeon','cave') else 'url(#painted-floor-2)'
    if painted.uri('wall-materials-v2',0):
        wi=1 if (theme=='ship' and ST['walls']=='timber') or (theme=='timber' and ST['walls']=='hatch') else 0 if ST['walls'] in ('timber','plaster') else 3 if ST['walls']=='brick' else None
        if wi is not None:
            wallface='url(#painted-wall)'
            parts.append(f'<defs><pattern id="painted-wall" width="96" height="96" patternUnits="userSpaceOnUse"><use href="#painted-wall-materials-v2-{wi}" width="96" height="96"/></pattern></defs>')
    if T.get("backdrop"):
        parts.append(f'<rect width="{w * cell}" height="{h * cell}" fill="{T["backdrop"]}"/>')
    roof = '#6b5240'
    paving='url(#cobble)'
    if painted.uri('street-materials-v2',0):
        parts.append('<defs><pattern id="painted-paving" width="128" height="128" patternUnits="userSpaceOnUse"><use href="#painted-street-materials-v2-0" width="128" height="128"/></pattern></defs>')
        paving='url(#painted-paving)'
    if painted.uri('town-roof-materials-v2',0):
        parts.append('<defs>'+''.join(f'<pattern id="painted-roof-{i}" width="96" height="96" patternUnits="userSpaceOnUse"><use href="#painted-town-roof-materials-v2-{i}" width="96" height="96"/></pattern>' for i in range(4))+'</defs>')
        roof='url(#painted-roof-0)'
    # base terrain as merged runs
    for y, row in enumerate(grid):
        base_row = [_under(grid, x, y, c) for x, c in enumerate(row)]
        if m["kind"] in ("dungeon", "cave", "battle", "interior") :
            base_row = [({"o": "."}.get(c, c) if row[i] == "o" else c) for i, c in enumerate(base_row)]
        for x0, n, c in _runs(base_row):
            fill = {"#": wallface or "url(#hatch)", "S": wallface or "url(#hatch)", "=": wood, "_": paving, ".": stonef,
                    "k": "url(#painted-surface-3)" if painted.uri('architecture',3) else "url(#carpet)", "q": fine,
                    "z": "url(#painted-surface-2)" if painted.uri('architecture',2) else "url(#tiles)", "w": T["water"], "~": T["deep"],
                    ",": "url(#art-meadow)", "t": "url(#art-brush)", ":": "url(#art-earth)",
                    "s": "url(#art-sand)", "m": "url(#art-mud)", "^": "url(#art-earth)", "B":roof,"b":wood}.get(c, FILL.get(c, "#888"))
            if c == "t":
                fill = "url(#art-meadow)"
            if natural and c in ":^ms":
                fill = "url(#art-meadow)"
            if illustration._atlas('water-materials') and c in "w~":
                fill = "url(#art-water)" if c == "~" else "url(#art-shallows)"
                if natural and m['kind']!='town':
                    fill = "url(#art-meadow)"
            parts.append(f'<rect x="{x0 * cell}" y="{y * cell}" width="{n * cell}" height="{cell}" fill="{fill}"/>')
            if c == "~" and not illustration._atlas('water-materials') and m["kind"] not in ("wilderness", "cave", "battle"):
                parts.append(f'<rect x="{x0 * cell}" y="{y * cell}" width="{n * cell}" height="{cell}" fill="url(#waves)"/>')
    if natural:
        parts.append(illustration.natural_materials(grid, cell,water=m['kind']!='town'))
        # Roads and water use their rounded union outlines; walls retain their exact shape.
        shadow_grid = [''.join(c if c not in ':w~ms' else ',' for c in row) for row in grid]
        parts.append(illustration.terrain_edges(shadow_grid, cell))
    else:
        parts.append(illustration.terrain_edges(grid, cell))
    bridge=illustration._material_path(grid,'b',cell)
    if bridge:
        parts.append(f'<path class="painted-bridge" d="{bridge}" transform="translate(1 3)" fill="#132820" opacity=".45"/>'
                     f'<path d="{bridge}" fill="{wood}" stroke="#463624" stroke-width="2.2" fill-rule="evenodd"/>')
    # built pools and channels get a stone coping along their edges (natural water in the wild does not)
    if T.get("coping") and m["kind"] not in ("wilderness", "cave", "region"):
        edges = []
        for y in range(h):
            for x in range(w):
                if grid[y][x] not in "w~":
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] not in "w~#B xbg":
                        x1 = (x + (dx > 0)) * cell if dx else x * cell
                        y1 = (y + (dy > 0)) * cell if dy else y * cell
                        x2, y2 = (x1, y1 + cell) if dx else (x1 + cell, y1)
                        edges.append(f"M{x1} {y1}L{x2} {y2}")
        if edges:
            d = "".join(edges)
            parts.append(f'<path d="{d}" stroke="#000" stroke-opacity=".22" stroke-width="7" stroke-linecap="round" transform="translate(1.5 2)"/>'
                         f'<path d="{d}" stroke="{T["coping"]}" stroke-width="5" stroke-linecap="round"/>'
                         f'<path d="{d}" stroke="{T["trim"] or T["wall_line"]}" stroke-opacity=".5" stroke-width="1"/>')
    parts.append(painted.building_roofs(grid,m,cell))
    hedge=illustration._material_path(grid,'%',cell,organic=True)
    painted_hedge=bool(hedge and painted.uri('foliage-details-v2',0))
    if painted_hedge:
        parts.append('<defs><pattern id="hedge-leaves" width="96" height="96" patternUnits="userSpaceOnUse"><use href="#painted-foliage-details-v2-0" width="96" height="96"/></pattern></defs>'
                     f'<path class="painted-hedge" d="{hedge}" fill="url(#hedge-leaves)" fill-rule="evenodd" stroke="#283c29" stroke-width="2"/>')
        # Alpha foliage breaks the clipped outline into natural leaf edges, without new tactical cells.
        edges=[]
        for yy,row in enumerate(grid):
            for xx,c in enumerate(row):
                if c!='%':continue
                for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                    nx,ny=xx+dx,yy+dy
                    if 0<=nx<w and 0<=ny<h and grid[ny][nx]=='%':continue
                    for offset in (-.22,.22):
                        size=cell*.6
                        px=(xx+.5+dx*.39+(offset if not dx else 0))*cell-size/2
                        py=(yy+.5+dy*.39+(offset if not dy else 0))*cell-size/2
                        edges.append(f'<use href="#painted-tree-{(xx+yy)%2}" x="{px:.1f}" y="{py:.1f}" width="{size:.1f}" height="{size:.1f}"/>')
        clip=' clip-path="url(#revealed-area)"' if player and m.get('fog') else ''
        parts.append(f'<g class="hedge-leaf-edge"{clip}>{"".join(edges)}</g>')
    joined, joined_cells = painted.joined_furnishings(grid,m,cell)
    parts.append(joined)
    # walls edge shading
    for y in range(h):
        for x in range(w):
            c = grid[y][x]
            if (x,y) in joined_cells:
                continue
            if c=='%' and painted_hedge:
                continue
            if c=='B' and roof!='#6b5240':
                continue
            cx, cy = x * cell, y * cell
            s = cell
            if c in "#B" and any(0 <= y + dy < h and 0 <= x + dx < w and grid[y + dy][x + dx] not in "#B "
                                 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                face = (wallface or T["wall_edge"]) if c == "#" else roof
                parts.append(f'<rect x="{cx}" y="{cy}" width="{s}" height="{s}" fill="{face}" stroke="{T["trim"] or "#211d19"}" stroke-width="{1.5 if T["trim"] else 1}"/>'
                             + (f'<rect x="{cx}" y="{cy}" width="{s}" height="{s}" fill="#000" fill-opacity=".12"/>' if wallface else ""))
                if c=='#' and ST['walls']=='timber' and theme!='ship' and wallface:
                    parts.append(f'<path d="M{cx+2} {cy+2}H{cx+s-2}V{cy+s-2}H{cx+2}Z M{cx+2} {cy+2}L{cx+s-2} {cy+s-2}" fill="none" stroke="#493d2c" stroke-width="2" opacity=".75"/>')
            elif c == "T":
                if not (player and m.get("fog") and (m.get("revealed") or ["0" * w] * h)[y][x] != "1"):
                    parts.append(illustration.tree(cx, cy, cell, f'{m.get("seed", 1)}:{x}:{y}'))
            elif c == "t":
                parts.append(f'<use href="#art-tree-{(x * 3 + y) % 8}" opacity=".55" '
                             f'transform="translate({cx + s / 2} {cy + s / 2}) scale({s / 64})"/>')
            elif painted.furnishing(c,m,x,y) and painted.uri(*painted.furnishing(c,m,x,y)):
                parts.append(painted.sprite(*painted.furnishing(c,m,x,y),cx+1,cy+1,s-2))
            elif c == "^":
                for _ in range(4):
                    px, py = cx + 4 + rng.random() * (s - 8), cy + 4 + rng.random() * (s - 8)
                    parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{2 + rng.random() * 3:.1f}" fill="#8e8576"/>')
            elif c == "o":
                parts.append(illustration.rock(cx, cy, cell, f'{m.get("seed", 1)}:{x}:{y}'))
            elif c == "P":
                parts.append(f'<circle cx="{cx + s / 2}" cy="{cy + s / 2}" r="{s * .38}" fill="#8f877a" stroke="#4a443c" stroke-width="2"/>')
            elif c == "h":  # furniture: a mix of round tables with stools, square tables, and chairs
                kind = rng.random()
                if kind < .4:
                    parts.append(f'<circle cx="{cx + s / 2 + 1.5}" cy="{cy + s / 2 + 2}" r="{s * .3}" fill="#000" fill-opacity=".2"/>'
                                 f'<circle cx="{cx + s / 2}" cy="{cy + s / 2}" r="{s * .3}" fill="{T["furniture"]}" stroke="{T["furniture_line"]}" stroke-width="1.5"/>'
                                 + "".join(f'<circle cx="{cx + s / 2 + s * .42 * dx:.1f}" cy="{cy + s / 2 + s * .42 * dy:.1f}" r="{s * .1:.1f}" fill="{T["furniture"]}" stroke="{T["furniture_line"]}" stroke-width=".8"/>'
                                           for dx, dy in rng.sample(((1, 0), (-1, 0), (0, 1), (0, -1)), 2)))
                elif kind < .75:
                    parts.append(f'<rect x="{cx + 4 + 1.5}" y="{cy + 4 + 2}" width="{s - 8}" height="{s - 8}" rx="3" fill="#000" fill-opacity=".2"/>'
                                 f'<rect x="{cx + 4}" y="{cy + 4}" width="{s - 8}" height="{s - 8}" rx="3" fill="{T["furniture"]}" stroke="{T["furniture_line"]}"/>'
                                 f'<path d="M{cx + 8} {cy + s / 2}H{cx + s - 8}" stroke="{T["furniture_line"]}" stroke-opacity=".5"/>')
                else:  # an armchair
                    parts.append(f'<rect x="{cx + 6}" y="{cy + 6}" width="{s - 12}" height="{s - 10}" rx="5" fill="{T["carpet"]}" stroke="{T["furniture_line"]}" stroke-width="1.2"/>'
                                 f'<rect x="{cx + 6}" y="{cy + 4}" width="{s - 12}" height="6" rx="3" fill="{T["furniture"]}" stroke="{T["furniture_line"]}"/>')
            elif c == "p":  # potted plant
                parts.append(f'<circle cx="{cx + s / 2}" cy="{cy + s / 2}" r="{s * .22}" fill="#9a5a3a" stroke="#5a2e1a" stroke-width="1.5"/>'
                             + "".join(f'<ellipse cx="{cx + s / 2 + s * .2 * dx:.1f}" cy="{cy + s / 2 + s * .2 * dy:.1f}" rx="{s * .2:.1f}" ry="{s * .09:.1f}" '
                                       f'transform="rotate({a} {cx + s / 2 + s * .2 * dx:.1f} {cy + s / 2 + s * .2 * dy:.1f})" fill="#4f8a3a" stroke="#2e5a22" stroke-width=".8"/>'
                                       for dx, dy, a in ((1, 0, 0), (-1, 0, 0), (0, 1, 90), (0, -1, 90), (.7, .7, 45), (-.7, -.7, 45), (.7, -.7, -45), (-.7, .7, -45)))
                             + f'<circle cx="{cx + s / 2}" cy="{cy + s / 2}" r="{s * .1}" fill="#6fae4a"/>')
            elif c == "e":  # bench: runs along its neighbours
                horiz = not ((y > 0 and grid[y - 1][x] == "e") or (y < h - 1 and grid[y + 1][x] == "e")) or \
                        (x > 0 and grid[y][x - 1] == "e") or (x < w - 1 and grid[y][x + 1] == "e")
                bx, by, bw, bh = (cx, cy + s * .3, s, s * .4) if horiz else (cx + s * .3, cy, s * .4, s)
                parts.append(f'<rect x="{bx + 1.5:.1f}" y="{by + 2:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="#000" fill-opacity=".2"/>'
                             f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="2" fill="{T["plank"]}" stroke="{T["plank_line"]}" stroke-width="1.2"/>'
                             + (f'<path d="M{bx} {by + bh / 2:.1f}H{bx + bw}" stroke="{T["plank_line"]}" stroke-width=".8"/>' if horiz else
                                f'<path d="M{bx + bw / 2:.1f} {by}V{by + bh}" stroke="{T["plank_line"]}" stroke-width=".8"/>'))
            elif c == "i":  # cabinets / shelves / wardrobe: doors and knobs
                parts.append(f'<rect x="{cx + 1}" y="{cy + 2}" width="{s - 2}" height="{s - 4}" fill="{T["counter"]}" stroke="{T["furniture_line"]}" stroke-width="1.2"/>'
                             f'<path d="M{cx + s / 2} {cy + 4}V{cy + s - 4}" stroke="{T["furniture_line"]}" stroke-width="1"/>'
                             f'<circle cx="{cx + s / 2 - 3}" cy="{cy + s / 2}" r="1.4" fill="{T["trim"] or "#c9a14a"}"/>'
                             f'<circle cx="{cx + s / 2 + 3}" cy="{cy + s / 2}" r="1.4" fill="{T["trim"] or "#c9a14a"}"/>')
            elif c == "y":  # bed: frame, blanket, pillow
                parts.append(f'<rect x="{cx + 3}" y="{cy + 2}" width="{s - 6}" height="{s - 4}" rx="2" fill="{T["furniture"]}" stroke="{T["furniture_line"]}"/>'
                             f'<rect x="{cx + 5}" y="{cy + s * .38}" width="{s - 10}" height="{s * .52}" rx="2" fill="{T["carpet"]}"/>'
                             f'<rect x="{cx + 7}" y="{cy + 5}" width="{s - 14}" height="{s * .22}" rx="3" fill="#f2ece0"/>')
            elif c == "j":  # tub / basin
                parts.append(f'<ellipse cx="{cx + s / 2 + 1.5}" cy="{cy + s / 2 + 2}" rx="{s * .44}" ry="{s * .36}" fill="#000" fill-opacity=".2"/>'
                             f'<ellipse cx="{cx + s / 2}" cy="{cy + s / 2}" rx="{s * .44}" ry="{s * .36}" fill="#f4f1ea" stroke="{T["trim"] or "#8f877a"}" stroke-width="1.5"/>'
                             f'<ellipse cx="{cx + s / 2}" cy="{cy + s / 2}" rx="{s * .32}" ry="{s * .24}" fill="{T["water"]}"/>')
            elif c == "c":  # counters join up with their neighbours into one long bar
                vert = ((y > 0 and grid[y - 1][x] == "c") or (y < h - 1 and grid[y + 1][x] == "c")) and not \
                       ((x > 0 and grid[y][x - 1] == "c") or (x < w - 1 and grid[y][x + 1] == "c"))
                if vert:
                    top = 0 if y > 0 and grid[y - 1][x] == "c" else 2
                    bot = 0 if y < h - 1 and grid[y + 1][x] == "c" else 2
                    parts.append(f'<rect x="{cx + 6}" y="{cy + top}" width="{s - 12}" height="{s - top - bot}" fill="{T["counter"]}"/>'
                                 f'<path d="M{cx + 6} {cy}V{cy + s}M{cx + s - 6} {cy}V{cy + s}" stroke="{T["furniture_line"]}"/>')
                else:
                    left = 0 if x > 0 and grid[y][x - 1] == "c" else 2
                    right = 0 if x < w - 1 and grid[y][x + 1] == "c" else 2
                    parts.append(f'<rect x="{cx + left}" y="{cy + 6}" width="{s - left - right}" height="{s - 12}" fill="{T["counter"]}"/>'
                                 f'<path d="M{cx} {cy + 6}H{cx + s}M{cx} {cy + s - 6}H{cx + s}" stroke="{T["furniture_line"]}"/>')
            elif c == "a":  # gaming table: green felt, gilt rim, a few chips
                parts.append(f'<ellipse cx="{cx + s / 2}" cy="{cy + s / 2}" rx="{s * .46}" ry="{s * .38}" fill="#000" fill-opacity=".25" transform="translate(2 3)"/>'
                             f'<ellipse cx="{cx + s / 2}" cy="{cy + s / 2}" rx="{s * .46}" ry="{s * .38}" fill="url(#felt)" stroke="#c9a14a" stroke-width="2"/>')
                for _ in range(3):
                    parts.append(f'<circle cx="{cx + s * (.3 + rng.random() * .4):.1f}" cy="{cy + s * (.35 + rng.random() * .3):.1f}" r="2.2" fill="{rng.choice(["#d9443b", "#f2e6c9", "#2f8fdd"])}"/>')
            elif c == "g":  # railing
                parts.append(f'<rect x="{cx}" y="{cy + s * .42}" width="{s}" height="{s * .16}" fill="{T["trim"] or "#8a6a43"}"/>'
                             f'<circle cx="{cx + 4}" cy="{cy + s / 2}" r="3" fill="{T["trim"] or "#8a6a43"}"/><circle cx="{cx + s - 4}" cy="{cy + s / 2}" r="3" fill="{T["trim"] or "#8a6a43"}"/>')
            elif c == "v":  # crates and barrels
                parts.append(f'<rect x="{cx + 3}" y="{cy + 3}" width="{s * .5}" height="{s * .5}" fill="#8a6a3a" stroke="#4a3418"/>'
                             f'<path d="M{cx + 3} {cy + 3} L{cx + 3 + s * .5} {cy + 3 + s * .5} M{cx + 3 + s * .5} {cy + 3} L{cx + 3} {cy + 3 + s * .5}" stroke="#4a3418"/>'
                             f'<circle cx="{cx + s * .7}" cy="{cy + s * .68}" r="{s * .24}" fill="#7a5530" stroke="#3a2412" stroke-width="2"/>')
            elif c == "l":  # lamp: a pool of warm light
                parts.append(f'<circle cx="{cx + s / 2}" cy="{cy + s / 2}" r="{s * 1.6}" fill="url(#lampglow)"/>'
                             f'<circle cx="{cx + s / 2}" cy="{cy + s / 2}" r="3.5" fill="#fff2c4" stroke="#8a6a2a"/>')
            elif c == "u":  # statue / display plinth
                parts.append(f'<rect x="{cx + 3}" y="{cy + 3}" width="{s - 6}" height="{s - 6}" fill="#d8d2c6" stroke="#8f8576" stroke-width="2"/>'
                             f'<circle cx="{cx + s / 2}" cy="{cy + s / 2}" r="{s * .22}" fill="#b8b0a2" stroke="#6e6557"/>')
            elif c == "n":  # mast / column
                parts.append(f'<circle cx="{cx + s / 2}" cy="{cy + s / 2}" r="{s * .34}" fill="#5a3a22" stroke="{T["trim"] or "#2a1a0e"}" stroke-width="2"/>')
            elif c == "f":
                if (x,y) in cold_hearths:
                    parts.append(painted.sprite('interior-details-v2',14,cx,cy,s))
                    continue
                parts.append(painted.sprite('environment',5,cx,cy,s) or illustration.fire(cx+s/2,cy+s/2,s,x+y))
                parts.append(illustration.fire(cx+s/2,cy+s/2,s*.62,x+y))
            elif c in "Dd":
                horiz = door_horizontal(grid, x, y)
                if painted.uri('fittings',0):
                    parts.append(painted.sprite('fittings',0 if c=='D' else 1,cx,cy,s,rotation=0 if horiz else 90))
                    continue
                door = (f'<rect x="{cx + 1}" y="{cy + s * .3}" width="{s - 2}" height="{s * .4}"' if horiz else
                        f'<rect x="{cx + s * .3}" y="{cy + 1}" width="{s * .4}" height="{s - 2}"')
                parts.append(door + (' fill="#7a4a1e" stroke="#3a2008" stroke-width="2"/>' if c == "D" else ' fill="none" stroke="#7a4a1e" stroke-width="2" stroke-dasharray="3 2"/>'))
            elif c == "S" and not player:
                parts.append(f'<rect x="{cx + 3}" y="{cy + 3}" width="{s - 6}" height="{s - 6}" fill="none" stroke="#e0c040" stroke-width="2" stroke-dasharray="4 3"/>'
                             f'<text x="{cx + s / 2}" y="{cy + s * .68}" font-size="{s * .5}" text-anchor="middle" fill="#e0c040">S</text>')
            elif c in "<>":
                for i in range(4):
                    parts.append(f'<line x1="{cx + 4}" y1="{cy + 5 + i * 7}" x2="{cx + s - 4}" y2="{cy + 5 + i * 7}" stroke="#6b6358" stroke-width="{3 - i * .5}"/>')
                parts.append(f'<text x="{cx + s - 6}" y="{cy + 12}" font-size="10" fill="#3a342e">{"▲" if c == "<" else "▼"}</text>')
            elif c == "r":
                parts.append(f'<circle cx="{cx + s / 2}" cy="{cy + s / 2}" r="{s * .4}" fill="#6b6358"/><circle cx="{cx + s / 2}" cy="{cy + s / 2}" r="{s * .26}" fill="#3f84bf"/>')
            elif c == "b":
                for i in range(4):
                    parts.append(f'<line x1="{cx + i * 8 + 4}" y1="{cy}" x2="{cx + i * 8 + 4}" y2="{cy + s}" stroke="#35291d" stroke-opacity=".24" stroke-width=".6"/>')
            elif c in FURNITURE_ART:
                parts.append(FURNITURE_ART[c](cx, cy, s, T, rng, lambda dx, dy, x=x, y=y: grid[y + dy][x + dx]
                                              if 0 <= x + dx < w and 0 <= y + dy < h else " "))
    if show_grid:
        gl = [f'<path d="' + "".join(f"M{x * cell} 0V{h * cell}" for x in range(w + 1)) +
              "".join(f"M0 {y * cell}H{w * cell}" for y in range(h + 1)) + '" class="tactical-grid" stroke="#182c25" stroke-opacity=".10" stroke-width=".65"/>']
        parts += gl
    # rooms/building labels
    revealed = m.get("revealed") or [("0" if m.get('fog') else "1") * w] * h
    for r in m.get("rooms", []):
        cx, cy = r["x"] + r["w"] // 2, r["y"] + r["h"] // 2
        if player and m.get("fog") and revealed[cy][cx] != "1":
            continue
        if m["kind"] == "town":
            parts.append(f'<text x="{(r["x"] + r["w"] / 2) * cell}" y="{(r["y"] + r["h"] / 2) * cell + 5}" text-anchor="middle" font-size="{cell * .42}" fill="#fff" stroke="#2b1d0e" stroke-width="3" paint-order="stroke">{esc(r["label"])}</text>')
        elif not player:  # room numbers are the DM's key, never shown at the table
            parts.append(f'<circle cx="{(r["x"] + .5) * cell}" cy="{(r["y"] + .5) * cell}" r="{cell * .38}" fill="#fff" fill-opacity=".8" stroke="#3a2a1a"/>'
                         f'<text x="{(r["x"] + .5) * cell}" y="{(r["y"] + .5) * cell + 5}" text-anchor="middle" font-size="{cell * .42}" font-weight="bold" fill="#3a2a1a">{r["n"]}</text>')
    for lb in m.get("labels", []):
        if player and lb.get("hidden"):
            continue
        if player and m.get("fog") and revealed[min(h - 1, lb["y"])][min(w - 1, lb["x"])] != "1":
            continue
        parts.append(map_label(lb, cell, w, h))
    for f in m.get("features", []):
        if f.get("hidden") and player:
            continue
        cx, cy = (f["x"] + .5) * cell, (f["y"] + .5) * cell
        if f["type"] == "trap":
            parts.append(f'<g opacity=".85"><circle cx="{cx}" cy="{cy}" r="{cell * .4}" fill="none" stroke="#c0392b" stroke-width="3" stroke-dasharray="4 3"/>'
                         f'<text x="{cx}" y="{cy + 5}" text-anchor="middle" font-size="{cell * .45}" fill="#c0392b">⚠</text><title>{esc(f.get("name", "trap"))}</title></g>')
        elif f["type"] == "light":
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{cell * .3}" fill="#ffd36b" filter="url(#glow)"/>')
        elif f["type"] == "poi":
            parts.append(f'<text x="{cx}" y="{cy + 6}" text-anchor="middle" font-size="{cell * .6}">★</text>')
    # spell walls (Wall of Fire): the burning band, then the wall itself, flickering
    for sw in m.get("spell_walls", []):
        parts.append(spell_wall_svg(sw, cell))
    # props: any icon from the vendored game-icons library placed on a tile as a decoration (a globe, a skull, a harp)
    for pr in m.get("props", []):
        if player and m.get("fog") and not (0 <= pr["y"] < len(revealed) and revealed[pr["y"]][pr["x"]] == "1"):
            continue
        parts.append(prop_svg(pr, cell, T))
    # highlight squares (movement range / area of effect)
    if highlight:
        for (x, y) in highlight:
            parts.append(f'<rect x="{x * cell}" y="{y * cell}" width="{cell}" height="{cell}" fill="#3ec7ff" fill-opacity=".25"/>')
    # items lying on the floor (visible wherever the players can see)
    # one marker per tile: a chest for a container (a stash, a strongbox), otherwise the top item with a count badge
    tiles = {}
    for f in m.get("floor", []):
        tiles.setdefault((f["x"], f["y"]), []).append(f)
    boxes = {(c["x"], c["y"]): c for c in m.get("containers", [])}
    for (fx, fy) in sorted(set(tiles) | set(boxes)):
        if player and m.get("fog") and revealed and not (0 <= fy < len(revealed) and revealed[fy][fx] == "1"):
            continue
        here, box = tiles.get((fx, fy), []), boxes.get((fx, fy))
        n = sum(1 for _ in here)
        coins = box.get("coins_cp", 0) if box else 0
        label = (f"{box['name']}: {n} item{'s' if n != 1 else ''}" + (f", {coins // 100:,} crowns" if coins >= 100 else "") if box else
                 ", ".join(f"{f['item'].get('qty', 1)}× {f['item']['name']}" for f in here) + " (on the floor)")
        px, py = fx * cell + cell - 9, fy * cell + cell - 9
        s0 = cell * .56
        x0, y0 = fx * cell + cell - s0 - 2, fy * cell + cell - s0 - 2
        badge = (f'<circle cx="{x0 + s0 - 1:.1f}" cy="{y0 + 1:.1f}" r="7" fill="#d8b36a" stroke="#1a130c" stroke-width="1.5"/>'
                 f'<text x="{x0 + s0 - 1:.1f}" y="{y0 + 4.5:.1f}" text-anchor="middle" font-size="9.5" font-weight="700" fill="#1a130c">{n}</text>'
                 if n > 1 or (box and n) else "")
        attrs = f'class="flooritem" data-tile="{fx},{fy}"' + (f' data-floor="{esc(here[0]["id"])}"' if here else "") + \
                (f' data-box="{esc(box["id"])}"' if box else "") + ' style="cursor:pointer"'
        if box:  # a small chest glyph
            parts.append(f'<g {attrs}><title>{esc(label)}</title>'
                         f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{s0:.1f}" height="{s0:.1f}" rx="4" fill="#1a130c" fill-opacity=".85" stroke="#d8b36a" stroke-width="1.5"/>'
                         f'<rect x="{x0 + s0 * .14:.1f}" y="{y0 + s0 * .38:.1f}" width="{s0 * .72:.1f}" height="{s0 * .44:.1f}" rx="2" fill="#8a5a32" stroke="#3e2410" stroke-width="1.2"/>'
                         f'<path d="M{x0 + s0 * .14:.1f},{y0 + s0 * .4:.1f} Q{x0 + s0 * .5:.1f},{y0 + s0 * .12:.1f} {x0 + s0 * .86:.1f},{y0 + s0 * .4:.1f} Z" fill="#a8703e" stroke="#3e2410" stroke-width="1.2"/>'
                         f'<rect x="{x0 + s0 * .44:.1f}" y="{y0 + s0 * .4:.1f}" width="{s0 * .12:.1f}" height="{s0 * .16:.1f}" fill="#e0b448"/>{badge}'
                         + (f'<circle cx="{x0 + 1:.1f}" cy="{y0 + 1:.1f}" r="6" fill="#f0c94a" stroke="#6b4a12" stroke-width="1.4"/>'
                            f'<circle cx="{x0 + 1:.1f}" cy="{y0 + 1:.1f}" r="3" fill="none" stroke="#6b4a12" stroke-width="1"/>' if coins else "")
                         + '</g>')
            continue
        f = here[0]
        if live:  # the viewer: a small framed picture of the top item
            from . import itemart
            parts.append(f'<g {attrs}><title>{esc(label)}</title>'
                         f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{s0:.1f}" height="{s0:.1f}" rx="4" fill="#1a130c" fill-opacity=".85" stroke="#d8b36a" stroke-width="1.5"/>'
                         f'<image href="/api/art/floor/{esc(m["id"])}/{esc(f["id"])}.svg?v={itemart.item_art_version(f["item"])}" x="{x0 + 1:.1f}" y="{y0 + 1:.1f}" '
                         f'width="{s0 - 2:.1f}" height="{s0 - 2:.1f}"/>{badge}</g>')
            continue
        parts.append(f'<g {attrs}><title>{esc(label)}</title>'
                     f'<rect x="{px - 7}" y="{py - 7}" width="14" height="14" rx="2" transform="rotate(45 {px} {py})" fill="#d8b36a" stroke="#2b1d0e" stroke-width="2"/>'
                     f'<circle cx="{px}" cy="{py}" r="2.5" fill="#2b1d0e"/></g>')
    # Perceived points use a quiet brass-and-sage marker above the art.
    for p in m.get("pois", []):
        if player and p.get('hidden'):
            continue
        pxx, pyy = p["x"], p["y"]
        if player and m.get("fog") and revealed and not (0 <= pyy < len(revealed) and revealed[pyy][pxx] == "1"):
            continue
        cx, cy = pxx * cell + 9, pyy * cell + 9
        parts.append(f'<g class="poi" data-poi="{esc(p["id"])}" style="cursor:pointer"><title>{esc(p["name"])}</title>'
                     f'<circle cx="{cx}" cy="{cy}" r="6.5" fill="#405c50" stroke="#c8b588" stroke-width="1.4"/>'
                     f'<text x="{cx}" y="{cy + 3.6}" text-anchor="middle" font-family="Georgia,serif" font-weight="bold" font-size="10.5" fill="#eee0bb">i</text></g>')
    # A single light wash ties materials together, beneath every token and the opaque fog.
    if m["kind"] in ("wilderness", "interior", "dungeon", "cave", "town", "battle"):
        parts.append(f'<rect width="{w * cell}" height="{h * cell}" fill="url(#map-light)" pointer-events="none"/>')
    lighting=m.get('lighting','bright')
    if lighting in ('dim','dark'):
        lights=[]
        for y,row in enumerate(grid):
            for x,c in enumerate(row):
                if c in 'lf*&F' and (x,y) not in cold_hearths and (not m.get('fog') or revealed[y][x]=='1'):
                    lights.append(((x+.5)*cell,(y+.5)*cell,cell*2.3))
        for p in m.get('props',[]):
            x,y=p['x'],p['y']
            if painted.fire_state(p)!='burning' or player and p.get('hidden'):continue
            if not (0<=x<w and 0<=y<h) or m.get('fog') and revealed[y][x]!='1':continue
            if grid[y][x] not in 'lf*&F':lights.append(((x+.5)*cell,(y+.5)*cell,cell*2.3))
        for e in entities:
            t=e.get('token') or {}
            if t.get('map')!=m['id'] or player and e.get('hidden'):continue
            if m.get('fog') and (not (0<=t['y']<h and 0<=t['x']<w) or revealed[t['y']][t['x']]!='1'):continue
            for it in e.get('inventory',[]):
                if it.get('lit'):
                    radius=cell*(8 if 'torch' in it.get('name','').lower() else 12 if 'lantern' in it.get('name','').lower() else 2)
                    lights.append(((t['x']+.5)*cell,(t['y']+.5)*cell,radius))
        holes=''.join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="url(#light-cutout)"/>' for x,y,r in lights)
        parts.append(f'<defs><radialGradient id="light-cutout"><stop stop-color="#000"/><stop offset=".45" stop-color="#333"/><stop offset="1" stop-color="#fff"/></radialGradient>'
                     f'<mask id="room-shadow"><rect width="{w*cell}" height="{h*cell}" fill="#fff"/>{holes}</mask></defs>'
                     f'<rect class="lighting-shade" width="{w*cell}" height="{h*cell}" fill="#06151c" opacity="{.48 if lighting=="dark" else .19}" mask="url(#room-shadow)" pointer-events="none"/>')
    # tokens
    parts.append(tokens_svg(m, entities, current, cell, player))
    # Outdoor precipitation respects walls/roofs, including mixed indoor/outdoor maps.
    exposed=weather_cells(grid,m['kind'])
    exposure_rows=[''.join('1' if (x,y) in exposed
                           and (not m.get('fog') or revealed[y][x]=='1') else '0' for x,c in enumerate(row)) for y,row in enumerate(grid)]
    exposure=''.join(f'<rect x="{x0*cell}" y="{y*cell}" width="{n*cell}" height="{cell}"/>'
                     for y,row in enumerate(exposure_rows) for x0,n,c in _runs(row) if c=='1')
    parts.append(f'<defs><clipPath id="weather-exposure">{exposure}</clipPath></defs>')
    # fog
    focus = None
    if player and m.get("fog"):
        fog, xs, ys = [], [], []
        for y, row in enumerate(revealed):
            for x0, n, c in _runs(row):
                if c != "1":
                    fog.append(f'<rect x="{x0 * cell - .5}" y="{y * cell - .5}" width="{n * cell + 1}" height="{cell + 1}"/>')
                else:
                    xs += [x0, x0 + n]
                    ys.append(y)
        visible_cells=''.join(f'<rect x="{x0*cell}" y="{y*cell}" width="{n*cell}" height="{cell}"/>' for y,row in enumerate(revealed) for x0,n,c in _runs(row) if c=='1')
        parts.append(f'<defs><clipPath id="revealed-area">{visible_cells}</clipPath></defs>'
                     f'<g id="fog" fill="#0e1918" shape-rendering="crispEdges">{"".join(fog)}</g>')
        if xs:
            pad = 3
            fx0, fy0 = max(0, min(xs) - pad), max(0, min(ys) - pad)
            fx1, fy1 = min(w, max(xs) + pad), min(h, max(ys) + 1 + pad)
            focus = f"{fx0 * cell},{fy0 * cell},{(fx1 - fx0) * cell},{(fy1 - fy0) * cell}"
    parts.append("</svg>")
    if focus:
        parts[0] = parts[0].replace("<svg ", f'<svg data-focus="{focus}" ', 1)
    svg="".join(parts)
    svg=painted.prune_patterns(svg)
    return svg.replace('>', '>'+painted.definitions(svg),1)


def weather_cells(grid,kind):
    """Expose outdoor surfaces and their connected water, keeping indoor pools covered."""
    h,w=len(grid),len(grid[0]);out=set();water=set()
    for y,row in enumerate(grid):
        for x,c in enumerate(row):
            if c in ',:tTsm_%^':out.add((x,y))
            if c in 'w~b':water.add((x,y))
    for y,row in enumerate(grid):
        for x,c in enumerate(row):
            if c=='o' and (kind=='wilderness' or any((x+dx,y+dy) in out for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)))):out.add((x,y))
    while water:
        start=water.pop();group={start};todo=[start];outside=False
        while todo:
            x,y=todo.pop()
            if kind in ('wilderness','town','battle') and (x in (0,w-1) or y in (0,h-1)):outside=True
            for p in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                if p in out:outside=True
                if p in water:water.remove(p);group.add(p);todo.append(p)
        if outside:out.update(group)
    return out


def spell_wall_svg(w, cell):
    """A standing spell wall: a heat shimmer over the squares its burning side reaches, and a sheet of
    animated flame along its squares, drawn the moment it's cast and gone when it ends."""
    r = random.Random(w["id"] + w["caster"])
    gid = f'wall-{esc(w["id"])}'
    out = [f'<g class="spell-wall"><title>{esc(w["name"])} ({esc(w["dice"])} {esc(w["type"])}; {esc(w["side"])} side burns)</title>',
           f'<defs><linearGradient id="{gid}-core" x1="0" y1="1" x2="0" y2="0">'
           '<stop offset="0" stop-color="#7a1004"/><stop offset=".35" stop-color="#ff4d00"/>'
           '<stop offset=".7" stop-color="#ffb32b"/><stop offset="1" stop-color="#fff2b0"/></linearGradient>'
           f'<radialGradient id="{gid}-heat"><stop offset="0" stop-color="#ff6a00" stop-opacity=".42"/>'
           '<stop offset="1" stop-color="#ff3a00" stop-opacity=".12"/></radialGradient></defs>']
    for (x, y) in w.get("hot", []):
        d = r.uniform(1.4, 2.4)
        out.append(f'<rect x="{x * cell}" y="{y * cell}" width="{cell}" height="{cell}" fill="url(#{gid}-heat)">'
                   f'<animate attributeName="opacity" values=".55;.95;.65;.9;.55" dur="{d:.2f}s" repeatCount="indefinite"/></rect>')
    for (x, y) in w["cells"]:
        x0, y0 = x * cell, y * cell
        out.append(f'<rect x="{x0}" y="{y0}" width="{cell}" height="{cell}" fill="#ff5a00" opacity=".85" filter="url(#glow)">'
                   f'<animate attributeName="opacity" values=".7;1;.8;.95;.7" dur="{r.uniform(.5, .9):.2f}s" repeatCount="indefinite"/></rect>')
        for i in range(3):
            fx = x0 + cell * r.uniform(.15, .85)
            h = cell * r.uniform(.75, 1.25)
            wd = cell * r.uniform(.18, .3)
            base = y0 + cell * .95
            dur = r.uniform(.35, .7)
            # each tongue is drawn from its own base so it can stretch and shrink in place
            path = (f'M{-wd:.1f} 0 Q{-wd * 1.3:.1f} {-h * .5:.1f} 0 {-h:.1f} '
                    f'Q{wd * 1.3:.1f} {-h * .5:.1f} {wd:.1f} 0 Z')
            out.append(f'<g transform="translate({fx:.1f} {base:.1f})"><path d="{path}" fill="url(#{gid}-core)" opacity=".9">'
                       f'<animateTransform attributeName="transform" type="scale" '
                       f'values="1 1;.9 1.15;1.05 .9;.95 1.08;1 1" dur="{dur:.2f}s" repeatCount="indefinite"/>'
                       f'<animate attributeName="opacity" values=".75;1;.8;.95;.75" dur="{dur * 1.3:.2f}s" repeatCount="indefinite"/></path></g>')
        out.append(f'<circle cx="{x0 + cell * .5:.1f}" cy="{y0 + cell * .55:.1f}" r="{cell * .16:.1f}" fill="#fff6cf" opacity=".85"/>')
    out.append('</g>')
    return "".join(out)


def prop_svg(pr, cell, T):
    """A decoration drawn from an icon: a soft shadow and the silhouette in the prop's colour, filling most of the tile."""
    size = cell * {"small": .5, "large": .95}.get(pr.get("size"), .74)
    x0, y0 = pr["x"] * cell + (cell - size) / 2, pr["y"] * cell + (cell - size) / 2
    line = T["furniture_line"]
    col = pr.get("color") or ("#2e1c0e" if line.lower() in GOLD_LINES else line)   # gold trim would vanish on warm floors
    body = assets.icon_body(pr["icon"]).replace('fill="currentColor"', "")
    rot = f' transform="rotate({pr["rotate"]} {x0 + size / 2:.1f} {y0 + size / 2:.1f})"' if pr.get("rotate") else ""
    name = esc(pr.get("name") or pr["icon"].replace("-", " "))
    study=painted.prop(pr,cell)
    if study:
        return f'<g class="prop"><title>{name}</title>{study}</g>'
    if any(word in pr['icon'] for word in ('fire', 'flame', 'burning')):
        return f'<g class="prop"><title>{name}</title>' + illustration.fire(x0+size/2,y0+size/2,size,pr.get('id',name)) + '</g>'
    return (f'<g class="prop"{rot}><title>{name}</title>'
            f'<svg x="{x0 + 1.5:.1f}" y="{y0 + 2:.1f}" width="{size:.1f}" height="{size:.1f}" viewBox="0 0 512 512" fill="#000" fill-opacity=".25">{body}</svg>'
            f'<svg x="{x0:.1f}" y="{y0:.1f}" width="{size:.1f}" height="{size:.1f}" viewBox="0 0 512 512" fill="{col}">{body}</svg></g>')


GOLD_LINES = {"#d8b45a", "#d8b36a", "#e3c46a", "#c9a14a", "#e8c98a"}


def wrap_words(text, max_chars):
    lines, cur = [], ""
    for word in str(text).split():
        if cur and len(cur) + 1 + len(word) > max_chars:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines or [""]


def map_label(lb, cell, w, h):
    """A placed label, wrapped to at most ~5 cells wide and nudged so no line runs off the map."""
    fs = cell * .45
    char_w = fs * .52
    max_chars = max(6, int(5 * cell / char_w))
    lines = wrap_words(lb["text"], max_chars)
    width = max(len(l) for l in lines) * char_w
    x = min(max(lb["x"] * cell, 4), w * cell - width - 4)
    y = min(max(lb["y"] * cell, fs + 2), h * cell - (len(lines) - 1) * fs * 1.1 - 4)
    spans = "".join(f'<tspan x="{x:.1f}" dy="{0 if i == 0 else fs * 1.1:.1f}">{esc(l)}</tspan>' for i, l in enumerate(lines))
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{fs}" font-style="italic" fill="#fff" stroke="#2b1d0e" '
            f'stroke-width="3" paint-order="stroke">{spans}</text>')


# words that open a name but don't identify anyone: 'Old Brenna Holt' -> 'Brenna', 'Captain Rhosk' -> 'Rhosk'
_LEAD_WORDS = {"old", "young", "the", "a", "an", "big", "little", "fat", "tall", "sir", "dame", "lord", "lady", "master",
               "mistress", "mister", "mr", "mrs", "madam", "brother", "sister", "mother", "father", "uncle", "aunt", "captain",
               "sergeant", "lieutenant", "commander", "inspector", "councillor", "doctor", "professor", "grand", "high",
               "saint", "st", "king", "queen", "prince", "princess", "duke", "baron", "count", "countess"}


def short_label(e):
    """The name a token shows: 'Kira Vale' -> 'Kira'; 'Old Brenna Holt' -> 'Brenna'; 'The Lamplighter' -> 'Lamplighter';
    'Goblin Warrior B' -> 'Warrior B'; 'Stone Guardian (east)' -> 'Guardian E'. `short` on the creature overrides it."""
    if e.get("short"):
        return e["short"]
    name = e["name"]
    tag = ""
    paren = re.search(r"\(([^)]*)\)\s*$", name)
    if paren:
        inner = paren.group(1).strip()
        tag = inner[0].upper() if inner and len(inner) <= 6 else ""   # (east) -> E; (Receiving Clerk) is dropped
        name = name[:paren.start()]
    words = [w for w in re.split(r"\s+", name.strip()) if w]
    if len(words) > 1 and len(words[-1]) == 1:            # a lettered duplicate: keep the letter
        tag, words = words[-1].upper(), words[:-1]
    if tag:
        core = words[-1] if words else e["id"]           # 'Goblin Warrior B' -> 'Warrior B'
    else:
        rest = [w for w in words if w.lower().strip(".,") not in _LEAD_WORDS and not w.lower().startswith("collector-")]
        core = (rest or words or [e["id"]])[0]
    return f"{core} {tag}".strip()


LABEL_FONT = 10
LABEL_MAX = 12   # characters before a name is trimmed with …
LABEL_TOP = 11
LABEL_BOTTOM = 3.5


def _label_width(text):
    return len(text) * LABEL_FONT * .56


def _layout_labels(tokens, cell):
    """Place every token's name tag so no two tags overlap and none sits on top of another token's face.
    Deterministic: PCs first, then allies, then the rest, left to right, top to bottom. Each tag tries, in order:
    below the token, above it, then further below/above (a second row). Returns {id: (text, x, y, width)}."""
    order = sorted(tokens, key=lambda t: (0 if t[0]["kind"] == "pc" else 1 if t[0].get("side") == "ally" else 2,
                                          t[0]["token"]["y"], t[0]["token"]["x"], t[0]["id"]))
    faces = [(cx - r, cy - r, cx + r, cy + r) for _, cx, cy, r in tokens]
    placed, out = [], {}

    def hits(box, others):
        return any(box[0] < o[2] and box[2] > o[0] and box[1] < o[3] and box[3] > o[1] for o in others)

    for e, cx, cy, r in order:
        text = short_label(e)
        if len(text) > LABEL_MAX:
            text = text[:LABEL_MAX - 1] + "…"
        w = _label_width(text)
        own = (cx - r, cy - r, cx + r, cy + r)
        others = [f for f in faces if f != own]
        spots = [cy + r + 12, cy - r - 5, cy + r + 29, cy - r - 22, cy + r + 46, cy - r - 39]
        best = None
        for ly in spots:
            box = (cx - w / 2 - 2, ly - LABEL_TOP, cx + w / 2 + 2, ly + LABEL_BOTTOM)
            if not hits(box, placed) and not hits(box, others):
                best = (ly, box)
                break
        if best is None:  # everything is taken: fall back to the first spot that at least clears other tags
            for ly in spots:
                box = (cx - w / 2 - 2, ly - LABEL_TOP, cx + w / 2 + 2, ly + LABEL_BOTTOM)
                if not hits(box, placed):
                    best = (ly, box)
                    break
            else:
                best = (spots[0], (cx - w / 2 - 2, spots[0] - LABEL_TOP, cx + w / 2 + 2, spots[0] + LABEL_BOTTOM))
        placed.append(best[1])
        out[e["id"]] = (text, cx, best[0], w)
    return out


def tokens_svg(m, entities, current, cell, player):
    out, symbols = [], {}
    revealed = m.get("revealed") or (["0"*m.get('w',0)]*m.get('h',0) if m.get('fog') else [])
    def is_dead(e):  # destroyed/killed; a knocked-out creature (Unconscious at 0 HP) keeps its full token
        down = e.get("dead") or (e["kind"] != "pc" and e.get("hp", 1) <= 0)
        return bool(down) and not (not e.get("dead") and any(c["name"] == "unconscious" for c in e.get("conditions", [])))
    placed = [e for e in entities if e.get("token") and e["token"].get("map") == m["id"] and not (player and e.get("hidden"))]
    # defeated creatures draw first (underneath) as small markers; the living share a square side by side
    entities = sorted(placed, key=lambda e: (0 if is_dead(e) else 1))
    square = {}
    for e in placed:
        square.setdefault((e["token"]["x"], e["token"]["y"]), []).append(e)
    living_at = {k: [e for e in v if not is_dead(e)] for k, v in square.items()}

    def visible(e):
        x, y = e["token"]["x"], e["token"]["y"]
        if player and m.get("fog") and revealed and e["kind"] != "pc" and e.get("side") != "ally":
            return 0 <= y < len(revealed) and revealed[y][x] == "1"
        return True

    def geom(e):
        x, y = e["token"]["x"], e["token"]["y"]
        r = e.get("cells", 1) * cell / 2
        cx, cy = x * cell + r, y * cell + r
        alive_here = living_at.get((x, y), [])
        if len(alive_here) > 1 and e in alive_here:
            i = alive_here.index(e)
            r = r * .62
            cx += (-1 if i % 2 == 0 else 1) * cell * .2
            cy += (-1 if i < 2 else 1) * cell * .2 if len(alive_here) > 2 else 0
        return cx, cy, r

    labels = _layout_labels([(e, *geom(e)) for e in entities if not is_dead(e) and visible(e)], cell)
    for e in entities:
        t = e.get("token")
        if not t or t.get("map") != m["id"]:
            continue
        if player and e.get("hidden"):
            continue
        x, y = t["x"], t["y"]
        if player and m.get("fog") and revealed and e["kind"] != "pc" and e.get("side") != "ally":
            if not (0 <= y < len(revealed) and revealed[y][x] == "1"):
                continue
        size = e.get("cells", 1)
        r = size * cell / 2
        cx, cy = x * cell + r, y * cell + r
        here = square.get((x, y), [e])
        stack = ",".join(o["id"] for o in here) if len(here) > 1 else ""
        if is_dead(e):
            # Full body remains searchable. Living occupants paint above it; never an anonymous cross.
            short=short_label(e)
            if len(short)>5:
                short=short[:3]+'…'+(short[-1] if len(short.split()[-1])==1 else '')
            label=esc(short)
            tagwidth=min(cell*.94,32)
            out.append(f'<g class="token dead corpse" data-id="{esc(e["id"])}" data-stack="{esc(stack)}" data-cx="{cx}" data-cy="{cy}" data-r="{r}" data-state="dead"><title>{esc(e["name"])} (dead)</title>'
                       f'<ellipse cx="{cx}" cy="{cy+3}" rx="{r*.78}" ry="{r*.48}" fill="#07100b" opacity=".5"/>'
                       +painted.corpse(e,cx,cy,2*r*1.12)+
                       f'<g class="nametag"><rect x="{cx-tagwidth/2:.1f}" y="{cy+r-1}" width="{tagwidth:.1f}" height="11" rx="3" fill="#211e19" stroke="#a89772" stroke-width=".5"/>'
                       f'<text x="{cx}" y="{cy+r+7}" font-size="7.5" text-anchor="middle" fill="#dfd2b8">†{label}</text></g></g>')
            continue
        alive_here = living_at.get((x, y), [])
        if len(alive_here) > 1:  # two living creatures in one square (moving through, grappled, mounted): shrink and offset
            i = alive_here.index(e)
            r = r * .62
            cx += (-1 if i % 2 == 0 else 1) * cell * .2
            cy += (-1 if i < 2 else 1) * cell * .2 if len(alive_here) > 2 else 0
        side = assets.side_of(e)
        color = assets.SIDE_COLORS.get(side, "#888")
        icon = assets.icon_for_entity(e)
        if side not in assets.SIDE_COLORS:
            side = "neutral"
        sym = f"i-{icon}"
        symbols[sym] = icon
        hue = assets.hue_from(e["id"])
        dead = is_dead(e)
        cls = "token" + (" current" if current == e["id"] else "") + (" dead" if dead else "")
        g = [f'<g class="{cls}" data-id="{esc(e["id"])}" data-stack="{esc(stack)}" data-cx="{cx:.1f}" data-cy="{cy:.1f}" data-r="{r:.1f}" '
             f'data-side="{side}" opacity="{0.45 if dead else 1}">',
             f'<title>{esc(e["name"])}</title>']
        if current == e["id"]:
            g.append(f'<circle class="turn-ring" cx="{cx}" cy="{cy}" r="{r + 3}" fill="none" stroke="#e6c47c" stroke-width="2.5" filter="url(#glow)"/>')
        g.append(f'<circle cx="{cx + 2}" cy="{cy + 3}" r="{r - 1}" fill="#000" fill-opacity=".3"/>')
        g.append(f'<circle cx="{cx}" cy="{cy}" r="{r - 1}" fill="#1a251f" stroke="{color}" stroke-width="1.8"/>')
        g.append(f'<circle cx="{cx}" cy="{cy}" r="{max(1,r - 2.5)}" fill="hsl({hue},38%,26%)"/>')
        conditions={c['name'] for c in e.get('conditions',[])}
        if e.get("portrait_href"):
            treatment=' filter="url(#petrified-face)"' if 'petrified' in conditions else ''
            if 'invisible' in conditions:treatment+=' opacity=".3"'
            if 'prone' in conditions:treatment+=f' transform="rotate(-25 {cx} {cy})"'
            g.append(f'<clipPath id="cp-{esc(e["id"])}"><circle cx="{cx}" cy="{cy}" r="{max(1,r - 2.5)}"/></clipPath>'
                     f'<image class="token-face" href="{esc(e["portrait_href"])}" x="{cx - r + 2.5}" y="{cy - r + 2.5}" width="{max(2,2 * r - 5)}" height="{max(2,2 * r - 5)}" clip-path="url(#cp-{esc(e["id"])})" preserveAspectRatio="xMidYMid slice"{treatment}/>')
        else:
            s = (2 * r - 12)
            g.append(f'<use href="#{sym}" x="{cx - s / 2}" y="{cy - s / 2}" width="{s}" height="{s}" fill="#f4efe6" color="#f4efe6"/>')
        # health indicator: exact bar for PCs/allies, coarse status ring for others
        if e.get("hp_max"):
            frac = max(0, min(1, e.get("hp", 0) / max(1, e["hp_max"])))
            if e["kind"] == "pc" or e.get("side") == "ally" or not player:
                bw = 2 * r - 6
                col = "#3cb371" if frac > .5 else "#e0a030" if frac > .25 else "#d9443b"
                g.append(f'<rect x="{cx - bw / 2}" y="{cy + r - 5}" width="{bw}" height="5" rx="2" fill="#111" fill-opacity=".7"/>'
                         f'<rect class="hpbar" data-w="{bw:.1f}" x="{cx - bw / 2}" y="{cy + r - 5}" width="{bw * frac}" height="5" rx="2" fill="{col}"/>')
            elif frac <= .5 and not dead:
                g.append(f'<path d="M{cx - r * .7} {cy - r * .7} L{cx + r * .7} {cy + r * .7}" stroke="#d9443b" stroke-width="3" stroke-opacity=".85"/>')
        conds = [c["name"] for c in e.get("conditions", [])][:4]
        if e.get('hp',1)<=0 or 'unconscious' in conds:
            g.append(f'<g class="down-state"><circle cx="{cx}" cy="{cy}" r="{r-1}" fill="#071315" opacity=".33"/>'
                     f'<rect x="{cx-13}" y="{cy-5}" width="26" height="11" rx="3" fill="#3e3422" stroke="#d9c18a" stroke-width=".7"/>'
                     f'<text x="{cx}" y="{cy+3}" text-anchor="middle" font-size="8" fill="#f5e5bb">Down</text></g>')
        for i, cname in enumerate(conds):
            ci = assets.CONDITION_ICONS.get(cname)
            if ci:
                symbols[f"i-{ci}"] = ci
                g.append(f'<g class="condition-badge" data-condition="{esc(cname)}"><title>{esc(cname.title())}</title>'
                         f'<circle cx="{cx + r - 6 - i * 13}" cy="{cy - r + 6}" r="7" fill="#172921" stroke="#dbc48c" stroke-width=".8"/>'
                         f'<use href="#i-{ci}" x="{cx + r - 12 - i * 13}" y="{cy - r}" width="12" height="12" fill="#e8d7a8" color="#e8d7a8"/></g>')
        if dead:
            g.append(f'<path d="M{cx - r * .6} {cy - r * .6} L{cx + r * .6} {cy + r * .6} M{cx + r * .6} {cy - r * .6} L{cx - r * .6} {cy + r * .6}" stroke="#111" stroke-width="4"/>')
        # name tag: placed by _layout_labels (below the token unless that collides with another tag)
        if e["id"] in labels:
            label, lx, ly, lw = labels[e["id"]]
            if abs(ly-cy) > r+22:
                above = ly < cy
                g.append(f'<path d="M{cx:.1f} {cy-r if above else cy+r:.1f}L{lx:.1f} '
                         f'{ly+LABEL_BOTTOM if above else ly-LABEL_TOP:.1f}" stroke="#d4c394" stroke-width=".6" opacity=".55"/>')
            g.append(f'<g class="nametag"><rect x="{lx - lw / 2 - 2:.1f}" y="{ly - LABEL_TOP:.1f}" width="{lw + 4:.1f}" height="{LABEL_TOP + LABEL_BOTTOM}" rx="3" '
                     f'fill="#1b2821" fill-opacity=".82" stroke="#cab780" stroke-opacity=".3" stroke-width=".5"/>'
                     f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" font-size="{LABEL_FONT}" font-weight="400" fill="#eee5d0">{esc(label)}</text></g>')
        g.append("</g>")
        out.append("".join(g))
    defs = '<filter id="petrified-face"><feColorMatrix type="saturate" values="0"/><feComponentTransfer><feFuncR type="linear" slope=".7" intercept=".16"/><feFuncG type="linear" slope=".7" intercept=".17"/><feFuncB type="linear" slope=".65" intercept=".16"/></feComponentTransfer></filter>'+"".join(assets.icon_symbol(icon, sym) for sym, icon in symbols.items())
    svg=f"<defs>{defs}</defs><g id='tokens'>{''.join(out)}</g>"
    return svg


def _place_labels(queue, marks, cell, W, H, clickable):
    """Put each place name beside its marker where it overlaps no other name or marker: the most important places
    choose first (capital, city, town...), trying above, below, right, left and the corners, then a smaller size.
    A name that fits nowhere is left to its marker's tooltip rather than drawn over another."""
    placed, out = list(marks), []

    def hits(b):
        return b[0] < 2 or b[1] < 2 or b[2] > W - 2 or b[3] > H - 2 or             any(b[0] < o[2] and o[0] < b[2] and b[1] < o[3] and o[1] < b[3] for o in placed)

    for q in sorted(queue, key=lambda q: q["rank"]):
        name, px, py, r = q["p"]["name"], q["px"], q["py"], q["r"]
        own = (px - r, py - r * 1.5, px + r, py + r)
        placed.remove(own) if own in placed else None   # a name may touch its own marker
        done = False
        for fs in (q["fs"], q["fs"] * .82):
            tw, th, gap = len(name) * fs * .5, fs * .95, 2
            spots = [("middle", px, py - r - gap - th * .2), ("middle", px, py + r + gap + th * .8),
                     ("start", px + r + gap, py + th * .35), ("end", px - r - gap, py + th * .35),
                     ("start", px + r * .7, py - r - gap), ("end", px - r * .7, py - r - gap),
                     ("start", px + r * .7, py + r + gap + th * .8), ("end", px - r * .7, py + r + gap + th * .8)]
            for anchor, tx, ty in spots:
                x0 = tx - tw / 2 if anchor == "middle" else (tx if anchor == "start" else tx - tw)
                box = (x0 - 1, ty - th * .8 - 1, x0 + tw + 1, ty + th * .25 + 1)
                if not hits(box):
                    placed.append(box)
                    out.append(clickable(q["p"], f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="{anchor}" font-size="{fs:.1f}" '
                               f'font-weight="{q["weight"]}" font-style="{q["style"]}" fill="#2b1d0e" stroke="#f6e7c1" '
                               f'stroke-width="{q["sw"]}" paint-order="stroke">{esc(name)}</text>'))
                    done = True
                    break
            if done:
                break
        placed.append(own)
    return out


def _simplify_route(points,tolerance):
    """Remove tiny decorative river elbows without moving its endpoints."""
    if len(points)<3:return points
    a,b=points[0],points[-1];dx,dy=b[0]-a[0],b[1]-a[1];length=dx*dx+dy*dy
    farthest,distance=0,0
    for i,p in enumerate(points[1:-1],1):
        t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)) if length else 0
        d=((p[0]-a[0]-t*dx)**2+(p[1]-a[1]-t*dy)**2)**.5
        if d>distance:farthest,distance=i,d
    if distance<=tolerance:return [a,b]
    return _simplify_route(points[:farthest+1],tolerance)[:-1]+_simplify_route(points[farthest:],tolerance)

def _smooth_route(points,cell):
    """Decorative route interpolation; positions and travel mechanics retain their exact cells."""
    pts=[((x+.5)*cell,(y+.5)*cell) for x,y in points]
    if not pts:return ''
    path=f'M{pts[0][0]:.1f} {pts[0][1]:.1f}'
    for i in range(len(pts)-1):
        a,b=pts[i],pts[i+1];before=pts[max(0,i-1)];after=pts[min(len(pts)-1,i+2)]
        controls=[]
        for k in (0,1):
            lo,hi=sorted((a[k],b[k]))
            controls.append((max(lo,min(hi,a[k]+(b[k]-before[k])/6)),max(lo,min(hi,b[k]-(after[k]-a[k])/6))))
        path+=f'C{controls[0][0]:.1f} {controls[1][0]:.1f} {controls[0][1]:.1f} {controls[1][1]:.1f} {b[0]:.1f} {b[1]:.1f}'
    return path

def render_region(m, mode="player", cell=8, party_pos=None):
    w, h = m["w"], m["h"]
    player = mode == "player"
    ink_palette = {"O": "#24474f", "C": "#4e7c80", "s": "#d4c6a1", "p": "#b5b88c", "g": "#99a275",
                   "f": "#75855f", "F": "#4e6a52", "h": "#b2a27a", "M": "#9a9684", "K": "#dedec8",
                   "w": "#7b896b", "d": "#ccb88b", "L": "#578b8b"}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w * cell} {h * cell}" width="{w * cell}" height="{h * cell}" font-family="Georgia,serif">',
             '<defs><filter id="paper"><feTurbulence baseFrequency=".04" numOctaves="3" seed="3"/><feColorMatrix values="0 0 0 0 .5  0 0 0 0 .45  0 0 0 0 .35  0 0 0 .18 0"/><feBlend in="SourceGraphic" mode="multiply"/></filter></defs>',
             '<g filter="url(#paper)">']
    parts.append(f'<rect width="{w*cell}" height="{h*cell}" fill="{ink_palette["p"]}"/>')
    for c in sorted(set(''.join(m['grid']))-{'p'}):
        d=illustration._material_path(m['grid'],c,cell,organic=True)
        if d:parts.append(f'<path class="regional-biome" d="{d}" fill="{ink_palette.get(c,BIOMES.get(c,("","#999"))[1])}" fill-rule="evenodd"/>')
    parts.append("</g>")
    rng = random.Random(m.get("seed") or 1)
    for y, row in enumerate(m["grid"]):  # glyphs for mountains and forests
        for x, c in enumerate(row):
            selected={'M':3,'K':3,'f':1,'F':0,'h':2,'w':13}.get(c)
            if selected is not None and painted.uri('regional-landmarks-v2',selected):
                if x%3==1 and y%3==1:
                    if rng.random()>.82:continue
                    size=cell*((4 if c in 'MK' else 3.6)+rng.uniform(-.6,.6))
                    px=(x+.5+rng.uniform(-.85,.85))*cell;py=(y+.5+rng.uniform(-.85,.85))*cell
                    parts.append(painted.sprite('regional-landmarks-v2',selected,px-size/2,py-size/2,size))
                continue
            if (x + y) % 2:
                continue
            px, py = x * cell + cell / 2, y * cell + cell / 2
            if c in "MK" and rng.random() < .55:
                parts.append(f'<path d="M{px - cell * .9} {py + cell * .5} L{px} {py - cell * .8} L{px + cell * .9} {py + cell * .5}" fill="{"#ecead7" if c == "K" else "#c0baa0"}" stroke="#605e4b" stroke-width=".65"/>'
                             f'<path d="M{px} {py - cell * .8} L{px + cell * .9} {py + cell * .5} L{px + cell * .12} {py + cell * .3} Z" fill="#5f6757" opacity=".65"/>'
                             f'<path d="M{px} {py-cell*.5} l{-cell*.32} {cell*.5} m{cell*.18} {-cell*.22} l{-cell*.2} {cell*.36}" fill="none" stroke="#6d6c55" stroke-width=".5"/>')
            elif c in "fF" and rng.random() < .5:
                parts.append(f'<path d="M{px-cell*.55} {py+cell*.45} l{cell*.38} {-cell*.8} l{cell*.27} {cell*.56} '
                             f'l{cell*.3} {-cell*1.05} l{cell*.55} {cell*1.29} Z" fill="{"#395543" if c == "F" else "#536d4d"}" stroke="#405440" stroke-width=".4"/>'
                             f'<path d="M{px+cell*.4} {py-cell*.46} v{cell*.72}" stroke="#a7b18a" stroke-width=".5" opacity=".6"/>')
            elif c == "h" and rng.random() < .35:
                parts.append(f'<path d="M{px - cell * .8} {py + cell * .3} Q{px} {py - cell * .6} {px + cell * .8} {py + cell * .3}" fill="none" stroke="#7a6d45" stroke-width="1.2"/>')
            elif c == "w" and rng.random() < .35:
                parts.append(f'<path d="M{px - 3} {py} h6 M{px - 2} {py - 2} v4" stroke="#3f5a38" stroke-width="1"/>')
            elif c in "OCL" and rng.random() < .16:
                parts.append(f'<path d="M{px-cell*.8} {py} q{cell*.8} {-cell*.32} {cell*1.6} 0" '
                             'fill="none" stroke="#c0d1bd" stroke-width=".5" opacity=".22"/>')
    for r in m.get("rivers", []):
        route = _smooth_route(_simplify_route(r,1.3),cell)
        parts.append(f'<path d="{route}" fill="none" stroke="#397a94" stroke-width="{cell * .45}" stroke-linejoin="round" stroke-linecap="round"/>')
    for r in m.get("roads", []):
        route = _smooth_route(r,cell)
        parts.append(f'<path d="{route}" fill="none" stroke="#6b4a2a" stroke-width="{cell * .3}" stroke-dasharray="{cell * .8} {cell * .4}" stroke-linejoin="round"/>')
    def clickable(p, inner):
        # a town or site with an id opens its journal entry on the table (what the party knows of it)
        if p.get("id"):
            return f'<g class="poi" data-poi="{esc(p["id"])}" style="cursor:pointer"><title>{esc(p["name"])}</title>{inner}</g>'
        return inner
    marks, queue = [], []   # marker boxes, and labels to place once every marker is known (so none overlap)
    for p in m.get("pois", []):
        if player and p.get("hidden"):
            continue
        px, py = (p["x"] + .5) * cell, (p["y"] + .5) * cell
        glyph = {"ruins": "⌂", "dungeon": "☗", "tower": "♜", "cave": "◓", "shrine": "✚", "camp": "⛺", "lair": "☠",
                 "battlefield": "⚔", "grove": "♣", "barrow": "∩", "mine": "⚒", "bridge": "≍", "inn": "⌂", "mill": "✣",
                 "stones": "⁂"}.get(p["kind"], "★")
        icon={'ruins':7,'dungeon':14,'tower':8,'cave':14,'shrine':10,'grove':1,'barrow':15,'mine':14,'bridge':11,'inn':5,'mill':9,'stones':15,'farm':12,'camp':12}.get(p['kind'])
        marker=painted.sprite('regional-landmarks-v2',icon,px-cell*1.3,py-cell*1.3,cell*2.6) if icon is not None else ''
        parts.append(clickable(p, marker or f'<text x="{px}" y="{py + 4}" text-anchor="middle" font-size="{cell * 1.6}" fill="#3a1a0a" stroke="#f6e7c1" stroke-width="2" paint-order="stroke">{glyph}</text>'))
        marks.append((px - cell * .8, py - cell * .8, px + cell * .8, py + cell * .8))
        queue.append({"p": p, "px": px, "py": py, "r": cell * .8, "fs": cell * 1.1, "rank": 7, "style": "italic", "weight": "normal", "sw": 2.5})
    sizes = {"hamlet": (.4, 1.0, "normal"), "village": (.55, 1.2, "normal"), "town": (.85, 1.5, "bold"),
             "city": (1.2, 1.9, "bold"), "capital": (1.5, 2.2, "bold"), "castle": (.8, 1.4, "bold"), "abbey": (.7, 1.3, "normal")}
    for s in m.get("settlements", []):
        if player and s.get("hidden"):
            continue
        px, py = (s["x"] + .5) * cell, (s["y"] + .5) * cell
        rr, fsz, weight = sizes.get(s["kind"], sizes["village"])
        r, fs = cell * rr, cell * fsz
        if s["kind"] == "castle":
            mark = (f'<rect x="{px - r}" y="{py - r}" width="{2 * r}" height="{2 * r}" fill="#d9c9a0" stroke="#2b1d0e" stroke-width="1.5"/>'
                    f'<path d="M{px - r} {py - r} v{-r * .5} h{r * .5} v{r * .5} h{r * .5} v{-r * .5} h{r * .5} v{r * .5} h{r * .5} v{-r * .5} h{r * .5} v{r * .5}" fill="#d9c9a0" stroke="#2b1d0e" stroke-width="1.2"/>')
        elif s["kind"] == "abbey":
            mark = (f'<circle cx="{px}" cy="{py}" r="{r}" fill="#f6e7c1" stroke="#2b1d0e" stroke-width="1.5"/>'
                    f'<path d="M{px} {py - r * .7} v{r * 1.4} M{px - r * .5} {py - r * .2} h{r}" stroke="#2b1d0e" stroke-width="1.4"/>')
        else:
            fill = "#b0302a" if s["kind"] in ("city", "capital") else "#f6e7c1"
            mark = f'<circle cx="{px}" cy="{py}" r="{r}" fill="{fill}" stroke="#2b1d0e" stroke-width="1.5"/>'
            if s["kind"] == "capital":
                mark += f'<circle cx="{px}" cy="{py}" r="{r * .45}" fill="#f6e7c1" stroke="#2b1d0e" stroke-width="1"/>'
        icon=6 if s['kind']=='castle' else 10 if s['kind']=='abbey' else 4 if s['kind'] in ('town','city','capital') else 5
        if painted.uri('regional-landmarks-v2',icon):
            r=max(r,cell*1.6)
            mark=painted.sprite('regional-landmarks-v2',icon,px-r,py-r,2*r)
        parts.append(clickable(s, mark))
        marks.append((px - r, py - r * 1.5, px + r, py + r))
        rank = {"capital": 0, "city": 1, "town": 2, "castle": 3, "abbey": 4, "village": 5, "hamlet": 6}.get(s["kind"], 5)
        queue.append({"p": s, "px": px, "py": py, "r": r, "fs": fs, "rank": rank, "style": "normal", "weight": weight, "sw": 3})
    for lb in m.get("labels", []):   # region names are fixed: place names steer round them
        if player and lb.get("hidden"):
            continue
        fs = cell * 1.7
        tw = len(lb["text"]) * (fs * .55 + 2)
        marks.append((lb["x"] * cell - tw / 2, lb["y"] * cell - fs * .8, lb["x"] * cell + tw / 2, lb["y"] * cell + fs * .25))
    parts += _place_labels(queue, marks, cell, w * cell, h * cell, clickable)
    for lb in m.get("labels", []):
        if player and lb.get("hidden"):
            continue
        parts.append(f'<text x="{lb["x"] * cell}" y="{lb["y"] * cell}" text-anchor="middle" font-size="{cell * 1.7}" font-style="italic" letter-spacing="2" fill="#1f1a14" fill-opacity=".75" stroke="#f6e7c1" stroke-width="2" stroke-opacity=".6" paint-order="stroke">{esc(lb["text"])}</text>')
    if party_pos:
        px, py = (party_pos[0] + .5) * cell, (party_pos[1] + .5) * cell
        parts.append(f'<g><circle class="region-party" cx="{px}" cy="{py}" r="{cell * 1.3}" fill="#2f8fdd" stroke="#fff" stroke-width="2"/><title>The party</title></g>')
    # compass & scale bar
    W, H = w * cell, h * cell
    mpc = m.get("miles_per_cell", 2)
    bar = 10 * cell
    parts.append(f'<g transform="translate({W - 60} 60)"><circle r="34" fill="#f6e7c1" fill-opacity=".8" stroke="#2b1d0e"/><path d="M0 -30 L7 0 L0 30 L-7 0 Z" fill="#2b1d0e"/><path d="M0 -30 L7 0 L-7 0 Z" fill="#b0302a"/><text y="-36" text-anchor="middle" font-size="14" fill="#2b1d0e">N</text></g>')
    parts.append(f'<g transform="translate(20 {H - 24})"><rect x="-6" y="-18" width="{bar + 12}" height="30" fill="#f6e7c1" fill-opacity=".8"/><rect width="{bar / 2}" height="6" fill="#2b1d0e"/><rect x="{bar / 2}" width="{bar / 2}" height="6" fill="#fff" stroke="#2b1d0e"/>'
                 f'<text y="-4" font-size="11" fill="#2b1d0e">0</text><text x="{bar}" y="-4" font-size="11" text-anchor="end" fill="#2b1d0e">{10 * mpc} miles</text></g>')
    parts.append(f'<text x="{W / 2}" y="34" text-anchor="middle" font-size="26" font-weight="bold" fill="#2b1d0e" stroke="#f6e7c1" stroke-width="4" paint-order="stroke">{esc(m["name"])}</text>')
    parts.append("</svg>")
    svg="".join(parts)
    return svg.replace('>', '>'+painted.definitions(svg),1)


def render_map(m, mode="player", entities=(), current=None, **kw):
    if m["kind"] == "region":
        return render_region(m, mode, party_pos=kw.get("party_pos"))
    return render_battle(m, mode, entities, current, **{k: v for k, v in kw.items() if k != "party_pos"})
