"""Top-down SVG art for the furnishing tiles (see maps.TERRAIN).

Each drawer gets the tile's pixel origin, its size, the map palette, a seeded rng and `nb(dx, dy)`, the neighbouring
cell's code, so long pieces (tables, shelves, stalls, curtains) join up and wall pieces sit against the wall.
"""
import math

WALLS = set("#B")


def _shadow(x, y, w, h, rx=2):
    return f'<rect x="{x + 2.5:.1f}" y="{y + 3.5:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="#111a14" fill-opacity=".35"/>'


def _axis(nb, c):
    """'h' if the piece runs left-right (its own kind beside it, or a wall above/below), else 'v'."""
    if nb(-1, 0) == c or nb(1, 0) == c:
        return "h"
    if nb(0, -1) == c or nb(0, 1) == c:
        return "v"
    if nb(0, -1) in WALLS or nb(0, 1) in WALLS:
        return "h"
    if nb(-1, 0) in WALLS or nb(1, 0) in WALLS:
        return "v"
    return "h"


def _span(nb, c, cx, cy, s, depth, axis):
    """The rect of a run piece: flush with same-kind neighbours, pushed against a wall if there is one."""
    d = s * depth
    if axis == "h":
        x0 = cx + (0 if nb(-1, 0) == c else 2)
        x1 = cx + s - (0 if nb(1, 0) == c else 2)
        y0 = cy + 2 if nb(0, -1) in WALLS else cy + s - d - 2 if nb(0, 1) in WALLS else cy + (s - d) / 2
        return x0, y0, x1 - x0, d
    y0 = cy + (0 if nb(0, -1) == c else 2)
    y1 = cy + s - (0 if nb(0, 1) == c else 2)
    x0 = cx + 2 if nb(-1, 0) in WALLS else cx + s - d - 2 if nb(1, 0) in WALLS else cx + (s - d) / 2
    return x0, y0, d, y1 - y0


def table(cx, cy, s, T, rng, nb):
    axis = _axis(nb, "A")
    x, y, w, h = _span(nb, "A", cx, cy, s, .74, axis)
    out = [_shadow(x, y, w, h),
           f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="2" fill="{T["plank"]}" stroke="{T["furniture_line"]}" stroke-width="1.2"/>']
    out.append(f'<rect x="{x+1:.1f}" y="{y+1:.1f}" width="{w-2:.1f}" height="{h-2:.1f}" rx="1" fill="url(#art-wood)" opacity=".55"/>'
               f'<path d="M{x+1:.1f} {y+h-1:.1f}H{x+w-1:.1f}" stroke="#241a10" stroke-width="2" opacity=".5"/>'
               f'<path d="M{x+2:.1f} {y+1:.1f}H{x+w-2:.1f}" stroke="#e8cfa2" stroke-width="1" opacity=".5"/>')
    for i in (1, 2):
        if axis == "h":
            out.append(f'<path d="M{x:.1f} {y + h * i / 3:.1f}H{x + w:.1f}" stroke="{T["plank_line"]}" stroke-width=".8"/>')
        else:
            out.append(f'<path d="M{x + w * i / 3:.1f} {y:.1f}V{y + h:.1f}" stroke="{T["plank_line"]}" stroke-width=".8"/>')
    for _ in range(rng.choice((0, 1, 1, 2))):   # whatever is on it: a mug, a plate, a candle, a book
        px, py = cx + s * (.3 + rng.random() * .4), cy + s * (.3 + rng.random() * .4)
        k = rng.choice(("mug", "plate", "candle", "book"))
        if k == "mug":
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.6" fill="#d9cdb4" stroke="#5a4a36" stroke-width=".8"/>')
        elif k == "plate":
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="#efe8da" stroke="#9a8e78" stroke-width=".8"/>'
                       f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2" fill="none" stroke="#c9bfa9" stroke-width=".6"/>')
        elif k == "candle":
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="#ffd98a" fill-opacity=".35"/><circle cx="{px:.1f}" cy="{py:.1f}" r="1.8" fill="#fff4cc"/>')
        else:
            out.append(f'<rect x="{px - 3.5:.1f}" y="{py - 2.5:.1f}" width="7" height="5" fill="{rng.choice(["#7d2430", "#2c4a6e", "#3d5a2a"])}" '
                       f'stroke="#1a130c" stroke-width=".6" transform="rotate({rng.randint(-25, 25)} {px:.1f} {py:.1f})"/>')
    return "".join(out)


def chair(cx, cy, s, T, rng, nb):
    # the back goes on the side away from a table, if one is next to it
    side = next(((dx, dy) for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)) if nb(dx, dy) in "AahW"), None)
    back = (-side[0], -side[1]) if side else rng.choice(((0, -1), (0, 1), (-1, 0), (1, 0)))
    sz = s * .46
    x, y = cx + (s - sz) / 2, cy + (s - sz) / 2
    out = [_shadow(x, y, sz, sz),
           f'<rect x="{x:.1f}" y="{y:.1f}" width="{sz:.1f}" height="{sz:.1f}" rx="2" fill="{T["furniture"]}" stroke="{T["furniture_line"]}" stroke-width="1"/>']
    if back[1]:
        by = y - 3 if back[1] < 0 else y + sz - 1
        out.append(f'<rect x="{x - 1:.1f}" y="{by:.1f}" width="{sz + 2:.1f}" height="4" rx="1.5" fill="{T["counter"]}" stroke="{T["furniture_line"]}" stroke-width=".8"/>')
    else:
        bx = x - 3 if back[0] < 0 else x + sz - 1
        out.append(f'<rect x="{bx:.1f}" y="{y - 1:.1f}" width="4" height="{sz + 2:.1f}" rx="1.5" fill="{T["counter"]}" stroke="{T["furniture_line"]}" stroke-width=".8"/>')
    return "".join(out)


