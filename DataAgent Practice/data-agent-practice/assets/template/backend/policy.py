from __future__ import annotations
from dataclasses import dataclass,asdict
import httpx
from .config import settings

ROLES={
 'analyst':{'domains':['Sales','Marketing','Supply Chain','Finance'],'export':True,'execute':False,'govern':False},
 'manager':{'domains':['Sales'],'region':'Mexico City','export':False,'execute':False,'govern':False},
 'engineer':{'domains':['Sales','Marketing','Supply Chain','Finance'],'export':True,'execute':True,'govern':False},
 'steward':{'domains':['Sales'],'export':False,'execute':False,'govern':True},
}
ASSET_DOMAINS={'orders':'Sales','order_items':'Sales','customers':'Sales','products':'Sales','inventory':'Supply Chain','shipments':'Supply Chain','returns':'Finance','campaigns':'Marketing','ad_metrics':'Marketing','competitor_prices':'Marketing','reviews':'Marketing'}
METRIC_DOMAINS={'revenue':'Sales','orders':'Sales','aov':'Sales','refund':'Finance','roas':'Marketing','stock':'Supply Chain','sentiment':'Marketing','pricing':'Marketing'}

@dataclass(frozen=True)
class Subject:
    tenant:str
    persona:str
    user_id:str='demo'

    def __post_init__(self):
        if self.tenant not in ['luma','northstar'] or self.persona not in ROLES:raise PermissionError('Unknown tenant or role')

    @property
    def role(self):return ROLES[self.persona]

async def authorize(subject:Subject,action:str,domain:str='Sales'):
    allowed=domain in subject.role['domains'] and (action in ['discover','query'] or bool(subject.role.get(action)))
    if settings.opa_url:
        async with httpx.AsyncClient() as client:
            r=await client.post(settings.opa_url.rstrip('/')+'/v1/data/nexo/allow',json={'input':{'subject':asdict(subject),'action':action,'domain':domain}},timeout=5)
            r.raise_for_status();allowed=allowed and r.json().get('result') is True
    if not allowed:raise PermissionError(f'Access denied: {action} in {domain}')
    return True
