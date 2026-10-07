"""Bundled painterly portraits and reusable objects. Decoration only; no gameplay RNG or state changes.

Character selection matches explicit appearance before class/default traits. Finite base assets are
shared; custom public portraits still take precedence in the server. No generation API runs in play.
"""
import base64
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from .assets import esc

ROOT=Path(__file__).resolve().parent.parent/'assets'/'generated'

@lru_cache(maxsize=384)
def uri(collection, index):
    path=ROOT/collection/f'{index:02d}.webp'
    return 'data:image/webp;base64,'+base64.b64encode(path.read_bytes()).decode() if path.is_file() else ''

# species, presentation, outfit, hair, age, skin, headwear. Catalog mirrors the generated cells.
HUMANS=[
 ('Human','masculine','leather','black','young','pale','none'),
 ('Human','masculine','plate','black','adult','olive','none'),
 ('Human','masculine','robe','silver','old','pale','hood'),
 ('Human','feminine','doublet','black','adult','dark','hat'),
 ('Human','feminine','leather','auburn','young','fair','none'),
 ('Human','feminine','chain','black','adult','brown','none'),
 ('Human','masculine','tunic','brown','adult','tan','none'),
 ('Human','feminine','tunic','silver','old','dark','none'),
 ('Human','feminine','leather','auburn','young','fair','none'),
 ('Human','masculine','plate','black','adult','dark','none'),
 ('Human','feminine','robe','silver','adult','pale','none'),
 ('Human','masculine','coat','black','young','olive','none'),
 ('Human','masculine','plate','blonde','young','pale','none'),
 ('Human','feminine','doublet','auburn','adult','brown','none'),
 ('Human','masculine','coat','silver','old','tan','none'),
 ('Human','masculine','monk','black','young','dark','none')]
FANTASY=[
 ('Elf','feminine','leather','auburn','adult','olive','none'),
 ('Elf','masculine','robe','silver','adult','pale','none'),
 ('Elf','feminine','leather','black','adult','dark','none'),
 ('Elf','masculine','plate','blonde','adult','pale','none'),
 ('Dwarf','masculine','vestments','silver','old','dark','circlet'),
 ('Dwarf','feminine','chain','auburn','adult','tan','none'),
 ('Orc','masculine','plate','white','adult','green','none'),
 ('Orc','feminine','leather','black','adult','green','none'),
 ('Tiefling','feminine','robe','white','adult','violet','none'),
 ('Tiefling','masculine','robe','black','adult','red','none'),
 ('Halfling','feminine','doublet','brown','young','fair','hat'),
 ('Halfling','masculine','leather','black','young','brown','none'),
 ('Gnome','feminine','tunic','white','old','fair','none'),
 ('Gnome','masculine','robe','silver','old','tan','none'),
 ('Dragonborn','masculine','plate','black','adult','gold','none'),
 ('Goliath','feminine','furs','black','adult','gray','none')]
EXTRA=[
 ('Human','masculine','leather','black','adult','pale','none'),
 ('Human','feminine','tunic','black','adult','olive','none'),
 ('Human','masculine','robe','silver','adult','pale','none'),
 ('Human','masculine','leather','silver','adult','dark','none'),
 ('Human','masculine','robe','silver','old','pale','none'),
 ('Human','feminine','vestments','black','adult','dark','none'),
 ('Human','masculine','chain','silver','old','olive','none'),
 ('Human','feminine','doublet','silver','old','pale','none'),
 ('Human','feminine','leather','black','adult','dark','none'),
 ('Human','masculine','leather','black','adult','brown','none'),
 ('Human','masculine','doublet','auburn','young','pale','none'),
 ('Human','feminine','plate','black','adult','olive','none'),
 ('Human','feminine','robe','white','adult','brown','none'),
 ('Human','masculine','coat','auburn','adult','pale','none'),
 ('Human','masculine','vestments','white','old','dark','none'),
 ('Human','feminine','tunic','brown','adult','pale','none')]
