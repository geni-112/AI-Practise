"""Provision the private-demo application host and deliver an encrypted release.

Requires the existing Mexico deployment state. Cloud AK/SK are never shipped to ECS.
All sensitive local material is stored under the ignored .runtime directory.
"""
from __future__ import annotations
import argparse,base64,hashlib,io,json,os,secrets,tarfile,time,uuid
from pathlib import Path
from dotenv import load_dotenv,dotenv_values,set_key
import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkecs.v2 import EcsClient,CreatePostPaidServersRequest,CreatePostPaidServersRequestBody,PostPaidServer,PostPaidServerNic,PostPaidServerPublicip,PostPaidServerRootVolume,PostPaidServerSecurityGroup,NovaCreateKeypairRequest,NovaCreateKeypairRequestBody,NovaCreateKeypairOption,ShowJobRequest,ShowServerRequest
from huaweicloudsdkeip.v2 import EipClient,CreatePublicipRequest,CreatePublicipRequestBody,CreatePublicipBandwidthOption,CreatePublicipOption
from huaweicloudsdkvpc.v2 import VpcClient,CreateSecurityGroupRequest,CreateSecurityGroupRequestBody,CreateSecurityGroupOption,CreateSecurityGroupRuleRequest,CreateSecurityGroupRuleRequestBody,CreateSecurityGroupRuleOption
from obs import ObsClient

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'.runtime';STATE=RUNTIME/'huawei-state.json'
CONTROL=RUNTIME/'cloud-artifact-secrets.json'
load_dotenv(ROOT/'.env',override=False)


def save(path,value):
    temporary=path.with_suffix('.tmp')
    with open(temporary,'w',opener=lambda p,f:os.open(p,f,0o600)) as file:json.dump(value,file,indent=2)
    temporary.chmod(0o600);temporary.replace(path)


def credentials():
    assert os.getenv('HUAWEICLOUD_REGION')=='la-north-2','Mexico City2 deployment only'
    result=BasicCredentials(os.environ['HUAWEICLOUD_SDK_AK'],os.environ['HUAWEICLOUD_SDK_SK'],os.environ['HUAWEICLOUD_PROJECT_ID'])
    if os.getenv('HUAWEICLOUD_SDK_SECURITY_TOKEN'):result.with_security_token(os.environ['HUAWEICLOUD_SDK_SECURITY_TOKEN'])
    return result


def client(service,cls):return cls.new_builder().with_credentials(credentials()).with_endpoint(f'https://{service}.la-north-2.myhuaweicloud.com').build()


def signer():
    # Only local signing is used; httpx supplies the enforced proxy and TLS verification.
    return ObsClient(access_key_id=os.environ['HUAWEICLOUD_SDK_AK'],secret_access_key=os.environ['HUAWEICLOUD_SDK_SK'],security_token=os.getenv('HUAWEICLOUD_SDK_SECURITY_TOKEN') or None,server='https://obs.la-north-2.myhuaweicloud.com',is_secure=True,ssl_verify=os.getenv('REQUESTS_CA_BUNDLE') or os.getenv('SSL_CERT_FILE') or '/etc/ssl/certs/ca-certificates.crt')


def signed(method,bucket,key=None,expires=300,headers=None):
    result=signer().createSignedUrl(method,bucketName=bucket,objectKey=key,expires=expires,headers=headers)
    return result.signedUrl,dict(result.actualSignedRequestHeaders)


def object_request(method,bucket,key=None,body=None,headers=None):
    url,signed_headers=signed(method,bucket,key,headers=headers)
    response=httpx.request(method,url,headers=signed_headers,content=body,timeout=90,follow_redirects=False)
    if response.status_code not in (200,201,204):
        # Do not raise an HTTP error that would contain signed URLs.
        import re
        code=re.search(r'<Code>([^<]+)</Code>',response.text)
        raise RuntimeError(f'OBS {method} failed: HTTP {response.status_code}, code {code.group(1) if code else "unknown"}')
    return response


