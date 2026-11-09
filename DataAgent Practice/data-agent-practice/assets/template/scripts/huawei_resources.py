"""Discover Mexico DWS capacity; provision only when --apply is explicitly used.

Reads credentials from the process environment. Never prints or writes AK/SK.
Existing cloud resources are never deleted or resized by this script.
"""
from __future__ import annotations
import os,json,argparse,secrets
from pathlib import Path
from dotenv import load_dotenv
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdws.v2 import DwsClient,ListNodeTypesRequest,ListClustersRequest,ListAvailabilityZonesRequest,CreateClusterV2Request,V2CreateClusterReq,V2CreateCluster,Volume,Tags
from huaweicloudsdkvpc.v2 import VpcClient,ListVpcsRequest,CreateVpcRequest,CreateVpcRequestBody,CreateVpcOption,CreateSubnetRequest,CreateSubnetRequestBody,CreateSubnetOption,CreateSecurityGroupRequest,CreateSecurityGroupRequestBody,CreateSecurityGroupOption,CreateSecurityGroupRuleRequest,CreateSecurityGroupRuleRequestBody,CreateSecurityGroupRuleOption
ROOT=Path(__file__).resolve().parents[1];STATE=ROOT/'.runtime/huawei-state.json'
load_dotenv(ROOT/'.env',override=False)

def flavor_candidates(flavors,service_zones):
    """Some regions omit per-flavor AZs; query the service's AZ list separately."""
    regional=[zone.code for zone in service_zones if zone.status=='available']
    candidates=[]
    for flavor in flavors:
        zones=([zone.code for zone in flavor.available_zones if zone.status=='normal' and zone.code in regional]
               if flavor.available_zones is not None else regional)
        stable=[version for version in flavor.datastores or [] if version.role=='STABLE']
        if flavor.datastore_type not in ('dws','dws3.0') or not zones or not flavor.vcpus or not flavor.ram or not stable:continue
        storage=[volume for volume in flavor.elastic_volume_specs or [] if volume.min_size and volume.type!='ESSD2']
        chosen=min(storage,key=lambda volume:volume.min_size) if storage else None
        if not chosen:continue
        datastore=stable[0]
        candidates.append({'flavor':flavor.spec_name,'datastore_type':flavor.datastore_type,'datastore_version':datastore.version,
            'vcpus':flavor.vcpus,'ram_gb':flavor.ram,'az':zones[0],
            'az_source':'flavor' if flavor.available_zones is not None else 'service',
            'min_cn':datastore.attachments.min_cn if datastore.attachments and datastore.attachments.min_cn else 2,
            'disk_type':chosen.type,'disk_gb':chosen.min_size})
    return sorted(candidates,key=lambda flavor:(flavor['vcpus'],flavor['ram_gb'],flavor['disk_gb']))

def preflight():
    required=['HUAWEICLOUD_SDK_AK','HUAWEICLOUD_SDK_SK','HUAWEICLOUD_PROJECT_ID']
    missing=[name for name in required if not os.getenv(name)]
    if missing:return {'status':'blocked_missing_credentials','missing':missing,'region':'la-north-2','resources_created':False}
    region=os.getenv('HUAWEICLOUD_REGION','la-north-2')
    if region!='la-north-2':raise ValueError('This prepared deployment targets Mexico City2 only; no automatic region substitution')
    credentials=BasicCredentials(os.environ['HUAWEICLOUD_SDK_AK'],os.environ['HUAWEICLOUD_SDK_SK'],os.environ['HUAWEICLOUD_PROJECT_ID'])
    if os.getenv('HUAWEICLOUD_SDK_SECURITY_TOKEN'):credentials.with_security_token(os.environ['HUAWEICLOUD_SDK_SECURITY_TOKEN'])
    dws=DwsClient.new_builder().with_credentials(credentials).with_endpoint(f'https://dws.{region}.myhuaweicloud.com').build()
    candidates=flavor_candidates(dws.list_node_types(ListNodeTypesRequest()).node_types or [],dws.list_availability_zones(ListAvailabilityZonesRequest()).availability_zones or [])
    if not candidates:return {'status':'no_sellable_dws_flavor','region':region,'resources_created':False}
    plan={'status':'plan_ready','region':region,'cluster_name':'nexo-data-agent-demo','node_count':3,'selected':candidates[0],'candidates':candidates,'public_ip':False,'network':'dedicated VPC 10.63.0.0/16; subnet 10.63.1.0/24','note':'Minimum documented dedicated-cluster node count. Smallest available CPU/RAM candidate, not a verified price quote. Account inventory and prices must be checked before claiming lowest total cost.','resources_created':False}
    return plan,dws,credentials