def desk(cx, cy, s, T, rng, nb):
    x, y, w, h = cx + 3, cy + 5, s - 6, s - 10
    ang = rng.randint(-12, 12)
    px, py = cx + s * .39, cy + s * .5
    rot = f'transform="rotate({ang} {px:.1f} {py:.1f})"'
    return (_shadow(x, y, w, h)
            + f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="{T["counter"]}" stroke="{T["furniture_line"]}" stroke-width="1.2"/>'
            f'<rect x="{cx + s * .22:.1f}" y="{cy + s * .3:.1f}" width="{s * .34:.1f}" height="{s * .4:.1f}" fill="#f2ead8" stroke="#b9ab8e" stroke-width=".6" {rot}/>'
            f'<path d="M{cx + s * .27:.1f} {cy + s * .42:.1f}h{s * .22:.1f}M{cx + s * .27:.1f} {cy + s * .5:.1f}h{s * .18:.1f}M{cx + s * .27:.1f} {cy + s * .58:.1f}h{s * .2:.1f}" '
            f'stroke="#6b5a44" stroke-width=".6" {rot}/>'
            f'<circle cx="{cx + s * .72:.1f}" cy="{cy + s * .38:.1f}" r="2.6" fill="#141018" stroke="#8a7a5a" stroke-width=".8"/>'
            f'<path d="M{cx + s * .72:.1f} {cy + s * .38:.1f}L{cx + s * .86:.1f} {cy + s * .66:.1f}" stroke="#efe6d0" stroke-width="1.6" stroke-linecap="round"/>')


BOOK_COLOURS = ["#7d2430", "#2c4a6e", "#3d5a2a", "#6e4a1e", "#4a2a5a", "#8a6a2a", "#2a2a2a", "#9a3a1e"]


