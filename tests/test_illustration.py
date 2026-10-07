"""Renderer regressions: illustrations are deterministic, fast to reuse, and read-only."""
import copy
import random
import unittest
import xml.etree.ElementTree as ET

from engine import art, illustration, maps, render


class IllustrationTest(unittest.TestCase):
    def test_every_theme_and_map_keeps_valid_svg_and_does_not_mutate_inputs(self):
        for m in (maps.gen_wilderness(12), maps.gen_cave(22), maps.gen_dungeon(33), maps.gen_region(8),
                  *(maps.gen_interior(19, kind=k) for k in ('tavern','temple','bathhouse','manor','library','workshop'))):
            m['id'] = 'test-map'
            before = copy.deepcopy(m)
            svg = render.render_map(m)
            ET.fromstring(svg)
            self.assertEqual(m, before)
            self.assertEqual(svg, render.render_map(m))

    def test_decoration_does_not_consume_global_rng(self):
        state = random.getstate()
        illustration.tree(0,0,32,'test')
        illustration.rock(0,0,32,'test')
        illustration.terrain_defs()
        illustration.natural_materials([':::','w~w',',,,'],32)
        self.assertEqual(state, random.getstate())

    def test_forest_reuses_symbols_and_has_no_per_tree_filters(self):
        defs = illustration.terrain_defs()
        ET.fromstring('<svg>' + defs + '</svg>')
        self.assertEqual(defs.count('id="art-tree-'),8)
        for i in range(100):
            node = illustration.tree(i*32,32,32,i)
            self.assertIn('<use ',node)
            self.assertNotIn('filter=',node)
            self.assertLess(len(node),200)
        self.assertIs(illustration.terrain_defs(), illustration.terrain_defs())

    def test_unseen_tree_cannot_spill_art_into_revealed_square(self):
        m = maps.new_map('wilderness','Test',3,3,fill=',',seed=8)
        m.update(id='test',grid=[',T,',',,,',',,,'],fog=True,revealed=['000','111','111'])
        svg = render.render_map(m)
        self.assertNotIn('href="#art-tree-',svg)
        self.assertNotRegex(svg, 'href="#painted-tree-[0-3]"')
        self.assertIn('id="fog"',svg)

    def test_material_union_handles_holes_and_diagonal_islands(self):
        for grid in ([':,:',',:,',':,:'], ['::: ', ':,: ', '::: '], [':::',':::',':::'], ['w~w','~~~','w~w']):
            path = illustration._material_path(grid, ':w~',32)
            self.assertTrue(path.endswith('Z'))
            self.assertIn(' Q',path)
            ET.fromstring('<svg>' + illustration.natural_materials(grid,32) + '</svg>')
        self.assertEqual(illustration._material_path([',,,'],':',32),'')

    def test_hidden_creature_art_remains_omitted(self):
        m = maps.new_map('wilderness','Test',3,3,fill=',',seed=8)
        m['id'] = 'test'
        e = dict(id='hidden-monster',name='Hidden Monster',kind='npc',type='beast',hidden=True,
                 token=dict(map='test',x=1,y=1))
        svg = render.render_map(m,entities=[e])
        self.assertNotIn('Hidden Monster',svg)
        self.assertNotIn('data-id="hidden-monster"',svg)

    def test_anatomical_creature_studies_and_fallback_are_valid(self):
        for name, typ in (('Dire Wolf','beast'),('Mastiff','beast'),('Adult Red Dragon','dragon'),('Ochre Jelly','ooze')):
            e = dict(id='test',kind='npc',name=name,srd_name=name,type=typ,size='Large',side='enemy')
            svg = art.portrait_svg(e)
            ET.fromstring(svg)
            ET.fromstring(art.face_svg(e))
            self.assertEqual(svg,art.portrait_svg(e))
            self.assertIn('painted-portrait',svg)

    def test_visual_updates_remain_versioned(self):
        e = dict(id='test',kind='pc',name='Test',species='Human',classes={'Fighter':1},inventory=[],bio={})
        before = copy.deepcopy(e)
        version = art.art_version(e)
        art.portrait_svg(e)
        self.assertEqual(e,before)
        self.assertNotEqual(version,art.art_version(dict(e,look={'hair':'long red braid'})))
        self.assertNotIn('<animate',render.tokens_svg(dict(id='test'),[
            dict(e,token={'map':'test','x':0,'y':0})],'test',32,True))
