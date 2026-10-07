# Builds edl.json for the compositor (clip frame tables at 30 fps) and sfx.json for the score (cue times).
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
REC = os.path.join(HERE, '..', 'rec')
FPS = 30

def stamps(rec):
    s = json.load(open(os.path.join(REC, rec, 'stamps.json')))
    return [x for x in s if not x[0].startswith('@')]

def clip(rec, t0, t1, speed, reverse=False):
    fr = stamps(rec); n = int(round((t1 - t0) / speed / 1000 * FPS)); out = []
    j = 0
    for i in range(n):
        t = t0 + i * speed * 1000 / FPS
        if reverse: t = t1 - i * speed * 1000 / FPS
        best = min(fr, key=lambda x: abs(x[1] - t))
        out.append(f'../rec/{rec}/frames/{best[0]}')
    return {'frames': out, 'dur': n / FPS, 'src': [t0, t1, speed]}

CLIPS = {
    'tavern':   clip('L7', 1200, 11200, 2.5),
    'roll':     clip('L7', 26500, 38800, 3.0),
    'init':     clip('L1', 1900, 4900, 1.5),
    'fireball': clip('L2', 4200, 9800, 1.25),
    'kit':      clip('L4b', 4700, 8300, 1.5),
    'brakka':   clip('L5', 16300, 19300, 1.5),
    'mock':     clip('L4', 15600, 21600, 3.0),
    'gate':     clip('L6', 13000, 16000, 3.0),
    'rewind':   clip('L2', 4200, 12600, 6.0, reverse=True),
}
json.dump({'fps': FPS, 'clips': CLIPS}, open(os.path.join(HERE, 'edl.json'), 'w'))

# source-time events inside clips -> trailer time, given where each clip starts in the cut
def at(clipname, start, src_ms):
    t0, t1, sp = CLIPS[clipname]['src']; return round(start + (src_ms - t0) / sp / 1000, 3)
cues = [
    {'k': 'swell', 't': 6.6, 'd': 1.4, 'v': 0.6},
    {'k': 'whoosh', 't': 15.6, 'd': 0.8}, {'k': 'whoosh', 't': 19.6, 'd': 0.8},
    {'k': 'type', 't': 24.35, 'n': 22, 'gap': 0.055},
    {'k': 'dice', 't': 26.45},
    {'k': 'thump', 't': 28.0}, {'k': 'whoosh', 't': 29.85, 'd': .5}, {'k': 'whoosh', 't': 31.85, 'd': .5}, {'k': 'whoosh', 't': 33.85, 'd': .5},
    {'k': 'whoosh', 't': 35.8, 'd': 0.6},
    {'k': 'type', 't': 40.25, 'n': 16, 'gap': 0.05},
    {'k': 'buzz', 't': 41.55},
    {'k': 'dice', 't': at('init', 44.0, 3775)},
    {'k': 'whoosh', 't': at('fireball', 46.0, 4450), 'd': 0.5, 'v': 1.2},
    {'k': 'boom', 't': at('fireball', 46.0, 5650)},
    {'k': 'dice', 't': at('fireball', 46.0, 6600), 'v': 0.7},
    {'k': 'dice', 't': at('kit', 50.5, 5150), 'v': 0.8},
    {'k': 'arrow', 't': at('kit', 50.5, 6350)},
    {'k': 'dice', 't': at('brakka', 53.0, 16550), 'v': 0.7},
    {'k': 'clang', 't': at('brakka', 53.0, 17780), 'v': 1.2},
    {'k': 'dice', 't': at('mock', 55.0, 20550), 'v': 0.7},
    {'k': 'dice', 't': 57.4, 'v': 0.6},
    {'k': 'tick', 't': 60.1, 'n': 3},
    {'k': 'type', 't': 60.25, 'n': 14, 'gap': 0.045},
    {'k': 'swell', 't': 61.5, 'd': 1.3, 'v': 0.8},
    {'k': 'boom', 't': at('gate', 64.0, 14000), 'v': 0.6},
    {'k': 'whoosh', 't': 75.2, 'd': 0.8, 'v': 1.2},
]
json.dump(cues, open(os.path.join(HERE, '..', 'audio', 'sfx.json'), 'w'), indent=1)
for k, v in CLIPS.items(): print(k, round(v['dur'], 2), len(v['frames']))
open(os.path.join(HERE, 'edl.js'), 'w').write('window.EDL = ' + json.dumps({'fps': FPS, 'clips': CLIPS}) + ';')
