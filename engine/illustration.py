"""Fast, deterministic decorative SVG. Never changes terrain or game state.

Reusable symbols keep large forests inexpensive; no per-tile blur or network assets.
The artwork uses its own seeded RNG so adding detail cannot affect rules or placement.
"""
import math
import random
import base64
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=4)
def _atlas(name):
    """Bundled once, embedded once per SVG; no runtime image-generation service."""
    path = Path(__file__).resolve().parent.parent / 'assets' / 'generated' / (name + '.webp')
    return 'data:image/webp;base64,' + base64.b64encode(path.read_bytes()).decode() if path.is_file() else ''


def _sprite_defs(name, prefix):
    uri = _atlas(name)
    if not uri:
        return ''
    return (f'<image id="{prefix}-atlas" width="768" height="768" href="{uri}"/>' +
            ''.join(f'<symbol id="{prefix}-{i}" viewBox="{(i%2)*384} {(i//2)*384} 384 384" overflow="hidden" preserveAspectRatio="none">'
                    f'<use href="#{prefix}-atlas"/></symbol>' for i in range(4)))


def _contour(rng, radius, n=16):
    points = []
    for i in range(n):
        a = i * math.tau / n
        r = radius * rng.uniform(.81, 1.12)
        points.append((math.cos(a) * r, math.sin(a) * r))
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points) + " Z"


