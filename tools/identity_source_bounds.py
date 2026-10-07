"""Report original-alpha sprite rectangles; does not change pixels or source images."""
import json
from pathlib import Path
import numpy as np
from scipy import ndimage
from PIL import Image

root=Path('assets/generated')
for path in sorted(root.glob('corpses-*v4.png')):
    a=np.asarray(Image.open(path).getchannel('A'))
    labels,count=ndimage.label(a>32)
    sizes=np.bincount(labels.ravel());sizes[0]=0
    chosen=np.argsort(sizes)[-16:]
    boxes=ndimage.find_objects(labels)
    records=[]
    for ident in chosen:
        y,x=boxes[ident-1]
        records.append((int(sizes[ident]),(x.start,y.start,x.stop,y.stop)))
    records=sorted(records,key=lambda r:(int(((r[1][1]+r[1][3])/2)*4/a.shape[0]),r[1][0]))
    crops={}
    for i,(area,(l,t,r,b)) in enumerate(records):
        x,y=i%4,i//4
        # Small empty margin preserves the source's generated alpha unchanged.
        crops[str(i)]=[(l-2)*4/a.shape[1]-x,(t-2)*4/a.shape[0]-y,(r+2)*4/a.shape[1]-x,(b+2)*4/a.shape[0]-y]
    target=root/(path.stem+'-crops.json')
    target.write_text(json.dumps(crops,indent=2),encoding='utf-8')
    print(path.stem,records)
