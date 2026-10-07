"""Describe reviewed atlas cells for offline identity matching; no game state is read."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent/'assets'/'generated'

def build():
    corpses=[];portraits=[]
    def add(target,col,i,species,pres,outfit,skin='tan',hair='black',**more):
        if target is corpses:col=col.replace('-v3','-v4')
        target.append(dict(collection=col,index=i,species=species,presentation=pres,outfit=outfit,
                           skin=skin,hair_color=hair,age='adult',headwear='none',**more))
    tones=[('pale','#f3d2b8'),('tan','#c99268'),('brown','#8d5634'),('dark','#4f2d1a')]
    outfits=['armor','leather','robe','work'];hair=['black','auburn','silver','brown']
    for pres,label in [('masculine','masculine'),('feminine','feminine'),('androgynous','neutral')]:
        for i in range(16):
            skin,colour=tones[i//4]
            add(corpses,f'corpses-human-{label}-v3',i,'Human',pres,outfits[i%4],skin,hair[i%4],skin_hex=colour)
            if label=='neutral':add(portraits,'portraits-human-neutral-v3',i,'Human',pres,['plate','leather','robe','tunic'][i%4],skin,hair[i%4])
    species=['Elf','Dwarf','Orc','Tiefling','Halfling','Gnome','Dragonborn','Goliath']
    skins=['olive','tan','green','violet','tan','brown','gold','gray']
    colours=['#b88a64','#c58a5c','#7a8f5f','#7a4a8e','#c99268','#c58a5c','#c9a13a','#9aa0a6']
    for a,sp in enumerate(species):
        for k in range(4):
            col='corpses-fantasy-'+('a' if a<4 else 'b')+'-v3'
            add(corpses,col,(a%4)*4+k,sp,'masculine' if k<2 else 'feminine','armor' if k%2==0 else 'robe',skins[a],skin_hex=colours[a])
        for k in range(2):
            add(corpses,'corpses-fantasy-neutral-v3',a*2+k,sp,'androgynous','armor' if k==0 else 'robe',skins[a],skin_hex=colours[a])
            add(portraits,'portraits-fantasy-neutral-v3',a*2+k,sp,'androgynous','plate' if k==0 else 'robe',skins[a],'silver' if sp in ('Gnome','Tiefling') else 'brown')
    monsters=['Goblin','Hobgoblin','Kobold','Lizardfolk','Ogre','Troll','Bugbear','Zombie']
    monster_skin=['green','ruddy','rust','green','tan','green','brown','pale']
    for a,sp in enumerate(monsters):
        for k,pres in enumerate(('masculine','feminine')):
            extra={'aliases':['zombie']} if sp=='Zombie' else {}
            add(corpses,'corpses-monsters-v3',a*2+k,sp,pres,'leather',monster_skin[a],**extra)
            add(portraits,'portraits-monsters-v3',a*2+k,sp,pres,'leather',monster_skin[a])
        for k in range(2):
            extra={'aliases':['zombie']} if sp=='Zombie' else {}
            add(corpses,'corpses-monsters-neutral-v3',a*2+k,sp,'androgynous','leather' if k==0 else 'work',monster_skin[a],**extra)
            add(portraits,'portraits-monsters-neutral-v3',a*2+k,sp,'androgynous','leather' if k==0 else 'tunic',monster_skin[a])
    variants=[('Dragonborn',skin,pres) for skin in ('blue','red','silver') for pres in ('masculine','feminine','androgynous')]
    variants += [('Tiefling','red',p) for p in ('masculine','feminine','androgynous')]
    variants += [('Elf','dark',p) for p in ('masculine','feminine','androgynous')]+[('Elf','fair','androgynous')]
    for i,(sp,skin,pres) in enumerate(variants):
        colour={'blue':'#2f5fa8','red':'#b8453d','silver':'#9eaab6','dark':'#4f2d1a','fair':'#f3d2b8'}[skin]
        add(corpses,'corpses-fantasy-colours-v3',i,sp,pres,'armor',skin,'silver' if sp=='Elf' else 'black',skin_hex=colour)
        add(portraits,'portraits-fantasy-colours-v4',i,sp,pres,'plate',skin,'silver' if sp=='Elf' else 'black')
    beasts=[('Wolf',['wolf']),('Mastiff',['mastiff','dog']),('Horse',['horse','pony']),('Mule',['mule']),
            ('Rat',['rat']),('Spider',['spider']),('Raven',['raven','crow']),('Owl',['owl']),('Lion',['lion']),
            ('Tiger',['tiger']),('Bear',['bear']),('Boar',['boar']),('Goat',['goat']),('Sheep',['sheep']),
            ('Crocodile',['crocodile','alligator']),('Owlbear',['owlbear'])]
    other=[('Red Dragon',['red dragon'],'Small'),('Red Dragon',['red dragon'],'Huge'),
           ('Blue Dragon',['blue dragon'],'Huge'),('Gold Dragon',['gold dragon'],'Huge'),
           ('Skeleton',['skeleton'],'Medium'),('Mummy',['mummy'],'Medium'),('Mummy',['mummy'],'Medium'),
           ('Animated Armor',['animated armor','animated armour'],'Medium'),('Bat',['bat'],'Large'),
           ('Frog',['frog','toad'],'Large'),('Snake',['snake','serpent'],'Large'),('Scorpion',['scorpion'],'Large'),
           ('Eagle',['eagle'],'Large'),('Griffon',['griffon','griffin'],'Large'),('Ant',['ant'],'Large'),('Deer',['deer','elk'],'Medium')]
    for i,(sp,aliases) in enumerate(beasts):
        add(corpses,'corpses-beasts-v3',i,sp,'masculine' if sp=='Lion' else 'any','none',aliases=aliases)
        add(portraits,'portraits-beasts-v3',i,sp,'masculine' if sp=='Lion' else 'any','none',aliases=aliases)
    for i,(sp,aliases,size) in enumerate(other):
        add(corpses,'corpses-creatures-v3',i,sp,'feminine' if i==5 else 'masculine' if i in (6,15) else 'any','none',aliases=aliases,size=size.lower())
        add(portraits,'portraits-creatures-v3',i,sp,'feminine' if i==5 else 'masculine' if i in (6,15) else 'any','none',aliases=aliases,size=size.lower())
    for i,(sp,pres) in enumerate([('Lion','feminine'),('Lion','androgynous'),('Deer','feminine'),('Deer','androgynous')]):
        add(corpses,'corpses-lion-deer-v1',i,sp,pres,'none',aliases=[sp.lower()])
        add(portraits,'portraits-lion-deer-v1',i,sp,pres,'none',aliases=[sp.lower()])
    ROOT.joinpath('identity-v3-catalogue.json').write_text(json.dumps(dict(corpses=corpses,portraits=portraits),indent=2),encoding='utf-8')
    print(f'{len(corpses)} body records, {len(portraits)} portrait records')

if __name__=='__main__':build()