@lru_cache(maxsize=1)
def terrain_defs():
    rng = random.Random(731)
    out = ['<defs><radialGradient id="leaf-light" cx="28%" cy="22%" r="85%">'
           '<stop stop-color="#a0ae68"/><stop offset=".38" stop-color="#637c48"/>'
           '<stop offset="1" stop-color="#263e30"/></radialGradient>'
           '<linearGradient id="stone-light" x2=".7" y2="1"><stop stop-color="#b2b2a1"/>'
           '<stop offset="1" stop-color="#535c58"/></linearGradient>'
           '<radialGradient id="map-light" cx="32%" cy="24%" r="85%"><stop stop-color="#efe0ae" stop-opacity=".12"/>'
           '<stop offset=".5" stop-color="#15342a" stop-opacity="0"/><stop offset="1" stop-color="#0c2922" stop-opacity=".27"/></radialGradient>'
           '<pattern id="fallback-water" width="96" height="64" patternUnits="userSpaceOnUse">'
           '<rect width="96" height="64" fill="#477f83"/><path d="M3 12 Q19 7 34 12 M49 36 Q67 30 87 35 M13 53 Q29 48 49 52" '
           'stroke="#b4d3bc" stroke-width=".8" opacity=".4" fill="none"/>'
           '<path d="M40 4 Q57 8 76 4 M4 32 Q14 28 23 31 M62 56 Q75 59 90 55" stroke="#224f59" stroke-width="2" opacity=".4" fill="none"/></pattern>'
           '<pattern id="fallback-shallows" width="96" height="64" patternUnits="userSpaceOnUse">'
           '<rect width="96" height="64" fill="#699e96"/><path d="M4 19 Q16 15 29 19 M45 40 Q57 35 71 39 M6 57 Q20 53 35 56" '
           'stroke="#d2d9b5" opacity=".4" stroke-width=".8" fill="none"/></pattern>']
    for name,i in (('water',0), ('shallows',1), ('rock',2)):
        if _atlas('water-materials'):
            out.append(f'<pattern id="art-{name}" width="128" height="128" patternUnits="userSpaceOnUse">'
                       f'<use href="#painted-water-{i}" width="128" height="128"/></pattern>')
        elif name != 'rock':
            out.append(f'<pattern id="art-{name}" href="#fallback-{name}"/>')
    # Ground flecks and grasses repeat over a large swatch, rather than over each square.
    for name, base, ink in (("meadow", "#727b50", "#c6c99a"), ("brush", "#526441", "#9fae72"),
                            ("earth", "#99836a", "#d4be98"), ("sand", "#c5b487", "#f2dfb1"),
                            ("mud", "#685d46", "#9f906d")):
        out.append(f'<pattern id="art-{name}" width="192" height="160" patternUnits="userSpaceOnUse">'
                   f'<rect width="192" height="160" fill="{base}"/>')
        for i in range(60):
            x, y = rng.uniform(0, 192), rng.uniform(0, 160)
            if name in ("meadow", "brush"):
                out.append(f'<path d="M{x:.1f},{y:.1f} q-2,-4 -1,-7 m1,7 q2,-3 4,-4" '
                           f'fill="none" stroke="{ink}" stroke-width=".7" opacity="{rng.uniform(.12,.35):.2f}"/>')
            else:
                out.append(f'<path d="M{x:.1f},{y:.1f} l{rng.uniform(1,4):.1f},-1" '
                           f'stroke="{ink}" stroke-width=".8" opacity=".3"/>')
        for i in range(9):
            x, y = rng.uniform(0, 192), rng.uniform(0, 160)
            out.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rng.uniform(6,22):.1f}" '
                       f'ry="{rng.uniform(3,10):.1f}" fill="#28342b" opacity=".055"/>')
        if _atlas('terrain-materials') and name in ('meadow', 'earth'):
            i = 0 if name == 'meadow' else 1
            out.append(f'<use href="#painted-material-{i}" width="192" height="160" preserveAspectRatio="none"/>')
        out.append('</pattern>')
    for variant in range(8):
        r = random.Random(109 + variant)
        outline = _contour(r, 15, 20)
        out.append(f'<g id="art-tree-{variant}"><path d="{outline}" transform="translate(5 7)" '
                   'fill="#14261d" opacity=".34"/><path d="M-2 8 L-3 19 L2 17 L3 7" fill="#67513b"/>'
                   f'<path d="{outline}" fill="#253e2f" stroke="#1b3027" stroke-width=".7"/>')
        # Offset clusters form an irregular crown, with individually lit leaf edges.
        for i in range(6):
            a = i * math.tau / 6 + r.uniform(-.2, .2)
            x, y = math.cos(a) * 7, math.sin(a) * 7
            d = _contour(r, r.uniform(7, 10), 12)
            out.append(f'<g transform="translate({x:.1f} {y:.1f})"><path d="{d}" fill="url(#leaf-light)" '
                       f'stroke="#253e2f" stroke-width=".45"/>'
                       '<path d="M-5 -3 Q-3 -7 1 -6 M-3 -1 L-1 -3 M2 -5 L4 -3" '
                       'stroke="#d3d2a0" stroke-width=".65" fill="none" opacity=".35"/></g>')
        out.append('<path d="M0 6 Q-3 0 1 -5 M-1 1 L-6 -3 M0 3 L5 0" fill="none" '
                   'stroke="#243b2d" stroke-width=".7" opacity=".5"/></g>')
    out.append(_sprite_defs('forest-canopies', 'painted-tree'))
    out.append(_sprite_defs('terrain-materials', 'painted-material'))
    out.append(_sprite_defs('water-materials', 'painted-water'))
    out.append('<linearGradient id="painted-flame" x2="0" y2="1"><stop stop-color="#e48b3f" stop-opacity=".3"/>'
               '<stop offset=".5" stop-color="#de7830"/><stop offset="1" stop-color="#ffe8a2"/></linearGradient>')
    for name, i in (('stone',2), ('wood',3)):
        out.append(f'<pattern id="art-{name}" width="128" height="128" patternUnits="userSpaceOnUse">'
                   f'<use href="#painted-material-{i}" width="128" height="128"/></pattern>')
    out.append('</defs>')
    return ''.join(out)


def tree(x, y, cell, seed):
    r = random.Random(seed)
    if _atlas('forest-canopies'):
        angle, size = r.randrange(-12, 13), r.uniform(46, 60) * cell / 32
        return (f'<use href="#painted-tree-{r.randrange(4)}" x="{-size/2:.1f}" y="{-size/2:.1f}" '
                f'width="{size:.1f}" height="{size:.1f}" '
                f'transform="translate({x+cell/2:.1f} {y+cell/2:.1f}) rotate({angle})"/>')
    angle, scale = r.randrange(-30, 31), r.uniform(1.03, 1.36) * cell / 32
    return (f'<use href="#art-tree-{r.randrange(8)}" x="0" y="0" '
            f'transform="translate({x + cell / 2:.1f} {y + cell / 2:.1f}) rotate({angle}) scale({scale:.3f})"/>')


