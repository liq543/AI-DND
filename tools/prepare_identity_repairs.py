"""Prepare single generated replacement sprites: trim, resize and format only."""
import json
import sys
from pathlib import Path
from PIL import Image

root=Path(__file__).resolve().parent.parent/'assets'/'generated'
for job in json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')):
    col,index=job['col'],job['index']
    source=Path(job['source'])
    originals=root/'cell-repairs';originals.mkdir(exist_ok=True)
    (originals/f'{col}-{index:02d}.png').write_bytes(source.read_bytes())
    tile=Image.open(source).convert('RGBA')
    bounds=tile.getchannel('A').point(lambda a:255 if a>32 else 0).getbbox()
    if bounds:tile=tile.crop(bounds)
    tile.thumbnail((184,184),Image.Resampling.LANCZOS)
    canvas=Image.new('RGBA',(192,192))
    canvas.alpha_composite(tile,((192-tile.width)//2,(192-tile.height)//2))
    canvas.save(root/col/f'{index:02d}.webp',quality=84,method=6)
    geometry=root/col/'geometry.json';data=json.loads(geometry.read_text())
    data[str(index)]=[round(v*256/192,2) for v in canvas.getchannel('A').point(lambda a:255 if a>32 else 0).getbbox()]
    geometry.write_text(json.dumps(data),encoding='utf-8')
    print(col,index,flush=True)
