"""Read-only timings for local portrait selection and rendering; generic disposable records."""
import json
import statistics
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from engine import art,painted,portrait_profiles

def main():
    samples=[];selection=[];cold=[];warm=[]
    for n in range(64):
        e=dict(id=f'timing-{n}',name='Traveller',kind='npc',type='humanoid',species='Human',
               gender=('male','female','neutral')[n%3],look={'outfit':('plate','leather','robe','tunic')[n%4]})
        start=time.perf_counter();e['portrait_profile']=portrait_profiles.capture(e);selection.append((time.perf_counter()-start)*1000)
        painted.uri.cache_clear();start=time.perf_counter();art.face_svg(e);art.portrait_svg(e);cold.append((time.perf_counter()-start)*1000)
        for _ in range(5):
            start=time.perf_counter();art.face_svg(e);art.portrait_svg(e);warm.append((time.perf_counter()-start)*1000)
        samples.append(e)
    def stats(values):return {'median_ms':round(statistics.median(values),3),'p95_ms':round(sorted(values)[int(len(values)*.95)],3),'worst_ms':round(max(values),3)}
    report={'samples':64,'initial_selection':stats(selection),'cold_face_and_portrait':stats(cold),'warm_face_and_portrait':stats(warm),'distinct_choices':len({art.portrait_choice(e) for e in samples}),'image_service_calls':0}
    (ROOT/'artifacts/visual-review/portrait-v5-timings.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