def rock(x, y, cell, seed):
    r = random.Random(seed)
    d = _contour(r, cell * .36, 7)
    return (f'<g transform="translate({x + cell / 2:.1f} {y + cell / 2:.1f})">'
            f'<path d="{d}" transform="translate(3 4)" fill="#16221e" opacity=".3"/>'
            f'<path d="{d}" fill="url(#stone-light)" stroke="#424c46" stroke-width=".8"/>'
            + (f'<path d="{d}" fill="url(#art-rock)" opacity=".65"/>' if _atlas('water-materials') else '') +
            f'<path d="M{-cell*.2:.1f} {-cell*.13:.1f} L0 {-cell*.26:.1f} L{cell*.2:.1f} {-cell*.07:.1f} '
            f'L0 {cell*.03:.1f} Z" fill="#d0d1bd" opacity=".4"/>'
            f'<path d="M0 {cell*.03:.1f} L{cell*.06:.1f} {cell*.26:.1f}" stroke="#404b45" opacity=".5"/></g>')


def fire(cx, cy, size, seed):
    r = random.Random(str(seed))
    out = [f'<g class="painted-fire" transform="translate({cx:.1f} {cy:.1f}) scale({size/32:.3f})">'
           '<ellipse cx="1" cy="9" rx="13" ry="8" fill="#211d19" opacity=".55"/>'
           '<circle class="firelight" r="29" fill="url(#lampglow)" opacity=".45"/>'
           '<path d="M-10 8L9 14 M-9 14L10 8" stroke="#4d3a28" stroke-width="4" stroke-linecap="round"/>']
    for i in range(7):
        x,h = r.uniform(-9,9),r.uniform(12,26)
        out.append(f'<path d="M{x-4:.1f} 9 Q{x-8:.1f} 0 {x:.1f} {-h:.1f} '
                   f'Q{x-2:.1f} {-h*.35:.1f} {x+5:.1f} -2 Q{x+8:.1f} 7 {x:.1f} 12 Z" '
                   f'fill="url(#painted-flame)" opacity="{r.uniform(.55,.85):.2f}"/>')
    out.append('<path d="M-4 9Q-7 4 0-9Q-1 2 5 8Q3 14-4 9" fill="#ffe5a2" opacity=".9"/>'
               '<circle cx="-3" cy="-17" r=".7" fill="#e9b75e"/><circle cx="8" cy="-13" r=".8" fill="#e9b75e"/></g>')
    return ''.join(out)


def terrain_edges(grid, cell):
    """Ground material transitions and wall shadows, underneath objects and fog."""
    h, w = len(grid), len(grid[0])
    paths = {"road": [], "shore": [], "wall": []}
    for y, row in enumerate(grid):
        for x, c in enumerate(row):
            kind = "road" if c == ":" else "shore" if c in "w~" else "wall" if c in "#B" else None
            if not kind:
                continue
            family = ":" if kind == "road" else "w~" if kind == "shore" else "#B "
            for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < w and 0 <= ny < h) or grid[ny][nx] in family:
                    continue
                xx, yy = (x + (dx > 0)) * cell, (y + (dy > 0)) * cell
                if kind == 'wall':
                    paths[kind].append(f'M{xx},{yy} l{0 if dx else cell},{cell if dx else 0}')
                else:
                    r = random.Random(f'edge:{x}:{y}:{dx}:{dy}')
                    pts = [(xx, yy)]
                    for i in range(1, 5):
                        along, offset = cell * i / 5, r.uniform(-cell*.055, cell*.055)
                        pts.append((xx + (offset if dx else along), yy + (along if dx else offset)))
                    pts.append((xx + (0 if dx else cell), yy + (cell if dx else 0)))
                    paths[kind].append('M' + ' L'.join(f'{a:.1f},{b:.1f}' for a,b in pts))
    out = []
    for kind, pieces in paths.items():
        if not pieces:
            continue
        d = ''.join(pieces)
        if kind == "wall":
            out.append(f'<path d="{d}" transform="translate(3 5)" stroke="#111a18" stroke-width="9" '
                       'opacity=".22" fill="none"/><path d="' + d + '" stroke="#e0d6b5" stroke-width="1" opacity=".35" fill="none"/>')
        else:
            color = "#4f5739" if kind == "road" else "#304d4b"
            out.append(f'<path d="{d}" stroke="{color}" stroke-width="5" stroke-linejoin="round" opacity=".32" fill="none"/>'
                       f'<path d="{d}" stroke="#d1c49c" stroke-width="1.5" opacity=".26" fill="none"/>')
    return ''.join(out)