def prepare_network():
    state=json.loads(STATE.read_text())
    assert state.get('cluster_id') and state.get('vpc_id') and state.get('subnet_id')
    if not state.get('app_security_group_id'):
        vpc=client('vpc',VpcClient)
        response=vpc.create_security_group(CreateSecurityGroupRequest(body=CreateSecurityGroupRequestBody(security_group=CreateSecurityGroupOption(name='nexo-demo-web',vpc_id=state['vpc_id']))))
        state['app_security_group_id']=response.security_group.id;save(STATE,state)
    vpc=client('vpc',VpcClient)
    for port in (80,443):
        field=f'app_ingress_{port}_id'
        if state.get(field):continue
        response=vpc.create_security_group_rule(CreateSecurityGroupRuleRequest(body=CreateSecurityGroupRuleRequestBody(security_group_rule=CreateSecurityGroupRuleOption(security_group_id=state['app_security_group_id'],direction='ingress',ethertype='IPv4',protocol='tcp',port_range_min=port,port_range_max=port,remote_ip_prefix='0.0.0.0/0',description='HTTPS demo login; HTTP only for HTTPS redirect and ACME'))))
        state[field]=response.security_group_rule.id;save(STATE,state)
    if not state.get('app_eip_id'):
        # The official EIP v2 regional endpoint is the VPC endpoint.
        response=client('vpc',EipClient).create_publicip(CreatePublicipRequest(body=CreatePublicipRequestBody(
            publicip=CreatePublicipOption(type='5_bgp',ip_version=4,alias='nexo-demo-web'),
            bandwidth=CreatePublicipBandwidthOption(name='nexo-demo-web',size=5,share_type='PER',charge_mode='traffic'))))
        state['app_eip_id']=response.publicip.id;state['app_public_ip']=response.publicip.public_ip_address;save(STATE,state)
    state['app_domain']='nexo-'+state['app_public_ip'].replace('.','-')+'.sslip.io';save(STATE,state)
    bucket='nexo-demo-'+os.environ['HUAWEICLOUD_PROJECT_ID'][:12]+'-mx'
    if not state.get('artifact_bucket'):
        body=b'<CreateBucketConfiguration><Location>la-north-2</Location></CreateBucketConfiguration>'
        object_request('PUT',bucket,body=body,headers={'x-obs-acl':'private','Content-Type':'application/xml'})
        state['artifact_bucket']=bucket;save(STATE,state)
    print(json.dumps({'status':'network_ready','region':'la-north-2','host_flavor':'s6.large.4','vcpus':2,'ram_gb':8,'system_disk_gb':40,'bandwidth_mbps':5,'bandwidth_billing':'traffic','domain':state['app_domain'],'database_public_ip':False,'ssh_public_access':False,'artifact_bucket_private':True},indent=2))


def app_environment(state,control):
    source=dotenv_values(ROOT/'.env')
    detail=json.loads((RUNTIME/'huawei-dws-details.json').read_text())
    endpoints=detail.get('endpoints') or []
    host=next((e.get('connect_info') for e in endpoints if e.get('connect_info')),None) or detail.get('private_ip')
    # The host may install its dependencies while the asynchronous DWS create runs.
    # A subsequent encrypted release supplies the endpoint before importing data.
    host=host or ''
    result={'DEMO_MODE':'true','DATA_BACKEND':'dws','DEPLOYMENT_KIND':'huawei_cloud',
        'MODEL_PROVIDER':source['MODEL_PROVIDER'],'MODEL_NAME':source['MODEL_NAME'],'MODEL_BASE_URL':source['MODEL_BASE_URL'],'MODEL_API_KEY':source['MODEL_API_KEY'],'MODEL_TIMEOUT':'120',
        'OPENMETADATA_URL':'http://127.0.0.1:8585','TEMPORAL_ENABLED':'true','TEMPORAL_ADDRESS':'127.0.0.1:7233',
        'HUAWEICLOUD_REGION':'la-north-2','DWS_HOST':host,'DWS_PORT':'8000','DWS_DATABASE':'gaussdb','DWS_USER':'nexo_reader','DWS_PASSWORD':control['reader_password'],
        'DWS_SSLMODE':'verify-ca','DWS_SSLROOTCERT':'/opt/nexo-app/.runtime/dws-ca.pem',
        'NEXO_GATE_SECRET':control['gate_secret'],'NEXO_INVITE_SHA256':hashlib.sha256(control['invite'].encode()).hexdigest(),'NEXO_INVITE_EXPIRES':str(control['invite_expires']),
        'NO_PROXY':'localhost,127.0.0.1,0.0.0.0','no_proxy':'localhost,127.0.0.1,0.0.0.0'}
    path=RUNTIME/'cloud-app.env'
    if not path.exists():path.touch(mode=0o600)
    for key,value in result.items():set_key(path,key,value,quote_mode='always')
    path.chmod(0o600)
    return path