FANTASY_EXTRA=[
 ('Goliath','masculine','furs','black','adult','gray','none'),
 ('Dragonborn','feminine','plate','black','adult','gold','none'),
 ('Elf','feminine','vestments','white','adult','pale','none'),
 ('Elf','masculine','leather','black','adult','dark','none'),
 ('Dwarf','masculine','plate','auburn','adult','ruddy','none'),
 ('Dwarf','feminine','vestments','silver','old','dark','circlet'),
 ('Orc','masculine','robe','white','old','green','none'),
 ('Orc','feminine','furs','silver','old','green','none'),
 ('Tiefling','masculine','doublet','white','adult','violet','none'),
 ('Tiefling','feminine','leather','black','adult','red','none'),
 ('Halfling','masculine','tunic','brown','adult','fair','none'),
 ('Halfling','feminine','leather','black','adult','dark','none'),
 ('Gnome','feminine','leather','auburn','young','fair','none'),
 ('Gnome','masculine','robe','blonde','young','tan','none'),
 ('Dragonborn','masculine','robe','black','adult','silver','none'),
 ('Goliath','feminine','plate','black','adult','gray','none')]
FIELDS=('species','presentation','outfit','hair_color','age','skin','headwear')
CREATURES=[('wolf',0),('mastiff',1),('dog',1),('horse',2),('mule',2),('pony',2),('dragon',3),
           ('rat',4),('owlbear',5),('goblin',6),('kobold',7),('lizardfolk',8),('ogre',9),('troll',9),
           ('skeleton',10),('zombie',11),('earth elemental',12),('fire elemental',13),('jelly',14),('ooze',14),
           ('aberration',15)]

def _color_distance(a,b):
    if not (a and b and str(a).startswith('#') and str(b).startswith('#')):return 0
    return sum((int(a[i:i+2],16)-int(b[i:i+2],16))**2 for i in (1,3,5))/195075

def selection(e,L,explicit,hair_colors,skin_colors):
    """Closest base with hard species/presentation boundaries and deterministic tie breaks."""
    records=[(col,i,r) for col,rows in (('portraits-human',HUMANS),('portraits-fantasy',FANTASY),('portraits-extra',EXTRA),('portraits-fantasy-extra',FANTASY_EXTRA)) for i,r in enumerate(rows)]
    records.extend((r['collection'],r['index'],tuple(r.get(k,'none') for k in FIELDS)) for r in identity_catalogue('portraits'))
    species=L['species']
    candidates=[r for r in records if r[2][0]==species]
    if not candidates:return None
    presentation=explicit.get('presentation')
    if presentation:candidates=[r for r in candidates if r[2][1]==presentation]
    if not candidates:return None
    if species=='Human' and 'skin' in explicit:
        nearest=min(_color_distance(explicit['skin'],skin_colors.get(r[2][5],'#c89a6a')) for r in candidates)
        candidates=[r for r in candidates if _color_distance(explicit['skin'],skin_colors.get(r[2][5],'#c89a6a'))<=nearest+.012]
    def score(record):
        row=record[2]
        score=0
        for i,k in enumerate(FIELDS[2:],2):
            expected=explicit.get(k,L.get(k))
            weight=9 if k in explicit else 1
            if k=='hair_color': mismatch=_color_distance(expected,hair_colors.get(row[i],'#222222'))
            elif k=='skin': mismatch=_color_distance(expected,skin_colors.get(row[i],'#c89a6a'))
            elif k=='outfit':
                a='armor' if expected in ('plate','chain') else 'robe' if expected in ('robe','vestments') else expected
                b='armor' if row[i] in ('plate','chain') else 'robe' if row[i] in ('robe','vestments') else row[i]
                mismatch=0 if a==b else 1
            else:mismatch=0 if expected==row[i] else 1
            score+=weight*mismatch
        if explicit.get('spectacles'):
            score+=0 if record[0]=='portraits-extra' and record[1] in (2,4) or record[0]=='portraits-fantasy' and record[1] in (12,13) else 12
        if explicit.get('hair_style')=='bun':
            score+=0 if record[0]=='portraits-extra' and record[1] in (1,7) else 7
        if explicit.get('beard') and explicit['beard']!='none':
            bearded={("portraits-fantasy",4),("portraits-fantasy-extra",4),
                     ("portraits-human",1),("portraits-human",6),("portraits-human",14),
                     ("portraits-extra",3),("portraits-extra",4),("portraits-extra",6),("portraits-extra",13),("portraits-extra",14)}
            score+=0 if (record[0],record[1]) in bearded else 18
        tie=int(hashlib.sha256(f"{L['seed']}:{record[0]}:{record[1]}".encode()).hexdigest()[:8],16)/2**32
        return score+tie*.18
    col,i,_=min(candidates,key=score)
    return (col,i) if uri(col,i) else None

