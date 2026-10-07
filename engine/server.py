"""Live virtual tabletop: http://localhost:8765

Read-only for players except one thing: fulfilling a roll the DM requested (POST /api/request/<id>/roll).
The roll itself happens here, in the engine, with the secure RNG — the browser never supplies a number.
Updates are pushed with Server-Sent Events whenever the signed log changes.
"""
import json
import mimetypes
import re
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import art, assets, itemart, srd, views
from .core import Game, RuleError, derive
from .store import TamperError, active_dir

ROOT = Path(__file__).resolve().parent.parent
VIEWER = ROOT / "viewer"
_lock = threading.Lock()
_cache = {"key": None, "game": None, "error": None}


def events_key():
    try:
        d = active_dir()
    except SystemExit:
        return None
    p = d / "engine" / "events.jsonl"
    try:
        st = p.stat()
        return (str(d), st.st_size, st.st_mtime_ns)
    except FileNotFoundError:
        return (str(d), 0, 0)


def game():
    key = events_key()
    with _lock:
        if key != _cache["key"]:
            try:
                old, old_key = _cache["game"], _cache["key"]
                # the usual case, a DM command appended events: verify and apply just those (fast)
                fresh = old.caught_up() if (old is not None and key and old_key and old_key[0] == key[0]
                                            and key[1] >= old_key[1]) else None
                if fresh is not None:
                    _cache["game"], _cache["error"], _cache["key"] = fresh, None, key
                    return _cache["game"], _cache["error"]
                _cache["game"] = Game(Path(key[0])) if key else None
                _cache["error"] = None if key else "No active campaign yet."
            except TamperError as e:
                _cache["game"], _cache["error"] = None, f"TAMPERING DETECTED: {e}"
            except Exception as e:  # noqa
                _cache["game"], _cache["error"] = None, f"{type(e).__name__}: {e}"
            _cache["key"] = key
        return _cache["game"], _cache["error"]