def upload(finalize=False):
    state=json.loads(STATE.read_text());bucket=state['artifact_bucket']
    if CONTROL.exists():control=json.loads(CONTROL.read_text())
    else:
        control={'key':base64.b64encode(AESGCM.generate_key(bit_length=256)).decode(),'reader_password':'Nr!7'+secrets.token_urlsafe(16),
            'gate_secret':secrets.token_hex(32),'invite':secrets.token_urlsafe(32),'invite_expires':int(time.time())+7*86400,
            'release_key':'releases/demo-release.enc','status_key':'bootstrap/status.json','domain':state['app_domain']}
        save(CONTROL,control)
    for field,method,key in [('release_get_url','GET',control['release_key']),('release_head_url','HEAD',control['release_key']),('status_put_url','PUT',control['status_key']),('diagnostics_put_url','PUT','bootstrap/diagnostics.enc')]:
        if field not in control:control[field]=signed(method,bucket,key,expires=10800)[0]
    save(CONTROL,control)
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w:gz') as archive:
        if finalize:
            payload=json.dumps({'finalize':True}).encode();info=tarfile.TarInfo('.runtime/release-control.json');info.size=len(payload);info.mode=0o600;archive.addfile(info,io.BytesIO(payload))
        else:
            env=app_environment(state,control)
            for directory in ['backend','scripts','infra','data','dist']:
                for path in sorted((ROOT/directory).rglob('*')):
                    if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.log'):
                        archive.add(path,arcname=str(path.relative_to(ROOT)),recursive=False)
            archive.add(ROOT/'requirements.lock.txt',arcname='requirements.lock.txt')
            archive.add(ROOT/'public/demo-data.json',arcname='public/demo-data.json')
            archive.add(ROOT/'src/messages.json',arcname='src/messages.json')
            archive.add(env,arcname='.env');archive.add(RUNTIME/'dws-certs/ca-1.pem',arcname='.runtime/dws-ca.pem')
            admin=json.dumps({'password':(RUNTIME/'huawei-dws-password').read_text()}).encode()
            info=tarfile.TarInfo('.runtime/deploy-admin.json');info.size=len(admin);info.mode=0o600;archive.addfile(info,io.BytesIO(admin))
    plaintext=stream.getvalue()
    with tarfile.open(fileobj=io.BytesIO(plaintext),mode='r:gz') as check:
        account_secrets=[os.getenv(name,'').encode() for name in ('HUAWEICLOUD_SDK_AK','HUAWEICLOUD_SDK_SK','HUAWEICLOUD_SDK_SECURITY_TOKEN') if os.getenv(name)]
        for member in check:
            if member.isfile():
                content=check.extractfile(member).read()
                assert not any(secret in content for secret in account_secrets),'Cloud owner credentials must not enter a release'
    nonce=os.urandom(12)
    encrypted=nonce+AESGCM(base64.b64decode(control['key'])).encrypt(nonce,plaintext,b'nexo-cloud-release-v1')
    object_request('PUT',bucket,control['release_key'],body=encrypted)
    control['encrypted_sha256']=hashlib.sha256(encrypted).hexdigest();control['release_bytes']=len(encrypted);save(CONTROL,control)
    print(json.dumps({'status':'release_uploaded','encrypted':True,'finalize_requested':finalize,'bytes':len(encrypted),'cloud_owner_credentials_in_release':False}))


