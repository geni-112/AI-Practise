"""Executed on the dedicated Huawei ECS only, after the encrypted release is unpacked."""
from __future__ import annotations
import json,os,pathlib,subprocess,time,socket,urllib.request,base64

ROOT=pathlib.Path('/opt/nexo-app')
CONTROL=pathlib.Path('/opt/nexo-control.json')
config=json.loads(CONTROL.read_text())
log_path=ROOT/'.runtime/bootstrap.log'
log_path.touch(mode=0o600,exist_ok=True)
stage='starting'


def report(name,**values):
    global stage
    stage=name
    body=json.dumps({'stage':name,'updated_at':int(time.time()),**values}).encode()
    (ROOT/'.runtime/deployment-status.json').write_bytes(body)
    try:
        request=urllib.request.Request(config['status_put_url'],data=body,method='PUT',headers={'Content-Type':''})
        with urllib.request.urlopen(request,timeout=30) as response:assert response.status==200
    except Exception:pass


def run(command,user=False,timeout=1800):
    if user:command=['runuser','-u','nexo','--',*command]
    with log_path.open('ab') as log:
        subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=timeout)


def diagnostics():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    parts=[log_path.read_bytes()[-100000:]]
    for command in [['journalctl','-u','nexo-api.service','-n','45','--no-pager'],['docker','logs','--tail','20','nexo-caddy']]:
        result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        parts.append(result.stdout[-50000:])
    data=b'\n'.join(parts);nonce=os.urandom(12)
    sealed=nonce+AESGCM(base64.b64decode(config['key'])).encrypt(nonce,data,b'nexo-cloud-diagnostics-v1')
    try:
        with urllib.request.urlopen(urllib.request.Request(config['diagnostics_put_url'],data=sealed,method='PUT',headers={'Content-Type':''}),timeout=30):pass
    except Exception:pass


def wait_http(url,seconds=600):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            with urllib.request.urlopen(url,timeout=5) as response:
                if response.status==200:return
        except Exception:pass
        time.sleep(10)
    raise TimeoutError('Internal service did not become ready')


def main():
    report('installing_python_dependencies')
    run(['chown','-R','nexo:nexo',str(ROOT)])
    if not (ROOT/'.venv/bin/python').exists():run(['python3','-m','venv',str(ROOT/'.venv')],user=True)
    python=str(ROOT/'.venv/bin/python')
    run([python,'-m','pip','install','--no-cache-dir','-r','requirements.lock.txt'],user=True)
    report('starting_open_source_services')
    run(['sysctl','-w','vm.max_map_count=262144'])
    pathlib.Path('/etc/sysctl.d/90-nexo-search.conf').write_text('vm.max_map_count=262144\n')
    compose=['docker','compose','-p','nexo','-f','infra/local-compose.yml','-f','infra/runtime-compose.yml']
    run([*compose,'up','-d'],timeout=1800)
    wait_http('http://127.0.0.1:8585/api/v1/system/version',seconds=900)
    report('registering_unified_metadata')
    run([python,'-m','backend.metadata'],user=True)
    if "DWS_HOST=''" in (ROOT/'.env').read_text():
        report('waiting_for_dws_endpoint')
        return
    report('loading_dws_synthetic_data')
    run([python,'-m','scripts.initialize_dws'],user=True,timeout=600)
    # A successful data load removes the bootstrap admin password from the host.
    report('starting_application')
    units=pathlib.Path('/etc/systemd/system')
    (units/'nexo-dependencies.service').write_text('''[Unit]
Description=NEXO internal metadata and orchestration services
After=docker.service
Requires=docker.service
[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/nexo-app
ExecStart=/usr/bin/docker compose -p nexo -f infra/local-compose.yml -f infra/runtime-compose.yml up -d
[Install]
WantedBy=multi-user.target
''')
    (units/'nexo-api.service').write_text('''[Unit]
Description=NEXO Data Agent API
After=nexo-dependencies.service network-online.target
Requires=nexo-dependencies.service
[Service]
User=nexo
Group=nexo
WorkingDirectory=/opt/nexo-app
EnvironmentFile=/opt/nexo-app/.env
Environment=PYTHONPATH=/opt/nexo-app
Environment=NO_PROXY=localhost,127.0.0.1,0.0.0.0
Environment=no_proxy=localhost,127.0.0.1,0.0.0.0
ExecStartPre=/opt/nexo-app/.venv/bin/python /opt/nexo-app/infra/wait_temporal.py
ExecStart=/opt/nexo-app/.venv/bin/python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=10
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/opt/nexo-app/.runtime /opt/nexo-app/logs
[Install]
WantedBy=multi-user.target
''')
    (ROOT/'logs').mkdir(exist_ok=True)
    run(['chown','nexo:nexo',str(ROOT/'logs')])
    run(['systemctl','daemon-reload'])
    run(['systemctl','enable','--now','nexo-dependencies.service','nexo-api.service'])
    domain=config['domain']
    caddy_dir=pathlib.Path('/opt/nexo-caddy');caddy_dir.mkdir(exist_ok=True)
    (caddy_dir/'Caddyfile').write_text(f'''{domain} {{
  encode zstd gzip
  header Referrer-Policy "no-referrer"
  header X-Content-Type-Options "nosniff"
  header Strict-Transport-Security "max-age=31536000"
  reverse_proxy 127.0.0.1:8000
}}
''')
    exists=subprocess.run(['docker','inspect','nexo-caddy'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    if exists:run(['docker','restart','nexo-caddy'])
    else:run(['docker','run','-d','--name','nexo-caddy','--restart','unless-stopped','--network','host','-v',str(caddy_dir/'Caddyfile')+':/etc/caddy/Caddyfile:ro','-v','nexo_caddy_data:/data','caddy:2.10.2'],timeout=600)
    report('verifying_cloud_stack')
    run([python,'-m','scripts.cloud_verify'],user=True,timeout=600)
    verification=json.loads((ROOT/'.runtime/cloud-verification.json').read_text())
    diagnostics()
    report('verified',domain=domain,synthetic_rows=10000,verification=verification)


if __name__=='__main__':
    try:main()
    except Exception as error:
        diagnostics()
        report('failed',failed_stage=stage,error_type=type(error).__name__)
        raise SystemExit(1)
