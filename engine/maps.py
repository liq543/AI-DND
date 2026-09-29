"""Procedural maps and grid geometry.

Generators (all seeded, so the same seed always rebuilds the same map):
    region      overland map: coasts, mountains, forests, rivers, settlements, roads
    town        streets, buildings with doors, market square, labelled key buildings
    dungeon     BSP rooms + corridors, doors, secret doors, traps, stairs, numbered rooms
    cave        cellular-automata caverns with pools and stalagmites
    wilderness  forest / plains / swamp / hills battlefield with streams, roads, rocks
    interior    tavern, shop or temple floor plan with furniture
    arena       quick encounter maps: road-ambush, forest-clearing, ruins, bridge, crypt, cave-chamber, tavern-brawl

Grid rules implemented from rules/core/01-playing-the-game.md "Playing on a Grid":
1 square = 5 ft; entering a square costs 1 (difficult terrain 2); diagonals cost 1 but can't cut the
corner of a wall or other space-filling feature; range counts squares by the shortest route.
"""
import heapq
import math
import random

# code: (name, move_cost or None = impassable, blocks_sight, cover)
TERRAIN = {
    "#": ("wall", None, True, "total"),
    "B": ("building wall", None, True, "total"),
    ".": ("floor", 1, False, None),
    "=": ("wood floor", 1, False, None),
    ",": ("grass", 1, False, None),
    ":": ("dirt road", 1, False, None),
    "_": ("cobblestone", 1, False, None),
    "t": ("undergrowth", 2, False, None),
    "^": ("rubble", 2, False, None),
    "w": ("shallow water", 2, False, None),
    "~": ("deep water", 2, False, None),
    "m": ("mud", 2, False, None),
    "s": ("sand", 1, False, None),
    "T": ("tree", None, True, "three-quarters"),
    "P": ("pillar", None, True, "three-quarters"),
    "o": ("boulder", None, False, "half"),
    "h": ("furniture", 2, False, "half"),
    "c": ("counter", None, False, "half"),
    "f": ("fireplace", None, False, "half"),
    "D": ("closed door", None, True, "total"),
    "d": ("open door", 1, False, None),
    "S": ("secret door", None, True, "total"),
    "<": ("stairs up", 1, False, None),
    ">": ("stairs down", 1, False, None),
    "x": ("chasm", None, False, None),
    "b": ("bridge", 1, False, None),
    "r": ("well / fountain", None, False, "half"),
    " ": ("void", None, True, "total"),
}
CORNER_BLOCKERS = set("#BTPDS o")

BIOMES = {  # region map cell codes
    "O": ("deep ocean", "#1e3f66"), "C": ("shallow sea", "#2f6690"), "s": ("beach", "#e0cda0"),
    "p": ("plains", "#a8c070"), "g": ("grassland", "#8fb35e"), "f": ("forest", "#4f7d3a"),
    "F": ("deep forest", "#335e2a"), "h": ("hills", "#a89a62"), "M": ("mountains", "#8a8078"),
    "K": ("snowy peaks", "#e8eef2"), "w": ("swamp", "#5f7355"), "d": ("desert", "#d9bf7a"),
    "L": ("lake", "#3b7cb0"),
}

# ============================================================== geometry

def cell(m, x, y):
    if 0 <= y < m["h"] and 0 <= x < m["w"]:
        return m["grid"][y][x]
    return " "


def move_cost(m, x, y):
    return TERRAIN.get(cell(m, x, y), TERRAIN["."])[1]


def blocks_sight(m, x, y):
    return TERRAIN.get(cell(m, x, y), TERRAIN["."])[2]


def cover_of(m, x, y):
    return TERRAIN.get(cell(m, x, y), TERRAIN["."])[3]


def neighbors(m, x, y):
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if dx and dy and (cell(m, x + dx, y) in CORNER_BLOCKERS or cell(m, x, y + dy) in CORNER_BLOCKERS):
                continue  # can't cut corners
            yield nx, ny


def pathfind(m, start, goal=None, budget=None, blocked=frozenset(), passthrough=frozenset(), cost_mult=1):
    """Dijkstra over squares. blocked = squares you cannot enter (hostile creatures);
    passthrough = squares you may cross but not stop in (allies). Returns (cost_map, parents)."""
    dist = {start: 0}
    parent = {}
    pq = [(0, start)]
    while pq:
        c, cur = heapq.heappop(pq)
        if c > dist.get(cur, 1e9):
            continue
        if goal and cur == goal:
            break
        for nx, ny in neighbors(m, *cur):
            mc = move_cost(m, nx, ny)
            if mc is None or (nx, ny) in blocked:
                continue
            nc = c + mc * cost_mult
            if budget is not None and nc > budget:
                continue
            if nc < dist.get((nx, ny), 1e9):
                dist[(nx, ny)] = nc
                parent[(nx, ny)] = cur
                heapq.heappush(pq, (nc, (nx, ny)))
    return dist, parent


def path_to(parent, start, goal):
    path = [goal]
    while path[-1] != start:
        path.append(parent[path[-1]])
    return list(reversed(path))


