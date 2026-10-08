"""Persist cosmetic face choices through ordinary signed entity events, never during rendering."""
import copy
import re

IDENTITY_FIELDS={'look','art_of','species','race','gender','sex','presentation','pronouns','ancestry'}
DESCRIPTION_FIELDS={'appearance','bio.appearance'}

def descriptive(text):
    """A scene action cannot establish the actor as somebody else's visual identity."""
    opening=re.split(r'[.!?;]\s|\n',str(text or ''),maxsplit=1)[0]
    action=re.search(r'\b(?:grabbed|grabs|seized|dragged|restrained|pushed|struck|attacked|escorted|carried|pulled|followed|helped|threatened)\b',opening,re.I)
    if not opening.strip():return False
    if not action:return True
    # A descriptive subject followed by a relative or passive clause remains a description.
    prefix=opening[:action.start()]
    return bool(re.search(r'\b(?:who|whose|with|wearing)\b|,\s*$',prefix,re.I))

def capture(entity,description=None):
    from . import art
    e=copy.deepcopy(entity);e.pop('portrait_profile',None)
    if description is not None:e['appearance']=description
    raw=e.get('appearance') or (e.get('bio') or {}).get('appearance') or ''
    text=art.subject_description(raw) if descriptive(raw) else ''
    e['appearance']=text
    if e.get('bio'):e['bio']=dict(e['bio'],appearance=text)
    choice=art.portrait_choice(e)
    return dict(version=1,identity=art.visual_identity(e),traits=art.look_of(e),
                mode='painted' if choice else 'procedural',choice=choice,source_look=copy.deepcopy(e.get('look') or {}),
                source_description=text,established=bool(text))

def prepare(state,type_,data):
    """Return an event payload containing its cosmetic snapshot; replay itself stays unchanged."""
    from .core import set_path
    if type_=='entity.add':
        e=copy.deepcopy(data['entity'])
        if not e.get('portrait_profile'):e['portrait_profile']=capture(e)
        return dict(data,entity=e)
    if type_!='entity.set':return data
    patch=data.get('set') or {}
    if 'portrait_profile' in patch:return data
    roots={k.split('.')[0] for k in patch}
    bio_fields=set(patch.get('bio') or {})
    if not (roots & IDENTITY_FIELDS or DESCRIPTION_FIELDS & set(patch) or 'appearance' in bio_fields or bio_fields & IDENTITY_FIELDS or any(k.startswith('bio.') and k.split('.')[1] in IDENTITY_FIELDS for k in patch)):
        return data
    old=state['entities'][data['id']];profile=old.get('portrait_profile')
    next_entity=copy.deepcopy(old)
    for k,v in patch.items():set_path(next_entity,k,v)
    incoming=patch.get('appearance') if 'appearance' in patch else patch.get('bio.appearance') if 'bio.appearance' in patch else (patch.get('bio') or {}).get('appearance')
    identity_change=bool(roots & IDENTITY_FIELDS or bio_fields & IDENTITY_FIELDS or any(k.startswith('bio.') and k.split('.')[1] in IDENTITY_FIELDS for k in patch))
    if identity_change:
        saved=capture(next_entity,profile.get('source_description') if profile and profile.get('established') else incoming)
    elif not profile or not profile.get('established'):
        raw=incoming if incoming is not None else next_entity.get('appearance') or (next_entity.get('bio') or {}).get('appearance') or ''
        if profile and not descriptive(raw):return data
        # Existing descriptions supply the original face; the first description establishes a new creature.
        original=old.get('appearance') or (old.get('bio') or {}).get('appearance') or ''
        saved=capture(old) if not profile and descriptive(original) else capture(next_entity,raw)
    else:return data
    return dict(data,set=dict(patch,portrait_profile=saved))

def original_descriptions(events):
    """First authored appearance per entity in this campaign; no other campaign is loaded."""
    found={}
    for ev in events:
        d=ev.get('data') or {}
        if ev['type']=='entity.add':
            e=d['entity'];found.pop(e['id'],None);text=e.get('appearance') or (e.get('bio') or {}).get('appearance')
            if descriptive(text):found.setdefault(e['id'],text)
        elif ev['type']=='entity.remove':found.pop(d['id'],None)
        elif ev['type']=='entity.set':
            patch=d.get('set') or {};text=patch.get('appearance') or patch.get('bio.appearance') or (patch.get('bio') or {}).get('appearance')
            if descriptive(text):found.setdefault(d['id'],text)
    return found
