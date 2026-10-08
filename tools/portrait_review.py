"""Read-only production portrait gallery and persistence evidence. No campaign mutations."""
import base64
import copy
import html
import json
import sys
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from engine import art,painted,portrait_profiles

def uri(svg):return 'data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode()
def entity(record,n):
    e=dict(id=f'portrait-review-{n}',name='Traveller',kind='npc',type='humanoid',species=record['species'],
           look={k:record[k] for k in ('presentation','skin','outfit','age')})
    e['portrait_profile']=portrait_profiles.capture(e)
    e['portrait_profile']['choice']=[record['collection'],record['index']]
    e['portrait_profile']['mode']='painted'
    return e

def card(e,label):
    return f'<figure><img width="256" height="256" src="{uri(art.portrait_svg(e))}"><div><img width="64" height="64" src="{uri(art.face_svg(e))}"></div><figcaption>{html.escape(label)}</figcaption></figure>'

def page(group):
    records=[r for r in painted.identity_catalogue('portraits') if r['collection'].endswith('-v5')]
    groups=list(dict.fromkeys(r['collection'] for r in records))
    nav=''.join(f'<a href="/{n}">{html.escape(g.replace("portraits-",""))}</a>' for n,g in enumerate(groups))+'<a href="/proof">Stable identities</a><a href="/company">Men-at-arms variety</a>'
    if group=='proof':
        e=dict(id='subject-proof',name='Townswoman',kind='npc',type='humanoid',appearance='A human woman with brown skin and braided dark hair.')
        e['portrait_profile']=portrait_profiles.capture(e)
        later=dict(e,appearance='An orc grabbed her. The dwarf captain shouted nearby.')
        cards=card(e,'Original appearance')+card(later,'Scene update: same face')
        title='A face belongs to its character'
        extra='<p>The appearance text now describes an Orc and a Dwarf acting nearby. The subject retains her original Human identity and selected face.</p>'
        assert art.face_svg(e)==art.face_svg(later)
    elif group=='company':
        samples=[]
        for n in range(48):
            e=dict(id=f'company-{n}',name='Man-at-arms',kind='npc',type='humanoid',appearance='A human man.',look={'outfit':('plate','leather','tunic','chain')[n%4]})
            e['portrait_profile']=portrait_profiles.capture(e);samples.append(e)
        choices={art.portrait_choice(e) for e in samples}
        cards=''.join(card(e,f'Man-at-arms {n+1}') for n,e in enumerate(samples))
        title='A company with individual faces';extra=f'<p>48 masculine soldiers · {len(choices)} distinct selected portraits.</p>'
    else:
        group=int(group);name=groups[group]
        subset=[r for r in records if r['collection']==name]
        cards=''.join(card(entity(r,n),f'{r["index"]:02d} · {r["age"]} · {r["outfit"]}') for n,r in enumerate(subset))
        title=name.replace('portraits-','').replace('-',' ').title();extra='<p>Full production portrait and its map face. Each base is pinned explicitly for this visual review.</p>'
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Portrait visual review</title>
    <style>body{{margin:0;padding:24px;background:#141b19;color:#e4d5b4;font:16px Georgia}}h1{{margin:12px 0}}nav{{display:flex;gap:8px;flex-wrap:wrap}}a{{color:#c5b887;border:1px solid #536052;padding:5px;font-size:12px}}main{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}}figure{{margin:0;padding:12px;background:#202923;border:1px solid #716447;text-align:center}}figure>img{{width:100%;max-width:256px;height:auto}}figcaption{{margin-top:8px;font-size:14px}}</style>
    <nav>{nav}</nav><h1>{title}</h1>{extra}<main>{cards}</main></html>'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:body=page(self.path.strip('/') or '0').encode()
        except (ValueError,IndexError):self.send_error(404);return
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass

if __name__=='__main__':
    print('Portrait review at http://localhost:8770',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8770),Handler).serve_forever()