def creature_selection(e):
    from . import art
    identity=art.visual_identity(e)
    names=[identity['species'].lower()] if identity['species_source']!='unspecified' else [str(e.get('srd_name') or e.get('type') or e.get('name') or '').lower()]
    presentation=identity['presentation']
    for name in names:
        hits=[r for r in identity_catalogue('portraits') if r['presentation'] in ('any',presentation)
              and any(re.search(r'\b'+re.escape(alias)+r'\b',name) for alias in r.get('aliases',[]))]
        if hits:
            longest=max(max(len(alias) for alias in r['aliases'] if re.search(r'\b'+re.escape(alias)+r'\b',name)) for r in hits)
            hits=[r for r in hits if any(len(alias)==longest and re.search(r'\b'+re.escape(alias)+r'\b',name) for alias in r['aliases'])]
            row=min(hits,key=lambda r:0 if str(e.get('size','Medium')).lower()==r.get('size','medium') else 1)
            return (row['collection'],row['index']) if uri(row['collection'],row['index']) else None
    name=names[0]
    # Owlbear precedes its unrelated beast family; specific types precede broad families.
    for word,i in CREATURES:
        if word=='dragon' and re.search(r'\b(black|blue|brass|bronze|copper|gold|green|silver|white)\s+dragon\b',name):continue
        if word=='zombie':continue  # Gendered undead use the shared catalogue, never a generic male face.
        if re.search(r'\b'+re.escape(word)+r'\b',name) and uri('portraits-creatures',i):return 'portraits-creatures',i
    return None


@lru_cache(maxsize=2)
def identity_catalogue(kind):
    path=ROOT/'identity-v3-catalogue.json'
    return tuple(json.loads(path.read_text(encoding='utf-8')).get(kind,[])) if path.is_file() else ()


@lru_cache(maxsize=1)
def portrait_records():
    records={(col,i):dict(zip(FIELDS,r)) for col,rows in (('portraits-human',HUMANS),('portraits-fantasy',FANTASY),('portraits-extra',EXTRA),('portraits-fantasy-extra',FANTASY_EXTRA)) for i,r in enumerate(rows)}
    records.update({(r['collection'],r['index']):r for r in identity_catalogue('portraits')})
    return records

