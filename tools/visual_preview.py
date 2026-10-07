"""Read-only art/animation review with generic fixtures and optional verified active maps.

Run ``python tools/visual_preview.py`` and open http://localhost:8767.
Use --benchmark to record cold and warm SVG generation times across representative maps.
"""
import argparse
import base64
import copy
import json
import statistics
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import art, assets, itemart, maps, render, painted

REVIEW_GAME=None


def fixtures():
    portraits = []
    for ident, name, species, cls, description in (
        ('ranger', 'The Wayfarer', 'Elf', 'Ranger', 'Long copper braid, olive skin, green eyes, forest green cloak. Feminine.'),
        ('knight', 'The Sentinel', 'Human', 'Fighter', 'Short black hair, weathered skin, stubble, stern expression, masculine.'),
        ('mage', 'The Arcanist', 'Tiefling', 'Wizard', 'Swept horns, long white hair, violet skin, amber eyes, navy robes.'),
        ('cleric', 'The Oathkeeper', 'Dwarf', 'Cleric', 'Braided silver beard, dark skin, old, gold circlet.'),
    ):
        portraits.append({'id': ident, 'name': name, 'kind': 'pc', 'species': species, 'classes': {cls: 1},
                          'bio': {'appearance': description}, 'inventory': [
                              {'name': 'Plate Armor', 'kind': 'armor', 'category': 'heavy', 'equipped': True}
                          ] if cls == 'Fighter' else []})
    portraits += [dict(id='wolf', name='Dire Wolf', kind='npc', type='beast', srd_name='Dire Wolf', side='enemy', size='Large'),
                  dict(id='dragon', name='Red Dragon', kind='npc', type='dragon', srd_name='Adult Red Dragon', side='enemy', size='Huge')]
    forest = maps.gen_wilderness(208, w=30, h=22, name='The Old Forest', stream=True)
    tavern = maps.gen_interior(91, w=28, h=20, name='The Lantern Inn', kind='tavern')
    dungeon = maps.gen_dungeon(43, w=36, h=26, name='The Forgotten Vault')
    bath = maps.gen_interior(65, w=28, h=20, name='The Mosaic Court', kind='bathhouse')
    region = maps.gen_region(75, w=96, h=64, name='The Borderlands')
    atlas = [forest, tavern, dungeon, bath, region]
    atlas += [maps.gen_interior(51+i,w=30,h=22,name=n,kind=k) for i,(n,k) in enumerate([
        ('The Scriptorium','library'),('The Smithy','workshop'),('The Chapel','temple'),('The Manor','manor')])]
    study=maps.new_map('battle','Fog and fallen bodies',22,16,fill=',',seed=33)
    study['grid']=[',,,,,,,,,,,,,,,,,,,,,,']*16
    study.update(fog=True,revealed=['1'*13+'0'*9]*16,
                 props=[dict(id='camp',icon='campfire',name='Burning campfire',x=5,y=4),
                        dict(id='cold',icon='campfire',name='Cold unlit hearth',x=8,y=4)])
    atlas.append(study)
    for light,name in [('dim','Lamplight study'),('dark','Darkness study')]:
        room=maps.gen_interior(59,w=26,h=18,name=name,kind='library')
        room['lighting']=light
        atlas.append(room)
    for i, m in enumerate(atlas):
        m['id'] = 'review-' + str(i)
        if m is not study:
            m['fog'] = False
            m['revealed'] = ['1' * m['w']] * m['h']
    return portraits, atlas


PORTRAITS, MAPS = fixtures()
ITEMS = [{'id': n, 'name': n, 'kind': 'gear', 'identified': True, 'magic': magic, 'rarity': rarity}
         for n, magic, rarity in [('Silver Longsword', False, 'Common'), ('Potion of Healing', True, 'Uncommon'),
                                 ('Ruby Amulet', True, 'Rare'), ('Leather Spellbook', False, 'Common')]]


def data(svg):
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode()


