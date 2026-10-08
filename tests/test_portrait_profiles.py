"""Faces are stable identity records, not interpretations of changing scene narration."""
import copy
import unittest
from engine import art,painted,portrait_profiles
from engine.core import empty_state,apply

class PortraitProfileTest(unittest.TestCase):
    def entity(self,**kw):
        return dict(dict(id='townswoman',name='Townswoman',kind='npc',type='humanoid',srd_name='Commoner',appearance='A young human townswoman with brown hair.'),**kw)

    def test_description_changes_leave_face_body_and_cache_key_unchanged(self):
        e=self.entity();e['portrait_profile']=portrait_profiles.capture(e)
        baseline=(art.visual_identity(e)['species'],art.visual_identity(e)['presentation'],art.portrait_choice(e),painted.corpse_selection(e),art.art_version(e),art.face_svg(e))
        for desc in ('An orc grabbed her and pulled her through the doorway.',
                     'The dwarf captain speaks to this woman. She wears a red cape now.',
                     'A shaken woman with her elf friend beside her.'):
            changed=dict(e,appearance=desc)
            self.assertEqual(baseline,(art.visual_identity(changed)['species'],art.visual_identity(changed)['presentation'],art.portrait_choice(changed),painted.corpse_selection(changed),art.art_version(changed),art.face_svg(changed)))

    def test_second_person_and_later_sentence_do_not_supply_species(self):
        for text in ('A townswoman. An orc grabbed her.', 'A woman seized by an orc.', 'A human woman with an elf brother.', 'A townswoman with an orc beside her.', 'A townswoman in an orc-made apron.', 'A townswoman tending an orc child.', 'A man-at-arms guarding a dwarf prisoner.', 'A washerwoman wearing an elf pendant.'):
            e=self.entity(appearance=text)
            self.assertEqual(art.species_of(e),'Human',text)
            self.assertEqual(art.visual_identity(e)['presentation'],'masculine' if 'man-at-arms' in text else 'feminine',text)

    def test_men_at_arms_and_gendered_names(self):
        for name in ('Men-at-arms','Man-at-arms','Armsman','Spearman','Watchman','Townsman','Father Rhosk','Brother Rhosk','King Rhosk'):
            e=self.entity(name=name,appearance='A mailed fighter. A woman is beside him.')
            self.assertEqual(art.visual_identity(e)['presentation'],'masculine',name)
        self.assertEqual(art.presentation_from('A woman with men-at-arms beside her.'),'feminine')
        for name in ('Mother Rhosk','Sister Rhosk','Queen Rhosk'):
            self.assertEqual(art.presentation_from(name),'feminine')
        self.assertEqual(art.visual_identity(self.entity(name='Guard',appearance='A woman in mail.'))['presentation'],'feminine')

    def test_first_description_establishes_face_then_event_updates_preserve_it(self):
        s=empty_state();e=self.entity(appearance='')
        initial=portrait_profiles.prepare(s,'entity.add',{'entity':e})
        apply(s,dict(type='entity.add',data=initial));self.assertFalse(s['entities'][e['id']]['portrait_profile']['established'])
        update=portrait_profiles.prepare(s,'entity.set',dict(id=e['id'],set={'appearance':'A woman with dark brown skin and braided black hair.'}))
        apply(s,dict(type='entity.set',data=update));before=copy.deepcopy(s['entities'][e['id']]['portrait_profile'])
        update=portrait_profiles.prepare(s,'entity.set',dict(id=e['id'],set={'appearance':'An orc grabbed this person.'}))
        self.assertNotIn('portrait_profile',update['set'])
        apply(s,dict(type='entity.set',data=update));self.assertEqual(before,s['entities'][e['id']]['portrait_profile'])

    def test_explicit_pins_intentionally_change_face_and_body(self):
        s=empty_state();e=self.entity();e['portrait_profile']=portrait_profiles.capture(e);s['entities'][e['id']]=e
        update=portrait_profiles.prepare(s,'entity.set',dict(id=e['id'],set={'look':{'species':'Elf','presentation':'male'}}))
        apply(s,dict(type='entity.set',data=update));changed=s['entities'][e['id']]
        self.assertEqual((art.species_of(changed),art.visual_identity(changed)['presentation']),('Elf','masculine'))
        record=painted.portrait_records()[art.portrait_choice(changed)]
        self.assertEqual((record['species'],record['presentation']),('Elf','masculine'))

    def test_profile_survives_json_and_catalogue_growth(self):
        import json
        e=self.entity();e['portrait_profile']=portrait_profiles.capture(e)
        stored=json.loads(json.dumps(e));self.assertEqual(art.portrait_choice(e),art.portrait_choice(stored))
        self.assertEqual(art.art_version(e),art.art_version(stored))

    def test_migration_uses_earliest_authored_subject_not_latest_story(self):
        events=[dict(type='entity.add',data={'entity':self.entity(appearance='')}),
                dict(type='entity.set',data={'id':'townswoman','set':{'appearance':'A townswoman with dark hair.'}}),
                dict(type='entity.set',data={'id':'townswoman','set':{'appearance':'An orc grabbed her.'}})]
        self.assertEqual(portrait_profiles.original_descriptions(events)['townswoman'],'A townswoman with dark hair.')

    def test_narrative_first_description_does_not_change_known_identity(self):
        e=self.entity(appearance='');s=empty_state()
        apply(s,dict(type='entity.add',data=portrait_profiles.prepare(s,'entity.add',{'entity':e})))
        before=art.portrait_choice(s['entities'][e['id']])
        patch=portrait_profiles.prepare(s,'entity.set',dict(id=e['id'],set={'appearance':'An orc grabbed her.'}))
        apply(s,dict(type='entity.set',data=patch))
        self.assertEqual(art.portrait_choice(s['entities'][e['id']]),before)
        self.assertEqual(art.species_of(s['entities'][e['id']]),'Human')

    def test_whole_bio_patch_can_establish_initial_appearance(self):
        e=self.entity(appearance='');s=empty_state()
        apply(s,dict(type='entity.add',data=portrait_profiles.prepare(s,'entity.add',{'entity':e})))
        patch=portrait_profiles.prepare(s,'entity.set',dict(id=e['id'],set={'bio':{'appearance':'A woman with dark hair.'}}))
        apply(s,dict(type='entity.set',data=patch))
        self.assertTrue(s['entities'][e['id']]['portrait_profile']['established'])

    def test_bio_can_establish_identity_after_an_action_only_description(self):
        e=self.entity(name='Guard',appearance='');s=empty_state()
        apply(s,dict(type='entity.add',data=portrait_profiles.prepare(s,'entity.add',{'entity':e})))
        for patch in ({'appearance':'An orc grabbed this person.'},{'bio.appearance':'A human woman with braided brown hair.'}):
            apply(s,dict(type='entity.set',data=portrait_profiles.prepare(s,'entity.set',dict(id=e['id'],set=patch))))
        self.assertTrue(s['entities'][e['id']]['portrait_profile']['established'])
        self.assertEqual(art.visual_identity(s['entities'][e['id']])['presentation'],'feminine')

    def test_visual_prefix_survives_a_later_action_clause(self):
        for text,pres in [('A young human woman with silver hair who helped the villagers.','feminine'),('A broad-shouldered human man, escorted by a dwarf guard.','masculine')]:
            e=self.entity(name='Citizen',appearance=text);e['portrait_profile']=portrait_profiles.capture(e)
            self.assertTrue(e['portrait_profile']['established'])
            self.assertEqual((art.species_of(e),art.visual_identity(e)['presentation']),('Human',pres))

    def test_removed_and_reused_id_does_not_inherit_previous_person(self):
        events=[dict(type='entity.add',data={'entity':self.entity()}),dict(type='entity.remove',data={'id':'townswoman'}),dict(type='entity.add',data={'entity':self.entity(appearance='')})]
        self.assertNotIn('townswoman',portrait_profiles.original_descriptions(events))

    def test_procedural_choice_is_retained_when_library_grows(self):
        from unittest.mock import patch
        e=self.entity(species='Aasimar');e['portrait_profile']=portrait_profiles.capture(e)
        self.assertIsNone(e['portrait_profile']['choice'])
        with patch.object(painted,'selection',return_value=('portraits-human',4)):
            self.assertIsNone(art.portrait_choice(e))

    def test_retained_unknown_identity_still_reports_missing_facts(self):
        e=self.entity(name='Guard',appearance='');e['portrait_profile']=portrait_profiles.capture(e)
        identity=art.visual_identity(e)
        self.assertEqual(identity['species_source'],'unspecified')
        self.assertEqual(identity['presentation_source'],'unspecified')

    def test_similar_soldiers_use_varied_compatible_faces(self):
        samples=[self.entity(id=f'company-{n}',name='Man-at-arms',appearance='A human man.',look={'outfit':('plate','leather','tunic','chain')[n%4]}) for n in range(48)]
        choices=[art.portrait_choice(e) for e in samples]
        self.assertGreaterEqual(len(set(choices)),16)
        for pair in choices:
            row=painted.portrait_records()[pair]
            self.assertEqual((row['species'],row['presentation']),('Human','masculine'))

    def test_explicit_dark_hair_is_not_replaced_by_a_red_braid(self):
        e=self.entity(appearance='A human woman with brown skin and braided dark hair.')
        row=painted.portrait_records()[art.portrait_choice(e)]
        self.assertIn(row['hair_color'],('black','brown'))

    def test_identity_audit_does_not_flag_another_actor_as_a_transformation(self):
        e=self.entity();e['portrait_profile']=portrait_profiles.capture(e)
        for text in ('An orc grabbed her.','A woman with an orc beside her.'):
            report=art.identity_report(dict(e,appearance=text))
            self.assertFalse(any('disagree' in warning for warning in report['warnings']))

    def test_canonical_clothing_pins_select_compatible_bases(self):
        for outfit,expected in [('leather','leather'),('chain','armor'),('plate','armor'),('tunic','tunic')]:
            e=self.entity(look={'outfit':outfit},appearance='A human man.')
            self.assertEqual(art.look_of(e)['outfit'],outfit)
            actual=painted.portrait_records()[art.portrait_choice(e)]['outfit']
            self.assertEqual('armor' if actual in ('chain','plate') else actual,expected)

if __name__=='__main__':unittest.main()
