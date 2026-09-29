"""SVG rendering of maps with terrain art, fog of war, tokens, labels and turn highlighting.

mode='player' hides everything the characters haven't discovered: unrevealed cells are fogged,
hidden features/labels/creatures are omitted and secret doors look like plain wall.
mode='dm' shows everything (for Claude's own reference; never sent to the viewer).
"""
import random

from . import assets
from .assets import esc
from .maps import BIOMES

CELL = 32

FILL = {
    "#": "#3a342e", "B": "#5b4636", ".": "#cfc4ae", "=": "#b38b5d", ",": "#8fb35e", ":": "#b89b6a",
    "_": "#a8a39a", "t": "#6f9a45", "^": "#bdb29b", "w": "#8cc3e0", "~": "#3f84bf", "m": "#7a6a4a",
    "s": "#e2d2a0", "T": "#8fb35e", "P": "#cfc4ae", "o": "#8fb35e", "h": "#b38b5d", "c": "#b38b5d",
    "f": "#b38b5d", "D": "#cfc4ae", "d": "#cfc4ae", "S": "#3a342e", "<": "#cfc4ae", ">": "#cfc4ae",
    "x": "#0c0a09", "b": "#8c6a43", "r": "#a8a39a", " ": "#000",
}
BASE_UNDER = {"T": ",", "o": None, "P": ".", "h": "=", "c": "=", "f": "=", "D": None, "d": None, "<": ".", ">": ".", "r": "_",
              "a": "k", "g": "=", "v": "=", "l": "=", "u": "q", "n": "="}

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
               "furniture": "#5a3a22", "furniture_line": "#d8b36a", "counter": "#4a2e1a", "backdrop": None},
}


