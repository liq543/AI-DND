"""Read-only visual audit of the verified active campaign, saved with its own notes."""
from collections import Counter
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from engine.core import Game
from engine import art

def main():
    g=Game()
    before=g.state['seq']
    rows=[dict(id=e['id'],**art.identity_report(e)) for e in g.state['entities'].values()]
    target=Path(g.dir)/'log'/'visual-review'/'identity-audit.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(dict(sequence=before,reports=rows),indent=2),encoding='utf-8')
    print(json.dumps(dict(entities=len(rows),issues=sum(bool(r['warnings']) for r in rows),
                         missing_presentation=sum(r['identity']['presentation_source']=='unspecified' for r in rows),
                         species_sources=dict(Counter(r['identity']['species_source'] for r in rows))),indent=2))

if __name__=='__main__':main()