def portrait(e, selected, mode='portrait',size=None):
    col,i=selected
    source=uri(col,i)
    label=esc(e.get('name',''))
    from . import art
    identity=art.visual_identity(e)
    traits=f'data-species="{esc(identity["species"])}" data-presentation="{identity["presentation"]}" data-art="{col}/{i:02d}"'
    if mode=='face':
        sz=size or 256
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="{sz}" height="{sz}"><title>{label}</title><image class="painted-face" {traits} href="{source}" x="-20" y="-8" width="296" height="296" preserveAspectRatio="xMidYMid slice"/></svg>'
    sz=size or 320
    inner=(f'<title>{label}</title><rect width="320" height="400" fill="#16251f"/>'
           f'<image class="painted-portrait" {traits} href="{source}" x="0" y="0" width="320" height="366" preserveAspectRatio="xMidYMid slice"/>')
    if mode=='portrait':
        inner+=('<rect x="5" y="5" width="310" height="390" rx="8" fill="none" stroke="#bda376" stroke-opacity=".7"/>'
                '<path d="M18 6H6V18M302 6H314V18M6 382V394H18M302 394H314V382" fill="none" stroke="#e2c99a"/>'
                f'<text x="160" y="383" text-anchor="middle" font-family="Georgia,serif" font-size="15" fill="#eee1c5" textLength="{min(275,len(e.get("name",""))*7)}" lengthAdjust="spacingAndGlyphs">{label}</text>')
    if mode=='bust':
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 366" width="{sz}" height="{int(sz*366/320)}">{inner}</svg>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 400" width="{sz}" height="{int(sz*1.25)}">{inner}</svg>'

FURNITURE={'y':('furniture',0),'C':('furniture',2),'W':('furniture',3),'K':('furniture',4),
           'Q':('furniture',5),'O':('furniture',6),'U':('furniture',7),'J':('furniture',8),
           'R':('furniture',9),'!':('furniture',10),'@':('furniture',11),'X':('furniture',12),
           'H':('furniture',13),'Y':('furniture',14),'$':('furniture',15),
           'u':('environment',1),'n':('environment',0),'P':('environment',0),'r':('environment',3),'j':('environment',6),
           'G':('environment',12),'L':('environment',13)}
FURNITURE.update({'e':('fittings',7),'i':('fittings',8),'p':('fittings',10),'F':('fittings',12),
                  '&':('fittings',11),'v':('fittings',14),'<':('fittings',4),'>':('fittings',5)})

def sprite(collection,index,x,y,w,h=None,rotation=0):
    source=uri(collection,index)
    if not source:return ''
    h=w if h is None else h
    rot=f' transform="rotate({rotation} {x+w/2:.1f} {y+h/2:.1f})"' if rotation else ''
    return f'<use class="painted-object" href="#painted-{collection}-{index}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"{rot}/>'

@lru_cache(maxsize=32)
def geometry(collection):
    path=ROOT/collection/'geometry.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}

def fitted_sprite(collection,index,x,y,w,h,vertical=False):
    """Fit an object's alpha bounds to a joined footprint, without repeating whole miniatures."""
    if not uri(collection,index):return ''
    a,b,c,d=geometry(collection).get(str(index),(0,0,256,256))
    if vertical:
        return (f'<g transform="translate({x+w:.1f} {y:.1f}) rotate(90)">'
                +fitted_sprite(collection,index,0,0,h,w)+ '</g>')
    return (f'<svg class="painted-joined" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'viewBox="{a} {b} {c-a} {d-b}" preserveAspectRatio="none" overflow="visible">'
            f'<use href="#painted-{collection}-{index}" width="256" height="256"/></svg>')

def furnishing(c,m,x,y):
    """Stable semantic variants: same object role, different appropriate materials."""
    theme=m.get('theme','stone')
    choices={'y':('interior-tables-v2',[14] if theme=='manor' else [12] if theme=='cellar' else [13]),
             'W':('interior-tables-v2',[3]),'a':('interior-tables-v2',[11]),
             'i':('interior-storage-v2',[1]),'Q':('interior-storage-v2',[3]),
             'U':('interior-storage-v2',[5]),'R':('interior-storage-v2',[8]),'$':('interior-storage-v2',[10]),
             'J':('interior-workspaces-v2',[2,3]),'F':('interior-workspaces-v2',[0]),
             '!':('interior-workspaces-v2',[1]),'@':('interior-workspaces-v2',[7]),
             'X':('interior-workspaces-v2',[12] if theme=='temple' else [13]),
             'j':('interior-workspaces-v2',[10]) if theme in ('timber','cellar') else FURNITURE['j'],
             'h':('interior-tables-v2',[0,9,10]),
             'Z':('interior-details-v2',[10]),'+':('interior-details-v2',[6]),
             'M':('interior-details-v2',[4,5])}
    match=choices.get(c)
    if match:
        col,indices=match
        if isinstance(indices,int):indices=[indices]
        index=indices[int(hashlib.sha256(f'{m.get("seed",1)}:{x}:{y}:{c}'.encode()).hexdigest()[:4],16)%len(indices)]
        if uri(col,index):return col,index
    return FURNITURE.get(c)