def map_art(m):
    if m.get('_identity_entities'):
        es=[dict(e,portrait_href=data(art.face_svg(e))) for e in m['_identity_entities']]
        return render.render_map(m,entities=es,live=True)
    if m.get('_campaign'):
        from engine import views
        if m.get('_full_study'):
            study=copy.deepcopy(m)
            study['fog']=False
            study['revealed']=['1'*study['w']]*study['h']
            es=[dict(e,portrait_href=data(art.face_svg(e))) for e in REVIEW_GAME.state['entities'].values()
                if (e.get('token') or {}).get('map')==m['id'] and not e.get('hidden')]
            return render.render_map(study,entities=es,live=True)
        return views.map_svg(REVIEW_GAME,m['id'],live=True)
    es = []
    if m['kind'] != 'region':
        free = [(x,y) for y,row in enumerate(m['grid']) for x,c in enumerate(row) if c in render.FLOORS]
        center = (m['w']/2, m['h']/2)
        free.sort(key=lambda p: abs(p[0]-center[0])+abs(p[1]-center[1]))
        used = []
        for e in PORTRAITS[:4]:
            pos = next(p for p in free if all(abs(p[0]-q[0])+abs(p[1]-q[1]) >= 3 for q in used))
            used.append(pos)
            es.append(dict(e, token={'map':m['id'], 'x':pos[0], 'y':pos[1]}, side='pc', size='Medium',
                           portrait_href=data(art.face_svg(e))))
    if m['name']=='Fog and fallen bodies':
        es=[]
        for i,e in enumerate(PORTRAITS[:4]):
            es.append(dict(e,token={'map':m['id'],'x':3+i*2,'y':9},side='pc',hp=0 if i==1 else 1,
                           conditions=[{'name':'unconscious'}] if i==1 else [],portrait_href=data(art.face_svg(e))))
        for i,name in enumerate(('Guard','Outlaw','Scholar','Orc')):
            es.append(dict(id='fallen-'+str(i),name=name,kind='npc',srd_name=name,type='humanoid',side='enemy',dead=True,hp=0,
                           token={'map':m['id'],'x':3+i*2,'y':12}))
        es.append(dict(id='fallen-wolf',name='Wolf',kind='npc',type='beast',dead=True,hp=0,token={'map':m['id'],'x':10,'y':6}))
        es.append(dict(id='unseen',name='Unseen enemy',kind='npc',type='beast',token={'map':m['id'],'x':17,'y':8}))
    return render.render_map(m, entities=es, current='ranger', live=True)