def user_data(control):
    # The key and signed URLs are private ECS user data. No account AK/SK is embedded.
    loader='''import base64,hashlib,io,json,pathlib,subprocess,tarfile,time,urllib.request
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
control=json.loads(pathlib.Path('/opt/nexo-control.json').read_text())
deadline=time.monotonic()+10000
last=None
while time.monotonic()<deadline:
    try:
        with urllib.request.urlopen(urllib.request.Request(control['release_head_url'],method='HEAD'),timeout=30) as response:etag=response.headers.get('ETag')
        if etag!=last:
            with urllib.request.urlopen(control['release_get_url'],timeout=90) as response:data=response.read(64*1024*1024)
            plaintext=AESGCM(base64.b64decode(control['key'])).decrypt(data[:12],data[12:],b'nexo-cloud-release-v1')
            archive=tarfile.open(fileobj=io.BytesIO(plaintext),mode='r:gz')
            if '.runtime/release-control.json' in archive.getnames():
                flag=json.load(archive.extractfile('.runtime/release-control.json'))
                if flag.get('finalize') and last is not None:
                    subprocess.run(['systemctl','disable','nexo-bootstrap.service'],check=True)
                    pathlib.Path('/opt/nexo-control.json').unlink()
                    raise SystemExit(0)
            destination=pathlib.Path('/opt/nexo-app');destination.mkdir(exist_ok=True)
            archive.extractall(destination,filter='data')
            subprocess.run(['python3',str(destination/'infra/cloud_bootstrap.py')],check=True)
            last=etag
    except Exception as error:
        body=json.dumps({'stage':'bootstrap_retry','error_type':type(error).__name__,'updated_at':int(time.time())}).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(control['status_put_url'],data=body,method='PUT',headers={'Content-Type':''}),timeout=20):pass
        except Exception:pass
    time.sleep(45)
'''
    setup={'key':control['key'],'release_get_url':control['release_get_url'],'release_head_url':control['release_head_url'],'status_put_url':control['status_put_url'],'diagnostics_put_url':control['diagnostics_put_url'],'domain':control['domain']}
    unit='''[Unit]
Description=Temporary encrypted NEXO release bootstrap
After=network-online.target docker.service
[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/nexo-bootstrap-loader.py
Restart=on-failure
RestartSec=60
[Install]
WantedBy=multi-user.target
'''
    script='''#!/bin/bash
set -eu
umask 077
export DEBIAN_FRONTEND=noninteractive
'''
    for path,content in [('/opt/nexo-control.json',json.dumps(setup)),('/opt/nexo-bootstrap-loader.py',loader),('/etc/systemd/system/nexo-bootstrap.service',unit)]:
        script+='cat > '+path+" <<'NEXO_PRIVATE_EOF'\n"+content+'\nNEXO_PRIVATE_EOF\n'
    script+='''chmod 600 /opt/nexo-control.json
python3 - <<'NEXO_PROGRESS'
import json,time,urllib.request
from pathlib import Path
config=json.loads(Path('/opt/nexo-control.json').read_text())
body=json.dumps({'stage':'installing_system_packages','updated_at':int(time.time())}).encode()
try:
    with urllib.request.urlopen(urllib.request.Request(config['status_put_url'],data=body,method='PUT',headers={'Content-Type':''}),timeout=15):pass
except Exception:pass
NEXO_PROGRESS
apt-get -o Acquire::Retries=1 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 update -qq
apt-get -o Acquire::Retries=1 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 install -y -qq python3-venv python3-cryptography docker.io docker-compose-v2 ca-certificates
id nexo >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin nexo
install -d -m 0755 /opt/nexo-app
systemctl enable --now docker
systemctl daemon-reload
systemctl enable --now nexo-bootstrap.service
'''
    assert len(script.encode())<=32768
    return base64.b64encode(script.encode()).decode()