def joined_furnishings(grid,m,cell):
    """Join straight runs while retaining bends, separate beds and exact tactical footprints."""
    h,w=len(grid),len(grid[0]);covered=set();out=[]
    for y,row in enumerate(grid):
        for x,c in enumerate(row):
            if (x,y) in covered or c not in 'AcKeRg|':continue
            theme=m.get('theme','stone')
            match={'A':('interior-tables-v2',2 if theme=='manor' else 1 if theme=='timber' else 0),
                   'c':('interior-tables-v2',5 if theme=='timber' else 4),
                   'K':('interior-storage-v2',0),'e':('interior-tables-v2',8),
                   'R':('interior-storage-v2',8),'g':('interior-details-v2',7),
                   '|':('interior-details-v2',2)}[c]
            if not uri(*match):continue
            horizontal=x+1<w and row[x+1]==c or not (y+1<h and grid[y+1][x]==c)
            dx,dy=(1,0) if horizontal else (0,1);n=1
            while x+dx*n<w and y+dy*n<h and grid[y+dy*n][x+dx*n]==c and (x+dx*n,y+dy*n) not in covered:n+=1
            if c=='A' and n>3:
                match=('interior-tables-v2',0)
            if c in 'AcKe' and uri('continuous-furniture-v2',0):
                match=('continuous-furniture-v2',{'A':0,'c':1,'K':3,'e':2}[c])
            covered.update((x+dx*i,y+dy*i) for i in range(n))
            depth=cell*({'A':.74,'c':.82,'K':.54,'e':.46,'R':.55,'g':.16,'|':.2}[c])
            px=x*cell+(2 if horizontal else (cell-depth)/2)
            py=y*cell+((cell-depth)/2 if horizontal else 2)
            ww,hh=(n*cell-4,depth) if horizontal else (depth,n*cell-4)
            out.append(f'<rect x="{px+1:.1f}" y="{py+2:.1f}" width="{ww:.1f}" height="{hh:.1f}" rx="1.5" fill="#161c13" opacity=".45"/>')
            out.append(fitted_sprite(*match,px,py,ww,hh,vertical=not horizontal))
            out.append(f'<rect x="{px:.1f}" y="{py:.1f}" width="{ww:.1f}" height="{hh:.1f}" rx="1" fill="none" stroke="#3a291c" stroke-width="1.1"/>')
            if c=='e':
                d=f'M{px} {py+hh*.17}H{px+ww}' if horizontal else f'M{px+ww*.83} {py}V{py+hh}'
                out.append(f'<path d="{d}" fill="none" stroke="#211f17" stroke-width="1.6"/>')
    return ''.join(out),covered

