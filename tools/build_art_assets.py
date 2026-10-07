"""Prepare generated atlases for inexpensive offline rendering (format/size/cell extraction only)."""
import argparse
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent / 'assets' / 'generated'

def prepare(source, name, columns, size, trim=False, crops=None):
    ROOT.mkdir(exist_ok=True)
    source = Path(source)
    original = Image.open(source).convert('RGBA')
    source_copy = ROOT / (name + '.png')
    if source.resolve() != source_copy.resolve():
        source_copy.write_bytes(source.read_bytes())
    folder = ROOT / name
    folder.mkdir(exist_ok=True)
    geometry={}
    crops=json.loads(Path(crops).read_text(encoding='utf-8')) if crops else {}
    for i in range(columns * columns):
        x, y = i % columns, i // columns
        a,b,c,d=crops.get(str(i),(0,0,1,1))
        tile = original.crop((round((x+a)*original.width/columns), round((y+b)*original.height/columns),
                              round((x+c)*original.width/columns), round((y+d)*original.height/columns)))
        if trim:
            bbox = tile.getchannel('A').point(lambda a:255 if a>32 else 0).getbbox()
            if bbox:
                tile = tile.crop(bbox)
                tile.thumbnail((size-8,size-8), Image.Resampling.LANCZOS)
                canvas = Image.new('RGBA',(size,size))
                canvas.alpha_composite(tile,((size-tile.width)//2,(size-tile.height)//2))
                tile = canvas
        tile = tile.resize((size,size),Image.Resampling.LANCZOS)
        bounds=tile.getchannel('A').point(lambda a:255 if a>32 else 0).getbbox() or (0,0,size,size)
        geometry[str(i)]=[round(v*256/size,2) for v in bounds]
        tile.save(folder / f'{i:02d}.webp',quality=84,method=6)
    (folder/'geometry.json').write_text(json.dumps(geometry),encoding='utf-8')
    print(name, columns*columns, 'tiles', sum(p.stat().st_size for p in folder.glob('*.webp')), 'bytes')

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source');parser.add_argument('name');parser.add_argument('--columns',type=int,default=4)
    parser.add_argument('--size',type=int,default=256);parser.add_argument('--trim',action='store_true')
    parser.add_argument('--crops',help='Optional normalized cell crop rectangles for atlas neighbor leakage')
    a=parser.parse_args();prepare(a.source,a.name,a.columns,a.size,a.trim,a.crops)