class Handler(BaseHTTPRequestHandler):
    server_version = "dnd-vtt/1.0"

    def log_message(self, *args):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8", cache=False):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def json(self, obj, code=200):
        self.send(code, json.dumps(obj, ensure_ascii=False))

    def svg(self, text):
        self.send(200, text, "image/svg+xml; charset=utf-8")

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        try:
            self.route_get()
        except BrokenPipeError:
            pass
        except Exception as e:  # noqa
            traceback.print_exc()
            self.json({"error": str(e)}, 500)

    def route_get(self):
        url = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(url.path)
        q = urllib.parse.parse_qs(url.query)
        if path in ("/", "/index.html"):
            return self.send(200, (VIEWER / "index.html").read_bytes(), "text/html; charset=utf-8")
        if re.fullmatch(r"/[a-z][a-z0-9-]*\.(js|css)", path) and (VIEWER / path[1:]).is_file():
            return self.send(200, (VIEWER / path[1:]).read_bytes(), mimetypes.guess_type(path)[0] + "; charset=utf-8")
        if path == "/events":
            return self.sse()
        if path.startswith("/api/icon/"):
            name = path.rsplit("/", 1)[-1].removesuffix(".svg")
            color = q.get("c", ["#222"])[0]
            return self.send(200, assets.icon_svg(name, color, 64), "image/svg+xml", cache=True)
        g, err = game()
        if path == "/api/state":
            if not g:
                return self.json({"error": err or "no game"})
            return self.json(views.player_view(g))
        if not g:
            return self.json({"error": err}, 503)
        s = g.state
        if path.startswith("/api/map/"):
            mid = path.rsplit("/", 1)[-1].removesuffix(".svg")
            m = s["maps"].get(mid)
            if not m or not m.get("shown") or mid not in views.openable_maps(g):
                return self.json({"error": "map not shown to players"}, 404)
            svg = views.map_svg(g, mid, "player", live=True)
            if m.get("background") and m["background"] in s["assets"]:
                svg = svg.replace("<defs>", f'<image href="/asset/{m["background"]}" x="0" y="0" width="{m["w"] * 32}" height="{m["h"] * 32}" preserveAspectRatio="none"/><defs>', 1)
            return self.svg(svg)
        if path == "/favicon.ico" or path == "/favicon.svg":
            return self.send(200, '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><polygon points="50,4 93,28 93,72 50,96 7,72 7,28" '
                                  'fill="#b3261e" stroke="#ffd9a0" stroke-width="5"/><polygon points="50,22 76,66 24,66" fill="#d9443b"/></svg>',
                             "image/svg+xml", cache=True)
        if path.startswith(("/api/portrait/", "/api/art/portrait/", "/api/art/face/", "/api/art/bust/")):
            eid = path.rsplit("/", 1)[-1].removesuffix(".svg")
            e = s["entities"].get(eid)
            if not e or (not views._seen(g,e) and not views.seen_by_players(g,e)):
                return self.json({"error": "unknown"}, 404)
            if e.get("portrait") and e["portrait"] in s["assets"] and s["assets"][e["portrait"]].get("public"):
                return self.redirect(f"/asset/{e['portrait']}")
            fn = art.face_svg if "/face/" in path else art.bust_svg_any if "/bust/" in path else art.portrait_svg
            return self.send(200, fn(e), "image/svg+xml; charset=utf-8", cache=True)
        if path.startswith("/api/token/"):
            eid = path.rsplit("/", 1)[-1].removesuffix(".svg")
            e = s["entities"].get(eid)
            if not views._seen(g,e):
                return self.json({"error": "unknown"}, 404)
            own = e.get("portrait") in s["assets"] and s["assets"][e["portrait"]].get("public")
            if own:  # an <img> can't load images inside an SVG, so the picture is inlined
                a = s["assets"][e["portrait"]]
                inner = assets.data_uri(Path(g.dir) / "assets" / a["file"])
                return self.send(200, assets.token_svg(e, 96, inner), "image/svg+xml; charset=utf-8", cache=True)
            return self.send(200, assets.token_svg(e, 96, face=art.face_svg(e, 108)), "image/svg+xml; charset=utf-8", cache=True)
        if path.startswith("/api/art/item/"):
            parts = path[len("/api/art/item/"):].removesuffix(".svg").split("/")
            if parts[0] == "srd" and len(parts) > 1:
                from . import mechanics as M
                it = M.resolve_item(g, urllib.parse.unquote(parts[1]))
                if not it:
                    return self.json({"error": "unknown item"}, 404)
                return self.send(200, itemart.item_svg({**it, "identified": True}), "image/svg+xml; charset=utf-8", cache=True)
            e = s["entities"].get(parts[0])
            it = next((i for i in (e or {}).get("inventory", []) if len(parts) > 1 and i["id"] == parts[1]), None) if e and e["kind"] == "pc" else None
            if not it and len(parts) > 1:  # changed hands since it was shown: follow it if unambiguous
                found = [i for o in s["entities"].values() if o["kind"] == "pc" for i in o.get("inventory", []) if i["id"] == parts[1]]
                it = found[0] if len(found) == 1 else None
            if not it:
                return self.json({"error": "unknown"}, 404)
            if it.get("art") in s["assets"] and s["assets"][it["art"]].get("public"):
                return self.redirect(f"/asset/{it['art']}")
            return self.send(200, itemart.item_svg(it), "image/svg+xml; charset=utf-8", cache=True)
        if path.startswith("/api/art/floor/"):
            parts = path[len("/api/art/floor/"):].removesuffix(".svg").split("/")
            m = s["maps"].get(parts[0]) if parts else None
            if not m or len(parts) < 2 or parts[0] not in views.openable_maps(g):
                return self.json({"error": "unknown"}, 404)
            f = next((x for x in m.get("floor", []) if x["id"] == parts[1]), None)
            if not f or (m.get("fog") and m.get("revealed") and m["revealed"][f["y"]][f["x"]] != "1"):
                return self.json({"error": "unknown"}, 404)
            return self.send(200, itemart.item_svg(f["item"]), "image/svg+xml; charset=utf-8", cache=True)
        if path.startswith("/api/card/"):
            return self.card(g, path[len("/api/card/"):], q)
        if path == "/api/pins":
            f = Path(g.dir) / "player-pins.json"
            return self.json({"pins": json.loads(f.read_text(encoding="utf-8")) if f.exists() else []})
        if path == "/api/notes":
            f = Path(g.dir) / "player-notes.md"
            return self.json({"text": f.read_text(encoding="utf-8") if f.exists() else ""})
        if path.startswith("/api/item/"):
            parts = path[len("/api/item/"):].split("/")
            if parts[0] == "srd" and len(parts) > 1:
                from . import mechanics as M
                it = M.resolve_item(g, urllib.parse.unquote(parts[1]))
                if not it:
                    return self.json({"error": "unknown item"}, 404)
                return self.json(views.item_info(g, {**it, "identified": True, "source": "SRD 5.2"}))
            if parts[0].startswith("floor~") and len(parts) > 1:  # an item on the floor or in a container: floor~<map>/<floor-id>
                m = s["maps"].get(parts[0][len("floor~"):])
                if not m or m["id"] not in views.openable_maps(g):
                    return self.json({"error": "unknown"}, 404)
                f = next((x for x in m.get("floor", []) if x["id"] == parts[1]), None)
                if not f or (m.get("fog") and m.get("revealed") and m["revealed"][f["y"]][f["x"]] != "1"):
                    return self.json({"error": "unknown"}, 404)
                return self.json(views.item_info(g, f["item"]))
            e = s["entities"].get(parts[0])
            it = next((i for i in (e or {}).get("inventory", []) if len(parts) > 1 and i["id"] == parts[1]), None) if e and e["kind"] == "pc" else None
            if not it and len(parts) > 1:
                # the item has changed hands since it was shown (a handout in the journal): follow it if it's unambiguous
                found = [(o, i) for o in s["entities"].values() if o["kind"] == "pc"
                         for i in o.get("inventory", []) if i["id"] == parts[1]]
                if len(found) == 1:
                    e, it = found[0]
            if not it:
                return self.json({"error": "unknown"}, 404)
            return self.json(views.item_info(g, it, e["id"]))
        if path.startswith("/api/creature/"):
            e = s["entities"].get(path.rsplit("/", 1)[-1])
            if not e or not views._seen(g,e) or e["kind"] == "pc":
                return self.json({"error": "unknown"}, 404)
            return self.json(views.creature_info(g, e))
        if path.startswith("/api/spell/"):
            from . import srd
            sp = srd.find("spells", path.rsplit("/", 1)[-1])
            if not sp:
                return self.json({"error": "unknown spell"}, 404)
            f = Path(__file__).resolve().parent.parent / "rules" / "spells" / f"{sp['slug']}.md"
            return self.json({"slug": sp["slug"], "name": sp["name"], "md": f.read_text(encoding="utf-8") if f.exists() else ""})
        if path.startswith("/asset/"):
            aid = path.split("/")[2]
            a = s["assets"].get(aid)
            if not a or not a.get("public"):
                return self.json({"error": "unknown asset"}, 404)
            f = Path(g.dir) / "assets" / a["file"]
            ctype = "image/svg+xml" if f.suffix == ".svg" else (mimetypes.guess_type(str(f))[0] or "application/octet-stream")
            return self.send(200, f.read_bytes(), ctype, cache=True)
        self.json({"error": "not found"}, 404)

    def redirect(self, to):
        self.send_response(302)
        self.send_header("Location", to)
        self.end_headers()

    def card(self, g, rest, q):
        s = g.state
        parts = rest.removesuffix(".svg").split("/")
        kind = parts[0]
        if kind == "char":
            e = s["entities"].get(parts[1])
            if not e or e["kind"] != "pc":
                return self.json({"error": "unknown"}, 404)
            return self.svg(assets.character_card(e, derive(e)))
        if kind == "creature":
            e = s["entities"].get(parts[1])
            if not e or not views._seen(g,e):
                return self.json({"error": "unknown"}, 404)
            return self.svg(assets.monster_card(e, reveal_stats=e.get("side") == "ally"))
        if kind == "item":
            e = s["entities"].get(parts[1])
            it = next((i for i in (e or {}).get("inventory", []) if i["id"] == parts[2]), None) if e and e["kind"] == "pc" else None
            if not it:
                return self.json({"error": "unknown"}, 404)
            return self.svg(assets.item_card(it))
        if kind == "handout":
            h = s["view"].get("handout") or {}
            if h.get("kind") == "text":
                return self.svg(assets.handout_card(h.get("title", "Handout"), h.get("text", "")))
            if h.get("kind") == "srd-item":
                from . import mechanics as M
                it = M.resolve_item(g, h["ref"]) or {"name": h["ref"], "kind": "gear"}
                return self.svg(assets.item_card({**it, "source": "SRD 5.2"}))
            return self.json({"error": "no text handout"}, 404)
        self.json({"error": "unknown card"}, 404)

    def sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last, beat = None, 0
        try:
            while True:
                key = events_key()
                if key != last:
                    last = key
                    self.wfile.write(f"event: update\ndata: {json.dumps({'k': str(key)})}\n\n".encode())
                    self.wfile.flush()
                beat += 1
                if beat % 150 == 0:   # a keep-alive every ~15 s
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                time.sleep(0.1)   # a change reaches the table within a tenth of a second
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return

    # ------------------------------------------------------------------ POST (roll requests only)
    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        parts = url.path.strip("/").split("/")
        if parts == ["api", "pins"]:
            if self.headers.get("X-Requested-With") != "dnd-vtt":
                return self.json({"error": "bad request"}, 400)
            g, err = game()
            if not g:
                return self.json({"error": err}, 503)
            n = int(self.headers.get("Content-Length") or 0)
            try:
                pins = [str(x)[:40] for x in json.loads(self.rfile.read(min(n, 20_000)).decode("utf-8") or "[]")][:200]
            except ValueError:
                return self.json({"error": "bad pins"}, 400)
            (Path(g.dir) / "player-pins.json").write_text(json.dumps(pins), encoding="utf-8")
            return self.json({"ok": True})
        if parts == ["api", "notes"]:
            if self.headers.get("X-Requested-With") != "dnd-vtt":
                return self.json({"error": "bad request"}, 400)
            g, err = game()
            if not g:
                return self.json({"error": err}, 503)
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(min(n, 200_000)).decode("utf-8", "replace")
            (Path(g.dir) / "player-notes.md").write_text(body, encoding="utf-8")
            return self.json({"ok": True})
        if len(parts) == 4 and parts[:2] == ["api", "request"] and parts[3] == "roll":
            rid = parts[2]
            if self.headers.get("X-Requested-With") != "dnd-vtt":
                return self.json({"error": "bad request"}, 400)
            try:
                with _lock:
                    from .cli import fulfill
                    g = Game()
                    if rid not in g.state["requests"]:
                        return self.json({"error": "That roll is no longer pending."}, 409)
                    g.cmdline = f"viewer: roll request {rid}"
                    fulfill(g, rid, "viewer")
                    g.commit()
                    views.write_snapshots(g)
                    lines, g.out = g.out, []
                    _cache["game"], _cache["error"], _cache["key"] = g, None, events_key()   # already current
                return self.json({"ok": True, "lines": lines})
            except RuleError as e:
                return self.json({"error": str(e)}, 409)
            except TamperError as e:
                return self.json({"error": f"Tampering detected: {e}"}, 409)
        self.json({"error": "The viewer can only roll dice the DM asked for."}, 403)


def serve(port=8765, host="127.0.0.1"):
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    print(f"Live table running at http://{'localhost' if host == '127.0.0.1' else host}:{port}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