def path_cost(m, path, cost_mult=1):
    """Validate an explicit path of squares; returns cost in squares or raises ValueError."""
    total = 0
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        if max(abs(x1 - x0), abs(y1 - y0)) != 1:
            raise ValueError(f"({x0},{y0})→({x1},{y1}) is not an adjacent square")
        if (x1, y1) not in set(neighbors(m, x0, y0)):
            raise ValueError(f"can't move diagonally around the corner at ({x0},{y0})→({x1},{y1})")
        mc = move_cost(m, x1, y1)
        if mc is None:
            raise ValueError(f"({x1},{y1}) is {TERRAIN.get(cell(m, x1, y1), ('?',))[0]} — impassable")
        total += mc * cost_mult
    return total


def distance_squares(a, b, size_a=1, size_b=1):
    """Grid range in squares between two creatures (by their top-left squares and sizes)."""
    ax0, ay0 = a
    bx0, by0 = b
    dx = max(0, bx0 - (ax0 + size_a - 1), ax0 - (bx0 + size_b - 1))
    dy = max(0, by0 - (ay0 + size_a - 1), ay0 - (by0 + size_b - 1))
    return max(dx, dy)


def line_cells(x0, y0, x1, y1):
    """Cells a line between two square centers passes through (supercover-ish sampling)."""
    n = max(abs(x1 - x0), abs(y1 - y0)) * 3 + 1
    seen, out = set(), []
    for i in range(n + 1):
        t = i / n
        c = (round(x0 + (x1 - x0) * t), round(y0 + (y1 - y0) * t))
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def has_los(m, a, b):
    for c in line_cells(*a, *b)[1:-1]:
        if blocks_sight(m, *c):
            return False
    return True


def cover_between(m, a, b, creatures=()):
    """SRD cover from attacker square a to target square b: None / 'half' / 'three-quarters' / 'total'.
    Traces lines from the attacker's best corner to the target's four corners (grid variant)."""
    rank = ["none", "half", "three-quarters", "total"]
    ax, ay = a
    bx, by = b
    creature_set = set(creatures) - {a, b}
    eps = 0.02  # pull corners slightly inside each square so lines along grid edges aren't ambiguous
    a_corners = [(ax + eps, ay + eps), (ax + 1 - eps, ay + eps), (ax + eps, ay + 1 - eps), (ax + 1 - eps, ay + 1 - eps)]
    b_corners = [(bx + eps, by + eps), (bx + 1 - eps, by + eps), (bx + eps, by + 1 - eps), (bx + 1 - eps, by + 1 - eps)]
    best = 3
    for cx, cy in a_corners:
        blocked, low = 0, False
        for tx, ty in b_corners:
            n = int(max(abs(tx - cx), abs(ty - cy)) * 6) + 2
            for i in range(1, n):
                t = i / n
                sq = (int(math.floor(cx + (tx - cx) * t)), int(math.floor(cy + (ty - cy) * t)))
                if sq in (a, b):
                    continue
                if blocks_sight(m, *sq):
                    blocked += 1
                    break
                if cover_of(m, *sq) in ("half", "three-quarters") or sq in creature_set:
                    low = True
        level = 3 if blocked == 4 else 2 if blocked >= 3 else 1 if (blocked or low) else 0
        best = min(best, level)
    return None if best == 0 else rank[best]


def visible_cells(m, origin, radius):
    ox, oy = origin
    out = {origin}
    for y in range(max(0, oy - radius), min(m["h"], oy + radius + 1)):
        for x in range(max(0, ox - radius), min(m["w"], ox + radius + 1)):
            if (x - ox) ** 2 + (y - oy) ** 2 > radius * radius + radius:
                continue
            ok = True
            for c in line_cells(ox, oy, x, y)[1:-1]:
                if blocks_sight(m, *c):
                    ok = False
                    break
            if ok:
                out.add((x, y))
    return out


def free_cells(m, count, rng, near=None, avoid=frozenset(), radius=6):
    cells = [(x, y) for y in range(m["h"]) for x in range(m["w"])
             if move_cost(m, x, y) == 1 and (x, y) not in avoid]
    if near:
        cells = [c for c in cells if max(abs(c[0] - near[0]), abs(c[1] - near[1])) <= radius] or cells
        cells.sort(key=lambda c: (c[0] - near[0]) ** 2 + (c[1] - near[1]) ** 2 + rng.random())
    else:
        rng.shuffle(cells)
    return cells[:count]


# ============================================================== noise & names

class Noise:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.perm = list(range(256))
        self.rng.shuffle(self.perm)
        self.perm += self.perm
        self.vals = [self.rng.random() for _ in range(256)]

    def _v(self, x, y):
        return self.vals[self.perm[(self.perm[x & 255] + y) & 255]]

    def value(self, x, y):
        xi, yi = math.floor(x), math.floor(y)
        xf, yf = x - xi, y - yi
        u, v = xf * xf * (3 - 2 * xf), yf * yf * (3 - 2 * yf)
        a, b = self._v(xi, yi), self._v(xi + 1, yi)
        c, d = self._v(xi, yi + 1), self._v(xi + 1, yi + 1)
        return (a + (b - a) * u) * (1 - v) + (c + (d - c) * u) * v

    def fbm(self, x, y, octaves=5):
        total, amp, freq, norm = 0, 1, 1, 0
        for _ in range(octaves):
            total += self.value(x * freq, y * freq) * amp
            norm += amp
            amp *= 0.5
            freq *= 2
        return total / norm


