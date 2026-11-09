"""Prepare safe user downloads. Credentials, runtime data and Git state are excluded."""
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'public/downloads';DEST.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(DEST/'commerce-data-10000.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for path in sorted((ROOT/'data').glob('*')):
        if path.is_file():archive.write(path,'commerce-data/'+path.name)
allowed_dirs=['src','backend','scripts','infra','tests','data']
allowed_files=['package.json','package-lock.json','tsconfig.json','vite.config.ts','index.html','README.md','RELEASE_STATUS.txt','requirements.txt','requirements.lock.txt','.env.example','.gitignore']
with zipfile.ZipFile(DEST/'nexo-demo-source.zip','w',zipfile.ZIP_DEFLATED) as archive:
    paths=[ROOT/name for name in allowed_files]
    paths += [p for directory in allowed_dirs for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
    paths += [ROOT/'public/demo-data.json']
    for path in sorted(paths):archive.write(path,'nexo-data-agent-demo/'+str(path.relative_to(ROOT)))
    archive.writestr('nexo-data-agent-demo/BUILD_STATUS.txt',(ROOT/'RELEASE_STATUS.txt').read_text())
for path in sorted(DEST.iterdir()):print(path.name,path.stat().st_size)