def building_roofs(grid,m,cell):
    """Texture connected roof masses; ridge lines never cover a doorway or courtyard."""
    if not uri('town-roof-materials-v2',0):return ''
    seen=set();out=[];h=len(grid);w=len(grid[0])
    for y,row in enumerate(grid):
        for x,c in enumerate(row):
            if c!='B' or (x,y) in seen:continue
            todo=[(x,y)];mass=[];seen.add((x,y))
            while todo:
                xx,yy=todo.pop();mass.append((xx,yy))
                for nx,ny in ((xx-1,yy),(xx+1,yy),(xx,yy-1),(xx,yy+1)):
                    if 0<=nx<w and 0<=ny<h and grid[ny][nx]=='B' and (nx,ny) not in seen:
                        seen.add((nx,ny));todo.append((nx,ny))
            ident=f'roof-{x}-{y}';i=(x*3+y+int(m.get('seed') or 1))%4
            rects=''.join(f'<rect x="{xx*cell}" y="{yy*cell}" width="{cell}" height="{cell}"/>' for xx,yy in mass)
            left=min(xx for xx,yy in mass)*cell;right=(max(xx for xx,yy in mass)+1)*cell
            top=min(yy for xx,yy in mass)*cell;bottom=(max(yy for xx,yy in mass)+1)*cell
            horizontal=right-left>=bottom-top
            cx=(left+right)/2;cy=(top+bottom)/2
            hip=min((bottom-top if horizontal else right-left)*.42,(right-left if horizontal else bottom-top)*.18)
            ridge=f'M{left+hip} {cy}H{right-hip}' if horizontal else f'M{cx} {top+hip}V{bottom-hip}'
            hips=(f'M{left} {top}L{left+hip} {cy}L{left} {bottom}M{right} {top}L{right-hip} {cy}L{right} {bottom}' if horizontal else
                  f'M{left} {top}L{cx} {top+hip}L{right} {top}M{left} {bottom}L{cx} {bottom-hip}L{right} {bottom}')
            # Light falls across the slopes, while all roof detail remains inside actual roof tiles.
            stops='<stop stop-color="#131915" stop-opacity=".55"/><stop offset=".46" stop-color="#f0d5a2" stop-opacity=".22"/><stop offset=".5" stop-color="#18211e" stop-opacity=".12"/><stop offset="1" stop-color="#101716" stop-opacity=".64"/>'
            axis='x2="0" y2="1"' if horizontal else 'x2="1" y2="0"'
            boundary=[];massset=set(mass)
            for xx,yy in mass:
                px=xx*cell;py=yy*cell
                for neighbor,d in (((xx,yy-1),f'M{px} {py}h{cell}'),((xx,yy+1),f'M{px} {py+cell}h{cell}'),
                                   ((xx-1,yy),f'M{px} {py}v{cell}'),((xx+1,yy),f'M{px+cell} {py}v{cell}')):
                    if neighbor not in massset:boundary.append(d)
            eaves=''.join(boundary)
            out.append(f'<defs><clipPath id="{ident}">{rects}</clipPath><linearGradient id="{ident}-slope" x1="0" y1="0" {axis}>{stops}</linearGradient></defs><g class="painted-roof" clip-path="url(#{ident})">'
                       f'<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" fill="url(#painted-roof-{i})"/>'
                       f'<rect class="roof-slope" x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" fill="url(#{ident}-slope)"/>'
                       f'<path d="{eaves}" fill="none" stroke="#111b17" stroke-opacity=".85" stroke-width="6"/>'
                       f'<path d="{hips}" fill="none" stroke="#161b18" stroke-opacity=".65" stroke-width="4"/>'
                       f'<path d="{hips}" fill="none" stroke="#c2aa83" stroke-opacity=".6" stroke-width="1"/>'
                       f'<path d="{ridge}" stroke="#141c18" stroke-width="7" stroke-linecap="round"/>'
                       f'<path d="{ridge}" stroke="#baa17d" stroke-width="3" stroke-linecap="round"/></g>')
    return ''.join(out)

def prune_patterns(svg):
    """Drop unused painted texture patterns before collecting their embedded images."""
    used=set(re.findall(r'url\(#(painted-(?:surface|floor|roof)-\d+)\)',svg))
    return re.sub(r'<pattern id="(painted-(?:surface|floor|roof)-\d+)"[^>]*>.*?</pattern>',
                  lambda m:m.group(0) if m.group(1) in used else '',svg,flags=re.S)