def _material_path(grid, chars, cell, organic=False):
    """Trace the union of a material's cells, including holes, with rounded corners.

    It is presentation only; movement/cover still use the original exact grid.
    Choosing the clockwise continuation keeps diagonally touching islands separate.
    """
    h, w = len(grid), len(grid[0])
    edges = set()
    for y, row in enumerate(grid):
        for x, c in enumerate(row):
            if c not in chars:
                continue
            for dx, dy, a, b in ((0,-1,(x,y),(x+1,y)), (1,0,(x+1,y),(x+1,y+1)),
                                 (0,1,(x+1,y+1),(x,y+1)), (-1,0,(x,y+1),(x,y))):
                nx, ny = x+dx, y+dy
                if not (0 <= nx < w and 0 <= ny < h) or grid[ny][nx] not in chars:
                    edges.add((a,b))
    outgoing = {}
    for a,b in edges:
        outgoing.setdefault(a, []).append(b)
    out = []
    while edges:
        first = min(edges)
        a,b = first
        loop = [a]
        while (a,b) in edges:
            edges.remove((a,b))
            if b == loop[0]:
                break
            loop.append(b)
            candidates = [c for c in outgoing.get(b, []) if (b,c) in edges]
            if not candidates:
                break
            dx, dy = b[0]-a[0], b[1]-a[1]
            # right turn, straight, left turn, reverse in screen coordinates
            dirs = [( -dy,dx),(dx,dy),(dy,-dx),(-dx,-dy)]
            c = min(candidates, key=lambda c: dirs.index((c[0]-b[0],c[1]-b[1])))
            a,b = b,c
        if len(loop) < 4:
            continue
        if organic:
            # Smooth the dense coastline rather than rounding individual square corners.
            points = [(x*cell,y*cell) for x,y in loop]
            r = random.Random('bank:' + str(loop[0]) + chars)
            points = [(x+r.uniform(-cell*.10,cell*.10),y+r.uniform(-cell*.10,cell*.10)) for x,y in points]
            for _ in range(2):
                smoothed = []
                for i,p in enumerate(points):
                    q = points[(i+1)%len(points)]
                    smoothed.extend(((p[0]*.65+q[0]*.35,p[1]*.65+q[1]*.35),
                                     (p[0]*.35+q[0]*.65,p[1]*.35+q[1]*.65)))
                points = smoothed
            mid = lambda a,b: ((a[0]+b[0])/2,(a[1]+b[1])/2)
            start = mid(points[-1],points[0])
            out.append(f'M{start[0]:.1f},{start[1]:.1f}')
            for i,p in enumerate(points):
                end = mid(p,points[(i+1)%len(points)])
                out.append(f' Q{p[0]:.1f},{p[1]:.1f} {end[0]:.1f},{end[1]:.1f}')
            out.append('Z')
            continue
        corners = []
        for i,p in enumerate(loop):
            prev, nex = loop[i-1], loop[(i+1)%len(loop)]
            if (p[0]-prev[0],p[1]-prev[1]) != (nex[0]-p[0],nex[1]-p[1]):
                corners.append(p)
        if not corners:
            continue
        starts, ends = [], []
        for i,p in enumerate(corners):
            prev, nex = corners[i-1], corners[(i+1)%len(corners)]
            before, after = math.dist(p,prev), math.dist(p,nex)
            radius = min(.42, before*.42, after*.42)
            starts.append(((p[0]+(prev[0]-p[0])*radius/before)*cell,
                           (p[1]+(prev[1]-p[1])*radius/before)*cell))
            ends.append(((p[0]+(nex[0]-p[0])*radius/after)*cell,
                         (p[1]+(nex[1]-p[1])*radius/after)*cell))
        out.append(f'M{ends[-1][0]:.1f},{ends[-1][1]:.1f}')
        for p,start,end in zip(corners,starts,ends):
            out.append(f'L{start[0]:.1f},{start[1]:.1f} Q{p[0]*cell},{p[1]*cell} {end[0]:.1f},{end[1]:.1f}')
        out.append('Z')
    return ''.join(out)