def identity_fixtures():
    """Alive/dead pairs from identical visual seeds; disposable generic records only."""
    studies=[]
    def study(name,samples):
        m=maps.new_map('battle',name,24,max(16,((len(samples)+3)//4)*5),fill='_',seed=41)
        m.update(id='identity-'+str(len(studies)),fog=False,pois=[],_identity_entities=[])
        for n,(sp,pres,skin,outfit,srd,typ) in enumerate(samples):
            x=1+(n%4)*6;y=2+(n//4)*5;ident=f'study-{len(studies)}-{n}'
            e=dict(id=ident,name=sp,kind='npc',species=sp,srd_name=srd or sp,type=typ or 'humanoid',side='neutral',size='Medium',
                   look=dict(presentation=pres,outfit=outfit,**({'skin':skin} if skin else {})),token=dict(map=m['id'],x=x,y=y))
            kept=dict(seed=ident,name=sp,species=sp,presentation=art.visual_identity(e)['presentation'],style=art._style_for(e),
                      traits=art.look_of(e),portrait_asset=art.portrait_choice(e),recipient_look=dict(e['look']))
            dead=dict(e,id=ident+'-body',dead=True,art_of=kept,token=dict(map=m['id'],x=x+2,y=y))
            m['_identity_entities'].extend((e,dead))
            m['pois'].append(dict(id='identity-label-'+str(n),x=x+1,y=y+2,name=f'{sp} · {pres[:1].upper()}'+(f' · {skin}' if skin else ''),public=True))
        studies.append(m)
    for outfit in ('plate','leather','robe','tunic'):
        study('Human identity · '+outfit,[('Human',p,s,outfit,None,None) for p in ('masculine','feminine','androgynous') for s in ('pale','tan','brown','dark')])
    for outfit in ('plate','robe'):
        study('Fantasy identity · '+outfit,[(sp,p,None,outfit,None,None) for sp in ('Elf','Dwarf','Orc','Tiefling','Halfling','Gnome','Dragonborn','Goliath') for p in ('masculine','feminine','androgynous')])
    study('Monster identity',[(sp,p,None,'leather',None,None) for sp in ('Goblin','Hobgoblin','Kobold','Lizardfolk','Ogre','Troll','Bugbear','Zombie') for p in ('masculine','feminine','androgynous')])
    for col,label in [('corpses-beasts-v4','Animal identity'),('corpses-creatures-v4','Creature identity')]:
        study(label,[(r['species'],r['presentation'] if r['presentation']!='any' else 'androgynous',None,'tunic',
                      r['aliases'][0],'dragon' if 'Dragon' in r['species'] else 'undead' if r['species'] in ('Mummy','Skeleton') else 'construct' if r['species']=='Animated Armor' else 'beast')
                     for r in painted.identity_catalogue('corpses') if r['collection']==col])
    study('Scale colours and dark elves',[(r['species'],r['presentation'],r['skin'],'plate',None,None) for r in painted.identity_catalogue('corpses') if r['collection']=='corpses-fantasy-colours-v4'])
    study('Lion and deer identity',[(sp,p,None,'tunic',sp,'beast') for sp in ('Lion','Deer') for p in ('masculine','feminine','androgynous')])
    return studies


def page():
    cards = ''.join(f'<figure><img src="{data(art.portrait_svg(e))}" alt="{assets.esc(e["name"])}">'
                    f'<figcaption>{assets.esc(e["name"])}</figcaption></figure>' for e in PORTRAITS)
    items = ''.join(f'<figure><img src="{data(itemart.item_svg(it))}" alt="{assets.esc(it["name"])}">'
                    f'<figcaption>{assets.esc(it["name"])}</figcaption></figure>' for it in ITEMS)
    buttons = ''.join(f'<button data-map="{i}">{assets.esc(m["name"])}</button>' for i,m in enumerate(MAPS))
    if len(MAPS)>20:
        buttons='<label>Map catalogue <select id="mapselect" aria-label="Map catalogue">'+''.join(f'<option value="{i}">{assets.esc(m["name"])}</option>' for i,m in enumerate(MAPS))+'</select></label><span>Full art study · game discovery is unchanged</span>'
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Illustration atelier · visual review</title><link rel="stylesheet" href="/style.css"><link rel="stylesheet" href="/review.css">'
            f'<body class="{"audit-page" if len(MAPS)>20 else ""}"><header><div class="eyebrow">THE LIVE TABLE / ART ATELIER</div><h1>A world worth exploring.</h1>'
            '<p>Local illustrations. Living light. A clearer view of the adventure.</p></header>'
            '<section><div class="sectionhead"><h2>The illustrated atlas</h2><span>Generated terrain · reusable foliage · tactical clarity</span></div>'
            f'<nav class="atlas-nav">{buttons}</nav><div id="viewport"><div id="mapwrap"><div id="map">{map_art(MAPS[0])}</div></div>'
            '<canvas id="ambient"></canvas><div id="fxscreen"></div></div>'
            '<div class="lab"><span>Animation study</span><button data-effect="spell">Arcane projectile</button><button data-effect="ring">Radiant ring</button>'
            '<button data-effect="freeze">Freeze frame</button>'
            '<button data-camera="detail">Inspect rooms</button><button data-camera="overview">Overview</button>'
            '<button data-effect="embers">Embers</button><button data-effect="rain">Rain</button><button data-effect="fog">Mist</button>'
            '<button data-effect="storm">Storm</button><button data-effect="snow">Snow</button><button data-effect="ash">Ash</button>'
            '<button data-effect="off">Motion off</button><output id="labstatus">Ready</output></div></section>'
            f'<section><div class="sectionhead"><h2>Faces of the adventure</h2><span>Appearance-driven character & creature illustrations</span></div><div class="portraits">{cards}</div></section>'
            f'<section><div class="sectionhead"><h2>Objects with a story</h2><span>Material & rarity-aware equipment</span></div><div class="items">{items}</div></section>'
            '<script src="/fx.js"></script><script src="/review.js"></script></body></html>')


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/':
            body, mime = page().encode(), 'text/html; charset=utf-8'
        elif path == '/mobile':
            body = ('<!doctype html><html><meta charset="utf-8"><title>Phone viewport review</title>'
                    '<body style="margin:0;background:#111a17;color:#dbc9a2;font:14px Georgia;text-align:center">'
                    '<p>Live table · 391 × 844 viewport</p>'
                    '<p><button onclick="document.querySelector(\'iframe\').focus()">Focus phone preview</button></p>'
                    '<iframe title="Phone-size live table" src="http://localhost:8766/" '
                    'style="width:391px;height:844px;border:1px solid #ad9861;border-radius:8px"></iframe></body></html>').encode()
            mime = 'text/html; charset=utf-8'
        elif path in ('/style.css', '/fx.js'):
            body = (ROOT/'viewer'/path[1:]).read_bytes()
            mime = 'text/css' if path.endswith('.css') else 'text/javascript'
        elif path in ('/review.css', '/review.js'):
            body = (ROOT/'tools'/('visual'+path[1:])).read_bytes()
            mime = 'text/css' if path.endswith('.css') else 'text/javascript'
        elif path.startswith('/map/') and path[5:].isdigit() and int(path[5:]) < len(MAPS):
            body, mime = map_art(MAPS[int(path[5:])]).encode(), 'image/svg+xml'
        elif path.startswith('/api/art/face/') and REVIEW_GAME:
            eid=path.rsplit('/',1)[-1].removesuffix('.svg')
            e=REVIEW_GAME.state['entities'].get(eid)
            from engine import views
            if not views._seen(REVIEW_GAME,e):self.send_error(404);return
            body,mime=art.face_svg(e).encode(),'image/svg+xml'
        elif path.startswith('/api/art/floor/') and REVIEW_GAME:
            bits=path.split('/')
            m=REVIEW_GAME.state['maps'].get(bits[4],{})
            f=next((f for f in m.get('floor',[]) if f['id']==bits[5].removesuffix('.svg')),None)
            if not f:self.send_error(404);return
            body,mime=itemart.item_svg(f['item']).encode(),'image/svg+xml'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def benchmark():
    rows = []
    work = [(m['kind'] + ':' + m['name'], lambda m=m: map_art(m)) for m in MAPS]
    work += [('portrait:'+e['id'], lambda e=e: art.portrait_svg(e)) for e in PORTRAITS]
    work += [('item:'+it['name'], lambda it=it: itemart.item_svg(it)) for it in ITEMS]
    for name, fn in work:
        painted.uri.cache_clear()
        t = time.perf_counter()
        fn()
        cold=(time.perf_counter()-t)*1000
        times = []
        for _ in range(15):
            t = time.perf_counter()
            svg = fn()
            times.append((time.perf_counter()-t)*1000)
        rows.append({'fixture': name, 'cold_ms':round(cold,2), 'median_ms': round(statistics.median(times),2),
                     'p95_ms': round(sorted(times)[-1],2), 'svg_bytes': len(svg.encode())})
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--campaign',action='store_true',help='Read-only review of the active campaign home maps')
    parser.add_argument('--all-maps',action='store_true',help='Full art studies of every map in the verified active campaign')
    parser.add_argument('--identity-study',action='store_true',help='Generic matching portrait/body studies; no campaign loaded')
    args = parser.parse_args()
    if args.identity_study:MAPS=identity_fixtures()
    if args.campaign or args.all_maps:
        from engine.core import Game
        REVIEW_GAME=Game()
        # Generic selector: all connected maps in the active campaign marked as home maps by the reviewer.
        # Explicit identifiers are supplied by the command line/environment, never stored as campaign facts in code.
        import os
        ids=os.environ.get('DND_REVIEW_MAPS','').split(',')
        if args.all_maps:
            MAPS=[dict(m,_campaign=True,_full_study=True) for m in REVIEW_GAME.state['maps'].values()]
        else:
            MAPS += [dict(REVIEW_GAME.state['maps'][mid],_campaign=True) for mid in ids if mid in REVIEW_GAME.state['maps']]
    if args.benchmark:
        benchmark()
    else:
        print(f'Art review at http://localhost:{args.port}', flush=True)
        ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