def definitions(svg):
    """Embed each used object once, even in a hall with dozens of chairs."""
    keys=sorted(set(re.findall(r'href="#painted-([a-z0-9-]+)-(\d+)"',svg)))
    return '<defs>'+''.join(f'<symbol id="painted-{col}-{i}" viewBox="0 0 256 256"><image href="{uri(col,int(i))}" width="256" height="256"/></symbol>' for col,i in keys if uri(col,int(i)))+'</defs>'

PROPS={'wooden-crate':('environment',2),'book-pile':('environment',9),'pentacle':('environment',10),
       'candle-holder':('environment',11),'round-bottom-flask':('utility',5),'cooking-pot':('furniture',11),
       'bird-cage':('utility',0),'drama-masks':('utility',1),'dress':('utility',2),'quill':('utility',3),
       'wine-bottle':('utility',4),'gems':('utility',6),'scales':('utility',7),'target-dummy':('utility',8),
       'snake':('utility',9),'serpent':('utility',9),'empty-wood-bucket':('utility',10),
       'crossed-chains':('utility',11),'torch':('utility',12),'fur-shirt':('utility',14),'trophy':('utility',15)}
PROPS.update({name:('interior-small-props-v2',index) for name,index in {
    'open-book':0,'bandage-roll':1,'bread':2,'beer-stein':3,'rolling-dice-cup':4,'chess-knight':5,
    'lipstick':6,'crossed-swords':7,'black-book':8,'rope-coil':9,'hunting-horn':10,
    'full-wood-bucket':11,'broken-bottle':12,'broken-ribbon':13,'kebab-spit':14,'wheat':15}.items()})
PROPS.update({name:('outdoor-props-v2',index) for name,index in {
    'sheep':0,'horse-head':2,'raven':3,'old-wagon':4,'wagon':5,'camping-tent':6,'sleeping-bag':7,
    'hut':8,'rake':9,'axe-in-log':10,'water-mill':11,'tattered-banner':12,'hay':13,'saddle':14,'barrier':15}.items()})
PROPS.update({'tavern-sign':('interior-details-v2',6),'eye-target':('interior-details-v2',12),
    'brass-eye':('interior-details-v2',12),'all-seeing-eye':('interior-details-v2',12),
    'ringing-bell':('interior-details-v2',13),'locked-chest':('interior-storage-v2',3),
    'candles':('environment',11),'throne-king':('furniture',14),
    'rug':('interior-decor-v2',0),'hide':('interior-decor-v2',3),'bust':('interior-decor-v2',5),
    'globe':('interior-decor-v2',7),'harp':('interior-decor-v2',8),'lute':('interior-decor-v2',9),
    'mirror':('interior-decor-v2',10),'kettle':('interior-decor-v2',13),'herbs':('interior-decor-v2',15)})

def fire_state(pr):
    if not any(w in pr.get('icon','') for w in ('fire','flame','burning','torch')):return None
    if pr.get('lit') is False:return 'cold'
    name=str(pr.get('name','')).lower()
    if any(w in name for w in ('cold','unlit','extinguished','burnt-out','burned-out')):return 'cold'
    if any(w in name for w in ('smoulder','smolder','dying embers')):return 'embers'
    return 'burning'

def prop(pr,cell):
    match=PROPS.get(pr.get('icon'))
    name=str(pr.get('name','')).lower()
    if fire_state(pr) in ('cold','embers'):
        match=('utility',13)
    if not match:return ''
    size=cell*{'small':.62,'large':1.05}.get(pr.get('size'),.9)
    return sprite(*match,(pr['x']+.5)*cell-size/2,(pr['y']+.5)*cell-size/2,size,rotation=pr.get('rotate',0))