def natural_materials(grid, cell, water=True):
    """One organic outline per material, instead of visibly tiled road and river bands."""
    out = []
    for chars, fill, stroke in ((":", "art-earth", "#615f42"), ("^", "art-earth", "#7a7556"), ('m','art-mud','#635e48'), ('s','art-sand','#b5a775')):
        d = _material_path(grid, chars, cell, organic=True)
        if d:
            out.append(f'<path class="natural-material" d="{d}" fill="url(#{fill})" fill-rule="evenodd" '
                       f'stroke="{stroke}" stroke-width="2" stroke-opacity=".45" stroke-linejoin="round"/>')
    river = _material_path(grid, 'w~', cell, organic=True) if water else ''
    if river:
        out.append(f'<defs><clipPath id="natural-river"><path d="{river}" fill-rule="evenodd"/></clipPath></defs>'
                   f'<path d="{river}" fill="none" stroke="#253d32" stroke-width="9" opacity=".55"/>'
                   f'<path d="{river}" fill="url(#art-water)" fill-rule="evenodd"/>'
                   f'<path d="{river}" fill="none" stroke="url(#art-shallows)" stroke-width="22" '
                   'clip-path="url(#natural-river)" opacity=".65"/>'
                   f'<path d="{river}" fill="none" stroke="#cac7a0" stroke-width="1.5" opacity=".55"/>')
        # Sparse reeds and pebbles tie the painted surface to its banks.
        r = random.Random(3701)
        for y,row in enumerate(grid):
            for x,c in enumerate(row):
                if c not in 'w~':
                    continue
                for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                    nx,ny=x+dx,y+dy
                    if not (0<=ny<len(grid) and 0<=nx<len(row)) or grid[ny][nx] in 'w~' or r.random()>.35:
                        continue
                    xx,yy=(x+.5+dx*.43)*cell,(y+.5+dy*.43)*cell
                    out.append(f'<g transform="translate({xx:.1f} {yy:.1f})" fill="none" stroke="#b8bb7d" stroke-width=".8" opacity=".8">'
                               '<path d="M0 2q-4-5-3-10 M0 3q0-7 3-12 M1 3q5-4 6-8"/>'
                               '<path d="M-1 3q-4-4-6-5 M0 3q1-7 0-10" stroke="#384e32" stroke-width="1.2"/></g>')
    return ''.join(out)