def bookshelf(cx, cy, s, T, rng, nb):
    axis = _axis(nb, "K")
    x, y, w, h = _span(nb, "K", cx, cy, s, .46, axis)
    out = [_shadow(x, y, w, h, 1),
           f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{T["counter"]}" stroke="{T["furniture_line"]}" stroke-width="1.2"/>']
    along, deep = (w, h) if axis == "h" else (h, w)
    pos = 1.5
    while pos < along - 2.5:
        bw = 2 + rng.random() * 2.2
        if rng.random() < .08:          # a gap on the shelf
            pos += bw + 1
            continue
        depth = (.55 + rng.random() * .35) * (deep - 3)
        col = rng.choice(BOOK_COLOURS)
        if axis == "h":
            out.append(f'<rect x="{x + pos:.1f}" y="{y + 1.5:.1f}" width="{bw:.1f}" height="{depth:.1f}" fill="{col}"/>')
        else:
            out.append(f'<rect x="{x + 1.5:.1f}" y="{y + pos:.1f}" width="{depth:.1f}" height="{bw:.1f}" fill="{col}"/>')
        pos += bw + .5
    return "".join(out)


def chest(cx, cy, s, T, rng, nb):
    w, h = s * .7, s * .5
    x, y = cx + (s - w) / 2, cy + (s - h) / 2
    return (_shadow(x, y, w, h)
            + f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="2" fill="#7a4a24" stroke="#3a2010" stroke-width="1.2"/>'
            f'<path d="M{x:.1f} {y + h * .38:.1f}H{x + w:.1f}" stroke="#3a2010" stroke-width="1"/>'
            f'<path d="M{x + w * .22:.1f} {y:.1f}V{y + h:.1f}M{x + w * .78:.1f} {y:.1f}V{y + h:.1f}" stroke="#8f8f8f" stroke-width="2"/>'
            f'<rect x="{x + w / 2 - 2:.1f}" y="{y + h * .38 - 1:.1f}" width="4" height="5" fill="#e0b448" stroke="#6a4a10" stroke-width=".6"/>')


def barrel(cx, cy, s, T, rng, nb):
    r = s * .36
    x, y = cx + s / 2, cy + s / 2
    return (f'<circle cx="{x + 1.5:.1f}" cy="{y + 2:.1f}" r="{r:.1f}" fill="#000" fill-opacity=".22"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#8a5a30" stroke="#2e1a0c" stroke-width="2.2"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r * .72:.1f}" fill="none" stroke="#3a2412" stroke-width="1.2"/>'
            f'<path d="M{x - r * .7:.1f} {y:.1f}H{x + r * .7:.1f}M{x:.1f} {y - r * .7:.1f}V{y + r * .7:.1f}" stroke="#6a4222" stroke-width=".7"/>'
            f'<circle cx="{x + r * .35:.1f}" cy="{y - r * .3:.1f}" r="1.6" fill="#2e1a0c"/>')


def sacks(cx, cy, s, T, rng, nb):
    out = []
    for _ in range(rng.choice((2, 3))):
        px, py = cx + s * (.3 + rng.random() * .4), cy + s * (.3 + rng.random() * .4)
        rx, ry = s * .22, s * .17
        rot = f'transform="rotate({rng.randint(-40, 40)} {px:.1f} {py:.1f})"'
        out.append(f'<ellipse cx="{px + 1:.1f}" cy="{py + 1.5:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="#000" fill-opacity=".2" {rot}/>'
                   f'<ellipse cx="{px:.1f}" cy="{py:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="#cbb58a" stroke="#7a6a48" stroke-width="1" {rot}/>'
                   f'<circle cx="{px:.1f}" cy="{py - ry * .6:.1f}" r="1.4" fill="#7a6a48"/>')
    return "".join(out)


def workbench(cx, cy, s, T, rng, nb):
    axis = _axis(nb, "J")
    x, y, w, h = _span(nb, "J", cx, cy, s, .6, axis)
    mx, my = x + w / 2, y + h / 2
    tool = rng.choice(("hammer", "saw", "vise", "awl"))
    art = {"hammer": f'<path d="M{mx - 6:.1f} {my + 3:.1f}L{mx + 5:.1f} {my - 3:.1f}" stroke="#6a4a2a" stroke-width="2"/>'
                     f'<rect x="{mx + 3:.1f}" y="{my - 6:.1f}" width="5" height="7" fill="#777" transform="rotate(-28 {mx + 5:.1f} {my - 3:.1f})"/>',
           "saw": f'<path d="M{mx - 7:.1f} {my - 2:.1f}L{mx + 6:.1f} {my - 4:.1f}L{mx + 6:.1f} {my + 2:.1f}Z" fill="#a8a8a8" stroke="#555" stroke-width=".6"/>'
                  f'<rect x="{mx - 10:.1f}" y="{my - 4:.1f}" width="4" height="5" fill="#6a4a2a"/>',
           "vise": f'<rect x="{mx - 4:.1f}" y="{my - 4:.1f}" width="8" height="8" fill="#6f6f6f" stroke="#333" stroke-width=".8"/>'
                   f'<path d="M{mx - 6:.1f} {my:.1f}H{mx + 6:.1f}" stroke="#333" stroke-width="1.2"/>',
           "awl": f'<path d="M{mx - 5:.1f} {my + 2:.1f}L{mx + 5:.1f} {my - 2:.1f}" stroke="#bbb" stroke-width="1.2"/>'
                  f'<circle cx="{mx - 6:.1f}" cy="{my + 2.5:.1f}" r="2.2" fill="#6a4a2a"/>'}[tool]
    return (_shadow(x, y, w, h)
            + f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="1.5" fill="{T["plank"]}" stroke="{T["furniture_line"]}" stroke-width="1.4"/>'
            + "".join(f'<circle cx="{x + w * fx:.1f}" cy="{y + h * fy:.1f}" r="1" fill="{T["plank_line"]}"/>' for fx, fy in ((.15, .7), (.8, .3), (.6, .8)))
            + art)


def rack(cx, cy, s, T, rng, nb):
    axis = _axis(nb, "R")
    x, y, w, h = _span(nb, "R", cx, cy, s, .3, axis)
    out = [_shadow(x, y, w, h),
           f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{T["furniture"]}" stroke="{T["furniture_line"]}" stroke-width="1"/>']
    for i in range(3):
        col = rng.choice(["#9a9a9a", "#7a5a34", "#b0b0b0"])
        if axis == "h":
            px = x + w * (.2 + .3 * i)
            out.append(f'<path d="M{px - 3:.1f} {y - 3:.1f}L{px + 3:.1f} {y + h + 3:.1f}" stroke="{col}" stroke-width="2.2" stroke-linecap="round"/>')
        else:
            py = y + h * (.2 + .3 * i)
            out.append(f'<path d="M{x - 3:.1f} {py - 3:.1f}L{x + w + 3:.1f} {py + 3:.1f}" stroke="{col}" stroke-width="2.2" stroke-linecap="round"/>')
    return "".join(out)


def anvil(cx, cy, s, T, rng, nb):
    x, y = cx + s / 2, cy + s / 2
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{s * .4:.1f}" fill="#5a3a22" stroke="#2e1a0c" stroke-width="1.2"/>'
            f'<path d="M{x - s * .32:.1f} {y - s * .12:.1f}H{x + s * .14:.1f}L{x + s * .36:.1f} {y:.1f}L{x + s * .14:.1f} {y + s * .12:.1f}H{x - s * .32:.1f}Z" '
            f'fill="#5f6166" stroke="#23252a" stroke-width="1.2"/>'
            f'<path d="M{x - s * .3:.1f} {y - s * .06:.1f}H{x + s * .12:.1f}" stroke="#9aa0a8" stroke-width="1"/>')


def forge(cx, cy, s, T, rng, nb):
    return (_shadow(cx + 2, cy + 2, s - 4, s - 4)
            + f'<rect x="{cx + 2}" y="{cy + 2}" width="{s - 4}" height="{s - 4}" rx="2" fill="#6a3a2a" stroke="#2a150e" stroke-width="1.4"/>'
            f'<path d="M{cx + 2} {cy + s / 2}H{cx + s - 2}M{cx + s / 2} {cy + 2}V{cy + s / 2}M{cx + s / 4} {cy + s / 2}V{cy + s - 2}" stroke="#4a2418" stroke-width=".8"/>'
            f'<circle cx="{cx + s / 2}" cy="{cy + s / 2}" r="{s * .26:.1f}" fill="#f08a24" filter="url(#glow)"/>'
            f'<circle cx="{cx + s / 2}" cy="{cy + s / 2}" r="{s * .12:.1f}" fill="#ffe08a"/>')


def stove(cx, cy, s, T, rng, nb):
    return (_shadow(cx + 3, cy + 3, s - 6, s - 6)
            + f'<rect x="{cx + 3}" y="{cy + 3}" width="{s - 6}" height="{s - 6}" rx="2" fill="#2e2c2a" stroke="#0e0d0c" stroke-width="1.4"/>'
            + "".join(f'<circle cx="{cx + s * fx:.1f}" cy="{cy + s * .38:.1f}" r="{s * .13:.1f}" fill="#1a1918" stroke="#6a6662" stroke-width="1"/>' for fx in (.32, .68))
            + f'<rect x="{cx + s * .25:.1f}" y="{cy + s * .66:.1f}" width="{s * .5:.1f}" height="3" rx="1" fill="#f08a24" filter="url(#glow)"/>')


def cauldron(cx, cy, s, T, rng, nb):
    x, y, r = cx + s / 2, cy + s / 2, s * .38
    brew = rng.choice(("#4f8a3a", "#6a3a7a", "#8a5a2a", "#3a6a8a"))
    return (f'<circle cx="{x + 1.5:.1f}" cy="{y + 2:.1f}" r="{r:.1f}" fill="#000" fill-opacity=".25"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#1e1c1b" stroke="#5a5652" stroke-width="2"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r * .72:.1f}" fill="{brew}"/>'
            f'<circle cx="{x - r * .25:.1f}" cy="{y - r * .2:.1f}" r="{r * .14:.1f}" fill="#fff" fill-opacity=".35"/>')


def brazier(cx, cy, s, T, rng, nb):
    x, y = cx + s / 2, cy + s / 2
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{s * 1.3:.1f}" fill="url(#lampglow)"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{s * .34:.1f}" fill="#7a5a2a" stroke="#3a2a10" stroke-width="2"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{s * .22:.1f}" fill="#f08a24" filter="url(#glow)"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{s * .1:.1f}" fill="#ffe08a"/>')


def altar(cx, cy, s, T, rng, nb):
    x, y, w, h = cx + 2, cy + 5, s - 4, s - 10
    return (_shadow(x, y, w, h)
            + f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="1" fill="#d8d2c6" stroke="#7a7266" stroke-width="1.4"/>'
            f'<rect x="{x + w * .3:.1f}" y="{y}" width="{w * .4:.1f}" height="{h}" fill="{T["carpet"]}"/>'
            f'<path d="M{x + w * .3:.1f} {y}V{y + h}M{x + w * .7:.1f} {y}V{y + h}" stroke="{T["carpet_trim"]}" stroke-width="1"/>'
            + "".join(f'<circle cx="{x + w * fx:.1f}" cy="{y + h / 2:.1f}" r="4" fill="#ffd98a" fill-opacity=".4"/>'
                      f'<circle cx="{x + w * fx:.1f}" cy="{y + h / 2:.1f}" r="1.8" fill="#fff4cc"/>' for fx in (.14, .86)))


def throne(cx, cy, s, T, rng, nb):
    back = next(((dx, dy) for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)) if nb(dx, dy) in WALLS), (0, -1))
    x, y, w, h = cx + 4, cy + 4, s - 8, s - 8
    if back[1]:
        bx, by, bw, bh = x - 1, (y - 2 if back[1] < 0 else y + h - 4), w + 2, 6
    else:
        bx, by, bw, bh = (x - 2 if back[0] < 0 else x + w - 4), y - 1, 6, h + 2
    gold = T["trim"] or "#c9a14a"
    return (_shadow(x, y, w, h)
            + f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" fill="{T["carpet"]}" stroke="{gold}" stroke-width="1.6"/>'
            f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="2" fill="{gold}" stroke="{T["furniture_line"]}" stroke-width="1"/>')


def coffin(cx, cy, s, T, rng, nb):
    vert = _axis(nb, "Y") == "v"
    x, y = cx + s / 2, cy + s / 2
    a, b = s * .2, s * .45
    pts = (f"{x - a * .6:.1f},{y - b:.1f} {x + a * .6:.1f},{y - b:.1f} {x + a:.1f},{y - b * .45:.1f} {x + a * .7:.1f},{y + b:.1f} "
           f"{x - a * .7:.1f},{y + b:.1f} {x - a:.1f},{y - b * .45:.1f}")
    rot = "" if vert else f' transform="rotate(90 {x:.1f} {y:.1f})"'
    return (f'<polygon points="{pts}" fill="#3a2418" stroke="#140c08" stroke-width="1.4"{rot}/>'
            f'<path d="M{x:.1f} {y - b * .6:.1f}V{y + b * .6:.1f}M{x - a * .4:.1f} {y - b * .25:.1f}H{x + a * .4:.1f}" stroke="{T["trim"] or "#8a7a5a"}" stroke-width="1"{rot}/>')


def strongbox(cx, cy, s, T, rng, nb):
    w = s * .62
    x, y = cx + (s - w) / 2, cy + (s - w) / 2
    return (_shadow(x, y, w, w)
            + f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{w:.1f}" rx="2" fill="#5a5e66" stroke="#1e2024" stroke-width="1.4"/>'
            + "".join(f'<circle cx="{x + w * fx:.1f}" cy="{y + w * fy:.1f}" r="1" fill="#aab0b8"/>' for fx in (.12, .88) for fy in (.12, .88))
            + f'<circle cx="{x + w / 2:.1f}" cy="{y + w / 2:.1f}" r="{w * .2:.1f}" fill="#3a3d44" stroke="#c9a14a" stroke-width="1.2"/>'
            f'<path d="M{x + w / 2:.1f} {y + w / 2:.1f}l{w * .12:.1f} {-w * .1:.1f}" stroke="#c9a14a" stroke-width="1.2"/>')


def cage(cx, cy, s, T, rng, nb):
    x, y, w = cx + 3, cy + 3, s - 6
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{w}" fill="#000" fill-opacity=".12" stroke="#2a2a2e" stroke-width="2"/>'
            + "".join(f'<path d="M{x + w * i / 5:.1f} {y}V{y + w}" stroke="#3a3a40" stroke-width="1.4"/>' for i in range(1, 5))
            + f'<path d="M{x} {y + w / 2}H{x + w}" stroke="#3a3a40" stroke-width="1.2"/>')