SYL_A = ["ash", "bel", "bran", "cor", "dun", "el", "fal", "gal", "har", "iron", "kel", "lor", "mar", "north",
         "oak", "pell", "quin", "raven", "stone", "thorn", "umber", "vale", "west", "wil", "yar", "zell",
         "amber", "black", "brook", "cold", "dawn", "elder", "frost", "glen", "high", "mist", "red", "silver"]
SYL_B = ["ford", "haven", "wick", "mere", "moor", "dale", "hold", "crest", "fall", "gate", "holm", "march",
         "ridge", "stead", "ton", "watch", "wood", "bury", "cairn", "field", "hollow", "reach", "shire", "vale"]
FOREST = ["Wood", "Weald", "Forest", "Thicket", "Greenwood"]
MOUNT = ["Peaks", "Spires", "Mountains", "Teeth", "Heights"]


def place_name(rng, used=None):
    used = used if used is not None else set()
    for _ in range(50):
        a, b = rng.choice(SYL_A), rng.choice(SYL_B)
        if a[-1] == b[0]:
            continue
        n = (a + b).capitalize()
        if n not in used:
            used.add(n)
            return n
    return f"Place {len(used) + 1}"


# ============================================================== map container

def new_map(kind, name, w, h, fill=".", cell_ft=5, seed=None, **extra):
    m = {"id": None, "name": name, "kind": kind, "w": w, "h": h, "cell_ft": cell_ft,
         "grid": [fill * w for _ in range(h)], "rooms": [], "labels": [], "features": [],
         "fog": kind in ("dungeon", "cave"), "lighting": "bright", "seed": seed}
    m.update(extra)
    m["revealed"] = ["1" * w if not m["fog"] else "0" * w for _ in range(h)]
    return m


class Grid:
    def __init__(self, m):
        self.m = m
        self.g = [list(r) for r in m["grid"]]

    def get(self, x, y):
        if 0 <= y < self.m["h"] and 0 <= x < self.m["w"]:
            return self.g[y][x]
        return " "

    def set(self, x, y, c):
        if 0 <= y < self.m["h"] and 0 <= x < self.m["w"]:
            self.g[y][x] = c

    def rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.set(xx, yy, c)

    def done(self):
        self.m["grid"] = ["".join(r) for r in self.g]
        return self.m


# ============================================================== dungeon