def portrait_finish(P, skin, w, top, chin, ey):
    """Sculpted face planes under facial features, rather than uniform oval shading."""
    return (f'<defs><linearGradient id="{P}plane"><stop stop-color="#4c3028" stop-opacity="0"/>'
            '<stop offset=".55" stop-color="#3b252b" stop-opacity=".05"/>'
            '<stop offset="1" stop-color="#171a25" stop-opacity=".38"/></linearGradient>'
            f'<linearGradient id="{P}key" x2="1" y2=".4"><stop stop-color="#ffe6ac" stop-opacity=".45"/>'
            '<stop offset="1" stop-color="#ffe6ac" stop-opacity="0"/></linearGradient></defs>'
            f'<g clip-path="url(#{P}head)"><rect x="{160-w}" y="{top}" width="{w*2}" height="{chin-top}" fill="url(#{P}plane)"/>'
            f'<path d="M{160-w},{top+25} Q122,{top+5} 156,{top+16} L150,{ey-13} '
            f'L127,{ey-5} L{160-w+4},{ey+12} Z" fill="url(#{P}key)"/>'
            f'<path d="M{160-w+3},{ey+9} L135,{ey+17} L148,{ey+30} L126,{chin-16} '
            f'L{160-w},{ey+32} Z" fill="#4c3530" opacity=".17"/>'
            f'<path d="M174,{ey+18} L{160+w-2},{ey+7} L{160+w},{ey+28} L180,{chin-14} '
            f'L169,{chin-9} Z" fill="#251e2a" opacity=".12"/>'
            f'<path d="M143,{ey+24} L132,{ey+16} L117,{ey+19}" fill="none" stroke="#ffe0ad" opacity=".3" stroke-width="1.5"/>'
            f'<path d="M151,{ey-6} L158,{ey+23} L148,{ey+29} L166,{ey+31} '
            f'L163,{ey+8} Z" fill="#382627" opacity=".2"/>'
            f'<path d="M155,{ey+3} L153,{ey+21} L157,{ey+24}" fill="none" stroke="#ffe6b6" opacity=".35" stroke-width="2"/>'
            f'<path d="M145,{chin-8} Q154,{chin-2} 164,{chin-7}" fill="none" stroke="#ffdead" opacity=".2" stroke-width="2"/>'
            '</g>')


