"""Read-only rendering fidelity: no fog leaks, distinct conditions, reusable painted assets."""
import copy
import types
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
from engine import art, maps, painted, render, views
from engine.core import empty_state

class VisualStatesTest(unittest.TestCase):
    def entity(self,**kw):
        return dict(id='scout',kind='npc',name='Scout',type='humanoid',side='enemy',hp=4,hp_max=4,
                    token=dict(map='study',x=1,y=1),**kw)

    def test_missing_reveals_fail_closed_and_hidden_points_never_show(self):
        m=maps.new_map('interior','Study',4,4,fill='.',seed=1)
        m.update(id='study',fog=True,revealed=[],pois=[dict(id='secret',name='Secret cache',x=1,y=1,hidden=True)])
        svg=render.render_map(m,entities=[self.entity()])
        root=ET.fromstring(svg)
        self.assertNotIn('data-id="scout"',svg)
        self.assertNotIn('Secret cache',svg)
        fog=next(n for n in root.iter() if n.get('id')=='fog')
        self.assertEqual(len(fog),4)

    def test_fog_hides_sidebar_initiative_and_coordinate_cues(self):
        s=empty_state();m=maps.new_map('interior','Study',4,4,fill='.',seed=1)
        m.update(id='study',fog=True,revealed=['1100']*4,shown=True)
        e=self.entity();hidden=dict(e,id='unseen',name='Secret beast',token=dict(map='study',x=3,y=1))
        s['entities']={'scout':e,'unseen':hidden};s['maps']={'study':m};s['view']['map']='study'
        g=types.SimpleNamespace(state=s,events=[])
        before=copy.deepcopy(s)
        self.assertTrue(views._seen(g,e));self.assertFalse(views._seen(g,hidden))
        self.assertFalse(views.seen_by_players(g,hidden))
        self.assertEqual([x['id'] for x in views.player_view(g)['others']],['scout'])
        feed=[dict(seq=1,kind='fx',fx='ring',at=[3,1],map='study'),dict(seq=2,kind='fx',fx='ring',at=[1,1],map='study')]
        self.assertEqual([c['seq'] for c in views.animation_cues(g,feed)],[2])
        self.assertEqual(s,before)

    def test_effect_clip_and_weather_exposure_match_revealed_ground(self):
        m=maps.new_map('interior','Study',4,3,fill='.',seed=1)
        m.update(id='study',grid=[',,..',',,..','....'],fog=True,revealed=['1000','1100','1100'])
        root=ET.fromstring(render.render_map(m))
        weather=next(n for n in root.iter() if n.get('id')=='weather-exposure')
        self.assertEqual([(r.get('width'),r.get('y')) for r in weather],[('32','0'),('64','32')])
        self.assertTrue(any(n.get('id')=='revealed-area' for n in root.iter()))
        m.update(grid=['wwbb','ww~~','zzqq'],fog=False)
        root=ET.fromstring(render.render_map(m))
        self.assertEqual(len(next(n for n in root.iter() if n.get('id')=='weather-exposure')),0)

    def test_creature_http_routes_cannot_reveal_fogged_creatures(self):
        import threading,urllib.request,urllib.error
        from http.server import ThreadingHTTPServer
        from engine import server
        s=empty_state();m=maps.new_map('interior','Study',4,4,fill='.',seed=1)
        m.update(id='study',fog=True,revealed=['1000']*4,shown=True)
        e=self.entity();s['entities']={'scout':e};s['maps']={'study':m}
        g=types.SimpleNamespace(state=s,events=[])
        with patch.object(server,'game',return_value=(g,None)):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
            try:
                for route in ('/api/creature/scout','/api/card/creature/scout','/api/art/face/scout.svg'):
                    with self.assertRaises(urllib.error.HTTPError) as raised:
                        urllib.request.urlopen(f'http://127.0.0.1:{httpd.server_port}'+route)
                    self.assertEqual(raised.exception.code,404)
            finally:
                httpd.shutdown();httpd.server_close();thread.join()

    def test_death_unconsciousness_and_petrification_are_distinct(self):
        m=maps.new_map('battle','Study',5,5,fill='.',seed=1);m['id']='study'
        base=self.entity();base['portrait_href']='data:image/svg+xml;base64,PHN2Zy8+'
        corpse=dict(base,dead=True,hp=0)
        svg=render.render_map(m,entities=[corpse]);ET.fromstring(svg)
        self.assertIn('class="token dead corpse"',svg);self.assertIn('#painted-corpses-',svg)
        self.assertNotIn('stroke="#d9443b" stroke-width="2"',svg)
        down=dict(base,hp=0,conditions=[dict(name='unconscious')])
        svg=render.render_map(m,entities=[down]);self.assertIn('down-state',svg);self.assertNotIn('token dead corpse',svg)
        self.assertEqual(views.status_band(down),'Unconscious');self.assertEqual(views.status_band(corpse),'Dead')
        stone=dict(base,conditions=[dict(name='petrified')]);svg=render.render_map(m,entities=[stone])
        self.assertIn('filter="url(#petrified-face)"',svg)
        self.assertIn('class="condition-badge" data-condition="petrified"',svg)
        self.assertIn('color="#e8d7a8"',svg)

    def test_each_lighting_state_is_visible_without_changing_map(self):
        for light in ('bright','dim','dark'):
            m=maps.new_map('interior','Study',4,4,fill='.',seed=1);m.update(id='study',lighting=light)
            before=copy.deepcopy(m);svg=render.render_map(m)
            self.assertIn(f'data-lighting="{light}"',svg)
            self.assertEqual('lighting-shade' in svg,light!='bright');self.assertEqual(m,before)

    def test_cold_fire_uses_unlit_asset_and_repeated_furniture_embeds_once(self):
        pr=dict(icon='campfire',name='Cold unlit hearth',x=1,y=1)
        self.assertIn('#painted-utility-13',painted.prop(pr,32));self.assertNotIn('firelight',painted.prop(pr,32))
        m=maps.new_map('interior','Study',8,8,fill='C',seed=1);m['id']='study'
        svg=render.render_map(m)
        self.assertEqual(svg.count('id="painted-furniture-2"'),1)
        self.assertEqual(svg.count('href="#painted-furniture-2"'),64)

    def test_portrait_bases_match_species_gender_and_explicit_details(self):
        self.assertNotIn('age',art.read_description('His knuckles show old breaks and old scars.'))
        self.assertEqual(art.read_description('An old man with silver hair.')['age'],'old')
        self.assertEqual(art.read_description('Silver hair tied back; his coat is going bald at the elbows.')['hair_style'],'ponytail')
        e=dict(id='scholar',name='Scholar',kind='pc',species='Human',classes={'Wizard':1},inventory=[],
               bio={'appearance':'Masculine, silver hair tied back, half-moon spectacles, burgundy robe.'})
        svg=art.portrait_svg(e);self.assertIn('painted-portrait',svg)
        self.assertTrue(painted.uri('portraits-extra',2) in svg)
        e.update(id='artisan',bio={'appearance':'Feminine, black hair in a knot, plain gray dress.'})
        svg=art.face_svg(e);self.assertTrue(painted.uri('portraits-extra',1) in svg)
        for sp in ('Human','Elf','Dwarf','Orc','Halfling','Gnome','Tiefling','Dragonborn','Goliath'):
            for p in ('feminine','masculine'):
                e.update(species=sp,look={'presentation':p})
                self.assertIn('painted-face',art.face_svg(e))

    def test_joined_furniture_and_versioned_assets_resolve_without_mutation(self):
        m=maps.new_map('interior','Study',7,4,fill='.',seed=1)
        m.update(id='study',theme='timber',grid=['AAAA...', '....K..','....K..','....K..'])
        before=copy.deepcopy(m)
        svg=render.render_map(m);root=ET.fromstring(svg)
        joined=[n for n in root.iter() if n.get('class')=='painted-joined']
        self.assertEqual(len(joined),2)
        self.assertEqual(joined[0].get('width'),'124.0')
        ids={n.get('id') for n in root.iter()}
        for n in root.iter():
            href=n.get('href','')
            if href.startswith('#painted-'):self.assertIn(href[1:],ids)
        self.assertEqual(m,before)

    def test_roofs_keep_doorways_clear_and_weather_excludes_building_floors(self):
        for kind in ('town','battle','wilderness'):
            m=maps.new_map(kind,'Study',5,3,fill='.',seed=1)
            m.update(id='study',fog=False,grid=['BBDBB','._,_=','.....'])
            before=copy.deepcopy(m);root=ET.fromstring(render.render_map(m))
            roofclips=[n for n in root.iter() if n.tag.endswith('clipPath') and n.get('id','').startswith('roof-')]
            self.assertEqual(len(roofclips),2)
            self.assertFalse(any(r.get('x')=='64' for clip in roofclips for r in clip))
            weather=next(n for n in root.iter() if n.get('id')=='weather-exposure')
            self.assertEqual([(r.get('x'),r.get('y'),r.get('width')) for r in weather],[('32','32','96')])
            self.assertEqual(m,before)

    def test_regional_landmarks_embed_and_routes_pass_exact_waypoints(self):
        m=maps.gen_region(75,w=32,h=24,name='Borderlands')
        svg=render.render_map(m);root=ET.fromstring(svg)
        self.assertTrue(any(n.get('class')=='regional-biome' for n in root.iter()))
        self.assertIn('id="painted-regional-landmarks-v2-',svg)
        route=render._smooth_route([(0,0),(2,3),(4,0)],8)
        self.assertTrue(route.startswith('M4.0 4.0'));self.assertIn('20.0 28.0',route)
        self.assertTrue(route.endswith('36.0 4.0'))

    def test_cold_hearth_is_dark_while_burning_prop_lights_the_room(self):
        m=maps.new_map('interior','Study',4,3,fill='.',seed=1)
        m.update(id='study',fog=False,lighting='dark',grid=['.f..','....','....'],props=[
            dict(id='cold',icon='campfire',name='Cold unlit hearth',x=1,y=0),
            dict(id='lit',icon='campfire',name='Burning fire',x=3,y=2)])
        svg=render.render_map(m);root=ET.fromstring(svg)
        mask=next(n for n in root.iter() if n.get('id')=='room-shadow')
        self.assertEqual([(n.get('cx'),n.get('cy')) for n in mask if n.tag.endswith('circle')],[('112.0','80.0')])
        self.assertIn('#painted-interior-details-v2-14',svg)

    def test_weather_separates_indoor_pool_from_outdoor_river(self):
        grid=[',ww##',',ww##','#####','#ww.#','#####']
        exposed=render.weather_cells(grid,'interior')
        self.assertIn((1,0),exposed)
        self.assertNotIn((1,3),exposed)
        self.assertNotIn((2,3),exposed)

    def test_explicit_wall_hatching_retains_footprint_with_theme_material(self):
        m=maps.new_map('wilderness','Study',4,3,fill=',',seed=1)
        m.update(id='study',theme='timber',style_walls='hatch',grid=['####','#..#','####'])
        before=copy.deepcopy(m);svg=render.render_map(m)
        self.assertIn('href="#painted-wall-materials-v2-1"',svg)
        self.assertEqual(m,before)
        m['theme']='stone';svg=render.render_map(m)
        self.assertIn('fill="url(#painted-surface-0)"',svg)

if __name__=='__main__':unittest.main()