def gen_dungeon(seed, w=48, h=36, name=None, theme="dungeon", rooms_target=10):
    rng = random.Random(seed)
    m = new_map("dungeon", name or f"The {rng.choice(['Sunken', 'Forgotten', 'Howling', 'Ashen', 'Drowned', 'Silent'])} {rng.choice(['Vault', 'Crypt', 'Halls', 'Warrens', 'Catacombs', 'Keep'])}",
                w, h, fill="#", seed=seed, theme=theme, lighting="dark")
    G = Grid(m)
    leaves = []

    def split(x, y, ww, hh, depth):
        if depth == 0 or (ww < 16 and hh < 14):
            leaves.append((x, y, ww, hh))
            return
        horiz = hh > ww if abs(hh - ww) > 4 else rng.random() < 0.5
        if horiz and hh >= 14:
            cut = rng.randint(6, hh - 6)
            split(x, y, ww, cut, depth - 1)
            split(x, y + cut, ww, hh - cut, depth - 1)
        elif ww >= 16:
            cut = rng.randint(7, ww - 7)
            split(x, y, cut, hh, depth - 1)
            split(x + cut, y, ww - cut, hh, depth - 1)
        else:
            leaves.append((x, y, ww, hh))

    split(1, 1, w - 2, h - 2, max(3, int(math.log2(rooms_target)) + 1))
    rooms = []
    for (x, y, ww, hh) in leaves:
        rw = rng.randint(4, max(4, ww - 3))
        rh = rng.randint(4, max(4, hh - 3))
        rx = x + rng.randint(1, max(1, ww - rw - 1))
        ry = y + rng.randint(1, max(1, hh - rh - 1))
        rw, rh = min(rw, w - rx - 1), min(rh, h - ry - 1)
        if rw < 3 or rh < 3:
            continue
        rooms.append([rx, ry, rw, rh])
        G.rect(rx, ry, rw, rh, ".")
    rng.shuffle(rooms)
    rooms.sort(key=lambda r: (r[0] + r[2] / 2) + (r[1] + r[3] / 2) * 0.5)

    def center(r):
        return r[0] + r[2] // 2, r[1] + r[3] // 2

    def in_room(x, y):
        return any(r[0] <= x < r[0] + r[2] and r[1] <= y < r[1] + r[3] for r in rooms)

    corridor_cells = set()

    def carve(a, b):
        (x0, y0), (x1, y1) = a, b
        pts = []
        if rng.random() < 0.5:
            pts += [(x, y0) for x in range(min(x0, x1), max(x0, x1) + 1)]
            pts += [(x1, y) for y in range(min(y0, y1), max(y0, y1) + 1)]
        else:
            pts += [(x0, y) for y in range(min(y0, y1), max(y0, y1) + 1)]
            pts += [(x, y1) for x in range(min(x0, x1), max(x0, x1) + 1)]
        for p in pts:
            if G.get(*p) == "#":
                G.set(*p, ".")
                corridor_cells.add(p)

    # connect in a chain (minimum spanning by order) plus a couple of loops
    for a, b in zip(rooms, rooms[1:]):
        carve(center(a), center(b))
    for _ in range(max(1, len(rooms) // 4)):
        a, b = rng.sample(rooms, 2)
        carve(center(a), center(b))

    # doors: corridor cells orthogonally adjacent to a room, flanked by walls
    doors = []
    for (x, y) in list(corridor_cells):
        if in_room(x, y):
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if in_room(x + dx, y + dy):
                if (G.get(x + dy, y + dx) == "#" and G.get(x - dy, y - dx) == "#"):
                    doors.append((x, y))
                break
    rng.shuffle(doors)
    placed = set()
    for (x, y) in doors:
        if any(abs(x - px) + abs(y - py) <= 2 for px, py in placed):
            continue
        placed.add((x, y))
        G.set(x, y, "D" if rng.random() < 0.7 else "d")
    # one secret door (hidden feature) if possible
    if len(placed) > 3:
        sx, sy = rng.choice(sorted(placed))
        G.set(sx, sy, "S")
        m["features"].append({"type": "secret_door", "x": sx, "y": sy, "hidden": True,
                              "name": "Secret door", "dc": 15, "note": "Wisdom (Perception) or Intelligence (Investigation) DC 15 to find"})
    # dressing
    for i, r in enumerate(rooms):
        x, y, ww, hh = r
        if ww >= 7 and hh >= 6 and rng.random() < 0.5:
            for px, py in ((x + 1, y + 1), (x + ww - 2, y + 1), (x + 1, y + hh - 2), (x + ww - 2, y + hh - 2)):
                G.set(px, py, "P")
        for _ in range(rng.randint(0, 3)):
            G.set(rng.randrange(x, x + ww), rng.randrange(y, y + hh), "^")
        if rng.random() < 0.25:
            G.set(x + ww // 2, y + hh // 2, "w")
    sx, sy = center(rooms[0])
    G.set(sx, sy, "<")
    ex, ey = center(rooms[-1])
    G.set(ex, ey, ">")
    purposes = ["Guard room", "Barracks", "Shrine", "Storeroom", "Prison cells", "Armory", "Library", "Crypt",
                "Well room", "Kitchen", "Throne room", "Treasury", "Laboratory", "Kennels", "Flooded hall"]
    rng.shuffle(purposes)
    for i, r in enumerate(rooms):
        label = "Entrance" if i == 0 else ("Inner sanctum" if i == len(rooms) - 1 else purposes[i % len(purposes)])
        m["rooms"].append({"n": i + 1, "x": r[0], "y": r[1], "w": r[2], "h": r[3], "label": label})
    # traps in corridors
    traps = ["Hidden pit", "Poisoned darts", "Collapsing roof", "Falling net", "Spiked pit", "Poisoned needle"]
    for p in rng.sample(sorted(corridor_cells), min(len(corridor_cells), rng.randint(1, 3))):
        if G.get(*p) == ".":
            m["features"].append({"type": "trap", "x": p[0], "y": p[1], "hidden": True, "name": rng.choice(traps),
                                  "note": "See rules/core/09-gameplay-toolbox.md → Traps"})
    m["start"] = [sx, sy]
    return G.done()


# ============================================================== cave

def gen_cave(seed, w=44, h=32, name=None):
    rng = random.Random(seed)
    m = new_map("cave", name or f"{rng.choice(['Gloom', 'Drip', 'Echo', 'Wyrm', 'Bat', 'Glow'])}{rng.choice(['hollow', 'deep', 'maw', 'warren', 'grotto'])} Caverns",
                w, h, fill="#", seed=seed, lighting="dark")
    cells = [[rng.random() < 0.45 or x in (0, w - 1) or y in (0, h - 1) for x in range(w)] for y in range(h)]
    for _ in range(5):
        new = [[False] * w for _ in range(h)]
        for y in range(h):
            for x in range(w):
                n = sum(cells[yy][xx] if 0 <= yy < h and 0 <= xx < w else True
                        for yy in range(y - 1, y + 2) for xx in range(x - 1, x + 2) if (xx, yy) != (x, y))
                new[y][x] = n >= 5 or (n <= 1 and rng.random() < 0.1) or x in (0, w - 1) or y in (0, h - 1)
        cells = new
    # keep the largest open region
    seen, best = set(), []
    for y in range(h):
        for x in range(w):
            if not cells[y][x] and (x, y) not in seen:
                comp, stack = [], [(x, y)]
                seen.add((x, y))
                while stack:
                    cx, cy = stack.pop()
                    comp.append((cx, cy))
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < w and 0 <= ny < h and not cells[ny][nx] and (nx, ny) not in seen:
                            seen.add((nx, ny))
                            stack.append((nx, ny))
                if len(comp) > len(best):
                    best = comp
    G = Grid(m)
    noise = Noise(seed)
    for (x, y) in best:
        v = noise.fbm(x / 7, y / 7)
        G.set(x, y, "w" if v < 0.3 else "~" if v < 0.24 else ".")
    for (x, y) in best:
        if G.get(x, y) == "." and rng.random() < 0.04:
            G.set(x, y, rng.choice("^^P"))
    start = min(best, key=lambda c: c[0] + c[1])
    G.set(*start, ".")
    m["start"] = list(start)
    far = max(best, key=lambda c: (c[0] - start[0]) ** 2 + (c[1] - start[1]) ** 2)
    m["labels"].append({"x": far[0], "y": far[1], "text": "Deep chamber", "hidden": True})
    return G.done()


# ============================================================== wilderness

def gen_wilderness(seed, w=36, h=26, name=None, biome="forest", road=True, stream=None):
    rng = random.Random(seed)
    noise = Noise(seed)
    base = {"forest": ",", "plains": ",", "swamp": "m", "hills": ",", "desert": "s", "snow": ","}.get(biome, ",")
    m = new_map("wilderness", name or f"{place_name(rng)} {biome.title()}", w, h, fill=base, seed=seed,
                biome=biome, lighting="bright")
    G = Grid(m)
    tree_th = {"forest": 0.58, "plains": 0.78, "swamp": 0.68, "hills": 0.72, "desert": 2, "snow": 0.7}.get(biome, 0.6)
    for y in range(h):
        for x in range(w):
            v = noise.fbm(x / 6, y / 6)
            r = rng.random()
            if v > tree_th and r < 0.55:
                G.set(x, y, "T")
            elif v > tree_th - 0.08 and r < 0.45:
                G.set(x, y, "t")
            elif biome == "swamp" and v < 0.38:
                G.set(x, y, "w" if v > 0.3 else "~")
            elif biome in ("hills", "desert") and r < 0.03:
                G.set(x, y, "o")
            elif r < 0.012:
                G.set(x, y, "o")
    if stream if stream is not None else rng.random() < 0.5:
        x = rng.randint(w // 4, 3 * w // 4)
        for y in range(h):
            for dx in range(-1, 1 + (y % 3 == 0)):
                G.set(x + dx, y, "~" if dx == 0 else "w")
            x += rng.choice((-1, 0, 0, 1))
        m["labels"].append({"x": x, "y": h // 2, "text": "Stream"})
    if road:
        y = rng.randint(h // 3, 2 * h // 3)
        for x in range(w):
            for dy in (0, 1):
                c = G.get(x, y + dy)
                G.set(x, y + dy, "b" if c in "~w" else ":")
            if rng.random() < 0.3:
                y = max(2, min(h - 3, y + rng.choice((-1, 1))))
        m["labels"].append({"x": 1, "y": y, "text": "Road"})
    m["start"] = [1, h // 2]
    return G.done()


# ============================================================== town

KEY_BUILDINGS = ["Tavern", "Temple", "Smithy", "General Store", "Town Hall", "Stables", "Alchemist",
                 "Guard Post", "Inn", "Market Hall"]
TAVERN_NAMES = ["The Prancing Stag", "The Rusty Flagon", "The Sleeping Giant", "The Gilded Goose",
                "The Crooked Lantern", "The Drowned Rat", "The Silver Tankard", "The Laughing Wyvern"]


def gen_town(seed, w=56, h=40, name=None):
    rng = random.Random(seed)
    m = new_map("town", name or place_name(rng), w, h, fill=",", seed=seed, lighting="bright")
    G = Grid(m)
    xs = sorted(rng.sample(range(8, w - 8), 3))
    ys = sorted(rng.sample(range(7, h - 7), 2))
    main_x, main_y = xs[1], ys[0]
    for x in range(w):
        G.set(x, main_y, "_")
        G.set(x, main_y + 1, "_")
    for y in range(h):
        G.set(main_x, y, "_")
        G.set(main_x + 1, y, "_")
    for x in xs[::2]:
        for y in range(h):
            if G.get(x, y) == ",":
                G.set(x, y, ":")
    for y in ys[1:]:
        for x in range(w):
            if G.get(x, y) == ",":
                G.set(x, y, ":")
    # market square
    G.rect(main_x - 3, main_y - 3, 8, 8, "_")
    G.set(main_x, main_y, "r")
    m["labels"].append({"x": main_x - 3, "y": main_y - 4, "text": "Market Square"})
    # buildings on lots adjacent to streets
    keys = KEY_BUILDINGS[:]
    rng.shuffle(keys)
    keys.insert(0, "Tavern")
    placed = 0
    for _ in range(400):
        bw, bh = rng.randint(4, 7), rng.randint(4, 6)
        bx, by = rng.randint(1, w - bw - 1), rng.randint(1, h - bh - 1)
        area = [(x, y) for y in range(by - 1, by + bh + 1) for x in range(bx - 1, bx + bw + 1)]
        if any(G.get(x, y) != "," for x, y in area):
            continue
        near_street = [(x, y) for x in range(bx, bx + bw) for y in (by - 2, by + bh + 1) if G.get(x, y) in "_:"] + \
                      [(x, y) for y in range(by, by + bh) for x in (bx - 2, bx + bw + 1) if G.get(x, y) in "_:"]
        if not near_street:
            continue
        G.rect(bx, by, bw, bh, "B")
        G.rect(bx + 1, by + 1, bw - 2, bh - 2, "=")
        sx, sy = rng.choice(near_street)
        if sy == by - 2:
            dx, dy = min(max(sx, bx + 1), bx + bw - 2), by
        elif sy == by + bh + 1:
            dx, dy = min(max(sx, bx + 1), bx + bw - 2), by + bh - 1
        elif sx == bx - 2:
            dx, dy = bx, min(max(sy, by + 1), by + bh - 2)
        else:
            dx, dy = bx + bw - 1, min(max(sy, by + 1), by + bh - 2)
        G.set(dx, dy, "D")
        label = keys[placed] if placed < len(keys) else None
        if label == "Tavern":
            label = rng.choice(TAVERN_NAMES)
        m["rooms"].append({"n": placed + 1, "x": bx, "y": by, "w": bw, "h": bh, "label": label or "House",
                           "door": [dx, dy]})
        placed += 1
        if placed >= 26:
            break
    for _ in range(w * h // 40):
        x, y = rng.randrange(w), rng.randrange(h)
        if G.get(x, y) == ",":
            G.set(x, y, "T" if rng.random() < 0.7 else "t")
    m["start"] = [main_x, main_y + 2]
    return G.done()


# ============================================================== interior

def gen_interior(seed, w=24, h=18, name=None, kind="tavern"):
    rng = random.Random(seed)
    title = name or (rng.choice(TAVERN_NAMES) if kind == "tavern" else f"{place_name(rng)} {kind.title()}")
    m = new_map("interior", title, w, h, fill="#", seed=seed, lighting="dim", building=kind)
    G = Grid(m)
    G.rect(1, 1, w - 2, h - 2, "=")
    # back rooms
    split_x = w - 7
    for y in range(1, h - 1):
        G.set(split_x, y, "#")
    mid = h // 2
    G.set(split_x, mid - 3, "D")
    G.set(split_x, mid + 3, "D")
    for x in range(split_x + 1, w - 1):
        G.set(x, mid, "#")
    m["rooms"] += [{"n": 1, "x": 1, "y": 1, "w": split_x - 1, "h": h - 2, "label": "Common room" if kind == "tavern" else "Main hall"},
                   {"n": 2, "x": split_x + 1, "y": 1, "w": w - split_x - 2, "h": mid - 1, "label": "Kitchen" if kind == "tavern" else "Storeroom"},
                   {"n": 3, "x": split_x + 1, "y": mid + 1, "w": w - split_x - 2, "h": h - mid - 2, "label": "Cellar stairs" if kind == "tavern" else "Office"}]
    G.set(w - 3, h - 3, ">")
    G.set(w // 3, 0, "D")  # front door
    if kind == "tavern":
        for y in range(3, h - 4):
            G.set(split_x - 3, y, "c")
        m["labels"].append({"x": split_x - 4, "y": 2, "text": "Bar"})
        G.set(2, mid, "f")
        for _ in range(7):
            x, y = rng.randint(3, split_x - 6), rng.randint(3, h - 4)
            if all(G.get(x + dx, y + dy) == "=" for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                G.set(x, y, "h")
    elif kind == "temple":
        for y in range(3, h - 3, 3):
            for x in (4, split_x - 4):
                G.set(x, y, "P")
        G.set(split_x - 2, mid, "c")
        m["labels"].append({"x": split_x - 3, "y": mid - 1, "text": "Altar"})
    else:
        for x in range(3, split_x - 2):
            G.set(x, 3, "c")
        for _ in range(5):
            G.set(rng.randint(3, split_x - 3), rng.randint(6, h - 3), "h")
    m["start"] = [w // 3, 1]
    return G.done()


# ============================================================== arenas (encounter maps)

def gen_arena(seed, preset="forest-clearing", name=None, w=26, h=20):
    rng = random.Random(seed)
    if preset == "road-ambush":
        m = gen_wilderness(seed, w, h, name or "Road Ambush", biome="forest", road=True, stream=False)
    elif preset == "forest-clearing":
        m = gen_wilderness(seed, w, h, name or "Forest Clearing", biome="forest", road=False)
        G = Grid(m)
        cx, cy, r = w // 2, h // 2, min(w, h) // 3
        for y in range(h):
            for x in range(w):
                if (x - cx) ** 2 + (y - cy) ** 2 < r * r:
                    G.set(x, y, ",")
        m = G.done()
    elif preset == "bridge":
        m = new_map("wilderness", name or "River Crossing", w, h, fill=",", seed=seed)
        G = Grid(m)
        for y in range(h):
            for x in range(w // 2 - 3, w // 2 + 3):
                G.set(x, y, "~" if abs(x - w // 2) < 2 else "w")
        by = h // 2
        for x in range(w // 2 - 4, w // 2 + 4):
            G.set(x, by, "b")
            G.set(x, by + 1, "b")
        for _ in range(30):
            x, y = rng.randrange(w), rng.randrange(h)
            if G.get(x, y) == ",":
                G.set(x, y, rng.choice("Tto"))
        m = G.done()
    elif preset == "ruins":
        m = new_map("wilderness", name or "Crumbling Ruins", w, h, fill=",", seed=seed)
        G = Grid(m)
        for _ in range(6):
            bx, by = rng.randint(1, w - 8), rng.randint(1, h - 7)
            bw, bh = rng.randint(4, 7), rng.randint(4, 6)
            for x in range(bx, bx + bw):
                for y in (by, by + bh - 1):
                    if rng.random() < 0.65:
                        G.set(x, y, "#")
            for y in range(by, by + bh):
                for x in (bx, bx + bw - 1):
                    if rng.random() < 0.65:
                        G.set(x, y, "#")
        for _ in range(w * h // 12):
            x, y = rng.randrange(w), rng.randrange(h)
            if G.get(x, y) == ",":
                G.set(x, y, rng.choice("^^tPo"))
        m = G.done()
    elif preset in ("crypt", "dungeon-room"):
        m = new_map("battle", name or "Crypt Chamber", w, h, fill="#", seed=seed, lighting="dark")
        G = Grid(m)
        G.rect(2, 2, w - 4, h - 4, ".")
        for x in range(4, w - 4, 4):
            G.set(x, 4, "P")
            G.set(x, h - 5, "P")
        for _ in range(8):
            G.set(rng.randint(3, w - 4), rng.randint(3, h - 4), rng.choice("^^o"))
        G.set(w // 2, 1, "D")
        G.set(w // 2, h - 2, ">")
        m = G.done()
    elif preset == "cave-chamber":
        m = gen_cave(seed, w, h, name or "Cave Chamber")
    elif preset == "tavern-brawl":
        m = gen_interior(seed, w, h, name, kind="tavern")
    else:
        raise ValueError(f"unknown arena preset '{preset}'")
    m["kind"] = "battle" if m["kind"] not in ("battle",) else m["kind"]
    m["fog"] = False
    m["revealed"] = ["1" * m["w"] for _ in range(m["h"])]
    m["preset"] = preset
    return m


# ============================================================== region (overland)

def gen_region(seed, w=120, h=80, name=None, miles_per_cell=2):
    rng = random.Random(seed)
    elev_n, moist_n, temp_n = Noise(seed), Noise(seed + 1), Noise(seed + 2)
    used = set()
    m = new_map("region", name or f"The {place_name(rng, used)} Reaches", w, h, fill="p", seed=seed,
                cell_ft=miles_per_cell * 5280, miles_per_cell=miles_per_cell, lighting="bright")
    m["fog"] = False
    elev = [[0.0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            nx, ny = x / w - 0.5, y / h - 0.5
            falloff = 1 - min(1, (nx * nx + ny * ny) ** 0.5 * 1.6)
            elev[y][x] = elev_n.fbm(x / 22, y / 22, 6) * 0.75 + falloff * 0.45 - 0.12
    G = Grid(m)
    for y in range(h):
        for x in range(w):
            e = elev[y][x]
            mo = moist_n.fbm(x / 18, y / 18, 4)
            t = 1 - y / h * 0.6 - max(0, e - 0.6) + temp_n.fbm(x / 30, y / 30) * 0.3
            if e < 0.32:
                c = "O"
            elif e < 0.36:
                c = "C"
            elif e < 0.38:
                c = "s"
            elif e > 0.8:
                c = "K" if t < 0.6 else "M"
            elif e > 0.72:
                c = "M"
            elif e > 0.63:
                c = "h"
            elif mo > 0.62:
                c = "F" if mo > 0.7 else "f"
            elif mo > 0.55 and e < 0.44:
                c = "w"
            elif mo < 0.34 and t > 0.7:
                c = "d"
            elif mo > 0.47:
                c = "g"
            else:
                c = "p"
            G.set(x, y, c)
    m = G.done()
    # rivers: start at high cells, walk downhill to the sea
    rivers = []
    sources = sorted([(elev[y][x], x, y) for y in range(h) for x in range(w) if m["grid"][y][x] in "Mh"],
                     reverse=True)
    rng.shuffle(sources)
    for _, x, y in sources[: 6]:
        path = [(x, y)]
        seen = {(x, y)}
        for _ in range(w * 2):
            cx, cy = path[-1]
            if m["grid"][cy][cx] in "OCL":
                break
            opts = [(elev[ny][nx] + rng.random() * 0.01, nx, ny) for nx, ny in
                    ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1))
                    if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen]
            if not opts:
                break
            _, nx, ny = min(opts)
            if elev[ny][nx] > elev[cy][cx] + 0.02:  # local basin -> lake
                g = [list(r) for r in m["grid"]]
                g[cy][cx] = "L"
                m["grid"] = ["".join(r) for r in g]
                break
            seen.add((nx, ny))
            path.append((nx, ny))
        if len(path) > 8:
            rivers.append(path)
    m["rivers"] = [[list(p) for p in r] for r in rivers]
    river_cells = {tuple(p) for r in rivers for p in r}

    # settlements
    def score(x, y):
        c = m["grid"][y][x]
        if c not in "pgfs":
            return -1
        s = {"p": 3, "g": 3, "f": 1, "s": 1}[c]
        if any((x + dx, y + dy) in river_cells for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)):
            s += 3
        if any(m["grid"][yy][xx] in "C" for xx in range(max(0, x - 3), min(w, x + 4)) for yy in range(max(0, y - 3), min(h, y + 4))):
            s += 2
        return s + rng.random()

    cands = sorted(((score(x, y), x, y) for y in range(2, h - 2) for x in range(2, w - 2)), reverse=True)
    settlements = []
    kinds = ["city"] + ["town"] * 4 + ["village"] * 7
    for s, x, y in cands:
        if s < 0 or len(settlements) >= len(kinds):
            break
        if all((x - sx) ** 2 + (y - sy) ** 2 > 14 ** 2 for sx, sy, *_ in settlements):
            settlements.append((x, y, kinds[len(settlements)]))
    m["settlements"] = [{"x": x, "y": y, "kind": k, "name": place_name(rng, used)} for x, y, k in settlements]

    # roads between settlements (cheap spanning tree over terrain cost)
    cost = {"p": 1, "g": 1, "s": 2, "f": 3, "F": 5, "h": 4, "w": 6, "d": 3, "M": 12, "K": 20}

    def road(a, b):
        dist, parent = {a: 0}, {}
        pq = [(0, a)]
        while pq:
            c, cur = heapq.heappop(pq)
            if cur == b:
                break
            if c > dist[cur]:
                continue
            cx, cy = cur
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1), (cx + 1, cy + 1), (cx - 1, cy - 1), (cx + 1, cy - 1), (cx - 1, cy + 1)):
                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                t = m["grid"][ny][nx]
                if t in "OCL":
                    continue
                step = cost.get(t, 2) * (1.4 if nx != cx and ny != cy else 1) + (2 if (nx, ny) in river_cells else 0)
                nc = c + step
                if nc < dist.get((nx, ny), 1e9):
                    dist[(nx, ny)] = nc
                    parent[(nx, ny)] = cur
                    heapq.heappush(pq, (nc, (nx, ny)))
        if b not in parent:
            return None
        p = [b]
        while p[-1] != a:
            p.append(parent[p[-1]])
        return p[::-1]

    roads, connected = [], [0] if settlements else []
    remaining = list(range(1, len(settlements)))
    while remaining:
        best = None
        for i in connected:
            for j in remaining:
                d = (settlements[i][0] - settlements[j][0]) ** 2 + (settlements[i][1] - settlements[j][1]) ** 2
                if best is None or d < best[0]:
                    best = (d, i, j)
        _, i, j = best
        remaining.remove(j)
        connected.append(j)
        r = road(settlements[i][:2], settlements[j][:2])
        if r:
            roads.append([list(p) for p in r])
    m["roads"] = roads

    # points of interest
    poi_kinds = [("ruins", "Ruins of"), ("dungeon", "Dungeon:"), ("tower", "Tower of"), ("cave", "Caves of"),
                 ("shrine", "Shrine of"), ("camp", "Bandit camp near")]
    pois = []
    for _ in range(8):
        for _ in range(100):
            x, y = rng.randrange(3, w - 3), rng.randrange(3, h - 3)
            if m["grid"][y][x] in "fFhMwdp" and all((x - s["x"]) ** 2 + (y - s["y"]) ** 2 > 36 for s in m["settlements"]):
                k, prefix = rng.choice(poi_kinds)
                pois.append({"x": x, "y": y, "kind": k, "name": f"{prefix} {place_name(rng, used)}", "hidden": rng.random() < 0.5})
                break
    m["pois"] = pois
    # name the biggest forest and mountain range
    for code, words in (("fF", FOREST), ("MK", MOUNT)):
        cells = [(x, y) for y in range(h) for x in range(w) if m["grid"][y][x] in code]
        if cells:
            cx = sum(c[0] for c in cells) // len(cells)
            cy = sum(c[1] for c in cells) // len(cells)
            nearest = min(cells, key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)
            m["labels"].append({"x": nearest[0], "y": nearest[1], "text": f"{place_name(rng, used)} {rng.choice(words)}", "style": "region"})
    m["revealed"] = ["1" * w for _ in range(h)]
    return m


GENERATORS = {
    "dungeon": gen_dungeon, "cave": gen_cave, "wilderness": gen_wilderness, "town": gen_town,
    "interior": gen_interior, "arena": gen_arena, "region": gen_region,
}


def crop(m, x, y, w, h, name=None):
    """Cut an encounter-sized battle map out of a larger area map (e.g. one dungeon room)."""
    x, y = max(0, x), max(0, y)
    w, h = min(w, m["w"] - x), min(h, m["h"] - y)
    out = new_map("battle", name or f"{m['name']} (detail)", w, h, seed=m.get("seed"), lighting=m.get("lighting", "bright"))
    out["grid"] = [row[x:x + w] for row in m["grid"][y:y + h]]
    out["fog"] = False
    out["revealed"] = ["1" * w for _ in range(h)]
    out["features"] = [{**f, "x": f["x"] - x, "y": f["y"] - y} for f in m.get("features", [])
                       if x <= f["x"] < x + w and y <= f["y"] < y + h]
    out["source"] = {"map": m.get("id"), "x": x, "y": y}
    return out
