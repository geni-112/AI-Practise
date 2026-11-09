"""Install a reviewed UI release on the existing host, with health-based rollback.

Run with the application's virtualenv as root. The archive contains only the
explicit source allowlist, built assets and a manifest; never configuration or
runtime data. The expected archive digest is supplied separately by the operator.
"""
from __future__ import annotations
import hashlib,io,json,os,pwd,re,shutil,subprocess,sys,tarfile,time
from pathlib import Path
import httpx,jwt
from dotenv import dotenv_values

ROOT=Path('/opt/nexo-app')
SOURCE={
    'src/styles.css','src/App.tsx','src/Chart.tsx','src/lib.ts',
    'index.html','backend/access.py','README.md','RELEASE_STATUS.txt',
    'infra/update_ui.py','src/i18n.ts','src/Locale.tsx','src/messages.json',
    'backend/localization.py','backend/agent.py','backend/planning.py','backend/api.py',
    'tests/test_localization.py','tests/test_model_contract.py',
}
DEPENDENCIES=('dws_connected','model_connected','openmetadata','temporal','iceberg')


def health():
    secret=dotenv_values(ROOT/'.env')['NEXO_GATE_SECRET']
    now=int(time.time())
    token=jwt.encode({'sub':'owner','aud':'nexo-demo','iss':'nexo-owner','iat':now,'exp':now+300},secret,algorithm='HS256')
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=15,trust_env=False) as client:
        anonymous=client.get('/api/health').status_code==401
        result=client.get('/api/health',cookies={'nexo_owner':token})
        result.raise_for_status()
        state=result.json()
        checks={key:bool(state.get(key)) for key in DEPENDENCIES}
        checks['anonymous_api_denied']=anonymous
        checks['login_available']=client.get('/login').status_code==200
        return checks


def install(archive_path:Path,expected_digest:str):
    if os.geteuid()!=0:raise PermissionError('Root is required on the dedicated application host')
    if not re.fullmatch('[a-f0-9]{64}',expected_digest):raise ValueError('Invalid digest')
    data=archive_path.read_bytes()
    if len(data)>24*1024*1024 or hashlib.sha256(data).hexdigest()!=expected_digest:
        raise ValueError('Release integrity check failed')
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        members=archive.getmembers()
        if len(members)>150 or any(not m.isfile() for m in members):raise ValueError('Unexpected archive members')
        names=[m.name for m in members]
        if len(set(names))!=len(names) or 'ui-manifest.json' not in names:raise ValueError('Invalid manifest')
        manifest=json.load(archive.extractfile('ui-manifest.json'))
        release=manifest['release']
        if not re.fullmatch('rappi-ui-[0-9a-f-]{8,50}',release):raise ValueError('Invalid release name')
        files=manifest['files']
        if set(names)!=set(files)|{'ui-manifest.json'}:raise ValueError('Unlisted release files')
        if not SOURCE.issubset(files):raise ValueError('Incomplete source release')
        total=0
        for member in members:
            name=member.name
            if name=='ui-manifest.json':continue
            path=Path(name)
            if path.is_absolute() or '..' in path.parts or not (name in SOURCE or name.startswith('dist/')):
                raise ValueError('Unexpected release path')
            total+=member.size
            if member.size>12*1024*1024 or total>48*1024*1024:raise ValueError('Oversized release')
            if hashlib.sha256(archive.extractfile(member).read()).hexdigest()!=files[name]:
                raise ValueError('File integrity check failed')
        backup=ROOT/'.runtime/ui-releases'/release
        if backup.exists():raise ValueError('Release already staged')
        backup.mkdir(parents=True,mode=0o700)
        staging=backup/'staging';staging.mkdir()
        for member in members:
            if member.name=='ui-manifest.json':continue
            destination=staging/member.name;destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(archive.extractfile(member).read());destination.chmod(0o644)
    previous={name:(ROOT/name).exists() for name in SOURCE}
    for name,exists in previous.items():
        if exists:
            destination=backup/'source'/name;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/name,destination)
    next_dist=ROOT/('.dist-next-'+release)
    shutil.copytree(staging/'dist',next_dist)
    owner=pwd.getpwnam('nexo')
    swapped=False
    try:
        for name in SOURCE:
            destination=ROOT/name;destination.parent.mkdir(parents=True,exist_ok=True)
            temporary=destination.with_name(destination.name+'.ui-next')
            shutil.copy2(staging/name,temporary)
            os.chown(temporary,owner.pw_uid,owner.pw_gid)
            temporary.replace(destination)
        (ROOT/'dist').rename(backup/'dist')
        try:next_dist.rename(ROOT/'dist')
        except Exception:
            (backup/'dist').rename(ROOT/'dist');raise
        swapped=True
        subprocess.run(['systemctl','restart','nexo-api.service'],check=True,timeout=90)
        checks={}
        for _ in range(30):
            try:
                checks=health()
                if all(checks.values()):break
            except Exception:pass
            time.sleep(4)
        else:raise RuntimeError('Post-release health checks failed')
        receipt={'release':release,'archive_sha256':expected_digest,'verified_at':int(time.time()),'checks':checks}
        receipt_path=ROOT/'.runtime/ui-release.json'
        receipt_path.write_text(json.dumps(receipt,indent=2));receipt_path.chmod(0o600)
        shutil.rmtree(staging)
        print(json.dumps({'ui_release':'verified',**receipt}),flush=True)
    except Exception:
        if swapped:
            (ROOT/'dist').rename(backup/'failed-dist')
            (backup/'dist').rename(ROOT/'dist')
        for name,exists in previous.items():
            if exists:shutil.copy2(backup/'source'/name,ROOT/name)
            else:(ROOT/name).unlink(missing_ok=True)
        subprocess.run(['systemctl','restart','nexo-api.service'],check=False,timeout=90)
        print(json.dumps({'ui_release':'rolled_back','release':release}),flush=True)
        raise


if __name__=='__main__':
    try:install(Path(sys.argv[1]),sys.argv[2])
    except Exception as error:
        print(json.dumps({'ui_release':'failed','error_type':type(error).__name__}),flush=True)
        sys.exit(1)