def _defs(theme="stone"):
    t = THEMES.get(theme, THEMES["stone"])
    return f"""<defs>
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
    T = THEMES.get(theme, THEMES["stone"])
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w * cell} {h * cell}" width="{w * cell}" height="{h * cell}" '
             f'font-family="Georgia,serif" data-cell="{cell}">', _defs(theme)]
    if T.get("backdrop"):
        parts.append(f'<rect width="{w * cell}" height="{h * cell}" fill="{T["backdrop"]}"/>')
    # base terrain as merged runs
    for y, row in enumerate(grid):
        base_row = [BASE_UNDER.get(c) or ({"D": ".", "d": ".", "o": ","}.get(c, c)) for c in row]
        if m["kind"] in ("dungeon", "cave", "battle", "interior") :
            base_row = [({"o": "."}.get(c, c) if row[i] == "o" else c) for i, c in enumerate(base_row)]
        for x0, n, c in _runs(base_row):
            fill = {"#": "url(#hatch)", "S": "url(#hatch)", "=": "url(#planks)", "_": "url(#cobble)", ".": "url(#flag)",
                    "k": "url(#carpet)", "q": "url(#marble)", "w": T["water"], "~": T["deep"]}.get(c, FILL.get(c, "#888"))
            parts.append(f'<rect x="{x0 * cell}" y="{y * cell}" width="{n * cell}" height="{cell}" fill="{fill}"/>')
            if c == "~":
                parts.append(f'<rect x="{x0 * cell}" y="{y * cell}" width="{n * cell}" height="{cell}" fill="url(#waves)"/>')
    # walls edge shading
    for y in range(h):
        for x in range(w):
            c = grid[y][x]
            cx, cy = x * cell, y * cell
            s = cell
            if c in "#B" and any(0 <= y + dy < h and 0 <= x + dx < w and grid[y + dy][x + dx] not in "#B "
                                 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                parts.append(f'<rect x="{cx}" y="{cy}" width="{s}" height="{s}" fill="{T["wall_edge"] if c == "#" else "#6b5240"}" stroke="{T["trim"] or "#211d19"}" stroke-width="{1.5 if T["trim"] else 1}"/>')
            elif c == "T":
                r = s * (0.42 + rng.random() * 0.12)
                parts.append(f'<circle cx="{cx + s / 2 + 2}" cy="{cy + s / 2 + 3}" r="{r}" fill="#000" fill-opacity=".18"/>'
                             f'<circle cx="{cx + s / 2}" cy="{cy + s / 2}" r="{r}" fill="url(#canopy)" stroke="#23451a" stroke-width="1"/>')
            elif c == "t":
                for _ in range(3):
                    px, py = cx + rng.random() * s, cy + rng.random() * s
                    parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{s * 0.16:.1f}" fill="#4d7a30"/>')
            elif c == "^":
                for _ in range(4):
                    px, py = cx + 4 + rng.random() * (s - 8), cy + 4 + rng.random() * (s - 8)
                    parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{2 + rng.random() * 3:.1f}" fill="#8e8576"/>')
            elif c == "o":
                parts.append(f'<ellipse cx="{cx + s / 2}" cy="{cy + s / 2}" rx="{s * .42}" ry="{s * .36}" fill="url(#rock)" stroke="#4a443c"/>')
            elif c == "P":
                parts.append(f'<circle cx="{cx + s / 2}" cy="{cy + s / 2}" r="{s * .38}" fill="#8f877a" stroke="#4a443c" stroke-width="2"/>')
            elif c == "h":
                parts.append(f'<rect x="{cx + 4}" y="{cy + 4}" width="{s - 8}" height="{s - 8}" rx="3" fill="{T["furniture"]}" stroke="{T["furniture_line"]}"/>')
            elif c == "c":
                parts.append(f'<rect x="{cx + 2}" y="{cy + 6}" width="{s - 4}" height="{s - 12}" fill="{T["counter"]}" stroke="{T["furniture_line"]}"/>')
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
                parts.append(f'<rect x="{cx + 3}" y="{cy + 3}" width="{s - 6}" height="{s - 6}" fill="#555"/><circle cx="{cx + s / 2}" cy="{cy + s / 2}" r="{s * .25}" fill="#f08a24" filter="url(#glow)"/>')
            elif c in "Dd":
                horiz = (x > 0 and grid[y][x - 1] in "#B") or (x < w - 1 and grid[y][x + 1] in "#B")
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
                    parts.append(f'<line x1="{cx + i * 8 + 4}" y1="{cy}" x2="{cx + i * 8 + 4}" y2="{cy + s}" stroke="#5a3e22" stroke-width="1"/>')
    if show_grid:
        gl = [f'<path d="' + "".join(f"M{x * cell} 0V{h * cell}" for x in range(w + 1)) +
              "".join(f"M0 {y * cell}H{w * cell}" for y in range(h + 1)) + '" stroke="#000" stroke-opacity=".13" stroke-width="1"/>']
        parts += gl
    # rooms/building labels
    revealed = m.get("revealed") or ["1" * w] * h
    for r in m.get("rooms", []):
        cx, cy = r["x"] + r["w"] // 2, r["y"] + r["h"] // 2
        if player and m.get("fog") and revealed[cy][cx] != "1":
            continue
        if m["kind"] == "town":
            parts.append(f'<text x="{(r["x"] + r["w"] / 2) * cell}" y="{(r["y"] + r["h"] / 2) * cell + 5}" text-anchor="middle" font-size="{cell * .42}" fill="#fff" stroke="#2b1d0e" stroke-width="3" paint-order="stroke">{esc(r["label"])}</text>')
        else:
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
    # highlight squares (movement range / area of effect)
    if highlight:
        for (x, y) in highlight:
            parts.append(f'<rect x="{x * cell}" y="{y * cell}" width="{cell}" height="{cell}" fill="#3ec7ff" fill-opacity=".25"/>')
    # items lying on the floor (visible wherever the players can see)
    for f in m.get("floor", []):
        fx, fy = f["x"], f["y"]
        if player and m.get("fog") and revealed and not (0 <= fy < len(revealed) and revealed[fy][fx] == "1"):
            continue
        px, py = fx * cell + cell - 9, fy * cell + cell - 9
        if live:  # the viewer: a small framed picture of the item
            from . import itemart
            s0 = cell * .56
            parts.append(f'<g class="flooritem" data-floor="{esc(f["id"])}" style="cursor:pointer"><title>{esc(f["item"]["name"])} (on the floor)</title>'
                         f'<rect x="{fx * cell + cell - s0 - 2:.1f}" y="{fy * cell + cell - s0 - 2:.1f}" width="{s0:.1f}" height="{s0:.1f}" rx="4" fill="#1a130c" fill-opacity=".85" stroke="#d8b36a" stroke-width="1.5"/>'
                         f'<image href="/api/art/floor/{esc(m["id"])}/{esc(f["id"])}.svg?v={itemart.item_art_version(f["item"])}" x="{fx * cell + cell - s0 - 1:.1f}" y="{fy * cell + cell - s0 - 1:.1f}" '
                         f'width="{s0 - 2:.1f}" height="{s0 - 2:.1f}"/></g>')
            continue
        parts.append(f'<g class="flooritem" data-floor="{esc(f["id"])}" style="cursor:pointer"><title>{esc(f["item"]["name"])} (on the floor)</title>'
                     f'<rect x="{px - 7}" y="{py - 7}" width="14" height="14" rx="2" transform="rotate(45 {px} {py})" fill="#d8b36a" stroke="#2b1d0e" stroke-width="2"/>'
                     f'<circle cx="{px}" cy="{py}" r="2.5" fill="#2b1d0e"/></g>')
    # points of interest the characters have perceived: a small blue marker in the tile's top-left corner
    for p in m.get("pois", []):
        pxx, pyy = p["x"], p["y"]
        if player and m.get("fog") and revealed and not (0 <= pyy < len(revealed) and revealed[pyy][pxx] == "1"):
            continue
        cx, cy = pxx * cell + 9, pyy * cell + 9
        parts.append(f'<g class="poi" data-poi="{esc(p["id"])}" style="cursor:pointer"><title>{esc(p["name"])}</title>'
                     f'<circle cx="{cx}" cy="{cy}" r="7.5" fill="#6fb0ff" stroke="#10243d" stroke-width="2"/>'
                     f'<text x="{cx}" y="{cy + 3.6}" text-anchor="middle" font-family="Georgia,serif" font-weight="bold" font-size="10.5" fill="#10243d">i</text></g>')
    # tokens
    parts.append(tokens_svg(m, entities, current, cell, player))
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
        parts.append(f'<g id="fog" fill="#0b0a0f" shape-rendering="crispEdges">{"".join(fog)}</g>')
        if xs:
            pad = 3
            fx0, fy0 = max(0, min(xs) - pad), max(0, min(ys) - pad)
            fx1, fy1 = min(w, max(xs) + pad), min(h, max(ys) + 1 + pad)
            focus = f"{fx0 * cell},{fy0 * cell},{(fx1 - fx0) * cell},{(fy1 - fy0) * cell}"
    parts.append("</svg>")
    if focus:
        parts[0] = parts[0].replace("<svg ", f'<svg data-focus="{focus}" ', 1)
    return "".join(parts)


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


def short_label(e):
    """'Kira Vale' -> 'Kira'; 'Goblin Warrior B' -> 'Goblin B'."""
    if e.get("short"):
        return e["short"]
    words = e["name"].split()
    if len(words) > 1 and len(words[-1]) == 1:
        return f"{words[0][:9]} {words[-1]}"
    return words[0][:11] if words else e["id"]


def tokens_svg(m, entities, current, cell, player):
    out, symbols = [], {}
    revealed = m.get("revealed") or []
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
            # corpse / wreck marker: small, faded, no label, still clickable (search it, loot it)
            rr = r * .45
            ox, oy = cx - r * .45, cy + r * .45
            out.append(f'<g class="token dead" data-id="{esc(e["id"])}" data-stack="{esc(stack)}" opacity=".6"><title>{esc(e["name"])} (defeated)</title>'
                       f'<circle cx="{ox}" cy="{oy}" r="{rr}" fill="#3a3030" stroke="#111" stroke-width="1.5"/>'
                       f'<path d="M{ox - rr * .6} {oy - rr * .6} L{ox + rr * .6} {oy + rr * .6} M{ox + rr * .6} {oy - rr * .6} L{ox - rr * .6} {oy + rr * .6}" stroke="#d9443b" stroke-width="2"/></g>')
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
            g.append(f'<circle cx="{cx}" cy="{cy}" r="{r + 3}" fill="none" stroke="#ffd34d" stroke-width="4" filter="url(#glow)"><animate attributeName="stroke-opacity" values="1;.35;1" dur="1.6s" repeatCount="indefinite"/></circle>')
        g.append(f'<circle cx="{cx + 2}" cy="{cy + 3}" r="{r - 1}" fill="#000" fill-opacity=".3"/>')
        g.append(f'<circle cx="{cx}" cy="{cy}" r="{r - 1}" fill="{color}"/>')
        g.append(f'<circle cx="{cx}" cy="{cy}" r="{r - 4}" fill="hsl({hue},38%,26%)"/>')
        if e.get("portrait_href"):
            g.append(f'<clipPath id="cp-{esc(e["id"])}"><circle cx="{cx}" cy="{cy}" r="{r - 4}"/></clipPath>'
                     f'<image href="{esc(e["portrait_href"])}" x="{cx - r + 4}" y="{cy - r + 4}" width="{2 * r - 8}" height="{2 * r - 8}" clip-path="url(#cp-{esc(e["id"])})" preserveAspectRatio="xMidYMid slice"/>')
        else:
            s = (2 * r - 12)
            g.append(f'<use href="#{sym}" x="{cx - s / 2}" y="{cy - s / 2}" width="{s}" height="{s}" fill="#f4efe6"/>')
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
        for i, cname in enumerate(conds):
            ci = assets.CONDITION_ICONS.get(cname)
            if ci:
                symbols[f"i-{ci}"] = ci
                g.append(f'<circle cx="{cx + r - 6 - i * 13}" cy="{cy - r + 6}" r="7" fill="#fff" stroke="#222"/>'
                         f'<use href="#i-{ci}" x="{cx + r - 12 - i * 13}" y="{cy - r}" width="12" height="12" fill="#222"/>')
        if dead:
            g.append(f'<path d="M{cx - r * .6} {cy - r * .6} L{cx + r * .6} {cy + r * .6} M{cx + r * .6} {cy - r * .6} L{cx - r * .6} {cy + r * .6}" stroke="#111" stroke-width="4"/>')
        # name tag: trimmed to about one square; neighbours on the same row alternate above/below so tags don't collide
        label = short_label(e)
        max_chars = max(5, int(cell * 1.35 / 5))
        if len(label) > max_chars:
            label = label[:max_chars - 1] + "…"
        crowded = any(living_at.get((x + dx, y)) for dx in (-1, 1))
        ly = cy - r - 3 if (crowded and x % 2) else cy + r + 9
        g.append(f'<text x="{cx}" y="{ly}" text-anchor="middle" font-size="9" fill="#fff" stroke="#000" stroke-width="2.5" paint-order="stroke">{esc(label)}</text>')
        g.append("</g>")
        out.append("".join(g))
    defs = "".join(assets.icon_symbol(icon, sym) for sym, icon in symbols.items())
    return f"<defs>{defs}</defs><g id='tokens'>{''.join(out)}</g>"


def render_region(m, mode="player", cell=8, party_pos=None):
    w, h = m["w"], m["h"]
    player = mode == "player"
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w * cell} {h * cell}" width="{w * cell}" height="{h * cell}" font-family="Georgia,serif">',
             '<defs><filter id="paper"><feTurbulence baseFrequency=".04" numOctaves="3" seed="3"/><feColorMatrix values="0 0 0 0 .5  0 0 0 0 .45  0 0 0 0 .35  0 0 0 .18 0"/><feBlend in="SourceGraphic" mode="multiply"/></filter></defs>',
             '<g filter="url(#paper)">']
    for y, row in enumerate(m["grid"]):
        for x0, n, c in _runs(row):
            parts.append(f'<rect x="{x0 * cell}" y="{y * cell}" width="{n * cell}" height="{cell + .5}" fill="{BIOMES.get(c, ("", "#999"))[1]}"/>')
    parts.append("</g>")
    rng = random.Random(m.get("seed") or 1)
    for y, row in enumerate(m["grid"]):  # glyphs for mountains and forests
        for x, c in enumerate(row):
            if (x + y) % 2:
                continue
            px, py = x * cell + cell / 2, y * cell + cell / 2
            if c in "MK" and rng.random() < .55:
                parts.append(f'<path d="M{px - cell * .9} {py + cell * .5} L{px} {py - cell * .8} L{px + cell * .9} {py + cell * .5}" fill="{"#f4f6f8" if c == "K" else "#6f665d"}" stroke="#3f3a34" stroke-width=".8"/>')
            elif c in "fF" and rng.random() < .5:
                parts.append(f'<circle cx="{px}" cy="{py}" r="{cell * .55}" fill="{"#26491f" if c == "F" else "#3c6a2e"}"/>')
            elif c == "h" and rng.random() < .35:
                parts.append(f'<path d="M{px - cell * .8} {py + cell * .3} Q{px} {py - cell * .6} {px + cell * .8} {py + cell * .3}" fill="none" stroke="#7a6d45" stroke-width="1.2"/>')
            elif c == "w" and rng.random() < .35:
                parts.append(f'<path d="M{px - 3} {py} h6 M{px - 2} {py - 2} v4" stroke="#3f5a38" stroke-width="1"/>')
    for r in m.get("rivers", []):
        pts = " ".join(f"{(x + .5) * cell},{(y + .5) * cell}" for x, y in r)
        parts.append(f'<polyline points="{pts}" fill="none" stroke="#3b7cb0" stroke-width="{cell * .45}" stroke-linejoin="round" stroke-linecap="round"/>')
    for r in m.get("roads", []):
        pts = " ".join(f"{(x + .5) * cell},{(y + .5) * cell}" for x, y in r)
        parts.append(f'<polyline points="{pts}" fill="none" stroke="#6b4a2a" stroke-width="{cell * .3}" stroke-dasharray="{cell * .8} {cell * .4}" stroke-linejoin="round"/>')
    for p in m.get("pois", []):
        if player and p.get("hidden"):
            continue
        px, py = (p["x"] + .5) * cell, (p["y"] + .5) * cell
        glyph = {"ruins": "⌂", "dungeon": "☗", "tower": "♜", "cave": "◓", "shrine": "✚", "camp": "⛺"}.get(p["kind"], "★")
        parts.append(f'<text x="{px}" y="{py + 4}" text-anchor="middle" font-size="{cell * 1.6}" fill="#3a1a0a" stroke="#f6e7c1" stroke-width="2" paint-order="stroke">{glyph}</text>'
                     f'<text x="{px}" y="{py + cell * 2.4}" text-anchor="middle" font-size="{cell * 1.1}" font-style="italic" fill="#2b1d0e" stroke="#f6e7c1" stroke-width="2.5" paint-order="stroke">{esc(p["name"])}</text>')
    for s in m.get("settlements", []):
        px, py = (s["x"] + .5) * cell, (s["y"] + .5) * cell
        r = {"city": cell * 1.2, "town": cell * .85, "village": cell * .55}[s["kind"]]
        parts.append(f'<circle cx="{px}" cy="{py}" r="{r}" fill="{"#b0302a" if s["kind"] == "city" else "#f6e7c1"}" stroke="#2b1d0e" stroke-width="1.5"/>')
        fs = {"city": 1.9, "town": 1.5, "village": 1.2}[s["kind"]] * cell
        parts.append(f'<text x="{px}" y="{py - r - 3}" text-anchor="middle" font-size="{fs}" font-weight="{"bold" if s["kind"] != "village" else "normal"}" fill="#2b1d0e" stroke="#f6e7c1" stroke-width="3" paint-order="stroke">{esc(s["name"])}</text>')
    for lb in m.get("labels", []):
        if player and lb.get("hidden"):
            continue
        parts.append(f'<text x="{lb["x"] * cell}" y="{lb["y"] * cell}" text-anchor="middle" font-size="{cell * 1.7}" font-style="italic" letter-spacing="2" fill="#1f1a14" fill-opacity=".75" stroke="#f6e7c1" stroke-width="2" stroke-opacity=".6" paint-order="stroke">{esc(lb["text"])}</text>')
    if party_pos:
        px, py = (party_pos[0] + .5) * cell, (party_pos[1] + .5) * cell
        parts.append(f'<g><circle cx="{px}" cy="{py}" r="{cell * 1.3}" fill="#2f8fdd" stroke="#fff" stroke-width="2"><animate attributeName="r" values="{cell};{cell * 1.6};{cell}" dur="2s" repeatCount="indefinite"/></circle><title>The party</title></g>')
    # compass & scale bar
    W, H = w * cell, h * cell
    mpc = m.get("miles_per_cell", 2)
    bar = 10 * cell
    parts.append(f'<g transform="translate({W - 60} 60)"><circle r="34" fill="#f6e7c1" fill-opacity=".8" stroke="#2b1d0e"/><path d="M0 -30 L7 0 L0 30 L-7 0 Z" fill="#2b1d0e"/><path d="M0 -30 L7 0 L-7 0 Z" fill="#b0302a"/><text y="-36" text-anchor="middle" font-size="14" fill="#2b1d0e">N</text></g>')
    parts.append(f'<g transform="translate(20 {H - 24})"><rect x="-6" y="-18" width="{bar + 12}" height="30" fill="#f6e7c1" fill-opacity=".8"/><rect width="{bar / 2}" height="6" fill="#2b1d0e"/><rect x="{bar / 2}" width="{bar / 2}" height="6" fill="#fff" stroke="#2b1d0e"/>'
                 f'<text y="-4" font-size="11" fill="#2b1d0e">0</text><text x="{bar}" y="-4" font-size="11" text-anchor="end" fill="#2b1d0e">{10 * mpc} miles</text></g>')
    parts.append(f'<text x="{W / 2}" y="34" text-anchor="middle" font-size="26" font-weight="bold" fill="#2b1d0e" stroke="#f6e7c1" stroke-width="4" paint-order="stroke">{esc(m["name"])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def render_map(m, mode="player", entities=(), current=None, **kw):
    if m["kind"] == "region":
        return render_region(m, mode, party_pos=kw.get("party_pos"))
    return render_battle(m, mode, entities, current, **{k: v for k, v in kw.items() if k != "party_pos"})