def creature_body(e, P, lite, dark, glow):
    """Anatomical studies for familiar beasts and dragons; unknown forms keep their icon."""
    name = str(e.get('srd_name') or e.get('name', '')).lower()
    dragon = 'dragon' in name and 'dragonborn' not in name
    wolf = any(word in name for word in ('wolf', 'mastiff', 'hound'))
    if not dragon and not wolf:
        return None
    r = random.Random('creature-study:' + str(e['id']))
    if wolf:
        shape = ('M80 182 L70 68 Q93 65 129 117 Q157 102 183 120 '
                 'Q220 57 242 78 L231 188 L252 220 L237 213 L239 241 L223 231 '
                 'L219 266 L197 250 L184 284 L160 292 L136 281 L118 253 '
                 'L97 268 L98 242 L76 252 L80 227 L63 227 L78 202 Z')
        parts = [f'<defs><clipPath id="{P}animal"><path d="{shape}"/></clipPath>'
                 f'<linearGradient id="{P}fur" x2=".8" y2="1"><stop stop-color="#c8c1a8"/>'
                 '<stop offset=".45" stop-color="#777c70"/><stop offset="1" stop-color="#283b39"/></linearGradient>'
                 '</defs>', f'<path d="{shape}" fill="url(#{P}fur)" stroke="#1b2a27" stroke-width="2"/>',
                 '<path d="M83 88 L94 164 L120 139 Z M230 91 L192 140 L216 160 Z" fill="#423e36"/>',
                 '<path d="M100 164 L136 152 L149 199 L139 240 L115 229 Z M218 163 L186 153 L172 199 L181 240 L207 225 Z" fill="#263a38" opacity=".55"/>',
                 '<path d="M158 124 Q141 177 130 224 L141 264 L160 284 L183 265 L193 225 Q174 181 164 126 Z" fill="#c8c2a9"/>',
                 '<path d="M144 230 Q160 221 179 231 L173 245 L160 250 L148 244 Z" fill="#162522" stroke="#d4d0b5" stroke-width=".6"/>',
                 '<path d="M147 233 Q159 229 169 233" fill="none" stroke="#81938b" stroke-width="1.5"/>',
                 '<path d="M160 250 V267 M139 262 Q160 275 182 260" fill="none" stroke="#303b32" stroke-width="1.4"/>']
        for s in (-1,1):
            x = 160 + s * 43
            parts.append(f'<path d="M{x-12} 182 Q{x} 176 {x+12} 184 Q{x} 191 {x-12} 182" fill="#dbc480" stroke="#1a2824" stroke-width="2"/>'
                         f'<ellipse cx="{x}" cy="183" rx="2" ry="5" fill="#172521"/><circle cx="{x-2}" cy="181" r="1.2" fill="#fff7c9"/>')
        parts.append(f'<g clip-path="url(#{P}animal)" fill="none" stroke-linecap="round">')
        for i in range(180):
            x, y = r.uniform(75,245), r.uniform(90,280)
            dx = (x-160)*.12
            parts.append(f'<path d="M{x:.1f} {y:.1f} q{dx:.1f} 5 {dx*.8:.1f} {r.uniform(8,17):.1f}" '
                         f'stroke="{r.choice(("#ebe1c3","#1e3430","#a3aa94"))}" opacity="{r.uniform(.12,.36):.2f}" stroke-width="{r.uniform(.6,1.4):.1f}"/>')
        parts.append('</g><path d="M131 255 L91 252 M131 262 L94 269 M187 254 L228 247 M188 262 L228 269" fill="none" stroke="#d3cfb4" stroke-width=".6" opacity=".6"/>')
    else:
        shape = ('M103 318 Q116 275 135 245 L100 214 L74 172 L98 142 '
                 'L122 132 L125 106 L143 123 L163 104 L178 127 L204 117 '
                 'L221 143 L232 179 L265 195 L259 209 L286 218 L280 244 '
                 'L258 266 L220 272 Q190 292 191 329 Z')
        parts = [f'<defs><clipPath id="{P}animal"><path d="{shape}"/></clipPath></defs>',
                 '<path d="M114 156 Q71 113 66 67 Q96 105 135 122 Z M188 136 Q199 96 252 72 Q224 117 212 156 Z" fill="#c4b487" stroke="#524331" stroke-width="2"/>',
                 f'<path d="{shape}" fill="url(#{P}sil)" stroke="{dark}" stroke-width="2"/>',
                 f'<path d="M103 318 L141 268 L156 220 L182 203 L196 232 L184 263 L191 329 Z" fill="{lite}" opacity=".28"/>',
                 '<path d="M98 181 L127 174 L155 186 L175 179 L191 191 L174 205 L144 205 L124 195 Z" fill="#221d1a" opacity=".45"/>',
                 '<path d="M150 190 Q169 177 188 186 Q173 203 153 200 Z" fill="#e7c36c" stroke="#3b281e" stroke-width="2"/>',
                 '<path d="M172 183 L169 201 L176 194 Z" fill="#18201e"/><circle cx="163" cy="189" r="2" fill="#fff2b4"/>',
                 f'<path d="M207 178 L234 196 L257 204 L243 216 L210 213 L196 196 Z" fill="{lite}" opacity=".45"/>',
                 '<path d="M246 218 Q255 212 261 218 L255 222 Z" fill="#34271e"/>',
                 '<path d="M173 241 Q222 233 280 235 L256 258 L211 256 Z" fill="#201c1c"/>',
                 '<path d="M196 240 L202 255 L209 239 M217 239 L223 252 L230 238 M241 237 L245 248 L252 237" fill="#ead9ab" stroke="#5e3f2b" stroke-width=".8"/>',
                 f'<path d="M175 255 Q217 276 256 262" fill="none" stroke="{lite}" stroke-width="3"/>',
                 f'<g clip-path="url(#{P}animal)" fill="none" stroke="{dark}" stroke-width=".9" opacity=".5">']
        for y in range(120,340,13):
            for x in range(80,290,14):
                xx, yy = x + r.uniform(-2,2) + (7 if (y//13)%2 else 0), y+r.uniform(-2,2)
                parts.append(f'<path d="M{xx:.1f} {yy:.1f} q6 -7 12 0 q-5 10 -12 0"/>')
        parts.append('</g>')
        for i in range(8):
            y = 281+i*6
            parts.append(f'<path d="M{122-i*2} {y} Q154 {y+11} {181+i} {y+2}" fill="none" stroke="{lite}" stroke-width="1.3" opacity=".3"/>')
    return ''.join(parts)