def create():
    state=json.loads(STATE.read_text());control=json.loads(CONTROL.read_text())
    if state.get('app_job_id') or state.get('app_server_id'):
        print(json.dumps({'status':'already_submitted','job_id':state.get('app_job_id'),'server_id':state.get('app_server_id')}));return
    inventory=json.loads((RUNTIME/'huawei-host-inventory.json').read_text())
    flavor=next(f for f in inventory['flavors'] if f['name']=='s6.large.4')
    assert 'la-north-2a(normal)' in flavor['os_extra_specs']['condoperationaz']
    image=next(i for i in json.loads((RUNTIME/'huawei-images.json').read_text()) if i['name']=='Ubuntu 24.04 server 64bit')
    ecs=client('ecs',EcsClient)
    if not state.get('app_keypair_name'):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        path=RUNTIME/'app-maintenance-key.pem'
        if path.exists():key=serialization.load_pem_private_key(path.read_bytes(),password=None)
        else:
            key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
            with open(path,'xb',opener=lambda p,f:os.open(p,f,0o600)) as file:file.write(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        name='nexo-demo-'+state['cluster_id'][:8]
        public=key.public_key().public_bytes(serialization.Encoding.OpenSSH,serialization.PublicFormat.OpenSSH).decode()
        ecs.nova_create_keypair(NovaCreateKeypairRequest(body=NovaCreateKeypairRequestBody(keypair=NovaCreateKeypairOption(public_key=public,name=name))))
        state['app_keypair_name']=name;save(STATE,state)
    state.setdefault('app_client_token',str(uuid.uuid4()));save(STATE,state)
    server=PostPaidServer(name='nexo-data-agent-app',description='Private synthetic Data Agent demo; openJiuwen, DWS MCP, OpenMetadata, Temporal',availability_zone='la-north-2a',count=1,
        flavor_ref=flavor['id'],image_ref=image['id'],key_name=state['app_keypair_name'],vpcid=state['vpc_id'],nics=[PostPaidServerNic(subnet_id=state['subnet_id'])],
        root_volume=PostPaidServerRootVolume(volumetype='SSD',size=40),security_groups=[PostPaidServerSecurityGroup(id=state['app_security_group_id'])],
        publicip=PostPaidServerPublicip(id=state['app_eip_id'],delete_on_termination=False),user_data=user_data(control),tags=['nexo-demo'])
    response=ecs.create_post_paid_servers(CreatePostPaidServersRequest(x_client_token=state['app_client_token'],body=CreatePostPaidServersRequestBody(server=server))).to_dict()
    state['app_job_id']=response.get('job_id')
    if response.get('server_ids'):state['app_server_id']=response['server_ids'][0]
    save(STATE,state)
    print(json.dumps({'status':'submitted','job_id':state.get('app_job_id'),'server_id':state.get('app_server_id'),'domain':state['app_domain']},indent=2))


def status():
    state=json.loads(STATE.read_text());report={}
    ecs=client('ecs',EcsClient)
    if state.get('app_job_id'):
        job=ecs.show_job(ShowJobRequest(job_id=state['app_job_id'])).to_dict()
        report['job']={k:job.get(k) for k in ('status','error_code','fail_reason')}
        for child in (job.get('entities') or {}).get('sub_jobs',[]):
            server=(child.get('entities') or {}).get('server_id')
            if server:state['app_server_id']=server;save(STATE,state)
    if state.get('app_server_id'):
        server=ecs.show_server(ShowServerRequest(server_id=state['app_server_id'])).server
        report['host_status']=server.status
    if CONTROL.exists():
        control=json.loads(CONTROL.read_text())
        try:report['bootstrap']=object_request('GET',state['artifact_bucket'],control['status_key']).json()
        except RuntimeError:report['bootstrap']={'stage':'not_reported_yet'}
    print(json.dumps(report,indent=2))


def diagnostics():
    state=json.loads(STATE.read_text());control=json.loads(CONTROL.read_text())
    data=object_request('GET',state['artifact_bucket'],'bootstrap/diagnostics.enc').content
    text=AESGCM(base64.b64decode(control['key'])).decrypt(data[:12],data[12:],b'nexo-cloud-diagnostics-v1').decode(errors='replace')
    values=list(dotenv_values(ROOT/'.env').values())+list(control.values())
    for value in values:
        if isinstance(value,str) and len(value)>6:text=text.replace(value,'[REDACTED]')
    path=RUNTIME/'cloud-diagnostics-redacted.log'
    with open(path,'w',opener=lambda p,f:os.open(p,f,0o600)) as file:file.write(text)
    print(text[-10000:])


def publish_downloads():
    """Stage reviewed, secret-free source downloads without changing running services."""
    import shlex
    state=json.loads(STATE.read_text());control=json.loads(CONTROL.read_text())
    source=ROOT/'public/downloads/nexo-demo-source.zip'
    key='downloads/nexo-demo-source.zip'
    object_request('PUT',state['artifact_bucket'],key,body=source.read_bytes())
    url=signed('GET',state['artifact_bucket'],key,expires=1800)[0]
    control['download_source_get_url']=url;save(CONTROL,control)
    commands='stty -echo\ncurl --fail --silent --show-error '+shlex.quote(url)+' -o /opt/nexo-app/dist/downloads/nexo-demo-source.zip\nstty echo\nclear\nwc -c /opt/nexo-app/dist/downloads/nexo-demo-source.zip\n'
    path=RUNTIME/'publish-downloads.sh'
    with open(path,'w',opener=lambda p,f:os.open(p,f,0o600)) as file:file.write(commands)
    path.chmod(0o600)
    print(json.dumps({'source_download_staged':True,'bytes':source.stat().st_size,'private_install_commands':str(path)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['network','upload','create','status','diagnostics','finalize','publish-downloads']);args=parser.parse_args()
    try:
        if args.action=='network':prepare_network()
        elif args.action=='upload':upload()
        elif args.action=='create':create()
        elif args.action=='status':status()
        elif args.action=='diagnostics':diagnostics()
        elif args.action=='publish-downloads':publish_downloads()
        else:upload(finalize=True)
    except Exception as error:
        message=str(getattr(error,'error_msg','')) if hasattr(error,'error_msg') else (str(error) if isinstance(error,(RuntimeError,AssertionError)) else '')
        for name,value in os.environ.items():
            if value and len(value)>6 and any(key in name for key in ('SECRET','TOKEN','_KEY','SDK_AK','SDK_SK','PASSWORD')):message=message.replace(value,'[REDACTED]')
        print(json.dumps({'status':'error','error_type':type(error).__name__,'error_code':getattr(error,'error_code',None),'status_code':getattr(error,'status_code',None),'message':message[:400]}))
        raise SystemExit(1)