def corpse_selection(e):
    """Identity is a hard boundary; clothing and colour only rank compatible bodies."""
    from . import art
    identity=art.visual_identity(e);humanlike=art.is_humanlike(e)
    records=identity_catalogue('corpses')
    if humanlike:
        L=art.look_of(e)
        candidates=[r for r in records if r['species']==identity['species'] and r['presentation']==identity['presentation']]
        chosen=art.portrait_choice(e)
        face=portrait_records().get(chosen,{})
        skin=(art.DRAGON_SCALES.get(face.get('skin')) if identity['species']=='Dragonborn' else None) or art.SKIN_TONES.get(face.get('skin')) or L.get('skin')
        outfit=face.get('outfit') or L['outfit']
        outfit='armor' if outfit in ('plate','chain') else 'robe' if outfit in ('robe','vestments','druid','monk') else 'leather' if outfit in ('leather','furs') else 'work'
        def score(r):
            colour=_color_distance(skin,r.get('skin_hex'))
            return (0 if r['outfit']==outfit else 1)+colour*12
    else:
        # Stat block/declared species take priority over nicknames such as "Dragon Slayer".
        names=[identity['species'].lower()] if identity['species_source']!='unspecified' else [str(e.get('srd_name') or e.get('type') or e.get('name') or '').lower()]
        candidates=[]
        for name in names:
            hits=[r for r in records if any(re.search(r'\b'+re.escape(alias)+r'\b',name) for alias in r.get('aliases',[]))]
            if hits:
                specificity=max(max(len(alias) for alias in r.get('aliases',[]) if re.search(r'\b'+re.escape(alias)+r'\b',name)) for r in hits)
                candidates=[r for r in hits if any(len(alias)==specificity and re.search(r'\b'+re.escape(alias)+r'\b',name) for alias in r.get('aliases',[]))]
                break
        # Undead human forms still obey presentation; anatomy-neutral animals do not.
        candidates=[r for r in candidates if r['presentation'] in ('any',identity['presentation'])]
        def score(r):
            size=str(e.get('size','Medium')).lower()
            return 0 if r.get('size','medium')==size else 1
    if not candidates:return None
    record=min(candidates,key=lambda r:(score(r),hashlib.sha256(f"{art._art_id(e)}:{r['collection']}:{r['index']}".encode()).hexdigest()))
    return (record['collection'],record['index']) if uri(record['collection'],record['index']) else None


def corpse(e,cx,cy,diameter):
    chosen=corpse_selection(e)
    angle=int(hashlib.sha256(e['id'].encode()).hexdigest()[:2],16)%70-35
    if chosen:return sprite(*chosen,cx-diameter/2,cy-diameter/2,diameter,rotation=angle)
    from . import art,assets
    if not art.is_humanlike(e):
        body=assets.icon_body(art.creature_icon(e))
        return f'<g class="corpse-anatomical-fallback" transform="translate({cx-diameter/2} {cy-diameter/2}) scale({diameter/512})" color="#8f8c71" fill="#8f8c71" opacity=".9">{body}</g>'
    # Uncatalogued anatomy gets a neutral covered silhouette, never another species' body.
    d=diameter
    return (f'<g class="corpse-fallback" transform="translate({cx} {cy}) rotate({angle})">'
            f'<path d="M{-d*.12} {-d*.35}Q{-d*.3} {-d*.24} {-d*.2} {d*.12}L{-d*.1} {d*.4}Q0 {d*.46} {d*.16} {d*.3}L{d*.22} {-d*.12}Q{d*.3} {-d*.28} {d*.12} {-d*.35}Z" fill="#938d73" stroke="#403e30" stroke-width="1.2"/>'
            f'<path d="M{-d*.1} {-d*.23}Q{d*.16} 0 {-d*.04} {d*.32}" fill="none" stroke="#bab298" stroke-opacity=".6" stroke-width="1"/></g>')

EQUIPMENT={'sword':0,'rapier':1,'axe':2,'crossbow':3,'potion':4,'amulet':5,'holy':5,'book':6,'key':7,
           'shield':8,'helm':9,'boots':10,'cloak':11,'scroll':12,'wand':13,'coin':14,'gem':15}
