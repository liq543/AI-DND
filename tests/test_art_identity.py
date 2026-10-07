"""Identity invariants across live faces, body assets and the DM's read-only helper."""
import copy
import random
import unittest
import xml.etree.ElementTree as ET
from engine import art, painted, maps, render


class ArtIdentityTest(unittest.TestCase):
    def entity(self,**kw):
        return dict(dict(id='artisan',name='Artisan',kind='npc',srd_name='Commoner',type='humanoid',side='neutral',appearance=''),**kw)

    def body_record(self,e):
        pair=painted.corpse_selection(e)
        self.assertIsNotNone(pair)
        return next(r for r in painted.identity_catalogue('corpses') if (r['collection'],r['index'])==pair)

    def test_structured_npc_species_and_gender_override_role_and_name(self):
        e=self.entity(name='The Orc Hunter',srd_name='Guard',species='Human',gender='female')
        before=copy.deepcopy(e)
        self.assertEqual(art.species_of(e),'Human')
        self.assertEqual(art.visual_identity(e)['presentation'],'feminine')
        self.assertEqual(self.body_record(e)['species'],'Human')
        self.assertEqual(self.body_record(e)['presentation'],'feminine')
        self.assertEqual(e,before)

    def test_every_supported_humanoid_keeps_species_and_presentation_when_dead(self):
        for species in ('Human','Elf','Dwarf','Orc','Tiefling','Halfling','Gnome','Dragonborn','Goliath',
                        'Goblin','Hobgoblin','Kobold','Lizardfolk','Ogre','Troll','Bugbear','Zombie'):
            for gender,pres in [('male','masculine'),('female','feminine'),('nonbinary','androgynous')]:
                with self.subTest(species=species,presentation=pres):
                    e=self.entity(species=species,gender=gender)
                    face=painted.portrait_records()[art.portrait_choice(e)]
                    body=self.body_record(e)
                    self.assertEqual((face['species'],face['presentation']),(species,pres))
                    self.assertEqual((body['species'],body['presentation']),(species,pres))
                    svg=art.face_svg(e);ET.fromstring(svg)
                    self.assertIn(f'data-species="{species}"',svg)

    def test_subject_identity_cues_and_explicit_pins(self):
        for text,pres in [('A female Elf guard.','feminine'),('A male dwarf in robes.','masculine'),
                          ('A man with a scar; his daughter wears a green dress.','masculine'),
                          ('A woman who watches her brother.','feminine'),('They wear practical mail.','androgynous')]:
            self.assertEqual(art.read_description(text)['presentation'],pres)
        e=self.entity(appearance='A female elf.',look=dict(species='orc',presentation='male'))
        self.assertEqual(art.visual_identity(e)['species'],'Orc')
        self.assertEqual(art.visual_identity(e)['presentation'],'masculine')
        self.assertTrue(art.identity_report(e)['warnings'])

    def test_unspecified_presentation_is_neutral_and_clothing_does_not_assign_it(self):
        for outfit in ('A dress.','Long hair and a robe.','Plate armor and a cloak.'):
            e=self.entity(species='Dwarf',appearance=outfit)
            identity=art.visual_identity(e)
            self.assertEqual(identity['presentation'],'androgynous')
            self.assertEqual(identity['presentation_source'],'unspecified')
            self.assertEqual(painted.portrait_records()[art.portrait_choice(e)]['presentation'],'androgynous')
            self.assertEqual(self.body_record(e)['presentation'],'androgynous')

    def test_pin_overrides_bio_identity_and_cache_version_changes(self):
        e=self.entity(bio=dict(species='Elf',gender='female',appearance='A pale woman.'))
        self.assertEqual(art.species_of(e),'Elf')
        self.assertEqual(art.visual_identity(e)['presentation'],'feminine')
        for field,value in [('gender','male'),('race','Orc'),('pronouns','he/him')]:
            changed=dict(e,**{field:value});self.assertNotEqual(art.art_version(e),art.art_version(changed))
        changed=copy.deepcopy(e);changed['bio']['gender']='male'
        self.assertNotEqual(art.art_version(e),art.art_version(changed))

    def test_named_beasts_use_own_species_not_a_wolf_or_a_nickname(self):
        for name,expected in [('Giant Rat','Rat'),('Owlbear','Owlbear'),('Pony','Horse'),('Mule','Mule'),('Giant Spider','Spider'),('Mastiff','Mastiff')]:
            e=self.entity(srd_name=name,name='Troll' if name=='Mastiff' else 'Dragon Slayer',type='beast')
            self.assertFalse(art.is_humanlike(e))
            self.assertEqual(self.body_record(e)['species'],expected)
            face=painted.portrait_records()[art.portrait_choice(e)]
            self.assertEqual(face['species'],expected)

    def test_dragon_colour_is_exact_or_falls_back_without_red_substitution(self):
        for colour in ('Red','Blue','Gold'):
            e=self.entity(srd_name=colour+' Dragon',type='dragon',size='Huge')
            self.assertEqual(self.body_record(e)['species'],colour+' Dragon')
            self.assertEqual(painted.portrait_records()[art.portrait_choice(e)]['species'],colour+' Dragon')
        for colour in ('White','Black','Green','Silver'):
            e=self.entity(srd_name=colour+' Dragon',type='dragon',size='Huge')
            self.assertIsNone(painted.corpse_selection(e))
            self.assertIsNone(art.portrait_choice(e))
            self.assertIn('corpse-anatomical-fallback',painted.corpse(e,16,16,32))

    def test_sex_specific_animal_traits_remain_compatible(self):
        for species in ('Lion','Deer'):
            for gender,pres in [('male','masculine'),('female','feminine'),('nonbinary','androgynous')]:
                e=self.entity(srd_name=species,type='beast',gender=gender)
                self.assertEqual(self.body_record(e)['presentation'],pres)
                self.assertEqual(painted.portrait_records()[art.portrait_choice(e)]['presentation'],pres)

    def test_creature_pins_and_unsupported_stat_blocks_never_fall_through_to_nicknames(self):
        e=self.entity(srd_name='Black Dragon',name='Red Dragon Hunter',type='dragon')
        self.assertIsNone(art.portrait_choice(e))
        self.assertIsNone(painted.corpse_selection(e))
        e['look']={'species':'Blue Dragon'}
        self.assertEqual(self.body_record(e)['species'],'Blue Dragon')
        self.assertEqual(painted.portrait_records()[art.portrait_choice(e)]['species'],'Blue Dragon')
        cat=self.entity(srd_name='Wolf',type='beast',look={'species':'Cat'})
        self.assertIsNone(painted.corpse_selection(cat))
        self.assertIsNone(art.portrait_choice(cat))
        self.assertEqual(art.creature_icon(cat),'cat')

    def test_female_orc_and_dragonborn_never_become_human_or_dragon(self):
        for sp in ('Orc','Dragonborn'):
            e=self.entity(kind='pc',species=sp,classes={'Fighter':1},inventory=[],bio={'gender':'female'})
            self.assertEqual(self.body_record(e)['species'],sp)
            self.assertEqual(self.body_record(e)['presentation'],'feminine')

    def test_dark_human_and_drow_keep_skin_family_across_face_and_body(self):
        e=self.entity(species='Human',gender='female',appearance='A woman with deep dark skin in white robes.')
        face=painted.portrait_records()[art.portrait_choice(e)]
        self.assertIn(face['skin'],('dark','brown'))
        self.assertIn(self.body_record(e)['skin'],('dark','brown'))
        e=self.entity(srd_name='Drow',gender='male')
        self.assertEqual(painted.portrait_records()[art.portrait_choice(e)]['skin'],'dark')
        self.assertEqual(self.body_record(e)['skin'],'dark')

    def test_helpers_and_death_render_do_not_change_state_or_rules_rng(self):
        e=self.entity(species='Elf',gender='female',dead=True,token=dict(map='study',x=1,y=1))
        m=maps.new_map('battle','Study',4,4,fill=',',seed=1);m['id']='study'
        before=copy.deepcopy((m,e));rng=random.getstate()
        art.identity_report(e);render.render_map(m,entities=[e])
        self.assertEqual((m,e),before);self.assertEqual(random.getstate(),rng)

    def test_missing_compatible_asset_never_crosses_identity_boundary(self):
        e=self.entity(species='Custom Folk',gender='female')
        self.assertIsNone(art.portrait_choice(e));self.assertIsNone(painted.corpse_selection(e))
        self.assertIn('corpse-fallback',painted.corpse(e,16,16,32))
        self.assertTrue(art.identity_report(e)['warnings'])

    def test_pinned_portrait_is_flagged_for_manual_identity_review(self):
        report=art.identity_report(self.entity(species='Human',gender='male',portrait='custom-image'))
        self.assertTrue(any('Pinned portrait' in w for w in report['warnings']))

if __name__=='__main__':unittest.main()