def persist(state):
    STATE.parent.mkdir(exist_ok=True);temp=STATE.with_suffix('.tmp')
    with open(temp,'w',opener=lambda path,flags:os.open(path,flags,0o600)) as file:file.write(json.dumps(state,indent=2))
    temp.chmod(0o600);temp.replace(STATE)

def apply(plan,dws,credentials):
    state=json.loads(STATE.read_text()) if STATE.exists() else {'region':plan['region']}
    if state.get('cluster_id'):return {'status':'already_submitted','cluster_id':state['cluster_id'],'region':state['region']}
    existing=[c for c in dws.list_clusters(ListClustersRequest()).clusters or [] if c.name==plan['cluster_name']]
    if existing:raise RuntimeError('A cluster with this name already exists. Reconcile its identity before making another create request.')
    # No paid mutation occurs until capacity discovery has succeeded.
    vpc=VpcClient.new_builder().with_credentials(credentials).with_endpoint(f'https://vpc.{plan["region"]}.myhuaweicloud.com').build()
    if not state.get('vpc_id'):
        matches=[x for x in vpc.list_vpcs(ListVpcsRequest(limit=100)).vpcs or [] if x.name=='nexo-demo-vpc']
        if matches:raise RuntimeError('Untracked VPC name exists. Reconcile before creating resources.')
        response=vpc.create_vpc(CreateVpcRequest(body=CreateVpcRequestBody(vpc=CreateVpcOption(cidr='10.63.0.0/16',name='nexo-demo-vpc',description='NEXO synthetic demo; Mexico City2'))))
        state['vpc_id']=response.vpc.id;persist(state)
    if not state.get('subnet_id'):
        response=vpc.create_subnet(CreateSubnetRequest(body=CreateSubnetRequestBody(subnet=CreateSubnetOption(name='nexo-demo-subnet',cidr='10.63.1.0/24',gateway_ip='10.63.1.1',vpc_id=state['vpc_id'],dhcp_enable=True,dns_list=['100.125.1.250']))))
        state['subnet_id']=response.subnet.id;persist(state)
    if not state.get('security_group_id'):
        response=vpc.create_security_group(CreateSecurityGroupRequest(body=CreateSecurityGroupRequestBody(security_group=CreateSecurityGroupOption(name='nexo-demo-dws',vpc_id=state['vpc_id']))))
        state['security_group_id']=response.security_group.id;persist(state)
    if not state.get('ingress_rule_id'):
        response=vpc.create_security_group_rule(CreateSecurityGroupRuleRequest(body=CreateSecurityGroupRuleRequestBody(security_group_rule=CreateSecurityGroupRuleOption(security_group_id=state['security_group_id'],direction='ingress',ethertype='IPv4',protocol='tcp',port_range_min=8000,port_range_max=8000,remote_ip_prefix='10.63.1.0/24',description='NEXO private application subnet only'))))
        state['ingress_rule_id']=response.security_group_rule.id;persist(state)
    password_path=ROOT/'.runtime/huawei-dws-password'
    if not password_path.exists():password_path.write_text('Nx!9'+secrets.token_urlsafe(18));password_path.chmod(0o600)
    selected=plan['selected'];volume=Volume(volume=selected['disk_type'],capacity=selected['disk_gb']) if selected['disk_type'] else None
    body=V2CreateClusterReq(cluster=V2CreateCluster(name=plan['cluster_name'],flavor=selected['flavor'],datastore_version=selected['datastore_version'],num_node=plan['node_count'],num_cn=selected['min_cn'],db_name='dbadmin',db_password=password_path.read_text(),db_port=8000,availability_zones=[selected['az']],vpc_id=state['vpc_id'],subnet_id=state['subnet_id'],security_group_id=state['security_group_id'],volume=volume,tags=[Tags(key='project',value='nexo-demo')]))
    response=dws.create_cluster_v2(CreateClusterV2Request(body=body))
    result=response.to_dict();state['create_response']=result
    cluster=result.get('cluster') or {};state['cluster_id']=cluster.get('id') or result.get('id')
    persist(state)
    return {'status':'submitted','region':plan['region'],'state_file':str(STATE),'cluster_id':state['cluster_id'],'note':'Provisioning is asynchronous. Data import requires a private network path from the application host. No EIP was created.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    result=preflight()
    if isinstance(result,dict):print(json.dumps(result,indent=2));raise SystemExit(2)
    plan,client,credentials=result
    if args.apply:print(json.dumps(apply(plan,client,credentials),indent=2))
    else:
        path=ROOT/'.runtime/huawei-plan.json';path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(plan,indent=2));print(json.dumps(plan,indent=2))
