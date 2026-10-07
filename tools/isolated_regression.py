"""Run regression checks from a disposable source copy with no real campaign directory."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

def main():
    with tempfile.TemporaryDirectory(prefix='dnd-art-regression-') as temporary:
        isolated=Path(temporary)
        for folder in ('engine','rules','tests','viewer','assets','dm','templates'):
            shutil.copytree(ROOT/folder,isolated/folder,
                            ignore=shutil.ignore_patterns('__pycache__','*.png','*.pyc'))
        env={**os.environ,'DND_CAMPAIGNS':str(isolated/'campaigns'),
             'DND_ENGINE_HOME':str(isolated/'home'),'PYTHONIOENCODING':'utf-8'}
        # The real campaign, keys, snapshots and log are never copied into this root.
        result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests'],
                              cwd=isolated,env=env,capture_output=True,text=True)
        report='\n'.join(line[:1200] for line in (result.stdout+'\n'+result.stderr).splitlines())
        output=ROOT/'artifacts'/'visual-review'/'regression-latest.txt'
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(report,encoding='utf-8')
        print(report)
        return result.returncode

if __name__=='__main__':sys.exit(main())