def stall(cx, cy, s, T, rng, nb):
    axis = _axis(nb, "M")
    x, y, w, h = _span(nb, "M", cx, cy, s, .9, axis)
    n, stripes = 4, []
    for i in range(n):
        col = T["carpet"] if i % 2 == 0 else "#efe6d0"
        if axis == "h":
            stripes.append(f'<rect x="{x + w * i / n:.1f}" y="{y:.1f}" width="{w / n + .3:.1f}" height="{h:.1f}" fill="{col}"/>')
        else:
            stripes.append(f'<rect x="{x:.1f}" y="{y + h * i / n:.1f}" width="{w:.1f}" height="{h / n + .3:.1f}" fill="{col}"/>')
    edge = (f'<path d="M{x:.1f} {y + h:.1f}H{x + w:.1f}" stroke="{T["counter"]}" stroke-width="3"/>' if axis == "h" else
            f'<path d="M{x + w:.1f} {y:.1f}V{y + h:.1f}" stroke="{T["counter"]}" stroke-width="3"/>')
    return (_shadow(x, y, w, h) + "".join(stripes)
            + f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="none" stroke="{T["furniture_line"]}" stroke-width="1.2"/>' + edge)


def signpost(cx, cy, s, T, rng, nb):
    x = cx + s / 2
    return (f'<rect x="{cx + 5.5}" y="{cy + s * .28 + 2:.1f}" width="{s - 8}" height="{s * .44:.1f}" fill="#000" fill-opacity=".2"/>'
            f'<rect x="{cx + 4}" y="{cy + s * .28:.1f}" width="{s - 8}" height="{s * .44:.1f}" rx="1.5" fill="{T["plank"]}" stroke="{T["furniture_line"]}" stroke-width="1.2"/>'
            + "".join(f'<path d="M{cx + 7} {cy + s * fy:.1f}h{s * (.5 + rng.random() * .2):.1f}" stroke="#3a2a1a" stroke-width=".8"/>' for fy in (.4, .5, .6))
            + f'<rect x="{x - 2:.1f}" y="{cy + s * .22:.1f}" width="4" height="4" fill="#e8dcc0" stroke="#6a5a40" stroke-width=".6"/>')


def curtain(cx, cy, s, T, rng, nb):
    if _axis(nb, "|") == "h":
        d = f"M{cx} {cy + s / 2}" + "".join(f"Q{cx + s * (i + .5) / 4:.1f} {cy + s / 2 + (4 if i % 2 else -4)} {cx + s * (i + 1) / 4:.1f} {cy + s / 2}" for i in range(4))
    else:
        d = f"M{cx + s / 2} {cy}" + "".join(f"Q{cx + s / 2 + (4 if i % 2 else -4)} {cy + s * (i + .5) / 4:.1f} {cx + s / 2} {cy + s * (i + 1) / 4:.1f}" for i in range(4))
    return (f'<path d="{d}" fill="none" stroke="{T["carpet"]}" stroke-width="5" stroke-linecap="round"/>'
            f'<path d="{d}" fill="none" stroke="{T["carpet_trim"]}" stroke-opacity=".5" stroke-width="1"/>')


def ladder(cx, cy, s, T, rng, nb):
    if nb(0, -1) in WALLS or nb(0, 1) in WALLS or "L" in (nb(0, -1), nb(0, 1)):
        return (f'<path d="M{cx + s * .32:.1f} {cy}V{cy + s}M{cx + s * .68:.1f} {cy}V{cy + s}" stroke="#7a5530" stroke-width="2.4"/>'
                + "".join(f'<path d="M{cx + s * .32:.1f} {cy + s * f:.1f}H{cx + s * .68:.1f}" stroke="#8a6a3a" stroke-width="1.6"/>' for f in (.15, .4, .65, .9)))
    return (f'<path d="M{cx} {cy + s * .32:.1f}H{cx + s}M{cx} {cy + s * .68:.1f}H{cx + s}" stroke="#7a5530" stroke-width="2.4"/>'
            + "".join(f'<path d="M{cx + s * f:.1f} {cy + s * .32:.1f}V{cy + s * .68:.1f}" stroke="#8a6a3a" stroke-width="1.6"/>' for f in (.15, .4, .65, .9)))


def hay(cx, cy, s, T, rng, nb):
    # Loose fibre piles follow the tile without exposing a rectangular swatch.
    out = [f'<ellipse cx="{cx+s*.52:.1f}" cy="{cy+s*.59:.1f}" rx="{s*.48:.1f}" ry="{s*.36:.1f}" fill="#2c281b" opacity=".24"/>']
    for _ in range(100):
        a, radius = rng.random()*math.tau, math.sqrt(rng.random())
        px, py = cx+s*.5+math.cos(a)*radius*s*.47, cy+s*.5+math.sin(a)*radius*s*.34
        angle, length = rng.uniform(-.6,.6), rng.uniform(s*.10,s*.30)
        dx,dy = math.cos(angle)*length,math.sin(angle)*length
        out.append(f'<path d="M{px-dx/2:.1f} {py-dy/2:.1f}q{dx*.45:.1f} {dy*.5-1:.1f} {dx:.1f} {dy:.1f}" '
                   f'stroke="{rng.choice(["#9a8852", "#c8b47a", "#a89560", "#ddd0a0"])}" stroke-width=".8" opacity=".7" fill="none"/>')
    return "".join(out)


def grate(cx, cy, s, T, rng, nb):
    x, y, w = cx + 5, cy + 5, s - 10
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{w}" rx="1" fill="#141414" stroke="#4a4a4a" stroke-width="1.6"/>'
            + "".join(f'<path d="M{x + w * i / 4:.1f} {y}V{y + w}" stroke="#5a5a5a" stroke-width="1.4"/>' for i in range(1, 4)))


def hedge(cx, cy, s, T, rng, nb):
    out = [f'<rect x="{cx + 1}" y="{cy + 1}" width="{s - 2}" height="{s - 2}" rx="6" fill="#2f5a24"/>']
    for _ in range(6):
        px, py = cx + 5 + rng.random() * (s - 10), cy + 5 + rng.random() * (s - 10)
        out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{4 + rng.random() * 3:.1f}" fill="{rng.choice(["#3f7a30", "#4f8a3a", "#356a28"])}"/>')
    return "".join(out)


DRAW = {"A": table, "C": chair, "W": desk, "K": bookshelf, "Q": chest, "O": barrel, "U": sacks, "J": workbench,
        "R": rack, "!": anvil, "F": forge, "&": stove, "@": cauldron, "*": brazier, "X": altar, "H": throne, "Y": coffin,
        "$": strongbox, "N": cage, "M": stall, "+": signpost, "|": curtain, "L": ladder, "Z": hay, "G": grate, "%": hedge}
